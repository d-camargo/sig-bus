# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import time
from urllib.parse import unquote

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from qgis.PyQt.QtNetwork import QNetworkReply
from sig_bus.geocoding import NominatimGeocoder, PhotonGeocoder, GoogleGeocoder, geocode

# `SigBus_dialog` importa a stack gráfica inteira do QGIS, que os mocks do
# conftest não cobrem — os testes de UI abaixo só rodam com QGIS real.
_QGIS_REAL = not os.environ.get('FORCE_MOCK_QGIS')
if _QGIS_REAL:
    try:
        import qgis.gui  # noqa: F401
    except ImportError:
        _QGIS_REAL = False
_SEM_QGIS = "exige QGIS real (rodando com os mocks do conftest)"

class TestGeocoding(unittest.TestCase):

    def setUp(self):
        # Reinicia o tempo da última requisição para evitar delays reais nos testes
        NominatimGeocoder._last_request_time = {}
        NominatimGeocoder.clear_cache()

    def test_geocode_empty_or_none(self):
        self.assertEqual(NominatimGeocoder.geocode(""), [])
        self.assertEqual(NominatimGeocoder.geocode(None), [])

    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_success(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = b'[{"lat": "-23.55", "lon": "-46.63", "display_name": "Sao Paulo"}]'
        mock_manager.blockingGet.return_value = mock_reply

        results = NominatimGeocoder.geocode("Sao Paulo")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-23.55")
        self.assertEqual(results[0]["lon"], "-46.63")
        self.assertEqual(results[0]["display_name"], "Sao Paulo")
        self.assertEqual(results[0]["provider"], "nominatim")

    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_network_error(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        # Simula erro de conexão
        mock_reply.error.return_value = QNetworkReply.NetworkError.ConnectionRefusedError
        mock_manager.blockingGet.return_value = mock_reply

        results = NominatimGeocoder.geocode("Qualquer Endereco")
        self.assertEqual(results, [])

    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_invalid_json(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
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

    @patch('sig_bus.geocoding.QgsMessageLog')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_falha_silenciosa_vira_linha_de_log(self, mock_instance, mock_log):
        """Decisão 52: a falha que zerou a geocodificação no QGIS 4 era um
        AttributeError engolido pelo except — agora tem que aparecer no log."""
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager
        mock_manager.blockingGet.side_effect = AttributeError("NoError")

        results = NominatimGeocoder.geocode("Qualquer Endereco")

        self.assertEqual(results, [])
        self.assertTrue(mock_log.logMessage.called)
        tags = [chamada.args[1] for chamada in mock_log.logMessage.call_args_list]
        self.assertIn('SIG-Bus', tags)

    @patch('sig_bus.geocoding.QgsMessageLog')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_log_inclui_etiqueta_da_tentativa(self, mock_instance, mock_log):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = b'[]'
        mock_manager.blockingGet.return_value = mock_reply

        NominatimGeocoder._get_json("https://nominatim.openstreetmap.org/search", etiqueta="a-estruturada-num")

        self.assertTrue(mock_log.logMessage.called)
        msgs = [chamada.args[0] for chamada in mock_log.logMessage.call_args_list]
        self.assertTrue(any("[a-estruturada-num]" in msg for msg in msgs))

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_rate_limiting(self, mock_instance, mock_sleep):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
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

    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_session_cache_corta_requisicao_repetida(self, mock_instance):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = b'[{"lat": "-23.55", "lon": "-46.63", "display_name": "Sao Paulo"}]'
        mock_manager.blockingGet.return_value = mock_reply

        res1 = NominatimGeocoder._get_json("https://nominatim.openstreetmap.org/search?q=Sao+Paulo")
        res2 = NominatimGeocoder._get_json("https://nominatim.openstreetmap.org/search?q=Sao+Paulo")

        self.assertEqual(res1, res2)
        # O blockingGet deve ter sido chamado apenas UMA vez graças ao cache de sessão
        self.assertEqual(mock_manager.blockingGet.call_count, 1)

    @patch('sig_bus.geocoding.QgsMessageLog')
    def test_log_redige_credenciais_na_url(self, mock_log):
        """Decisão 65: credenciais em URLs nunca devem aparecer no log."""
        from sig_bus.geocoding import _log, _redigir_credenciais

        url_com_chave = "https://maps.googleapis.com/maps/api/geocode/json?address=Test&key=AIzaSySecretKey123&api_key=secret456"
        _log("consultando {}".format(url_com_chave), 0)

        self.assertTrue(mock_log.logMessage.called)
        msg_logged = mock_log.logMessage.call_args[0][0]
        self.assertNotIn("AIzaSySecretKey123", msg_logged)
        self.assertNotIn("secret456", msg_logged)
        self.assertIn("key=***", msg_logged)
        self.assertIn("api_key=***", msg_logged)

        url_com_auth = "https://user:password123@example.com/api?token=secret789"
        redigido = _redigir_credenciais(url_com_auth)
        self.assertNotIn("password123", redigido)
        self.assertNotIn("secret789", redigido)
        self.assertIn("user:***@", redigido)
        self.assertIn("token=***", redigido)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.time.time')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_rate_limit_mesmo_host_limitado_espera(self, mock_instance, mock_time, mock_sleep):
        """Decisão 67: duas requisições seguidas ao mesmo host limitado esperam 1 s."""
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager
        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = b'[]'
        mock_manager.blockingGet.return_value = mock_reply

        NominatimGeocoder._last_request_time = {}

        mock_time.return_value = 10.0
        NominatimGeocoder._get_json("https://nominatim.openstreetmap.org/search?q=1")
        mock_sleep.assert_not_called()

        mock_time.return_value = 10.2
        NominatimGeocoder._get_json("https://nominatim.openstreetmap.org/search?q=2")
        mock_sleep.assert_called_once()
        self.assertAlmostEqual(mock_sleep.call_args[0][0], 0.8, places=2)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.time.time')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_rate_limit_hosts_limitados_diferentes_nao_compartilham_espera(self, mock_instance, mock_time, mock_sleep):
        """Decisão 67: hosts limitados diferentes não compartilham a espera de 1 s."""
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager
        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = b'[]'
        mock_manager.blockingGet.return_value = mock_reply

        NominatimGeocoder._last_request_time = {}

        mock_time.return_value = 10.0
        NominatimGeocoder._get_json("https://nominatim.openstreetmap.org/search?q=1")

        mock_time.return_value = 10.2
        NominatimGeocoder._get_json("https://photon.komoot.io/api?q=2")

        mock_sleep.assert_not_called()

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.time.time')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_rate_limit_host_sem_limite_nao_espera(self, mock_instance, mock_time, mock_sleep):
        """Decisão 67: hosts fora de HOSTS_COM_LIMITE não esperam."""
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager
        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = b'[]'
        mock_manager.blockingGet.return_value = mock_reply

        NominatimGeocoder._last_request_time = {}

        mock_time.return_value = 10.0
        NominatimGeocoder._get_json("https://maps.googleapis.com/maps/api/geocode/json?q=1")

        mock_time.return_value = 10.2
        NominatimGeocoder._get_json("https://maps.googleapis.com/maps/api/geocode/json?q=2")

        mock_sleep.assert_not_called()

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
        NominatimGeocoder._last_request_time = {}
        NominatimGeocoder.clear_cache()

    def _mock_manager(self, mock_instance, respostas):
        """Prepara o blockingGet para devolver uma resposta por tentativa."""
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager
        self.urls = []

        def blocking_get(req):
            self.urls.append(_url_da_requisicao(req))
            idx = len(self.urls) - 1
            corpo = respostas[idx] if idx < len(respostas) else b'[]'
            reply = MagicMock()
            reply.error.return_value = QNetworkReply.NetworkError.NoError
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
    def test_fallback_sem_bounded_quando_bounded_zera(self, mock_instance, mock_sleep):
        # 3 tentativas com bounded=1 voltam mudo; a 4ª (primeira sem bounded=1) acha
        respostas = [b'[]', b'[]', b'[]', b'[{"lat": "-29.16", "lon": "-51.17"}]']
        self._mock_manager(mock_instance, respostas)
        contexto = dict(self.CONTEXTO, viewbox="-51.3,-29.0,-51.0,-29.3")

        results = NominatimGeocoder.geocode(self.ENDERECO, contexto)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.urls), 4)
        # As primeiras 3 tentativas contêm bounded=1
        for u in self.urls[:3]:
            self.assertIn("bounded=1", unquote(u))
        # A 4ª tentativa mantém viewbox mas remove bounded=1
        url_fallback = unquote(self.urls[3])
        self.assertIn("viewbox=-51.3,-29.0,-51.0,-29.3", url_fallback)
        self.assertNotIn("bounded=1", url_fallback)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_acerto_na_primeira_rodada_nao_dispara_o_fallback(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[{"lat": "-29.16", "lon": "-51.17"}]'])
        contexto = dict(self.CONTEXTO, viewbox="-51.3,-29.0,-51.0,-29.3")

        results = NominatimGeocoder.geocode(self.ENDERECO, contexto)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.urls), 1)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_bairro_igual_ao_municipio_nao_se_repete_na_busca_livre(self, mock_instance, mock_sleep):
        # "…, 210 - Caxias do Sul" faz o parser ler "Caxias do Sul" como bairro:
        # sem o corte da decisão 53 o q= viria "Caxias do Sul, Caxias do Sul - RS".
        self._mock_manager(mock_instance, [b'[]', b'[]', b'[]'])

        NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

        livre = unquote(self.urls[2]).lower()
        self.assertEqual(livre.count("caxias do sul"), 1)

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_sem_contexto_faz_uma_unica_busca_livre(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[{"lat": "-29.16", "lon": "-51.17"}]'])

        results = NominatimGeocoder.geocode(self.ENDERECO)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.urls), 1)
        self.assertNotIn("street=", self.urls[0])

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_nominatim_acerto_nao_consulta_photon(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[{"lat": "-29.16", "lon": "-51.17"}]'])

        results = geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(self.urls), 1)
        self.assertIn("nominatim.openstreetmap.org", self.urls[0])

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_cascata_vazia_consulta_photon_e_devolve_normalizados(self, mock_instance, mock_sleep):
        photon_geojson = (
            b'{"type": "FeatureCollection", "features": ['
            b'{"geometry": {"type": "Point", "coordinates": [-51.17, -29.16]}, '
            b'"properties": {"name": "Rua Giuseppe Formolo", "city": "Caxias do Sul", "state": "RS", "country": "Brasil"}}'
            b']}'
        )
        self._mock_manager(mock_instance, [b'[]', b'[]', b'[]', photon_geojson])

        results = geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-29.16")
        self.assertEqual(results[0]["lon"], "-51.17")
        self.assertIn("photon.komoot.io", self.urls[-1])

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_photon_descarta_candidato_de_outro_municipio_sem_bbox(self, mock_instance, mock_sleep):
        photon_geojson = (
            b'{"type": "FeatureCollection", "features": ['
            b'{"geometry": {"type": "Point", "coordinates": [-51.22, -30.03]}, '
            b'"properties": {"name": "Rua Giuseppe Formolo", "city": "Porto Alegre", "state": "RS", "country": "Brasil"}},'
            b'{"geometry": {"type": "Point", "coordinates": [-51.17, -29.16]}, '
            b'"properties": {"name": "Rua Giuseppe Formolo", "city": "Caxias do Sul", "state": "RS", "country": "Brasil"}}'
            b']}'
        )
        self._mock_manager(mock_instance, [b'[]', b'[]', b'[]', photon_geojson])

        results = geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-29.16")

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_photon_vazio_ou_erro_devolve_lista_vazia(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[]', b'[]', b'[]', b'[]'])

        results = geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(results, [])

    @patch('sig_bus.geocoding.QgsMessageLog')
    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_cascata_completa_registra_etiquetas_na_ordem(self, mock_instance, mock_sleep, mock_log):
        self._mock_manager(mock_instance,
                           [b'[]', b'[]', b'[]', b'{"type": "FeatureCollection", "features": []}'])

        geocode(self.ENDERECO, self.CONTEXTO)

        msgs = [chamada.args[0] for chamada in mock_log.logMessage.call_args_list]
        etiquetas = [m.split("]")[0].split("[")[1] for m in msgs if "[" in m]
        self.assertEqual(etiquetas,
                         ["a-estruturada-num", "b-estruturada", "c-livre", "photon"])


class TestCityBbox(unittest.TestCase):

    def setUp(self):
        NominatimGeocoder._last_request_time = {}
        NominatimGeocoder.clear_cache()

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
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
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
            reply.error.return_value = QNetworkReply.NetworkError.NoError
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
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = b'[]'
        mock_manager.blockingGet.return_value = mock_reply

        bbox = NominatimGeocoder.city_bbox("CidadeInexistente", "XX")
        self.assertIsNone(bbox)


class TestPhotonGeocoder(unittest.TestCase):

    def setUp(self):
        NominatimGeocoder._last_request_time = {}
        NominatimGeocoder.clear_cache()

    def test_geocode_empty_or_none(self):
        self.assertEqual(PhotonGeocoder.geocode(""), [])
        self.assertEqual(PhotonGeocoder.geocode(None), [])

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_geocode_photon_success(self, mock_instance, mock_sleep):
        mock_manager = MagicMock()
        mock_instance.return_value = mock_manager

        geojson = (
            b'{"type": "FeatureCollection", "features": ['
            b'{"geometry": {"type": "Point", "coordinates": [-51.17, -29.16]}, '
            b'"properties": {"name": "Rua Giuseppe Formolo", "city": "Caxias do Sul", "state": "RS", "country": "Brasil"}}'
            b']}'
        )

        mock_reply = MagicMock()
        mock_reply.error.return_value = QNetworkReply.NetworkError.NoError
        mock_reply.content.return_value = geojson
        mock_manager.blockingGet.return_value = mock_reply

        results = PhotonGeocoder.geocode("Rua Giuseppe Formolo", {"city": "Caxias do Sul", "state": "RS"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-29.16")
        self.assertEqual(results[0]["lon"], "-51.17")
        self.assertIn("Rua Giuseppe Formolo", results[0]["display_name"])
        self.assertEqual(results[0]["provider"], "photon")


class TestGoogleGeocoder(unittest.TestCase):

    def setUp(self):
        NominatimGeocoder._last_request_time = {}
        NominatimGeocoder.clear_cache()

    def test_geocode_empty_or_none(self):
        self.assertEqual(GoogleGeocoder.geocode(""), [])
        self.assertEqual(GoogleGeocoder.geocode(None), [])

    def test_google_url_com_viewbox_e_chave(self):
        """Verifica a ordem da bounds (lat_min,lon_min|lat_max,lon_max) e parâmetros."""
        contexto = {
            "city": "Caxias do Sul",
            "state": "RS",
            "country": "Brasil",
            # lon_min, lat_max, lon_max, lat_min (ordem Nominatim)
            "viewbox": "-51.2,-29.1,-51.1,-29.2",
        }
        url = GoogleGeocoder._google_url("Rua Giusepe Fórmolo, 210", contexto, chave="MINHA_CHAVE")
        self.assertIn("key=MINHA_CHAVE", url)
        self.assertIn("components=country:BR", url)
        self.assertIn("language=pt-BR", url)
        self.assertIn("region=br", url)
        # lon_min=-51.2, lat_max=-29.1, lon_max=-51.1, lat_min=-29.2
        # Ordem do Google: lat_min,lon_min|lat_max,lon_max -> -29.2,-51.2|-29.1,-51.1
        self.assertIn("bounds=-29.2,-51.2|-29.1,-51.1", url)

    def test_google_url_sem_viewbox(self):
        """Sem viewbox a URL não leva o parâmetro bounds."""
        contexto = {"city": "Caxias do Sul", "state": "RS"}
        url = GoogleGeocoder._google_url("Rua Giusepe Fórmolo, 210", contexto, chave="MINHA_CHAVE")
        self.assertNotIn("bounds=", url)

    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_geocode_normalizacao(self, mock_get_json):
        """Verifica normalização: lat/lon não trocados, lng vira lon, types/partial_match/location_type guardados."""
        payload_real_reduzido = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Rua Giuseppe Fórmolo, 210 - Panazzolo, Caxias do Sul - RS, 95080-000, Brasil",
                    "geometry": {
                        "location": {
                            "lat": -29.1834,
                            "lng": -51.1892
                        },
                        "location_type": "ROOFTOP"
                    },
                    "partial_match": False,
                    "types": ["street_address"]
                }
            ]
        }
        mock_get_json.return_value = payload_real_reduzido

        results = GoogleGeocoder.geocode(
            "Rua Giusepe Fórmolo, 210",
            contexto={"viewbox": "-51.2,-29.1,-51.1,-29.2"},
            chave="MINHA_CHAVE"
        )

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res["lat"], "-29.1834")
        self.assertEqual(res["lon"], "-51.1892")
        self.assertEqual(res["display_name"], "Rua Giuseppe Fórmolo, 210 - Panazzolo, Caxias do Sul - RS, 95080-000, Brasil")
        self.assertEqual(res["types"], ["street_address"])
        self.assertIs(res["partial_match"], False)
        self.assertEqual(res["location_type"], "ROOFTOP")
        self.assertEqual(res["provider"], "google")

    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_status_zero_results_nao_loga_aviso(self, mock_get_json):
        mock_get_json.return_value = {"status": "ZERO_RESULTS", "results": []}
        self.assertEqual(GoogleGeocoder._buscar("http://x"), [])

    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_status_erro_devolve_vazio(self, mock_get_json):
        mock_get_json.return_value = {"status": "REQUEST_DENIED", "results": []}
        self.assertEqual(GoogleGeocoder._buscar("http://x"), [])

    @patch('sig_bus.geocoding.QgsMessageLog')
    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_request_denied_loga_error_message_e_guarda_ultimo_erro(self, mock_get_json, mock_log):
        """Decisão 64: chave quebrada não pode ficar indistinguível de endereço
        inexistente — o `error_message` do Google vai para o log e para a UI."""
        GoogleGeocoder.ultimo_erro = None
        mock_get_json.return_value = {
            "status": "REQUEST_DENIED",
            "error_message": "The provided API key is invalid.",
            "results": [],
        }

        self.assertEqual(GoogleGeocoder._buscar("http://x", etiqueta="google"), [])

        self.assertIn("REQUEST_DENIED", GoogleGeocoder.ultimo_erro)
        self.assertIn("The provided API key is invalid.", GoogleGeocoder.ultimo_erro)
        msgs = [c.args[0] for c in mock_log.logMessage.call_args_list]
        self.assertTrue(any("REQUEST_DENIED" in m and "invalid" in m for m in msgs), msgs)

    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_over_query_limit_preenche_ultimo_erro(self, mock_get_json):
        GoogleGeocoder.ultimo_erro = None
        mock_get_json.return_value = {"status": "OVER_QUERY_LIMIT", "results": []}

        self.assertEqual(GoogleGeocoder._buscar("http://x"), [])
        self.assertEqual(GoogleGeocoder.ultimo_erro, "OVER_QUERY_LIMIT")

    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_acerto_limpa_ultimo_erro(self, mock_get_json):
        GoogleGeocoder.ultimo_erro = "REQUEST_DENIED"
        mock_get_json.return_value = {
            "status": "OK",
            "results": [{
                "formatted_address": "Rua Teste, 1",
                "geometry": {"location": {"lat": -29.1, "lng": -51.1}},
                "types": ["street_address"],
            }],
        }

        self.assertEqual(len(GoogleGeocoder._buscar("http://x")), 1)
        self.assertIsNone(GoogleGeocoder.ultimo_erro)

    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_descarta_acerto_nivel_cidade(self, mock_get_json):
        """Candidato tipo `locality` (a cidade inteira) não serve para localizar uma parada."""
        mock_get_json.return_value = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Caxias do Sul - RS, Brasil",
                    "geometry": {"location": {"lat": -29.16, "lng": -51.17}},
                    "types": ["locality", "political"],
                },
                {
                    "formatted_address": "Rua Giuseppe Fórmolo, 210 - Caxias do Sul - RS, Brasil",
                    "geometry": {"location": {"lat": -29.1834, "lng": -51.1892}},
                    "types": ["street_address"],
                },
            ],
        }
        results = GoogleGeocoder._buscar("http://x")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["display_name"], "Rua Giuseppe Fórmolo, 210 - Caxias do Sul - RS, Brasil")

    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_so_aceita_types_de_nivel_rua(self, mock_get_json):
        """Decisão 66: a regra é lista de aceitação, não de recusa — `postal_code`
        e `neighborhood` também são centro de área, não endereço."""
        mock_get_json.return_value = {
            "status": "OK",
            "results": [
                {"formatted_address": "95080-000, Caxias do Sul - RS",
                 "geometry": {"location": {"lat": -29.16, "lng": -51.17}},
                 "types": ["postal_code"]},
                {"formatted_address": "Panazzolo, Caxias do Sul - RS",
                 "geometry": {"location": {"lat": -29.17, "lng": -51.18}},
                 "types": ["neighborhood", "political"]},
                {"formatted_address": "Terminal Central, Caxias do Sul - RS",
                 "geometry": {"location": {"lat": -29.18, "lng": -51.19}},
                 "types": ["establishment", "point_of_interest"]},
            ],
        }
        results = GoogleGeocoder._buscar("http://x")
        self.assertEqual([r["display_name"] for r in results],
                         ["Terminal Central, Caxias do Sul - RS"])

    @patch('sig_bus.geocoding.QgsMessageLog')
    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_google_descarte_diz_no_log_qual_types_motivou(self, mock_get_json, mock_log):
        mock_get_json.return_value = {
            "status": "OK",
            "results": [{
                "formatted_address": "Caxias do Sul - RS, Brasil",
                "geometry": {"location": {"lat": -29.16, "lng": -51.17}},
                "types": ["locality", "political"],
                "partial_match": True,
            }],
        }

        self.assertEqual(GoogleGeocoder._buscar("http://x", etiqueta="google"), [])

        msgs = [c.args[0] for c in mock_log.logMessage.call_args_list]
        self.assertTrue(any("nível-rua" in m and "locality" in m for m in msgs), msgs)


