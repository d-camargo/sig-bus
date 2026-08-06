# -*- coding: utf-8 -*-
"""
/***************************************************************************
 street_index — Corretor de grafia de logradouros sobre o banco vivo do OSM
                                 A QGIS plugin
 Consulta o Overpass API pelos nomes de vias dentro de uma bbox e sugere a
 grafia mais parecida quando os demais provedores de geocodificação não
 encontram nada (decisão 68).
 ***************************************************************************/
"""

import json
import traceback
from difflib import get_close_matches

from qgis.core import Qgis, QgsMessageLog, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from .address_format import normalizar_logradouro
from .geocoding_config import LOG_TAG

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = b"SIG-Bus-QGIS/0.4 (Street Index)"

# Cache de sessão dos nomes de vias já buscados, indexado pela viewbox.
_CACHE = {}


def _log(mensagem, nivel):
    QgsMessageLog.logMessage("Corretor de grafia: {}".format(mensagem), LOG_TAG, nivel)


def _montar_query(viewbox):
    """Converte a viewbox do Nominatim ('lon_min,lat_max,lon_max,lat_min') para
    a ordem de bbox do Overpass ('lat_min,lon_min,lat_max,lon_max' — decisão 69)
    e monta a query que traz as vias nomeadas e o centro de cada uma."""
    lon_min, lat_max, lon_max, lat_min = [p.strip() for p in str(viewbox).split(",")]
    bbox = "{},{},{},{}".format(lat_min, lon_min, lat_max, lon_max)
    return '[out:json][timeout:25];way["highway"]["name"]({});out tags center;'.format(bbox)


def nomes_de_vias(viewbox):
    """
    Consulta o Overpass API (banco vivo do OSM, não os índices derivados que
    Nominatim/Photon consultam) pelas vias nomeadas dentro da bbox.

    Nunca levanta exceção: erro de rede, JSON inválido ou viewbox ausente
    devolvem lista vazia. Guarda o resultado num cache de sessão indexado pela
    viewbox — a mesma viewbox não refaz a requisição.

    :param viewbox: bbox no formato do Nominatim
                     ('lon_min,lat_max,lon_max,lat_min').
    :return: lista de tuplas (nome, lat, lon) ou [] em qualquer falha.
    """
    if not viewbox:
        return []

    if viewbox in _CACHE:
        return _CACHE[viewbox]

    try:
        partes = str(viewbox).split(",")
        if len(partes) != 4:
            return []

        query = _montar_query(viewbox)
        url = "{}?data={}".format(
            OVERPASS_URL, QUrl.toPercentEncoding(query).data().decode("utf-8"))

        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", USER_AGENT)

        manager = QgsNetworkAccessManager.instance()
        if not manager:
            _log("QgsNetworkAccessManager indisponível", Qgis.MessageLevel.Warning)
            return []

        reply = manager.blockingGet(req)
        if not reply:
            _log("sem resposta do Overpass", Qgis.MessageLevel.Warning)
            return []

        if reply.error() != QNetworkReply.NetworkError.NoError:
            _log("falha de rede (erro={})".format(reply.error()), Qgis.MessageLevel.Warning)
            return []

        content = bytes(reply.content()).decode("utf-8")
        if not content:
            _log("resposta vazia do Overpass", Qgis.MessageLevel.Warning)
            return []

        data = json.loads(content)
        elementos = data.get("elements") if isinstance(data, dict) else None
        if not isinstance(elementos, list):
            return []

        vias = []
        for el in elementos:
            if not isinstance(el, dict):
                continue
            tags = el.get("tags") or {}
            nome = tags.get("name")
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")
            if nome and lat is not None and lon is not None:
                vias.append((nome, lat, lon))

        _CACHE[viewbox] = vias
        return vias

    except Exception:
        _log("exceção ao consultar o Overpass\n{}".format(traceback.format_exc()),
             Qgis.MessageLevel.Warning)
        return []


def corrigir(logradouro, viewbox):
    """
    Sugere a grafia real de um logradouro a partir do banco vivo do OSM, por
    similaridade de texto — plano B para quando nenhum provedor de
    geocodificação encontrou o endereço digitado.

    Nunca levanta exceção nem bloqueia o fluxo (decisão 19): sem logradouro,
    sem viewbox ou sem via parecida o suficiente (`cutoff=0.80`), devolve None.

    :param logradouro: texto digitado pelo usuário.
    :param viewbox: bbox no formato do Nominatim
                     ('lon_min,lat_max,lon_max,lat_min').
    :return: tupla (nome_real, lat, lon) do candidato mais parecido, ou None.
    """
    if not logradouro or not viewbox:
        return None

    vias = nomes_de_vias(viewbox)
    if not vias:
        return None

    indice = {}
    for nome, lat, lon in vias:
        chave = normalizar_logradouro(nome)
        if chave and chave not in indice:
            indice[chave] = (nome, lat, lon)

    if not indice:
        return None

    alvo = normalizar_logradouro(logradouro)
    candidatos = get_close_matches(alvo, list(indice.keys()), n=1, cutoff=0.80)
    if not candidatos:
        return None

    return indice[candidatos[0]]
