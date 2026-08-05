# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import sys
import time
from urllib.parse import unquote

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from qgis.PyQt.QtNetwork import QNetworkReply
from sig_bus.geocoding import NominatimGeocoder, PhotonGeocoder

class TestGeocoding(unittest.TestCase):

    def setUp(self):
        # Reinicia o tempo da última requisição para evitar delays reais nos testes
        NominatimGeocoder._last_request_time = 0.0
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

        results = NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

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

        results = NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

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

        results = NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["lat"], "-29.16")

    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_photon_vazio_ou_erro_devolve_lista_vazia(self, mock_instance, mock_sleep):
        self._mock_manager(mock_instance, [b'[]', b'[]', b'[]', b'[]'])

        results = NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

        self.assertEqual(results, [])

    @patch('sig_bus.geocoding.QgsMessageLog')
    @patch('sig_bus.geocoding.time.sleep')
    @patch('sig_bus.geocoding.QgsNetworkAccessManager.instance')
    def test_cascata_completa_registra_etiquetas_na_ordem(self, mock_instance, mock_sleep, mock_log):
        self._mock_manager(mock_instance,
                           [b'[]', b'[]', b'[]', b'{"type": "FeatureCollection", "features": []}'])

        NominatimGeocoder.geocode(self.ENDERECO, self.CONTEXTO)

        msgs = [chamada.args[0] for chamada in mock_log.logMessage.call_args_list]
        etiquetas = [m.split("]")[0].split("[")[1] for m in msgs if "[" in m]
        self.assertEqual(etiquetas,
                         ["a-estruturada-num", "b-estruturada", "c-livre", "photon"])


class TestCityBbox(unittest.TestCase):

    def setUp(self):
        NominatimGeocoder._last_request_time = 0.0
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
        NominatimGeocoder._last_request_time = 0.0
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


if __name__ == '__main__':
    unittest.main()

