# -*- coding: utf-8 -*-
"""
/***************************************************************************
 gtfs_edit_core — núcleo de edição de dados GTFS do SIG-Bus
                                 A QGIS plugin
 Gerencia o ciclo de vida da cópia de trabalho (Working Copy) do GeoPackage
 do GTFS para edição, sem dependências do ambiente QGIS GUI nesta fatia.
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
import shutil
import sqlite3


class WorkingCopy(object):
    """
    Gerencia a cópia de trabalho do GeoPackage para edição do GTFS.
    A cópia é criada no mesmo diretório do arquivo original.
    """

    def __init__(self, source_gpkg):
        """
        Construtor da classe.
        :param source_gpkg: Caminho absoluto para o arquivo feed.gpkg de origem ou diretório.
        """
        if source_gpkg and os.path.isdir(source_gpkg):
            self.source_path = None
            directory = source_gpkg
        else:
            self.source_path = source_gpkg
            directory = os.path.dirname(source_gpkg) if source_gpkg else ""
        self.edit_path = os.path.join(directory, "feed_edit.gpkg") if directory else ""

    def is_active(self):
        """
        Verifica se a cópia de trabalho de edição existe no disco.
        :return: True se feed_edit.gpkg existir, False caso contrário.
        """
        return bool(self.edit_path and os.path.exists(self.edit_path))

    def enter(self, overwrite=False):
        """
        Entra no modo de edição copiando o GeoPackage original para a cópia de trabalho.
        :param overwrite: Se True, sobrescreve a cópia de trabalho se já existir.
        :return: True se a cópia foi criada com sucesso, False caso contrário.
        """
        if self.is_active() and not overwrite:
            return False

        if not self.source_path or not self.edit_path:
            return False

        try:
            shutil.copyfile(self.source_path, self.edit_path)
            return True
        except Exception:
            return False

    def enter_empty(self, overwrite=False):
        """
        Cria um GeoPackage vazio com a estrutura de tabelas do GTFS.
        :param overwrite: Se True, sobrescreve a cópia de trabalho se já existir.
        :return: True se criado com sucesso, False caso contrário.
        """
        edit_path = self.edit_path

        if not edit_path:
            return False

        if os.path.exists(edit_path):
            if not overwrite:
                return False
            try:
                os.remove(edit_path)
            except OSError:
                return False

        try:
            from osgeo import ogr, osr
            try:
                from . import gtfs_schema
            except ImportError:
                try:
                    import gtfs_schema
                except ImportError:
                    from sig_bus import gtfs_schema

            driver = ogr.GetDriverByName("GPKG")
            if driver is None:
                return False

            ds = driver.CreateDataSource(edit_path)
            if ds is None:
                return False

            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)

            # Criar as tabelas do esquema GTFS + shapes_point
            tables = list(gtfs_schema.GTFS_FILES.keys())
            if "shapes_point" not in tables:
                tables.append("shapes_point")

            for table_name in tables:
                if table_name in ("stops", "shapes_point"):
                    geom_type = ogr.wkbPoint
                    layer_srs = srs
                elif table_name == "shapes":
                    geom_type = ogr.wkbLineString
                    layer_srs = srs
                else:
                    geom_type = ogr.wkbNone
                    layer_srs = None

                lyr = ds.CreateLayer(table_name, srs=layer_srs, geom_type=geom_type)
                if not lyr:
                    raise RuntimeError("Falha ao criar camada '{}'".format(table_name))

                # Cria os campos da tabela
                columns = gtfs_schema.column_order(table_name)
                for col in columns:
                    field_defn = ogr.FieldDefn(col, ogr.OFTString)
                    lyr.CreateField(field_defn)

            # Fecha/salva o datasource
            ds = None
            return True

        except Exception:
            # Se falhar a criação, removemos o arquivo incompleto se ele foi criado
            if os.path.exists(edit_path):
                try:
                    os.remove(edit_path)
                except OSError:
                    pass
            return False

    def discard(self):
        """
        Descarta a cópia de trabalho, apagando o arquivo temporário de edição.
        :return: True se o arquivo foi excluído com sucesso, False caso contrário.
        """
        if self.is_active():
            try:
                os.remove(self.edit_path)
                return True
            except Exception:
                return False
        return False


def load_route_stop_times(gpkg_path, route_short_name, service_id=None):
    """
    Carrega as viagens e tempos de parada de uma linha a partir do GeoPackage,
    organizados por sentido (direction_id).

    :param gpkg_path: Caminho para o arquivo GeoPackage (SQLite).
    :param route_short_name: Nome curto da linha (routes.route_short_name).
    :param service_id: ID de serviço opcional (trips.service_id) para filtragem.
    :return: Dicionário {direction_id: {"trip_headsign": str, "stop_times": [dict, ...]}}
    """
    if not gpkg_path or not os.path.exists(gpkg_path) or not route_short_name:
        return {}

    conn = sqlite3.connect(gpkg_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT route_id FROM routes WHERE route_short_name = ?", (str(route_short_name),))
        route_rows = cursor.fetchall()
        if not route_rows:
            return {}

        route_ids = [r["route_id"] for r in route_rows]
        placeholders = ",".join(["?"] * len(route_ids))
        params = list(route_ids)

        query = f"""
            SELECT t.direction_id, t.trip_headsign, st.*
            FROM trips t
            JOIN stop_times st ON t.trip_id = st.trip_id
            WHERE t.route_id IN ({placeholders})
        """
        if service_id is not None:
            query += " AND t.service_id = ?"
            params.append(str(service_id))

        query += " ORDER BY t.direction_id, st.trip_id, CAST(st.stop_sequence AS INTEGER)"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        result = {}
        for row in rows:
            row_dict = dict(row)
            dir_id_raw = row_dict.pop("direction_id", 0)
            headsign = row_dict.pop("trip_headsign", "") or ""

            try:
                dir_id = int(dir_id_raw) if dir_id_raw is not None else 0
            except (ValueError, TypeError):
                dir_id = 0

            if dir_id not in result:
                result[dir_id] = {
                    "trip_headsign": headsign,
                    "stop_times": []
                }
            elif not result[dir_id]["trip_headsign"] and headsign:
                result[dir_id]["trip_headsign"] = headsign

            result[dir_id]["stop_times"].append(row_dict)

        return result
    finally:
        conn.close()


def apply_stop_times(gpkg_path, stop_times):
    """
    Atualiza os horários de chegada e saída em stop_times numa única transação.

    :param gpkg_path: Caminho para o arquivo GeoPackage (SQLite).
    :param stop_times: Lista de dicionários (ou tuplas) contendo
                       trip_id, stop_sequence, arrival_time e departure_time.
    :return: Número total de linhas alteradas no banco de dados.
    """
    if not gpkg_path or not os.path.exists(gpkg_path) or not stop_times:
        return 0

    conn = sqlite3.connect(gpkg_path)
    cursor = conn.cursor()
    total_affected = 0

    try:
        query = """
            UPDATE stop_times
            SET arrival_time = ?, departure_time = ?
            WHERE trip_id = ? AND stop_sequence = ?
        """
        for item in stop_times:
            if isinstance(item, dict):
                arr = item.get("arrival_time")
                dep = item.get("departure_time")
                tid = item.get("trip_id")
                seq = item.get("stop_sequence")
            elif isinstance(item, (list, tuple)) and len(item) >= 4:
                tid, seq, arr, dep = item[0], item[1], item[2], item[3]
            else:
                continue

            cursor.execute(query, (arr, dep, tid, seq))
            total_affected += cursor.rowcount

        conn.commit()
        return total_affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