class TestGeocodeCascataGoogle(unittest.TestCase):

    def setUp(self):
        NominatimGeocoder._last_request_time = {}
        NominatimGeocoder.clear_cache()

    @patch('sig_bus.geocoding.get_google_api_key')
    @patch('sig_bus.geocoding.get_provider_mode')
    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_com_chave_e_acerto_google_nominatim_nao_consultado(self, mock_get_json, mock_mode, mock_key):
        mock_mode.return_value = "auto"
        mock_key.return_value = "MINHA_CHAVE_GOOGLE"

        google_ok = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "Rua Giuseppe Fórmolo, 210 - Caxias do Sul - RS, Brasil",
                    "geometry": {"location": {"lat": -29.1834, "lng": -51.1892}},
                    "types": ["street_address"],
                }
            ]
        }
        mock_get_json.return_value = google_ok

        results = geocode("Rua Giusepe Fórmolo, 210", contexto={"city": "Caxias do Sul"})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-29.1834")
        self.assertEqual(mock_get_json.call_count, 1)
        url_chamada = mock_get_json.call_args[0][0]
        self.assertIn("maps.googleapis.com", url_chamada)
        self.assertIn("key=MINHA_CHAVE_GOOGLE", url_chamada)

    @patch('sig_bus.geocoding.get_google_api_key')
    @patch('sig_bus.geocoding.get_provider_mode')
    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_com_chave_e_request_denied_cascata_gratis_roda_inteira(self, mock_get_json, mock_mode, mock_key):
        mock_mode.return_value = "auto"
        mock_key.return_value = "CHAVE_INVALIDA"

        google_denied = {"status": "REQUEST_DENIED", "results": []}
        nominatim_ok = [{"lat": "-29.16", "lon": "-51.17", "display_name": "Rua Teste"}]

        mock_get_json.side_effect = [google_denied, nominatim_ok]

        results = geocode("Rua Giusepe Fórmolo, 210", contexto={"city": "Caxias do Sul", "state": "RS"})

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-29.16")
        self.assertEqual(mock_get_json.call_count, 2)
        urls = [c[0][0] for c in mock_get_json.call_args_list]
        self.assertIn("maps.googleapis.com", urls[0])
        self.assertIn("nominatim.openstreetmap.org", urls[1])

    @patch('sig_bus.geocoding.get_google_api_key')
    @patch('sig_bus.geocoding.get_provider_mode')
    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_sem_chave_mesma_sequencia_sem_google(self, mock_get_json, mock_mode, mock_key):
        mock_mode.return_value = "auto"
        mock_key.return_value = ""

        nominatim_ok = [{"lat": "-29.16", "lon": "-51.17", "display_name": "Rua Teste"}]
        mock_get_json.return_value = nominatim_ok

        results = geocode("Rua Giusepe Fórmolo, 210", contexto={"city": "Caxias do Sul", "state": "RS"})

        self.assertEqual(len(results), 1)
        self.assertEqual(mock_get_json.call_count, 1)
        url_chamada = mock_get_json.call_args[0][0]
        self.assertIn("nominatim.openstreetmap.org", url_chamada)
        self.assertNotIn("maps.googleapis.com", url_chamada)

    @patch('sig_bus.geocoding.corrigir')
    @patch('sig_bus.geocoding.NominatimGeocoder._get_json')
    def test_todos_provedores_falham_aciona_corretor_como_ultimo_degrau(self, mock_get_json, mock_corrigir):
        mock_get_json.return_value = []
        mock_corrigir.return_value = ("Rua Giuseppe Fôrmolo", -29.20, -51.20)

        contexto = {"viewbox": "-51.30,-29.10,-51.10,-29.25"}
        results = geocode("Rua Giusepe Fórmolo, 210", contexto=contexto)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-29.2")
        self.assertEqual(results[0]["lon"], "-51.2")
        self.assertEqual(results[0]["display_name"], "Rua Giuseppe Fôrmolo")
        self.assertEqual(results[0]["provider"], "osm-overpass")
        mock_corrigir.assert_called_once_with("Rua Giusepe Fórmolo", "-51.30,-29.10,-51.10,-29.25")

    @patch('sig_bus.geocoding.corrigir')
    @patch('sig_bus.geocoding.NominatimGeocoder.geocode')
    def test_nome_corrigido_refaz_uma_busca_no_nominatim(self, mock_nominatim, mock_corrigir):
        """Passo 113: o `center` da via do Overpass não resolve número de casa —
        com o nome corrigido, o Nominatim é consultado mais uma vez, e é o
        resultado dele (com o número) que vale."""
        mock_corrigir.return_value = ("Rua Giuseppe Fôrmolo", -29.20, -51.20)
        # 1ª chamada: cascata normal, vazia. 2ª: reteste com o nome corrigido.
        mock_nominatim.side_effect = [
            [],
            [{"lat": "-29.1834", "lon": "-51.1892",
              "display_name": "Rua Giuseppe Fôrmolo, 210", "provider": "nominatim"}],
        ]

        contexto = {"viewbox": "-51.30,-29.10,-51.10,-29.25"}
        with patch('sig_bus.geocoding.PhotonGeocoder.geocode', return_value=[]):
            results = geocode("Rua Giusepe Fórmolo, 210", contexto=contexto)

        self.assertEqual(mock_nominatim.call_count, 2)
        self.assertEqual(mock_nominatim.call_args_list[1].args[0], "Rua Giuseppe Fôrmolo, 210")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-29.1834")
        # Grafia corrigida se declara (decisão 59): o nome real vai no candidato.
        self.assertEqual(results[0]["properties"]["street"], "Rua Giuseppe Fôrmolo")

    @patch('sig_bus.geocoding.corrigir')
    @patch('sig_bus.geocoding.NominatimGeocoder.geocode')
    def test_corretor_nao_roda_quando_algum_provedor_acertou(self, mock_nominatim, mock_corrigir):
        mock_nominatim.return_value = [{"lat": "-29.16", "lon": "-51.17"}]

        geocode("Rua Giusepe Fórmolo, 210", contexto={"viewbox": "-51.30,-29.10,-51.10,-29.25"})

        mock_corrigir.assert_not_called()

    @patch('sig_bus.geocoding.corrigir')
    @patch('sig_bus.geocoding.NominatimGeocoder.geocode')
    def test_nada_encontrado_ainda_devolve_vazio(self, mock_nominatim, mock_corrigir):
        mock_nominatim.return_value = []
        mock_corrigir.return_value = None

        with patch('sig_bus.geocoding.PhotonGeocoder.geocode', return_value=[]):
            results = geocode("Rua Inexistente ZZZ, 999",
                              contexto={"viewbox": "-51.30,-29.10,-51.10,-29.25"})

        self.assertEqual(results, [])


