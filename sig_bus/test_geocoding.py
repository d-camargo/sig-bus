# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import sys
import time
from urllib.parse import unquote

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from qgis.PyQt.QtNetwork import QNetworkReply
from sig_bus.geocoding import NominatimGeocoder

class TestGeocoding(unittest.TestCase):

    def setUp(self):
        # Reinicia o tempo da última requisição para evitar delays reais nos testes
        NominatimGeocoder._last_request_time = 0.0

    def test_geocode_empty_or_none(self):
        self.assertEqual(NominatimGeocoder.geocode(""), [])
        self.assertEqual(NominatimGeocoder.geocode(None), [])

    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_success(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NoError
        mock_reply.content.return_value = b'[{"lat": "-23.55", "lon": "-46.63", "display_name": "Sao Paulo"}]'
        mock_manager.blockingGet.return_value = mock_reply

        results = NominatimGeocoder.geocode("Sao Paulo")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-23.55")
        self.assertEqual(results[0]["lon"], "-46.63")
        self.assertEqual(results[0]["display_name"], "Sao Paulo")

    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_network_error(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        # Simula erro de conexão
        mock_reply.error.return_value = QNetworkReply.ConnectionRefusedError
        mock_manager.blockingGet.return_value = mock_reply

        results = NominatimGeocoder.geocode("Qualquer Endereco")
        self.assertEqual(results, [])

    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_invalid_json(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NoError
        mock_reply.content.return_value = b'invalid json response'
        mock_manager.blockingGet.return_value = mock_reply

        results = NominatimGeocoder.geocode("Qualquer Endereco")
        self.assertEqual(results, [])

    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_exception_raised(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager
        # Simula que a chamada ao blockingGet lança uma exceção inesperada
        mock_manager.blockingGet.side_effect = RuntimeError("QGIS Crash")

        results = NominatimGeocoder.geocode("Qualquer Endereco")
        self.assertEqual(results, [])

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_rate_limiting(self, mock_instance, mock_sleep):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NoError
        mock_reply.content.return_value = b'[]'
        mock_manager.blockingGet.return_value = mock_reply

        # Faz duas chamadas rápidas consecutivas
        NominatimGeocoder.geocode("End 1")
        NominatimGeocoder.geocode("End 2")

        # Como o tempo entre chamadas foi quase zero, o sleep deve ter sido chamado para aguardar
        mock_sleep.assert_called()
        # O argumento de sleep deve ser aproximadamente 1 segundo (dependendo do tempo de execução do teste)
        args, kwargs = mock_sleep.call_args
        self.assertTrue(0.0 < args[0] <= 1.0)

def _url_da_requisicao(req):
    """Extrai a URL de um QNetworkRequest (Qt real ou o mock do conftest)."""
    url = getattr(req, "url", None)
    if callable(url):
        return url().toString()
    return req._url._url


class TestGeocodingContexto(unittest.TestCase):
    """Cascata de busca estruturada com contexto (decisões 44 e 47)."""

    CONTEXTO = {
        "city": "Caxias do Sul",
        "state": "RS",
        "country": "Brasil",
    }
    ENDERECO = "Rua Giusepe Fórmolo, 210 - Caxias do Sul"

    def setUp(self):
        NominatimGeocoder._last_request_time = 0.0

    def _mock_manager(self, mock_instance, respostas):
        """Prepara o blockingGet para devolver uma resposta por tentativa."""
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager
        self.urls = []

        def blocking_get(req):
            self.urls.append(_url_da_requisicao(req))
            corpo = respostas[len(self.urls) - 1]
            reply = MagicMock()
            reply.error.return_value = QNetworkReply.NoError
            reply.content.return_value = corpo
            return reply

        mock_manager.blockingGet.side_effect = blocking_get

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_cascata_para_na_tentativa_a(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[{"lat": "-29.16", "lon": "-51.17"}]'])

        results = NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.urls), 1)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_cascata_cai_para_b_quando_a_volta_vazio(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[]', b'[{"lat": "-29.16", "lon": "-51.17"}]'])

        results = NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.urls), 2)
        # (b) é a estruturada sem número
        estruturada_sem_numero = unquote(self.urls[1])
        self.assertIn("street=Rua Giusepe Fórmolo", estruturada_sem_numero)
        self.assertNotIn("210", estruturada_sem_numero)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_cascata_cai_para_c_quando_a_e_b_voltam_vazio(self, mock_instance, mock_sleep):
        self._mock_manager(
            mock_instance, [b'[]', b'[]', b'[{"lat": "-29.16", "lon": "-51.17"}]'])

        results = NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.urls), 3)
        # (c) é a busca livre, com município/UF/país anexados
        livre = unquote(self.urls[2])
        self.assertIn("q=", livre)
        self.assertNotIn("street=", livre)
        self.assertIn("Caxias do Sul - RS", livre)
        self.assertIn("Brasil", livre)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_url_da_tentativa_a(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[{"lat": "-29.16", "lon": "-51.17"}]'])

        NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

        url = unquote(self.urls[0])
        self.assertIn("street=210 Rua Giusepe Fórmolo", url)
        self.assertIn("city=Caxias do Sul", url)
        self.assertIn("state=RS", url)
        self.assertIn("countrycodes=br", url)
        self.assertIn("limit=5", url)
        self.assertIn("addressdetails=1", url)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_viewbox_limita_a_busca(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[{"lat": "-29.16", "lon": "-51.17"}]'])
        contexto = dict(self.CONTEXTO, viewbox="-51.3,-29.0,-51.0,-29.3")

        NominatimGeocoder.geocode(self.ENDERECO, contexto)

        url = unquote(self.urls[0])
        self.assertIn("viewbox=-51.3,-29.0,-51.0,-29.3", url)
        self.assertIn("bounded=1", url)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_sem_contexto_faz_uma_unica_busca_livre(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[]'])

        results = NominatimGeocoder.geocode(self.ENDERECO)

        self.assertEqual(results, [])
        self.assertEqual(len(self.urls), 1)
        self.assertNotIn("street=", self.urls[0])


class TestCityBbox(unittest.TestCase):

    def setUp(self):
        NominatimGeocoder._last_request_time = 0.0

    def test_city_bbox_empty_or_none(self):
        self.assertIsNone(NominatimGeocoder.city_bbox(""))
        self.assertIsNone(NominatimGeocoder.city_bbox(None))
        self.assertIsNone(NominatimGeocoder.city_bbox("   "))

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_city_bbox_sucesso(self, mock_instance, mock_sleep):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NoError
        # Nominatim boundingbox: [lat_min, lat_max, lon_min, lon_max]
        mock_reply.content.return_value = b'[{"boundingbox": ["-29.35", "-29.01", "-51.32", "-50.95"]}]'
        mock_manager.blockingGet.return_value = mock_reply

        bbox = NominatimGeocoder.city_bbox("Caxias do Sul", "RS")
        # Deve retornar lon_min,lat_max,lon_max,lat_min
        self.assertEqual(bbox, "-51.32,-29.01,-50.95,-29.35")

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_city_bbox_fallback_busca_livre(self, mock_instance, mock_sleep):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        urls_chamadas = []
        def side_effect(req):
            url = getattr(req, "url", None)
            if callable(url):
                urls_chamadas.append(url().toString())
            else:
                urls_chamadas.append(req._url._url)
            reply = MagicMock()
            reply.error.return_value = QNetworkReply.NoError
            if len(urls_chamadas) == 1:
                reply.content.return_value = b'[]'
            else:
                reply.content.return_value = b'[{"boundingbox": ["-29.35", "-29.01", "-51.32", "-50.95"]}]'
            return reply

        mock_manager.blockingGet.side_effect = side_effect

        bbox = NominatimGeocoder.city_bbox("Caxias do Sul", "RS")
        self.assertEqual(bbox, "-51.32,-29.01,-50.95,-29.35")
        self.assertEqual(len(urls_chamadas), 2)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_city_bbox_sem_resultado(self, mock_instance, mock_sleep):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NoError
        mock_reply.content.return_value = b'[]'
        mock_manager.blockingGet.return_value = mock_reply

        bbox = NominatimGeocoder.city_bbox("CidadeInexistente", "XX")
        self.assertIsNone(bbox)


if __name__ == '__main__':
    unittest.main()

