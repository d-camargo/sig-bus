# -*- coding: utf-8 -*-
"""
/***************************************************************************
 osm_geocoding — Geocodificação usando a API pública do Nominatim (OpenStreetMap)
                                 A QGIS plugin
 ***************************************************************************/
"""

import time
import json
from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from .address_format import parse_address

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


def _pct(valor):
    """Codifica um valor de forma segura para a URL."""
    return QUrl.toPercentEncoding(str(valor)).data().decode('utf-8')


class NominatimGeocoder(object):
    """
    Classe para geocodificação de endereços usando o serviço público do Nominatim.
    Respeita a política de uso do Nominatim (limite de requisições, User-Agent).
    """
    _last_request_time = 0.0

    @classmethod
    def geocode(cls, endereco, contexto=None):
        """
        Geocodifica um endereço usando a API do Nominatim.

        Sem contexto, faz uma busca livre — o comportamento histórico. Com
        contexto (decisões 44 e 47), faz busca estruturada em cascata, parando
        no primeiro acerto: (a) estruturada com número; (b) estruturada sem
        número (rua inteira); (c) busca livre com município/UF/país anexados.

        Garante um intervalo mínimo de 1 segundo entre requisições reais para
        respeitar a política de uso público do Nominatim. Nunca levanta exceção;
        em caso de erro de rede, parsing ou endereço não encontrado, retorna uma
        lista vazia.

        :param endereco: String contendo o endereço a ser geocodificado.
        :param contexto: Dicionário opcional com 'city', 'state', 'country' e
                         'viewbox' (bbox do município no formato
                         'lon_min,lat_max,lon_max,lat_min').
        :return: Lista de dicionários representando os candidatos encontrados,
                 onde cada item tem 'lat', 'lon', etc., ou lista vazia em caso de falha/vazio.
        """
        if not endereco:
            return []

        try:
            urls = cls._montar_urls(endereco, contexto)
        except Exception:
            return []

        for url in urls:
            resultados = cls._buscar(url)
            if resultados:
                return resultados
        return []

    @classmethod
    def city_bbox(cls, municipio, uf=None):
        """
        Retorna o bounding box do município no formato 'lon_min,lat_max,lon_max,lat_min'
        para ser utilizado como viewbox no contexto de geocodificação.

        :param municipio: Nome do município (str).
        :param uf: Sigla ou nome do estado (str, opcional).
        :return: String no formato 'lon_min,lat_max,lon_max,lat_min' ou None se não encontrado.
        """
        if not municipio:
            return None

        municipio_str = str(municipio).strip()
        if not municipio_str:
            return None

        uf_str = str(uf).strip() if uf else ""

        params = ["format=json", "countrycodes=br", "limit=1", "city={}".format(_pct(municipio_str))]
        if uf_str:
            params.append("state={}".format(_pct(uf_str)))
        params.append("country=Brasil")

        url = "{}?{}".format(NOMINATIM_SEARCH_URL, "&".join(params))
        resultados = cls._buscar(url)

        if not resultados:
            livre = [municipio_str]
            if uf_str:
                livre.append(uf_str)
            livre.append("Brasil")
            url = "{}?format=json&countrycodes=br&limit=1&q={}".format(
                NOMINATIM_SEARCH_URL, _pct(", ".join(livre))
            )
            resultados = cls._buscar(url)

        if resultados and isinstance(resultados, list) and len(resultados) > 0:
            item = resultados[0]
            bbox = item.get("boundingbox")
            if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                # Nominatim boundingbox: [lat_min, lat_max, lon_min, lon_max]
                # Viewbox format: lon_min,lat_max,lon_max,lat_min
                return "{},{},{},{}".format(bbox[2], bbox[1], bbox[3], bbox[0])

        return None

    @classmethod
    def _montar_urls(cls, endereco, contexto):
        """
        Monta as URLs da cascata de tentativas, na ordem em que devem ser feitas.

        Sem contexto, devolve uma única URL de busca livre (comportamento antigo).
        """
        if not contexto:
            return ["{}?format=json&q={}".format(NOMINATIM_SEARCH_URL, _pct(endereco))]

        partes = parse_address(endereco)
        logradouro = (partes.get("logradouro") or "").strip()
        numero = (partes.get("numero") or "").strip()
        bairro = (partes.get("bairro") or "").strip()

        municipio = (contexto.get("city") or "").strip()
        uf = (contexto.get("state") or "").strip()
        pais = (contexto.get("country") or "").strip() or "Brasil"
        viewbox = (contexto.get("viewbox") or "").strip()

        # Parâmetros comuns a todas as tentativas (decisões 44 e 47).
        comuns = ["format=json", "countrycodes=br", "limit=5", "addressdetails=1"]
        if viewbox:
            comuns += ["viewbox={}".format(_pct(viewbox)), "bounded=1"]

        def estruturada(street):
            params = ["street={}".format(_pct(street))]
            if municipio:
                params.append("city={}".format(_pct(municipio)))
            if uf:
                params.append("state={}".format(_pct(uf)))
            params.append("country={}".format(_pct(pais)))
            return "{}?{}".format(NOMINATIM_SEARCH_URL, "&".join(comuns + params))

        urls = []
        # (a) estruturada com número.
        if logradouro and numero:
            urls.append(estruturada("{} {}".format(numero, logradouro)))
        # (b) estruturada sem número (rua inteira → ponto no meio da via).
        if logradouro:
            urls.append(estruturada(logradouro))
        # (c) busca livre com município/UF/país anexados.
        livre = [p for p in (logradouro or endereco, numero, bairro) if p]
        if municipio:
            livre.append("{} - {}".format(municipio, uf) if uf else municipio)
        livre.append(pais)
        urls.append("{}?{}&q={}".format(
            NOMINATIM_SEARCH_URL, "&".join(comuns), _pct(", ".join(livre))))
        return urls

    @classmethod
    def _buscar(cls, url):
        """
        Faz uma requisição ao Nominatim, respeitando o intervalo de 1 segundo.

        Uma espera por requisição real. Devolve [] em qualquer falha.
        """
        # Garante no mínimo 1 segundo de intervalo entre requisições
        now = time.time()
        elapsed = now - cls._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        cls._last_request_time = time.time()

        try:
            req = QNetworkRequest(QUrl(url))
            req.setRawHeader(b"User-Agent", b"SIG-Bus-QGIS/0.4 (Geocoding)")

            manager = QgsNetworkAccessManager.instance()
            if not manager:
                return []

            # Executa a requisição síncrona/bloqueante no QGIS
            reply = manager.blockingGet(req)
            if not reply:
                return []

            if reply.error() != QNetworkReply.NoError:
                return []

            content = bytes(reply.content()).decode("utf-8")
            if not content:
                return []

            data = json.loads(content)
            if isinstance(data, list):
                return data
            return []

        except Exception:
            # Garante que nenhuma exceção seja propagada, conforme especificação
            return []
