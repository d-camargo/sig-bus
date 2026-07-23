# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import sys

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from qgis.core import QgsPointXY
from sig_bus.osm_routing import route_stops, build_road_graph, shortest_path

class TestOsmRouting(unittest.TestCase):

    def test_route_stops_empty(self):
        self.assertEqual(route_stops([]), [])
        self.assertEqual(route_stops(None), [])

    def test_route_stops_single_stop(self):
        stop = {"stop_lat": -23.55, "stop_lon": -46.63}
        res = route_stops([stop])
        self.assertEqual(len(res), 1)
        self.assertAlmostEqual(res[0].x(), -46.63)
        self.assertAlmostEqual(res[0].y(), -23.55)

    @patch('sig_bus.osm_routing.fetch_ways_for_stops')
    def test_route_stops_straight_line_fallback_on_network_error(self, mock_fetch):
        # Quando o fetch falhar e retornar lista vazia
        mock_fetch.return_value = []
        
        stops = [
            {"stop_lat": -23.55, "stop_lon": -46.63},
            {"stop_lat": -23.551, "stop_lon": -46.631}
        ]
        res = route_stops(stops)
        self.assertEqual(len(res), 2)
        self.assertAlmostEqual(res[0].x(), -46.63)
        self.assertAlmostEqual(res[0].y(), -23.55)
        self.assertAlmostEqual(res[1].x(), -46.631)
        self.assertAlmostEqual(res[1].y(), -23.551)

    @patch('sig_bus.osm_routing.fetch_ways_for_stops')
    def test_route_stops_connected_vias(self, mock_fetch):
        # Cria uma malha conectada simples de 3 nós na mesma reta vertical
        # Node 1 (-46.63, -23.550)
        # Node 2 (-46.63, -23.551)
        # Node 3 (-46.63, -23.552)
        mock_fetch.return_value = [
            {"type": "node", "id": 1, "lat": -23.550, "lon": -46.63},
            {"type": "node", "id": 2, "lat": -23.551, "lon": -46.63},
            {"type": "node", "id": 3, "lat": -23.552, "lon": -46.63},
            {"type": "way", "id": 10, "nodes": [1, 2, 3]}
        ]

        stops = [
            {"stop_lat": -23.550, "stop_lon": -46.63},
            {"stop_lat": -23.551, "stop_lon": -46.63},
            {"stop_lat": -23.552, "stop_lon": -46.63}
        ]

        res = route_stops(stops)
        # Deve encontrar o caminho: Node 1 -> Node 2 -> Node 3
        # E a junção não deve conter vértices duplicados.
        # Esperado: 3 pontos
        self.assertEqual(len(res), 3)
        self.assertAlmostEqual(res[0].y(), -23.550)
        self.assertAlmostEqual(res[1].y(), -23.551)
        self.assertAlmostEqual(res[2].y(), -23.552)

    @patch('sig_bus.osm_routing.fetch_ways_for_stops')
    def test_route_stops_partial_fallback(self, mock_fetch):
        # Malha onde apenas o primeiro trecho está conectado
        # Node 1 (-46.63, -23.550) -> Node 2 (-46.63, -23.551)
        # Node 3 (-46.63, -23.552) está isolado
        mock_fetch.return_value = [
            {"type": "node", "id": 1, "lat": -23.550, "lon": -46.63},
            {"type": "node", "id": 2, "lat": -23.551, "lon": -46.63},
            {"type": "way", "id": 10, "nodes": [1, 2]},
            {"type": "node", "id": 3, "lat": -23.552, "lon": -46.63}
        ]

        stops = [
            {"stop_lat": -23.550, "stop_lon": -46.63},
            {"stop_lat": -23.551, "stop_lon": -46.63},
            {"stop_lat": -23.552, "stop_lon": -46.63}
        ]

        res = route_stops(stops)
        # Primeiro trecho (1 -> 2): roteado [Node 1, Node 2]
        # Segundo trecho (2 -> 3): sem caminho, fallback linha reta [Node 2, Node 3]
        # Junção concatena removendo duplicado -> [Node 1, Node 2, Node 3]
        self.assertEqual(len(res), 3)
        self.assertAlmostEqual(res[0].y(), -23.550)
        self.assertAlmostEqual(res[1].y(), -23.551)
        self.assertAlmostEqual(res[2].y(), -23.552)

if __name__ == '__main__':
    unittest.main()
