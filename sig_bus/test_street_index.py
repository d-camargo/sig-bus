# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import json
import sys

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from urllib.parse import parse_qs, urlparse, unquote

from qgis.PyQt.QtNetwork import QNetworkReply
from sig_bus import street_index
from sig_bus.street_index import nomes_de_vias, corrigir


VIEWBOX = "-51.30,-29.10,-51.10,-29.25"  # lon_min,lat_max,lon_max,lat_min


def _url_da_requisicao(req):
    """Extrai a URL de um QNetworkRequest (Qt real ou o mock do conftest)."""
    url = getattr(req, "url", None)
    if callable(url):
        return url().toString()
    return getattr(req._url, "_url", str(req._url))


def _overpass_response(vias):
    elements = []
    for i, (nome, lat, lon) in enumerate(vias):
        elements.append({
            "type": "way",
            "id": i,
            "tags": {"highway": "residential", "name": nome},
            "center": {"lat": lat, "lon": lon},
        })
    return json.dumps({"elements": elements}).encode("utf-8")


class TestStreetIndex(unittest.TestCase):

    def setUp(self):
        street_index._CACHE = {}

    def test_nomes_de_vias_sem_viewbox(self):
        self.assertEqual(nomes_de_vias(""), [])
        self.assertEqual(nomes_de_vias(None), [])

    @patch('sig_bus.street_index.QgsNetworkAccessManager.instance')
    def test_nomes_de_vias_bbox_na_ordem_do_overpass(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = _overpass_response([("Rua Giuseppe Fôrmolo", -29.20, -51.20)])
        mock_manager.blockingGet.return_value = mock_reply

        vias = nomes_de_vias(VIEWBOX)
        self.assertEqual(vias, [("Rua Giuseppe Fôrmolo", -29.20, -51.20)])

        # Confere a query enviada: bbox na ordem lat_min,lon_min,lat_max,lon_max
        # (decisão 69), convertida a partir da viewbox do Nominatim.
        req = mock_manager.blockingGet.call_args[0][0]
        url = urlparse(_url_da_requisicao(req))
        query = unquote(parse_qs(url.query)["data"][0])
        self.assertIn("(-29.25,-51.30,-29.10,-51.10)", query)

    @patch('sig_bus.street_index.QgsNetworkAccessManager.instance')
    def test_nomes_de_vias_cache_de_sessao(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = _overpass_response([("Rua Um", -29.20, -51.20)])
        mock_manager.blockingGet.return_value = mock_reply

        self.assertEqual(len(nomes_de_vias(VIEWBOX)), 1)
        self.assertEqual(len(nomes_de_vias(VIEWBOX)), 1)
        self.assertEqual(mock_manager.blockingGet.call_count, 1)

    @patch('sig_bus.street_index.QgsNetworkAccessManager.instance')
    def test_nomes_de_vias_erro_de_rede(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.ConnectionRefusedError
        mock_manager.blockingGet.return_value = mock_reply

        self.assertEqual(nomes_de_vias(VIEWBOX), [])

    @patch('sig_bus.street_index.QgsNetworkAccessManager.instance')
    def test_nomes_de_vias_json_invalido(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = b'nao e json'
        mock_manager.blockingGet.return_value = mock_reply

        self.assertEqual(nomes_de_vias(VIEWBOX), [])

    @patch('sig_bus.street_index.QgsNetworkAccessManager.instance')
    def test_nomes_de_vias_excecao(self, mock_instance):
        mock_instance.side_effect = RuntimeError("QGIS Crash")
        self.assertEqual(nomes_de_vias(VIEWBOX), [])

    @patch('sig_bus.street_index.nomes_de_vias')
    def test_corrigir_casa_com_grafia_parecida(self, mock_nomes):
        mock_nomes.return_value = [("Rua Giuseppe Fôrmolo", -29.20, -51.20)]

        resultado = corrigir("Rua Giusepe Fórmolo", VIEWBOX)
        self.assertEqual(resultado, ("Rua Giuseppe Fôrmolo", -29.20, -51.20))

    @patch('sig_bus.street_index.nomes_de_vias')
    def test_corrigir_sem_via_parecida(self, mock_nomes):
        mock_nomes.return_value = [("Rua Giuseppe Fôrmolo", -29.20, -51.20)]

        self.assertIsNone(corrigir("Rua Inexistente ZZZ", VIEWBOX))

    def test_corrigir_sem_logradouro_ou_viewbox(self):
        self.assertIsNone(corrigir("", VIEWBOX))
        self.assertIsNone(corrigir("Rua Um", ""))
        self.assertIsNone(corrigir(None, None))

    @patch('sig_bus.street_index.nomes_de_vias')
    def test_corrigir_sem_vias_devolve_none(self, mock_nomes):
        mock_nomes.return_value = []
        self.assertIsNone(corrigir("Rua Um", VIEWBOX))


if __name__ == '__main__':
    unittest.main()
