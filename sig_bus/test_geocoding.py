# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import sys
import time

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

if __name__ == '__main__':
    unittest.main()
