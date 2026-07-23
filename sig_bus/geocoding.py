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

class NominatimGeocoder(object):
    """
    Classe para geocodificação de endereços usando o serviço público do Nominatim.
    Respeita a política de uso do Nominatim (limite de requisições, User-Agent).
    """
    _last_request_time = 0.0

    @classmethod
    def geocode(cls, endereco):
        """
        Geocodifica um endereço de texto livre usando a API do Nominatim.
        
        Garante um intervalo mínimo de 1 segundo entre requisições para respeitar a
        política de uso público do Nominatim (no mínimo 1 requisição por segundo).
        Nunca levanta exceção; em caso de erro de rede, parsing ou endereço não
        encontrado, retorna uma lista vazia.

        :param endereco: String contendo o endereço a ser geocodificado.
        :return: Lista de dicionários representando os candidatos encontrados,
                 onde cada item tem 'lat', 'lon', etc., ou lista vazia em caso de falha/vazio.
        """
        if not endereco:
            return []

        # Garante no mínimo 1 segundo de intervalo entre requisições
        now = time.time()
        elapsed = now - cls._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        cls._last_request_time = time.time()

        try:
            # Codifica o endereço de forma segura para a URL
            q_encoded = QUrl.toPercentEncoding(endereco).data().decode('utf-8')
            url = "https://nominatim.openstreetmap.org/search?format=json&q={}".format(q_encoded)

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
