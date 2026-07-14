# -*- coding: utf-8 -*-
"""
/***************************************************************************
 gtfs_builder_core — Núcleo de construção de GTFS do zero para o SIG-Bus
                                 A QGIS plugin
 Gerencia as funções auxiliares para a construção e cálculo de progresso
 de um feed GTFS do zero.
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
import sqlite3

try:
    from . import gtfs_schema
    from . import gtfs_reader
except ImportError:
    try:
        import gtfs_schema
        import gtfs_reader
    except ImportError:
        from sig_bus import gtfs_schema
        from sig_bus import gtfs_reader


def compute_progress(gpkg_path):
    """
    Calcula o progresso mínimo e máximo de preenchimento do GTFS no GeoPackage.

    Retorna a tupla: (pct_minimo, pct_maximo, faltando_minimo, faltando_maximo)
    """
    required_tables = gtfs_reader.REQUIRED_LAYERS

    # Monta a lista completa de campos opcionais das tabelas requeridas
    optional_fields = {}
    total_opt_cols = 0
    for table in required_tables:
        if table in gtfs_schema.GTFS_FILES:
            cols = gtfs_schema.GTFS_FILES[table]['columns']
            opt_cols = [col.name for col in cols if col.editable and not col.required]
            optional_fields[table] = opt_cols
            total_opt_cols += len(opt_cols)

    # Total de pontos possíveis para o progresso máximo:
    # - len(required_tables) tabelas obrigatórias (mínimo)
    # - total_opt_cols campos opcionais
    # - 1 ponto para shapes associado a cada viagem
    # - 1 ponto para segundo sentido por rota
    total_max_points = len(required_tables) + total_opt_cols + 1 + 1

    if not os.path.exists(gpkg_path):
        faltando_maximo = []
        for table, cols in optional_fields.items():
            for col in cols:
                faltando_maximo.append(f"Campo opcional {table}.{col} não preenchido")
        faltando_maximo.append("Traçado (shape) não associado a todas as viagens")
        faltando_maximo.append("Segundo sentido (ida/volta) não cadastrado para todas as linhas")
        return (0.0, 0.0, list(required_tables), faltando_maximo)

    conn = None
    try:
        conn = sqlite3.connect(gpkg_path)
        cursor = conn.cursor()

        # Tabelas existentes no GeoPackage
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        # 1. Progresso Mínimo
        min_satisfied_count = 0
        faltando_minimo = []

        for table in required_tables:
            if table not in existing_tables:
                faltando_minimo.append(table)
                continue

            # Verifica colunas obrigatórias
            if table in gtfs_schema.GTFS_FILES:
                cols = gtfs_schema.GTFS_FILES[table]['columns']
                req_cols = [col.name for col in cols if col.required]
            else:
                req_cols = []

            if not req_cols:
                # Se não há colunas obrigatórias configuradas, basta ter pelo menos uma linha
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                if count > 0:
                    min_satisfied_count += 1
                else:
                    faltando_minimo.append(table)
            else:
                # Constrói cláusula WHERE para garantir que todos os campos obrigatórios estão preenchidos
                where_clauses = [f"({col} IS NOT NULL AND TRIM({col}) != '')" for col in req_cols]
                where_str = " AND ".join(where_clauses)
                query = f"SELECT COUNT(*) FROM {table} WHERE {where_str}"
                try:
                    cursor.execute(query)
                    count = cursor.fetchone()[0]
                    if count > 0:
                        min_satisfied_count += 1
                    else:
                        faltando_minimo.append(table)
                except sqlite3.OperationalError:
                    # Caso alguma coluna não exista fisicamente no banco
                    faltando_minimo.append(table)

        pct_minimo = (min_satisfied_count / len(required_tables)) * 100.0

        # 2. Progresso Máximo
        # Começa com a pontuação obtida no mínimo
        obtained_max_points = min_satisfied_count
        faltando_maximo = []

        # Cobertura dos campos opcionais
        for table, cols in optional_fields.items():
            if table not in existing_tables:
                for col in cols:
                    faltando_maximo.append(f"Campo opcional {table}.{col} não preenchido")
                continue

            for col in cols:
                # Verifica se há pelo menos uma linha onde esse campo opcional está preenchido
                query = f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND TRIM({col}) != ''"
                try:
                    cursor.execute(query)
                    count = cursor.fetchone()[0]
                    if count > 0:
                        obtained_max_points += 1
                    else:
                        faltando_maximo.append(f"Campo opcional {table}.{col} não preenchido")
                except sqlite3.OperationalError:
                    faltando_maximo.append(f"Campo opcional {table}.{col} não preenchido")

        # Shapes preenchido em cada trip
        shapes_satisfied = 0.0
        if "trips" in existing_tables:
            cursor.execute("SELECT COUNT(*) FROM trips")
            total_trips = cursor.fetchone()[0]
            if total_trips > 0:
                if "shapes" in existing_tables:
                    # Conta viagens que possuem shape_id preenchido e que existe na tabela shapes
                    query = """
                        SELECT COUNT(*) FROM trips
                        WHERE shape_id IS NOT NULL AND TRIM(shape_id) != ''
                          AND shape_id IN (SELECT shape_id FROM shapes)
                    """
                    cursor.execute(query)
                    trips_with_shapes = cursor.fetchone()[0]
                    shapes_satisfied = trips_with_shapes / total_trips
                else:
                    shapes_satisfied = 0.0
            else:
                shapes_satisfied = 0.0
        else:
            shapes_satisfied = 0.0

        obtained_max_points += shapes_satisfied
        if shapes_satisfied < 1.0:
            faltando_maximo.append("Traçado (shape) não associado a todas as viagens")

        # Segundo sentido por linha (ida/volta)
        dir_satisfied = 0.0
        if "routes" in existing_tables and "trips" in existing_tables:
            cursor.execute("SELECT route_id FROM routes")
            routes = [row[0] for row in cursor.fetchall()]
            total_routes = len(routes)
            if total_routes > 0:
                routes_with_both_dirs = 0
                for r_id in routes:
                    # direction_id pode ser armazenado como string ou int no gpkg.
                    query = """
                        SELECT COUNT(DISTINCT direction_id) FROM trips
                        WHERE route_id = ?
                          AND direction_id IS NOT NULL
                          AND direction_id IN (0, 1, '0', '1')
                    """
                    cursor.execute(query, (r_id,))
                    dirs_count = cursor.fetchone()[0]
                    if dirs_count >= 2:
                        routes_with_both_dirs += 1
                dir_satisfied = routes_with_both_dirs / total_routes
            else:
                dir_satisfied = 0.0
        else:
            dir_satisfied = 0.0

        obtained_max_points += dir_satisfied
        if dir_satisfied < 1.0:
            faltando_maximo.append("Segundo sentido (ida/volta) não cadastrado para todas as linhas")

        pct_maximo = (obtained_max_points / total_max_points) * 100.0

        return (pct_minimo, pct_maximo, faltando_minimo, faltando_maximo)

    except sqlite3.Error:
        faltando_maximo = []
        for table, cols in optional_fields.items():
            for col in cols:
                faltando_maximo.append(f"Campo opcional {table}.{col} não preenchido")
        faltando_maximo.append("Traçado (shape) não associado a todas as viagens")
        faltando_maximo.append("Segundo sentido (ida/volta) não cadastrado para todas as linhas")
        return (0.0, 0.0, list(required_tables), faltando_maximo)
    finally:
        if conn:
            conn.close()


def normalize_address(texto):
    """
    Normaliza um texto de endereço convertendo para minúsculas e colapsando espaços múltiplos.
    """
    if texto is None:
        return ""
    return " ".join(str(texto).lower().split())


def find_existing_stop(gpkg_path, endereco):
    """
    Busca no GeoPackage se já existe uma parada com o endereço fornecido (normalizado).
    Verifica as colunas stop_desc e stop_name.
    Retorna o stop_id correspondente se encontrado, ou None caso contrário.
    """
    normalized_target = normalize_address(endereco)
    if not normalized_target:
        return None

    if not os.path.exists(gpkg_path):
        return None

    conn = None
    try:
        conn = sqlite3.connect(gpkg_path)
        cursor = conn.cursor()

        # Verifica se a tabela 'stops' existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stops'")
        if not cursor.fetchone():
            return None

        # Busca todas as paradas
        cursor.execute("SELECT stop_id, stop_name, stop_desc FROM stops")
        for stop_id, stop_name, stop_desc in cursor.fetchall():
            if normalize_address(stop_name) == normalized_target or normalize_address(stop_desc) == normalized_target:
                return stop_id
    except sqlite3.Error:
        return None
    finally:
        if conn:
            conn.close()
    return None


def list_reusable_calendars(gpkg_path):
    """
    Busca no GeoPackage os calendários distintos já gravados.
    Retorna uma lista de tuplas (service_id, monday, tuesday, wednesday,
    thursday, friday, saturday, sunday, start_date, end_date).
    Se o arquivo ou a tabela não existirem, retorna lista vazia.
    """
    if not os.path.exists(gpkg_path):
        return []

    conn = None
    try:
        conn = sqlite3.connect(gpkg_path)
        cursor = conn.cursor()

        # Verifica se a tabela 'calendar' existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='calendar'")
        if not cursor.fetchone():
            return []

        # SELECT de service_id + dias + vigência distintos já gravados em calendar
        cursor.execute("""
            SELECT DISTINCT service_id, monday, tuesday, wednesday, thursday,
                            friday, saturday, sunday, start_date, end_date
            FROM calendar
        """)
        return cursor.fetchall()
    except sqlite3.Error:
        return []
    finally:
        if conn:
            conn.close()


def expand_frequency_to_stop_times(stop_ids, hora_inicio, hora_fim, intervalo_min):
    """
    Função pura (sem I/O) que gera as viagens e as linhas de stop_times
    (trip_id, arrival_time, departure_time, stop_id, stop_sequence)
    para uma frequência regular.
    """
    def to_seconds(time_str):
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 3600 + m * 60 + s

    def from_seconds(seconds):
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    start_sec = to_seconds(hora_inicio)
    end_sec = to_seconds(hora_fim)
    step_sec = int(intervalo_min) * 60

    if step_sec <= 0:
        return [], []

    trips = []
    stop_times = []

    current_sec = start_sec
    while current_sec <= end_sec:
        time_str = from_seconds(current_sec)
        trip_id = f"trip_{time_str.replace(':', '')}"

        trips.append({
            "trip_id": trip_id
        })

        for idx, stop_id in enumerate(stop_ids, start=1):
            stop_times.append({
                "trip_id": trip_id,
                "arrival_time": time_str,
                "departure_time": time_str,
                "stop_id": stop_id,
                "stop_sequence": idx
            })

        current_sec += step_sec

    return trips, stop_times


def save_route(gpkg_path, agency, linha, paradas, service, frequencia):
    """
    Grava ou atualiza a agência (uma vez), insere a rota, viagens, paradas
    (reaproveitando existentes), calendário e horários de parada no GeoPackage.
    """
    import uuid
    from osgeo import ogr

    # 1. Processa stops primeiro usando OGR (pois lida com a geometria espacial)
    local_new_stops = {}
    stop_ids = []

    ds = ogr.Open(gpkg_path, 1)
    if not ds:
        raise RuntimeError("Não foi possível abrir o GeoPackage via OGR.")

    lyr = ds.GetLayerByName("stops")
    if not lyr:
        ds = None
        raise RuntimeError("Camada 'stops' não encontrada no GeoPackage.")

    try:
        for stop in paradas:
            endereco = stop.get("stop_desc") or stop.get("stop_name")
            norm_address = normalize_address(endereco)

            # Verifica cache local primeiro, depois o banco de dados
            if norm_address in local_new_stops:
                existing_id = local_new_stops[norm_address]
            else:
                existing_id = find_existing_stop(gpkg_path, endereco)

            if existing_id is not None:
                stop_ids.append(existing_id)
            else:
                stop_id = stop.get("stop_id")
                if not stop_id:
                    stop_id = "stop_{}".format(uuid.uuid4().hex[:8])

                stop_ids.append(stop_id)
                if norm_address:
                    local_new_stops[norm_address] = stop_id

                # Insere nova parada
                feat = ogr.Feature(lyr.GetLayerDefn())
                cols = gtfs_schema.column_order("stops")
                for col in cols:
                    if col in ("stop_lat", "stop_lon"):
                        val = stop.get(col)
                        feat.SetField(col, str(val) if val is not None else "")
                    else:
                        if col == "stop_id":
                            val = stop_id
                        else:
                            val = stop.get(col)
                        feat.SetField(col, str(val) if val is not None else "")

                # Configura a geometria
                lat = float(stop.get("stop_lat", 0.0))
                lon = float(stop.get("stop_lon", 0.0))
                pt = ogr.Geometry(ogr.wkbPoint)
                pt.AddPoint(lon, lat)
                feat.SetGeometry(pt)

                lyr.CreateFeature(feat)
    finally:
        ds = None  # Fecha a conexão OGR

    # 2. Usa sqlite3 para inserir/atualizar as outras tabelas
    conn = sqlite3.connect(gpkg_path)
    try:
        cursor = conn.cursor()

        def get_physical_cols(table_name):
            cursor.execute("PRAGMA table_info({})".format(table_name))
            return {row[1] for row in cursor.fetchall()}

        # --- AGENCY ---
        agency_id = "1"
        if agency:
            physical_cols = get_physical_cols("agency")
            cursor.execute("SELECT agency_id FROM agency LIMIT 1")
            row = cursor.fetchone()

            agency_id = agency.get("agency_id")
            if not agency_id:
                if row:
                    agency_id = row[0]
                else:
                    agency_id = "1"

            agency_data = dict(agency)
            agency_data["agency_id"] = agency_id

            cols = [col for col in gtfs_schema.column_order("agency") if col in physical_cols]
            if row:
                # Atualiza
                set_clauses = []
                values = []
                for col in cols:
                    if col in agency_data:
                        set_clauses.append("{} = ?".format(col))
                        values.append(str(agency_data[col]) if agency_data[col] is not None else None)
                values.append(row[0])
                query = "UPDATE agency SET {} WHERE agency_id = ?".format(", ".join(set_clauses))
                cursor.execute(query, values)
            else:
                # Insere
                values = [str(agency_data.get(col)) if agency_data.get(col) is not None else None for col in cols]
                placeholders = ", ".join(["?"] * len(cols))
                query = "INSERT INTO agency ({}) VALUES ({})".format(", ".join(cols), placeholders)
                cursor.execute(query, values)
        else:
            # Tenta recuperar agency_id existente
            cursor.execute("SELECT agency_id FROM agency LIMIT 1")
            row = cursor.fetchone()
            if row:
                agency_id = row[0]

        if not linha:
            conn.commit()
            return

        # --- CALENDAR ---
        service_id = "default_service"
        if isinstance(service, dict):
            service_id = service.get("service_id")
            if service_id:
                physical_cols = get_physical_cols("calendar")
                cursor.execute("SELECT service_id FROM calendar WHERE service_id = ?", (service_id,))
                if not cursor.fetchone():
                    cols = [col for col in gtfs_schema.column_order("calendar") if col in physical_cols]
                    values = [str(service.get(col)) if service.get(col) is not None else None for col in cols]
                    placeholders = ", ".join(["?"] * len(cols))
                    query = "INSERT INTO calendar ({}) VALUES ({})".format(", ".join(cols), placeholders)
                    cursor.execute(query, values)
        elif isinstance(service, str):
            service_id = service

        # --- ROUTES ---
        route_id = linha.get("route_id")
        if not route_id:
            short_name = linha.get("route_short_name")
            if short_name:
                route_id = "route_{}".format(short_name)
            else:
                route_id = "route_{}".format(uuid.uuid4().hex[:8])

        cursor.execute("SELECT route_id FROM routes WHERE route_id = ?", (route_id,))
        route_exists = cursor.fetchone() is not None

        route_data = dict(linha)
        route_data["route_id"] = route_id
        route_data["agency_id"] = agency_id

        physical_cols = get_physical_cols("routes")
        cols = [col for col in gtfs_schema.column_order("routes") if col in physical_cols]
        if route_exists:
            # Atualiza
            set_clauses = []
            values = []
            for col in cols:
                if col in route_data:
                    set_clauses.append("{} = ?".format(col))
                    values.append(str(route_data[col]) if route_data[col] is not None else None)
            values.append(route_id)
            query = "UPDATE routes SET {} WHERE route_id = ?".format(", ".join(set_clauses))
            cursor.execute(query, values)
        else:
            # Insere
            values = [str(route_data.get(col)) if route_data.get(col) is not None else None for col in cols]
            placeholders = ", ".join(["?"] * len(cols))
            query = "INSERT INTO routes ({}) VALUES ({})".format(", ".join(cols), placeholders)
            cursor.execute(query, values)

        # --- TRIPS & STOP TIMES ---
        # Limpa trips e stop_times antigos desta rota
        cursor.execute("""
            DELETE FROM stop_times 
            WHERE trip_id IN (SELECT trip_id FROM trips WHERE route_id = ?)
        """, (route_id,))
        cursor.execute("DELETE FROM trips WHERE route_id = ?", (route_id,))

        # Expande frequência para viagens e tempos de parada
        if isinstance(frequencia, dict):
            hora_inicio = frequencia.get("hora_inicio")
            hora_fim = frequencia.get("hora_fim")
            intervalo_min = frequencia.get("intervalo_min")
        else:
            hora_inicio, hora_fim, intervalo_min = frequencia

        trips_list, stop_times_list = expand_frequency_to_stop_times(
            stop_ids, hora_inicio, hora_fim, intervalo_min
        )

        direction_id = linha.get("direction_id")
        trip_headsign = linha.get("trip_headsign")

        # Insere viagens
        physical_cols = get_physical_cols("trips")
        trip_cols = [col for col in gtfs_schema.column_order("trips") if col in physical_cols]
        for trip in trips_list:
            trip_data = {
                "route_id": route_id,
                "service_id": service_id,
                "trip_id": trip["trip_id"],
                "trip_headsign": trip_headsign,
                "direction_id": direction_id,
                "shape_id": linha.get("shape_id"),
            }
            values = [str(trip_data.get(col)) if trip_data.get(col) is not None else None for col in trip_cols]
            placeholders = ", ".join(["?"] * len(trip_cols))
            query = "INSERT INTO trips ({}) VALUES ({})".format(", ".join(trip_cols), placeholders)
            cursor.execute(query, values)

        # Insere tempos de parada
        physical_cols = get_physical_cols("stop_times")
        stop_time_cols = [col for col in gtfs_schema.column_order("stop_times") if col in physical_cols]
        for st in stop_times_list:
            values = [str(st.get(col)) if st.get(col) is not None else None for col in stop_time_cols]
            placeholders = ", ".join(["?"] * len(stop_time_cols))
            query = "INSERT INTO stop_times ({}) VALUES ({})".format(", ".join(stop_time_cols), placeholders)
            cursor.execute(query, values)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def build_line_shape(gpkg_path, shape_id, paradas_em_ordem):
    """
    Chama route_stops(paradas_em_ordem) para obter o traçado contínuo da linha
    (roteado e/ou fallback reto), limpa os pontos antigos com o mesmo shape_id em shapes_point,
    insere os novos vértices na tabela shapes_point e, por fim, chama
    GtfsReader(gpkg_path).build_shapes_line(gpkg_path) para regenerar a camada shapes.
    """
    try:
        from . import osm_routing
        from . import gtfs_reader
    except ImportError:
        try:
            import osm_routing
            import gtfs_reader
        except ImportError:
            from sig_bus import osm_routing
            from sig_bus import gtfs_reader

    from osgeo import ogr

    # 1. Chama route_stops para obter os pontos (QgsPointXY)
    pontos = osm_routing.route_stops(paradas_em_ordem)
    if not pontos:
        return None

    # 2. Deleta os pontos antigos com o mesmo shape_id
    conn = sqlite3.connect(gpkg_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shapes_point WHERE shape_id = ?", (shape_id,))
        conn.commit()
    finally:
        conn.close()

    # 3. Insere os novos vértices na tabela/camada shapes_point usando OGR para lidar com geometria
    ds = ogr.Open(gpkg_path, 1)
    if not ds:
        raise RuntimeError("Não foi possível abrir o GeoPackage via OGR.")

    lyr = ds.GetLayerByName("shapes_point")
    if not lyr:
        ds = None
        raise RuntimeError("Camada 'shapes_point' não encontrada no GeoPackage.")

    try:
        for idx, pt in enumerate(pontos, start=1):
            feat = ogr.Feature(lyr.GetLayerDefn())
            feat.SetField("shape_id", str(shape_id))
            feat.SetField("shape_pt_lat", str(pt.y()))
            feat.SetField("shape_pt_lon", str(pt.x()))
            feat.SetField("shape_pt_sequence", str(idx))

            # Configura a geometria do ponto (WGS 84)
            geom = ogr.Geometry(ogr.wkbPoint)
            geom.AddPoint(pt.x(), pt.y())
            feat.SetGeometry(geom)

            lyr.CreateFeature(feat)
    finally:
        ds = None  # Fecha e salva a conexão OGR

    # 4. Reconstrói a camada 'shapes' (linhas) a partir de 'shapes_point'
    reader = gtfs_reader.GtfsReader(gpkg_path)
    return reader.build_shapes_line(gpkg_path)
