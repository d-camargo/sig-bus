# -*- coding: utf-8 -*-
"""
/***************************************************************************
 gtfs_validator — validador de integridade e formatos GTFS do SIG-Bus
                                 A QGIS plugin
 Realiza a validação de integridade referencial e formatação dos dados
 editados no GeoPackage do GTFS.
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
import re
import sqlite3



class GtfsValidator(object):
    """
    Validador de dados GTFS contidos no GeoPackage.
    """

    def __init__(self, gpkg_path):
        """
        Construtor do validador.
        :param gpkg_path: Caminho completo para o arquivo GeoPackage (feed_edit.gpkg).
        """
        self.gpkg_path = gpkg_path

    def validate_integrity(self):
        """
        Valida a integridade referencial do banco de dados do GTFS.
        Retorna uma tupla (erros, avisos), onde cada elemento é uma lista de strings
        detalhando os problemas encontrados.

        Realiza as validações via consultas SQL agregadas de alto desempenho:
        - trips.route_id -> routes.route_id
        - trips.service_id -> calendar.service_id / calendar_dates.service_id
        - trips.shape_id -> shapes.shape_id
        - stop_times.trip_id -> trips.trip_id
        - stop_times.stop_id -> stops.stop_id
        - routes.agency_id -> agency.agency_id
        """
        errors = []
        warnings = []

        if not os.path.exists(self.gpkg_path):
            errors.append("Arquivo GeoPackage não encontrado: {}".format(self.gpkg_path))
            return errors, warnings

        try:
            conn = sqlite3.connect(self.gpkg_path)
            cursor = conn.cursor()

            # Descobre quais tabelas de fato existem no GeoPackage
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            # 1. trips.route_id -> routes.route_id
            if "trips" in existing_tables:
                if "routes" in existing_tables:
                    query = """
                        SELECT t.route_id, COUNT(*)
                        FROM trips t
                        LEFT JOIN routes r ON t.route_id = r.route_id
                        WHERE t.route_id IS NOT NULL AND t.route_id != '' AND r.route_id IS NULL
                        GROUP BY t.route_id
                    """
                    cursor.execute(query)
                    for route_id, count in cursor.fetchall():
                        errors.append(
                            "Erro de integridade referencial: route_id '{}' em trips ({} ocorrências) não existe na tabela routes.".format(
                                route_id, count
                            )
                        )
                else:
                    cursor.execute("SELECT COUNT(*) FROM trips WHERE route_id IS NOT NULL AND route_id != ''")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        errors.append(
                            "Erro de integridade referencial: a tabela 'routes' está ausente, mas existem {} viagens referenciando-a em 'trips'.".format(
                                count
                            )
                        )

            # 2. trips.service_id -> calendar.service_id / calendar_dates.service_id
            if "trips" in existing_tables:
                has_calendar = "calendar" in existing_tables
                has_calendar_dates = "calendar_dates" in existing_tables

                if has_calendar and has_calendar_dates:
                    query = """
                        SELECT t.service_id, COUNT(*)
                        FROM trips t
                        LEFT JOIN calendar c ON t.service_id = c.service_id
                        LEFT JOIN calendar_dates cd ON t.service_id = cd.service_id
                        WHERE t.service_id IS NOT NULL AND t.service_id != ''
                          AND c.service_id IS NULL
                          AND cd.service_id IS NULL
                        GROUP BY t.service_id
                    """
                    cursor.execute(query)
                    for service_id, count in cursor.fetchall():
                        errors.append(
                            "Erro de integridade referencial: service_id '{}' em trips ({} ocorrências) não existe nas tabelas calendar ou calendar_dates.".format(
                                service_id, count
                            )
                        )
                elif has_calendar:
                    query = """
                        SELECT t.service_id, COUNT(*)
                        FROM trips t
                        LEFT JOIN calendar c ON t.service_id = c.service_id
                        WHERE t.service_id IS NOT NULL AND t.service_id != '' AND c.service_id IS NULL
                        GROUP BY t.service_id
                    """
                    cursor.execute(query)
                    for service_id, count in cursor.fetchall():
                        errors.append(
                            "Erro de integridade referencial: service_id '{}' em trips ({} ocorrências) não existe na tabela calendar.".format(
                                service_id, count
                            )
                        )
                elif has_calendar_dates:
                    query = """
                        SELECT t.service_id, COUNT(*)
                        FROM trips t
                        LEFT JOIN calendar_dates cd ON t.service_id = cd.service_id
                        WHERE t.service_id IS NOT NULL AND t.service_id != '' AND cd.service_id IS NULL
                        GROUP BY t.service_id
                    """
                    cursor.execute(query)
                    for service_id, count in cursor.fetchall():
                        errors.append(
                            "Erro de integridade referencial: service_id '{}' em trips ({} ocorrências) não existe na tabela calendar_dates.".format(
                                service_id, count
                            )
                        )
                else:
                    cursor.execute("SELECT COUNT(*) FROM trips WHERE service_id IS NOT NULL AND service_id != ''")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        errors.append(
                            "Erro de integridade referencial: as tabelas 'calendar' e 'calendar_dates' estão ausentes, mas existem {} viagens referenciando service_id em 'trips'.".format(
                                count
                            )
                        )

            # 3. trips.shape_id -> shapes.shape_id
            if "trips" in existing_tables:
                if "shapes" in existing_tables:
                    query = """
                        SELECT t.shape_id, COUNT(*)
                        FROM trips t
                        LEFT JOIN shapes s ON t.shape_id = s.shape_id
                        WHERE t.shape_id IS NOT NULL AND t.shape_id != '' AND s.shape_id IS NULL
                        GROUP BY t.shape_id
                    """
                    cursor.execute(query)
                    for shape_id, count in cursor.fetchall():
                        errors.append(
                            "Erro de integridade referencial: shape_id '{}' em trips ({} ocorrências) não existe na tabela shapes.".format(
                                shape_id, count
                            )
                        )
                else:
                    cursor.execute("SELECT COUNT(*) FROM trips WHERE shape_id IS NOT NULL AND shape_id != ''")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        errors.append(
                            "Erro de integridade referencial: a tabela 'shapes' está ausente, mas existem {} viagens referenciando-a em 'trips'.".format(
                                count
                            )
                        )

            # 4. stop_times.trip_id -> trips.trip_id
            if "stop_times" in existing_tables:
                if "trips" in existing_tables:
                    query = """
                        SELECT st.trip_id, COUNT(*)
                        FROM stop_times st
                        LEFT JOIN trips t ON st.trip_id = t.trip_id
                        WHERE st.trip_id IS NOT NULL AND st.trip_id != '' AND t.trip_id IS NULL
                        GROUP BY st.trip_id
                    """
                    cursor.execute(query)
                    for trip_id, count in cursor.fetchall():
                        errors.append(
                            "Erro de integridade referencial: trip_id '{}' em stop_times ({} ocorrências) não existe na tabela trips.".format(
                                trip_id, count
                            )
                        )
                else:
                    cursor.execute("SELECT COUNT(*) FROM stop_times WHERE trip_id IS NOT NULL AND trip_id != ''")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        errors.append(
                            "Erro de integridade referencial: a tabela 'trips' está ausente, mas existem {} registros referenciando-a em 'stop_times'.".format(
                                count
                            )
                        )

            # 5. stop_times.stop_id -> stops.stop_id
            if "stop_times" in existing_tables:
                if "stops" in existing_tables:
                    query = """
                        SELECT st.stop_id, COUNT(*)
                        FROM stop_times st
                        LEFT JOIN stops s ON st.stop_id = s.stop_id
                        WHERE st.stop_id IS NOT NULL AND st.stop_id != '' AND s.stop_id IS NULL
                        GROUP BY st.stop_id
                    """
                    cursor.execute(query)
                    for stop_id, count in cursor.fetchall():
                        errors.append(
                            "Erro de integridade referencial: stop_id '{}' em stop_times ({} ocorrências) não existe na tabela stops.".format(
                                stop_id, count
                            )
                        )
                else:
                    cursor.execute("SELECT COUNT(*) FROM stop_times WHERE stop_id IS NOT NULL AND stop_id != ''")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        errors.append(
                            "Erro de integridade referencial: a tabela 'stops' está ausente, mas existem {} registros referenciando-a em 'stop_times'.".format(
                                count
                            )
                        )

            # 6. routes.agency_id -> agency.agency_id
            if "routes" in existing_tables:
                if "agency" in existing_tables:
                    query = """
                        SELECT r.agency_id, COUNT(*)
                        FROM routes r
                        LEFT JOIN agency a ON r.agency_id = a.agency_id
                        WHERE r.agency_id IS NOT NULL AND r.agency_id != '' AND a.agency_id IS NULL
                        GROUP BY r.agency_id
                    """
                    cursor.execute(query)
                    for agency_id, count in cursor.fetchall():
                        errors.append(
                            "Erro de integridade referencial: agency_id '{}' em routes ({} ocorrências) não existe na tabela agency.".format(
                                agency_id, count
                            )
                        )
                else:
                    cursor.execute("SELECT COUNT(*) FROM routes WHERE agency_id IS NOT NULL AND agency_id != ''")
                    count = cursor.fetchone()[0]
                    if count > 0:
                        warnings.append(
                            "Aviso de integridade referencial: a tabela 'agency' está ausente, mas existem {} rotas com agency_id preenchido.".format(
                                count
                            )
                        )

            conn.close()
        except sqlite3.Error as e:
            errors.append("Erro ao acessar banco de dados SQLite/GeoPackage para validação: {}".format(e))

        return errors, warnings

    def validate_formats(self):
        """
        Valida o formato de dados GTFS contidos no GeoPackage.
        Retorna uma tupla (erros, avisos), onde cada elemento é uma lista de strings.
        """
        errors = []
        warnings = []

        if not os.path.exists(self.gpkg_path):
            return errors, warnings

        try:
            conn = sqlite3.connect(self.gpkg_path)
            
            def regexp(expr, item):
                if item is None:
                    return True
                return re.search(expr, str(item)) is not None
                
            conn.create_function("REGEXP", 2, regexp)
            cursor = conn.cursor()

            # Descobre quais tabelas de fato existem no GeoPackage
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            # 1. Horários (stop_times.arrival_time, stop_times.departure_time) -> HH:MM:SS
            if "stop_times" in existing_tables:
                cursor.execute("PRAGMA table_info(stop_times)")
                cols = {row[1] for row in cursor.fetchall()}
                
                time_regex = r'^\d+:[0-5]\d:[0-5]\d$'
                
                if "arrival_time" in cols:
                    cursor.execute("""
                        SELECT arrival_time, COUNT(*)
                        FROM stop_times
                        WHERE arrival_time IS NOT NULL AND arrival_time != ''
                          AND arrival_time NOT REGEXP ?
                        GROUP BY arrival_time
                    """, (time_regex,))
                    for val, count in cursor.fetchall():
                        errors.append(
                            "Erro de formato: arrival_time '{}' em stop_times ({} ocorrências) não segue o formato HH:MM:SS.".format(
                                val, count
                            )
                        )

                if "departure_time" in cols:
                    cursor.execute("""
                        SELECT departure_time, COUNT(*)
                        FROM stop_times
                        WHERE departure_time IS NOT NULL AND departure_time != ''
                          AND departure_time NOT REGEXP ?
                        GROUP BY departure_time
                    """, (time_regex,))
                    for val, count in cursor.fetchall():
                        errors.append(
                            "Erro de formato: departure_time '{}' em stop_times ({} ocorrências) não segue o formato HH:MM:SS.".format(
                                val, count
                            )
                        )

            # 2. Datas (calendar.start_date, calendar.end_date, calendar_dates.date) -> YYYYMMDD
            date_regex = r'^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$'
            
            if "calendar" in existing_tables:
                cursor.execute("PRAGMA table_info(calendar)")
                cols = {row[1] for row in cursor.fetchall()}
                
                if "start_date" in cols:
                    cursor.execute("""
                        SELECT start_date, COUNT(*)
                        FROM calendar
                        WHERE start_date IS NOT NULL AND start_date != ''
                          AND start_date NOT REGEXP ?
                        GROUP BY start_date
                    """, (date_regex,))
                    for val, count in cursor.fetchall():
                        errors.append(
                            "Erro de formato: start_date '{}' em calendar ({} ocorrências) não segue o formato YYYYMMDD.".format(
                                val, count
                            )
                        )

                if "end_date" in cols:
                    cursor.execute("""
                        SELECT end_date, COUNT(*)
                        FROM calendar
                        WHERE end_date IS NOT NULL AND end_date != ''
                          AND end_date NOT REGEXP ?
                        GROUP BY end_date
                    """, (date_regex,))
                    for val, count in cursor.fetchall():
                        errors.append(
                            "Erro de formato: end_date '{}' em calendar ({} ocorrências) não segue o formato YYYYMMDD.".format(
                                val, count
                            )
                        )

            if "calendar_dates" in existing_tables:
                cursor.execute("PRAGMA table_info(calendar_dates)")
                cols = {row[1] for row in cursor.fetchall()}
                
                if "date" in cols:
                    cursor.execute("""
                        SELECT date, COUNT(*)
                        FROM calendar_dates
                        WHERE date IS NOT NULL AND date != ''
                          AND date NOT REGEXP ?
                        GROUP BY date
                    """, (date_regex,))
                    for val, count in cursor.fetchall():
                        errors.append(
                            "Erro de formato: date '{}' em calendar_dates ({} ocorrências) não segue o formato YYYYMMDD.".format(
                                val, count
                            )
                        )

            # 3. Lat/Lon (stops.stop_lat, stops.stop_lon) -> [-90, 90] / [-180, 180]
            if "stops" in existing_tables:
                cursor.execute("PRAGMA table_info(stops)")
                cols = {row[1] for row in cursor.fetchall()}
                
                if "stop_lat" in cols:
                    cursor.execute("""
                        SELECT stop_id, stop_lat
                        FROM stops
                        WHERE stop_lat IS NOT NULL AND stop_lat != ''
                          AND (CAST(stop_lat AS REAL) < -90.0 OR CAST(stop_lat AS REAL) > 90.0)
                    """)
                    for stop_id, val in cursor.fetchall():
                        errors.append(
                            "Erro de formato: stop_lat '{}' em stops (stop_id '{}') fora da faixa válida [-90, 90].".format(
                                val, stop_id
                            )
                        )

                if "stop_lon" in cols:
                    cursor.execute("""
                        SELECT stop_id, stop_lon
                        FROM stops
                        WHERE stop_lon IS NOT NULL AND stop_lon != ''
                          AND (CAST(stop_lon AS REAL) < -180.0 OR CAST(stop_lon AS REAL) > 180.0)
                    """)
                    for stop_id, val in cursor.fetchall():
                        errors.append(
                            "Erro de formato: stop_lon '{}' em stops (stop_id '{}') fora da faixa válida [-180, 180].".format(
                                val, stop_id
                            )
                        )

            # 4. Enums (routes.route_type, trips.direction_id, calendar_dates.exception_type)
            if "routes" in existing_tables:
                cursor.execute("PRAGMA table_info(routes)")
                cols = {row[1] for row in cursor.fetchall()}
                
                if "route_type" in cols:
                    cursor.execute("""
                        SELECT route_id, route_type
                        FROM routes
                        WHERE route_type IS NOT NULL AND route_type != ''
                          AND CAST(route_type AS TEXT) NOT IN ('0', '1', '2', '3', '4', '5', '6', '7', '11', '12')
                    """)
                    for route_id, val in cursor.fetchall():
                        errors.append(
                            "Erro de formato: route_type '{}' em routes (route_id '{}') inválido. Valores aceitos: 0, 1, 2, 3, 4, 5, 6, 7, 11, 12.".format(
                                val, route_id
                            )
                        )

            if "trips" in existing_tables:
                cursor.execute("PRAGMA table_info(trips)")
                cols = {row[1] for row in cursor.fetchall()}
                
                if "direction_id" in cols:
                    cursor.execute("""
                        SELECT trip_id, direction_id
                        FROM trips
                        WHERE direction_id IS NOT NULL AND direction_id != ''
                          AND CAST(direction_id AS TEXT) NOT IN ('0', '1')
                    """)
                    for trip_id, val in cursor.fetchall():
                        errors.append(
                            "Erro de formato: direction_id '{}' em trips (trip_id '{}') inválido. Valores aceitos: 0 ou 1.".format(
                                val, trip_id
                            )
                        )

            if "calendar_dates" in existing_tables:
                cursor.execute("PRAGMA table_info(calendar_dates)")
                cols = {row[1] for row in cursor.fetchall()}
                
                if "exception_type" in cols:
                    cursor.execute("""
                        SELECT service_id, date, exception_type
                        FROM calendar_dates
                        WHERE exception_type IS NOT NULL AND exception_type != ''
                          AND CAST(exception_type AS TEXT) NOT IN ('1', '2')
                    """)
                    for service_id, dt, val in cursor.fetchall():
                        errors.append(
                            "Erro de formato: exception_type '{}' em calendar_dates (service_id '{}', date '{}') inválido. Valores aceitos: 1 ou 2.".format(
                                val, service_id, dt
                            )
                        )

            conn.close()
        except sqlite3.Error as e:
            errors.append("Erro ao acessar banco de dados SQLite/GeoPackage para validação de formato: {}".format(e))

        return errors, warnings

    def validate(self):
        """
        Executa todas as validações no GeoPackage de edição do GTFS.
        Retorna uma tupla (erros, avisos).
        """
        err_integrity, warn_integrity = self.validate_integrity()
        err_format, warn_format = self.validate_formats()
        return err_integrity + err_format, warn_integrity + warn_format

