# -*- coding: utf-8 -*-
import os
import sqlite3
import shutil
import tempfile
import unittest
from unittest.mock import patch
import sys

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from qgis.core import QgsPointXY
from sig_bus.gtfs_edit_core import WorkingCopy
from sig_bus.gtfs_builder_core import (
    compute_progress,
    normalize_address,
    find_existing_stop,
    list_reusable_calendars,
    expand_frequency_to_stop_times,
)
from sig_bus import gtfs_schema
from sig_bus import gtfs_reader

class TestGtfsBuilderProgress(unittest.TestCase):
    def setUp(self):
        # Cria um diretório temporário para o teste
        self.test_dir = tempfile.mkdtemp()
        self.wc = WorkingCopy(self.test_dir)
        self.gpkg_path = self.wc.edit_path

    def tearDown(self):
        # Remove o diretório temporário
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_progress_empty_and_populated(self):
        # 1. Cria gpkg vazio usando a função do passo 31
        success = self.wc.enter_empty(overwrite=True)
        self.assertTrue(success, "Falha ao criar o gpkg vazio")
        self.assertTrue(os.path.exists(self.gpkg_path), "gpkg não existe fisicamente")

        # 2. Roda compute_progress no gpkg vazio
        pct_min, pct_max, falt_min, falt_max = compute_progress(self.gpkg_path)

        print("\n--- GPKG VAZIO ---")
        print(f"pct_minimo: {pct_min}%")
        print(f"pct_maximo: {pct_max}%")
        print(f"faltando_minimo: {falt_min}")
        print(f"faltando_maximo (tamanho={len(falt_max)}): {falt_max[:5]}...")

        # Asserts para gpkg vazio
        self.assertEqual(pct_min, 0.0, "pct_minimo deveria ser 0% para gpkg vazio")
        self.assertEqual(pct_max, 0.0, "pct_maximo deveria ser 0% para gpkg vazio")
        self.assertEqual(set(falt_min), set(gtfs_reader.REQUIRED_LAYERS), 
                         "Todas as tabelas obrigatórias deveriam estar em faltando_minimo")

        # 3. Popula manualmente 1 linha de cada tabela obrigatória com todos os campos required=True preenchidos
        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()

        # Remove todos os triggers para permitir inserts sem o módulo Spatialite
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        triggers = [row[0] for row in cursor.fetchall()]
        for trigger in triggers:
            cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")

        # Popular 'agency'
        # agency_name, agency_url, agency_timezone são obrigatórios
        cursor.execute("""
            INSERT INTO agency (agency_id, agency_name, agency_url, agency_timezone, agency_lang)
            VALUES ('A1', 'Agency One', 'http://example.com', 'America/Sao_Paulo', 'pt')
        """)

        # Popular 'routes'
        # route_id, route_type são obrigatórios
        cursor.execute("""
            INSERT INTO routes (route_id, route_type, route_short_name)
            VALUES ('R1', '3', 'Line 1')
        """)

        # Popular 'calendar'
        # service_id, days (monday..sunday), start_date, end_date são obrigatórios
        cursor.execute("""
            INSERT INTO calendar (service_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date)
            VALUES ('S1', '1', '1', '1', '1', '1', '0', '0', '20260701', '20261231')
        """)

        # Popular 'stops'
        # stop_id, stop_name, stop_lat, stop_lon são obrigatórios
        cursor.execute("""
            INSERT INTO stops (stop_id, stop_name, stop_lat, stop_lon)
            VALUES ('ST1', 'Stop 1', '-23.55', '-46.63')
        """)

        # Popular 'trips'
        # route_id, service_id, trip_id são obrigatórios
        cursor.execute("""
            INSERT INTO trips (route_id, service_id, trip_id, shape_id)
            VALUES ('R1', 'S1', 'T1', 'SH1')
        """)

        # Popular 'stop_times'
        # trip_id, arrival_time, departure_time, stop_id, stop_sequence são obrigatórios
        cursor.execute("""
            INSERT INTO stop_times (trip_id, arrival_time, departure_time, stop_id, stop_sequence)
            VALUES ('T1', '08:00:00', '08:05:00', 'ST1', '1')
        """)

        # Adiciona o shape para a viagem a fim de testar se a cobertura do shape aumenta no progresso máximo
        cursor.execute("""
            INSERT INTO shapes (shape_id) VALUES ('SH1')
        """)

        # Adiciona outra viagem para o mesmo route_id, mas com direction_id = 1 (para testar ida/volta)
        # O primeiro tem direction_id NULL, vamos atualizar ou inserir outra viagem
        cursor.execute("UPDATE trips SET direction_id = '0' WHERE trip_id = 'T1'")
        cursor.execute("""
            INSERT INTO trips (route_id, service_id, trip_id, shape_id, direction_id)
            VALUES ('R1', 'S1', 'T2', 'SH1', '1')
        """)
        cursor.execute("""
            INSERT INTO stop_times (trip_id, arrival_time, departure_time, stop_id, stop_sequence)
            VALUES ('T2', '18:00:00', '18:05:00', 'ST1', '1')
        """)

        conn.commit()
        conn.close()

        # 4. Roda compute_progress novamente
        pct_min_pop, pct_max_pop, falt_min_pop, falt_max_pop = compute_progress(self.gpkg_path)

        print("\n--- GPKG POPULADO ---")
        print(f"pct_minimo: {pct_min_pop}%")
        print(f"pct_maximo: {pct_max_pop}%")
        print(f"faltando_minimo: {falt_min_pop}")
        print(f"faltando_maximo (tamanho={len(falt_max_pop)}): {falt_max_pop}")

        # Asserts para gpkg populado
        self.assertEqual(pct_min_pop, 100.0, "pct_minimo deveria ser 100% após popular campos obrigatórios")
        self.assertEqual(len(falt_min_pop), 0, "faltando_minimo deveria estar vazio")
        self.assertGreater(pct_max_pop, 0.0, "pct_maximo deveria ser maior que 0% após popular")

        # Como populamos direction_id = 0 e 1, e colocamos shape_id que existe em shapes,
        # vamos testar que os avisos de shapes e direção não estão em faltando_maximo!
        self.assertNotIn("Traçado (shape) não associado a todas as viagens", falt_max_pop,
                         "shapes deveria estar satisfeito para todas as viagens")
        self.assertNotIn("Segundo sentido (ida/volta) não cadastrado para todas as linhas", falt_max_pop,
                         "segundo sentido por linha deveria estar satisfeito")

        print("\nTodos os testes de progresso passaram!")

    def test_normalize_address_and_find_existing_stop(self):
        # 1. Test normalize_address
        self.assertEqual(normalize_address("  Rua   Bahia,  123  "), "rua bahia, 123")
        self.assertEqual(normalize_address("RUA BAHIA, 123"), "rua bahia, 123")
        self.assertEqual(normalize_address(None), "")
        self.assertEqual(normalize_address(""), "")

        # 2. Test find_existing_stop on non-existent gpkg
        self.assertIsNone(find_existing_stop("non_existent_path.gpkg", "Rua Bahia"))

        # 3. Test find_existing_stop on empty gpkg
        success = self.wc.enter_empty(overwrite=True)
        self.assertTrue(success)
        self.assertIsNone(find_existing_stop(self.gpkg_path, "Rua Bahia"))

        # 4. Insert stops to test finding by name and description
        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()

        # Remove triggers to allow insert without spatialite
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        triggers = [row[0] for row in cursor.fetchall()]
        for trigger in triggers:
            cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")

        # Insert Stop 1 with name
        cursor.execute("""
            INSERT INTO stops (stop_id, stop_name, stop_desc, stop_lat, stop_lon)
            VALUES ('ST1', 'Rua Bahia, 123', 'Some desc', -23.55, -46.63)
        """)

        # Insert Stop 2 with description
        cursor.execute("""
            INSERT INTO stops (stop_id, stop_name, stop_desc, stop_lat, stop_lon)
            VALUES ('ST2', 'Other Stop', 'Avenida Paulista, 1000', -23.56, -46.65)
        """)

        conn.commit()
        conn.close()

        # Test finding by name (different casings and spacings)
        self.assertEqual(find_existing_stop(self.gpkg_path, "  Rua   Bahia,  123  "), "ST1")
        self.assertEqual(find_existing_stop(self.gpkg_path, "rua bahia, 123"), "ST1")
        self.assertEqual(find_existing_stop(self.gpkg_path, "RUA BAHIA, 123"), "ST1")

        # Test finding by description
        self.assertEqual(find_existing_stop(self.gpkg_path, "  Avenida   Paulista,  1000  "), "ST2")
        self.assertEqual(find_existing_stop(self.gpkg_path, "avenida paulista, 1000"), "ST2")

        # Test not finding
        self.assertIsNone(find_existing_stop(self.gpkg_path, "Rua Amazonas"))
        self.assertIsNone(find_existing_stop(self.gpkg_path, None))

    def test_list_reusable_calendars(self):
        # 1. Test on non-existent gpkg
        self.assertEqual(list_reusable_calendars("non_existent_path.gpkg"), [])

        # 2. Test on empty gpkg (without calendar table)
        success = self.wc.enter_empty(overwrite=True)
        self.assertTrue(success)
        self.assertEqual(list_reusable_calendars(self.gpkg_path), [])

        # 3. Test on gpkg with calendar table but no entries
        # Note: enter_empty creates the calendar table. Let's verify it starts empty.
        self.assertEqual(list_reusable_calendars(self.gpkg_path), [])

        # 4. Insert calendars to test returning them
        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()

        # Remove triggers to allow insert without spatialite
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        triggers = [row[0] for row in cursor.fetchall()]
        for trigger in triggers:
            cursor.execute(f"DROP TRIGGER IF EXISTS {trigger}")

        # Insert Calendar 1
        cursor.execute("""
            INSERT INTO calendar (service_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date)
            VALUES ('S1', '1', '1', '1', '1', '1', '0', '0', '20260701', '20261231')
        """)

        # Insert Calendar 2
        cursor.execute("""
            INSERT INTO calendar (service_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date)
            VALUES ('S2', '0', '0', '0', '0', '0', '1', '1', '20260702', '20261230')
        """)

        # Insert a duplicate Calendar 2 (to check DISTINCT)
        cursor.execute("""
            INSERT INTO calendar (service_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date)
            VALUES ('S2', '0', '0', '0', '0', '0', '1', '1', '20260702', '20261230')
        """)

        conn.commit()
        conn.close()

        # Test list_reusable_calendars returns both unique calendars
        calendars = list_reusable_calendars(self.gpkg_path)
        self.assertEqual(len(calendars), 2)
        
        # Sort by service_id to guarantee order in assert
        calendars.sort(key=lambda x: x[0])
        
        expected_s1 = ('S1', '1', '1', '1', '1', '1', '0', '0', '20260701', '20261231')
        expected_s2 = ('S2', '0', '0', '0', '0', '0', '1', '1', '20260702', '20261230')
        
        # Values could be strings or integers depending on how they are stored or cast, let's convert to strings for robust comparison
        s1_str = tuple(str(x) for x in calendars[0])
        s2_str = tuple(str(x) for x in calendars[1])
        
        self.assertEqual(s1_str, expected_s1)
        self.assertEqual(s2_str, expected_s2)

    def test_expand_frequency_to_stop_times(self):
        # Critério: com 3 paradas, 06:00–08:00, intervalo de 60 min, gera 3 viagens (06:00, 07:00, 08:00),
        # cada uma com 3 linhas de stop_times em sequência 1,2,3.
        stop_ids = ['stop1', 'stop2', 'stop3']
        trips, stop_times = expand_frequency_to_stop_times(stop_ids, "06:00", "08:00", 60)

        self.assertEqual(len(trips), 3)
        self.assertEqual(len(stop_times), 9)

        # Verificar trip_ids das viagens
        expected_trips = [
            {"trip_id": "trip_060000"},
            {"trip_id": "trip_070000"},
            {"trip_id": "trip_080000"}
        ]
        self.assertEqual(trips, expected_trips)

        # Verificar as linhas de stop_times
        # Viagem 1 (06:00:00)
        self.assertEqual(stop_times[0], {
            "trip_id": "trip_060000",
            "arrival_time": "06:00:00",
            "departure_time": "06:00:00",
            "stop_id": "stop1",
            "stop_sequence": 1
        })
        self.assertEqual(stop_times[1], {
            "trip_id": "trip_060000",
            "arrival_time": "06:00:00",
            "departure_time": "06:00:00",
            "stop_id": "stop2",
            "stop_sequence": 2
        })
        self.assertEqual(stop_times[2], {
            "trip_id": "trip_060000",
            "arrival_time": "06:00:00",
            "departure_time": "06:00:00",
            "stop_id": "stop3",
            "stop_sequence": 3
        })

        # Viagem 3 (08:00:00)
        self.assertEqual(stop_times[6], {
            "trip_id": "trip_080000",
            "arrival_time": "08:00:00",
            "departure_time": "08:00:00",
            "stop_id": "stop1",
            "stop_sequence": 1
        })

    def test_save_route(self):
        # 1. Cria gpkg vazio
        success = self.wc.enter_empty(overwrite=True)
        self.assertTrue(success)

        # Importa save_route
        from sig_bus.gtfs_builder_core import save_route

        # Dados de teste
        agency = {
            "agency_name": "Empresa Teste",
            "agency_url": "http://teste.com",
            "agency_timezone": "America/Sao_Paulo",
        }
        linha = {
            "route_short_name": "100",
            "route_long_name": "Linha Teste 100",
            "route_type": "3",
            "direction_id": "0",
            "trip_headsign": "Destino Teste",
        }
        paradas = [
            {"stop_name": "Parada A", "stop_lat": -20.0, "stop_lon": -40.0},
            {"stop_name": "Parada B", "stop_lat": -20.1, "stop_lon": -40.1},
        ]
        service = {
            "service_id": "service_diario",
            "monday": "1",
            "tuesday": "1",
            "wednesday": "1",
            "thursday": "1",
            "friday": "1",
            "saturday": "1",
            "sunday": "1",
            "start_date": "20260101",
            "end_date": "20261231",
        }
        frequencia = ("06:00:00", "08:00:00", 60)

        # Chama save_route
        save_route(self.gpkg_path, agency, linha, paradas, service, frequencia)

        # Valida que as tabelas possuem os dados
        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()

        # Verifica agency
        cursor.execute("SELECT agency_name, agency_url, agency_timezone FROM agency")
        self.assertEqual(cursor.fetchone(), ("Empresa Teste", "http://teste.com", "America/Sao_Paulo"))

        # Verifica routes
        cursor.execute("SELECT route_short_name, route_long_name, route_type FROM routes")
        self.assertEqual(cursor.fetchone(), ("100", "Linha Teste 100", "3"))

        # Verifica stops
        cursor.execute("SELECT stop_name, stop_lat, stop_lon FROM stops ORDER BY stop_id")
        stops = sorted(cursor.fetchall(), key=lambda x: x[0])
        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0][0], "Parada A")
        self.assertEqual(stops[1][0], "Parada B")

        # Verifica calendar
        cursor.execute("SELECT service_id, start_date, end_date FROM calendar")
        self.assertEqual(cursor.fetchone(), ("service_diario", "20260101", "20261231"))

        # Verifica trips
        cursor.execute("SELECT trip_id, route_id, service_id, direction_id, trip_headsign FROM trips ORDER BY trip_id")
        trips = cursor.fetchall()
        self.assertEqual(len(trips), 3)
        self.assertEqual(trips[0][0], "trip_060000")
        self.assertEqual(trips[0][3], "0")
        self.assertEqual(trips[0][4], "Destino Teste")

        # Verifica stop_times
        cursor.execute("SELECT trip_id, arrival_time, departure_time, stop_sequence FROM stop_times ORDER BY trip_id, stop_sequence")
        st = cursor.fetchall()
        self.assertEqual(len(st), 6) # 3 trips * 2 stops = 6 stop_times
        self.assertEqual(st[0], ("trip_060000", "06:00:00", "06:00:00", "1"))

        conn.close()

    def test_save_agency_only(self):
        # 1. Cria gpkg vazio
        success = self.wc.enter_empty(overwrite=True)
        self.assertTrue(success)

        # Importa save_route
        from sig_bus.gtfs_builder_core import save_route

        # Dados da agência
        agency = {
            "agency_name": "Agência Apenas",
            "agency_url": "http://apenas.com",
            "agency_timezone": "America/Sao_Paulo",
            "agency_lang": "pt",
            "agency_phone": "123456"
        }

        # Chama save_route apenas com agency
        save_route(self.gpkg_path, agency=agency, linha=None, paradas=[], service=None, frequencia=None)

        # Valida que apenas a agência foi salva
        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()

        cursor.execute("SELECT agency_name, agency_url, agency_timezone, agency_lang, agency_phone FROM agency")
        row = cursor.fetchone()
        self.assertEqual(row, ("Agência Apenas", "http://apenas.com", "America/Sao_Paulo", "pt", "123456"))

        # Valida que as tabelas de rotas, viagens, etc estão vazias
        cursor.execute("SELECT COUNT(*) FROM routes")
        self.assertEqual(cursor.fetchone()[0], 0)

        cursor.execute("SELECT COUNT(*) FROM trips")
        self.assertEqual(cursor.fetchone()[0], 0)

        conn.close()

    @patch('sig_bus.osm_routing.route_stops')
    def test_build_line_shape(self, mock_route_stops):
        # 1. Setup mock route_stops to return 3 QgsPointXY points
        pt1 = QgsPointXY(-46.63, -23.55)
        pt2 = QgsPointXY(-46.635, -23.555)
        pt3 = QgsPointXY(-46.64, -23.56)
        mock_route_stops.return_value = [pt1, pt2, pt3]

        # 2. Setup empty gpkg
        self.wc.enter_empty(overwrite=True)

        # 3. Call build_line_shape
        from sig_bus.gtfs_builder_core import build_line_shape
        stops = [
            {"stop_lat": -23.55, "stop_lon": -46.63},
            {"stop_lat": -23.555, "stop_lon": -46.635},
            {"stop_lat": -23.56, "stop_lon": -46.64}
        ]

        layer = build_line_shape(self.gpkg_path, "SHAPE_1", stops)

        # 4. Check that build_shapes_line returned the shapes line layer
        self.assertIsNotNone(layer)
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.featureCount(), 1)

        # 5. Check geometries in shapes_point
        conn = sqlite3.connect(self.gpkg_path)
        cursor = conn.cursor()
        cursor.execute("SELECT shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence FROM shapes_point ORDER BY CAST(shape_pt_sequence AS INTEGER)")
        points = cursor.fetchall()
        conn.close()

        self.assertEqual(len(points), 3)
        self.assertEqual(points[0], ("SHAPE_1", "-23.55", "-46.63", "1"))
        self.assertEqual(points[1], ("SHAPE_1", "-23.555", "-46.635", "2"))
        self.assertEqual(points[2], ("SHAPE_1", "-23.56", "-46.64", "3"))

        # Check shapes line layer geometry
        features = list(layer.getFeatures())
        self.assertEqual(len(features), 1)
        feat = features[0]
        self.assertEqual(feat["shape_id"], "SHAPE_1")
        geom = feat.geometry()
        self.assertFalse(geom.isEmpty())
        polyline = geom.asPolyline()
        self.assertEqual(len(polyline), 3)
        self.assertAlmostEqual(polyline[0].x(), -46.63)
        self.assertAlmostEqual(polyline[0].y(), -23.55)
        self.assertAlmostEqual(polyline[1].x(), -46.635)
        self.assertAlmostEqual(polyline[1].y(), -23.555)
        self.assertAlmostEqual(polyline[2].x(), -46.64)
        self.assertAlmostEqual(polyline[2].y(), -23.56)


if __name__ == '__main__':
    unittest.main()