@unittest.skipUnless(_QGIS_REAL, _SEM_QGIS)
class TestGeocodingConfigUI(unittest.TestCase):

    def test_botao_configurar_metodo_existem(self):
        from sig_bus.SigBus_dialog import SigBusDialog
        self.assertTrue(hasattr(SigBusDialog, '_open_geocoding_config'))


@unittest.skipUnless(_QGIS_REAL, _SEM_QGIS)
class TestProviderOrigin(unittest.TestCase):
    """Passo 114 (decisão 70): a procedência do ponto precisa aparecer na UI
    sem exigir instanciar o diálogo — os helpers usados são `@staticmethod`."""

    def test_rotulo_por_provider(self):
        from sig_bus.SigBus_dialog import SigBusDialog
        self.assertEqual(SigBusDialog._candidate_provider_label({"provider": "google"}), "Google")
        self.assertEqual(SigBusDialog._candidate_provider_label({"provider": "osm-overpass"}), "OSM")
        self.assertEqual(SigBusDialog._candidate_provider_label({"provider": "nominatim"}), "Nominatim")
        self.assertEqual(SigBusDialog._candidate_provider_label({"provider": "photon"}), "Photon")

    def test_candidato_antigo_sem_provider_nao_quebra(self):
        from sig_bus.SigBus_dialog import SigBusDialog
        candidato = {"lat": "-29.16", "lon": "-51.17", "display_name": "Rua Teste"}
        self.assertIsNone(SigBusDialog._candidate_provider_label(candidato))
        self.assertEqual(SigBusDialog._candidate_item_label(candidato), "Rua Teste")

    def test_mensagem_fim_de_lote_com_falhas_parciais(self):
        """Passo 115: a mensagem de fim de lote (passo 102) cita endereços com falhas parciais."""
        from sig_bus.SigBus_dialog import SigBusDialog, Qgis

        dialog = SigBusDialog.__new__(SigBusDialog)
        dialog.input_city = MagicMock()
        dialog.input_city.text.return_value = "Caxias do Sul"
        dialog.input_state = MagicMock()
        dialog.input_state.text.return_value = "RS"
        dialog.input_country = MagicMock()
        dialog.input_country.text.return_value = "Brasil"
        dialog._working_copy = None

        row1 = {"input_address": MagicMock(), "lat": None, "lon": None}
        row1["input_address"].text.return_value = "Rua Giuseppe Fôrmolo, 210"
        row2 = {"input_address": MagicMock(), "lat": None, "lon": None}
        row2["input_address"].text.return_value = "Rua Inexistente ZZZ, 999"
        dialog.stop_rows = [row1, row2]

        def mock_set_status(r, status, ok):
            pass
        def mock_set_localizado(r, addr, cand):
            r["lat"] = -29.16
            r["lon"] = -51.17
        dialog._set_stop_row_status = mock_set_status
        dialog._set_stop_row_localizado = mock_set_localizado

        mock_bar = MagicMock()
        mock_iface = MagicMock()
        mock_iface.messageBar.return_value = mock_bar

        with patch('sig_bus.SigBus_dialog.iface', mock_iface), \
             patch('sig_bus.geocoding.geocode') as mock_geo, \
             patch('sig_bus.geocoding.NominatimGeocoder.city_bbox', return_value="-51.3,-29.0,-51.0,-29.3"):
            
            mock_geo.side_effect = [
                [{"lat": -29.16, "lon": -51.17}],
                []
            ]
            dialog._geocode_stops()

            mock_bar.pushMessage.assert_called_once()
            args, kwargs = mock_bar.pushMessage.call_args
            self.assertIn("1 parada(s) localizada(s), 1 não localizada(s)", args[1])
            self.assertIn('"Rua Inexistente ZZZ, 999"', args[1])
            self.assertEqual(kwargs.get("level"), Qgis.MessageLevel.Warning)

    def test_pista_sem_chave_oferece_configurar(self):
        """Passo 115: sem chave, a mensagem de fim de lote oferece a saída paga."""
        from sig_bus.SigBus_dialog import SigBusDialog

        with patch('sig_bus.geocoding_config.get_google_api_key', return_value=""):
            pista = SigBusDialog._pista_de_geocodificacao()

        self.assertIn("Configurar geocodificação…", pista)
        self.assertIn("Google", pista)

    def test_pista_com_chave_quebrada_mostra_o_erro_do_google(self):
        """Passo 115 (decisão 64): chave quebrada não pode ser confundida com
        erro de grafia — a causa provável vai na mensagem."""
        from sig_bus.SigBus_dialog import SigBusDialog
        from sig_bus.geocoding import GoogleGeocoder

        GoogleGeocoder.ultimo_erro = "REQUEST_DENIED: The provided API key is invalid."
        try:
            with patch('sig_bus.geocoding_config.get_google_api_key', return_value="CHAVE"):
                pista = SigBusDialog._pista_de_geocodificacao()
        finally:
            GoogleGeocoder.ultimo_erro = None

        self.assertIn("REQUEST_DENIED", pista)
        self.assertIn("não a grafia", pista)

    def test_pista_com_chave_boa_nao_acrescenta_nada(self):
        from sig_bus.SigBus_dialog import SigBusDialog
        from sig_bus.geocoding import GoogleGeocoder

        GoogleGeocoder.ultimo_erro = None
        with patch('sig_bus.geocoding_config.get_google_api_key', return_value="CHAVE"):
            self.assertEqual(SigBusDialog._pista_de_geocodificacao(), "")


if __name__ == '__main__':
    unittest.main()



