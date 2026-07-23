# -*- coding: utf-8 -*-
"""
/***************************************************************************
 osm_routing — Funções de roteamento baseado em dados do OpenStreetMap (OSM)
                                 A QGIS plugin
 Gerencia o download da rede viária do OSM via Overpass API e o roteamento
 entre paradas de ônibus.
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 * *************************************************************************/
"""

import json
import math
from qgis.core import (
    QgsBlockingNetworkRequest,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY
)
from qgis.analysis import (
    QgsVectorLayerDirector,
    QgsGraphBuilder,
    QgsNetworkDistanceStrategy,
    QgsGraphAnalyzer
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

# Cache de memória por conjunto de paradas (chave: tupla de coordenadas lat/lon)
_WAYS_CACHE = {}

def fetch_ways_for_stops(paradas_em_ordem, margem_m=300):
    """
    Monta uma bbox única cobrindo todas as paradas da linha com uma margem de
    margem_m metros ao redor e consulta o Overpass API uma vez pedindo
    as vias (highway=*).

    :param paradas_em_ordem: Lista de dicionários representando as paradas,
                             onde cada parada deve conter 'stop_lat' e 'stop_lon'.
    :param margem_m: Margem em metros ao redor da bounding box (default: 300).
    :return: Lista de elementos OSM (ways e nodes) do campo 'elements' da
             resposta do Overpass. Em caso de erro, retorna lista vazia [].
    """
    if not paradas_em_ordem:
        return []

    lats = []
    lons = []
    for p in paradas_em_ordem:
        try:
            # Tolerância se os valores forem strings ou None
            lat_val = p.get("stop_lat")
            lon_val = p.get("stop_lon")
            if lat_val is not None and lon_val is not None:
                lats.append(float(lat_val))
                lons.append(float(lon_val))
        except (ValueError, TypeError):
            continue

    if not lats or not lons:
        return []

    # Criar chave hashable para o cache de memória
    cache_key = tuple(zip(lats, lons))
    if cache_key in _WAYS_CACHE:
        return _WAYS_CACHE[cache_key]

    min_lat = min(lats)
    max_lat = max(lats)
    min_lon = min(lons)
    max_lon = max(lons)

    # Conversão de metros para graus
    # 1 grau de latitude é aprox. 111.111 metros
    lat_margin = margem_m / 111111.0
    
    # 1 grau de longitude depende da latitude
    avg_lat = (min_lat + max_lat) / 2.0
    cos_lat = math.cos(math.radians(avg_lat))
    if abs(cos_lat) < 0.0001:
        cos_lat = 0.0001
    lon_margin = margem_m / (111111.0 * cos_lat)

    bbox_min_lat = min_lat - lat_margin
    bbox_max_lat = max_lat + lat_margin
    bbox_min_lon = min_lon - lon_margin
    bbox_max_lon = max_lon + lon_margin

    bbox_str = "{:.6f},{:.6f},{:.6f},{:.6f}".format(
        bbox_min_lat, bbox_min_lon, bbox_max_lat, bbox_max_lon
    )

    # Query Overpass para pegar as vias de highway e seus nós recursivamente
    query = (
        "[out:json][timeout:25];"
        "(way[\"highway\"]({});>;);"
        "out body;"
    ).format(bbox_str)

    url = "https://overpass-api.de/api/interpreter"
    
    try:
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", b"SIG-Bus-QGIS/0.4 (OSM Routing)")
        req.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, 
            "application/x-www-form-urlencoded"
        )
        
        payload = "data={}".format(QUrl.toPercentEncoding(query).data().decode("utf-8"))
        
        blocking = QgsBlockingNetworkRequest()
        res = blocking.post(req, payload.encode("utf-8"), True)
        
        if res != QgsBlockingNetworkRequest.NoError:
            return []
            
        reply = blocking.reply()
        if not reply:
            return []
            
        content = bytes(reply.content()).decode("utf-8")
        if not content:
            return []
            
        data = json.loads(content)
        elements = data.get("elements", [])
        
        # Guarda no cache se obtivermos uma resposta parseada com sucesso
        _WAYS_CACHE[cache_key] = elements
        return elements
        
    except Exception:
        # Fallback silencioso da decisão 27: erro de rede ou parsing retorna lista vazia
        return []


def build_road_graph(elementos_osm):
    """
    Usa QgsVectorLayerDirector + QgsGraphBuilder para montar, a partir de elementos OSM,
    uma camada de linhas em memória e retorna um único grafo roteável para a linha inteira.

    :param elementos_osm: Lista de elementos OSM (ways e nodes) do Overpass API.
    :return: QgsGraph roteável construído.
    """
    if not elementos_osm:
        elementos_osm = []

    # 1. Mapear nodes por ID para obter coordenadas (lon, lat)
    nodes = {}
    for el in elementos_osm:
        if el.get("type") == "node":
            nid = el.get("id")
            lat = el.get("lat")
            lon = el.get("lon")
            if nid is not None and lat is not None and lon is not None:
                nodes[nid] = (float(lon), float(lat))

    # 2. Criar camada temporária de linhas em memória
    layer = QgsVectorLayer("LineString?crs=EPSG:4326", "osm_vias", "memory")
    provider = layer.dataProvider()

    features = []
    for el in elementos_osm:
        if el.get("type") == "way":
            way_nodes = el.get("nodes", [])
            points = []
            for nid in way_nodes:
                if nid in nodes:
                    lon, lat = nodes[nid]
                    points.append(QgsPointXY(lon, lat))
            
            if len(points) >= 2:
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPolylineXY(points))
                features.append(feat)

    if features:
        provider.addFeatures(features)
    layer.updateExtents()

    # 3. Construir o grafo
    director = QgsVectorLayerDirector(layer, -1, '', '', '', QgsVectorLayerDirector.DirectionBoth)
    strategy = QgsNetworkDistanceStrategy()
    director.addStrategy(strategy)

    builder = QgsGraphBuilder(layer.crs())
    tied_points = []
    director.makeGraph(builder, tied_points)
    
    return builder.graph()


def shortest_path(grafo, ponto_a, ponto_b):
    """
    Faz snap de cada ponto ao vértice mais próximo do grafo e usa
    QgsGraphAnalyzer.dijkstra (Dijkstra) para achar o caminho entre eles.

    :param grafo: QgsGraph construído.
    :param ponto_a: Ponto de partida (QgsPointXY, dict com stop_lat/stop_lon ou tupla/lista [lon, lat]).
    :param ponto_b: Ponto de destino (QgsPointXY, dict com stop_lat/stop_lon ou tupla/lista [lon, lat]).
    :return: Lista de objetos QgsPointXY representando o caminho na malha viária,
             ou None se os pontos estiverem em componentes desconexas do grafo
             ou se o grafo não tiver vértices.
    """
    if not grafo or grafo.vertexCount() == 0:
        return None

    def get_qgspoint(p):
        if isinstance(p, QgsPointXY):
            return p
        if isinstance(p, dict):
            lat = p.get("stop_lat") or p.get("lat") or p.get("y")
            lon = p.get("stop_lon") or p.get("lon") or p.get("x")
            if lat is not None and lon is not None:
                return QgsPointXY(float(lon), float(lat))
        if hasattr(p, "x") and hasattr(p, "y"):
            return QgsPointXY(p.x(), p.y())
        if isinstance(p, (tuple, list)) and len(p) >= 2:
            return QgsPointXY(float(p[0]), float(p[1]))
        raise ValueError("Formato de ponto inválido")

    try:
        pt_a = get_qgspoint(ponto_a)
        pt_b = get_qgspoint(ponto_b)
    except Exception:
        return None

    idx_a = -1
    idx_b = -1
    min_dist_a = float("inf")
    min_dist_b = float("inf")

    for i in range(grafo.vertexCount()):
        v_pt = grafo.vertex(i).point()
        dist_a = v_pt.distance(pt_a)
        if dist_a < min_dist_a:
            min_dist_a = dist_a
            idx_a = i
        dist_b = v_pt.distance(pt_b)
        if dist_b < min_dist_b:
            min_dist_b = dist_b
            idx_b = i

    if idx_a == -1 or idx_b == -1:
        return None

    tree, cost = QgsGraphAnalyzer.dijkstra(grafo, idx_a, 0)
    
    if idx_b != idx_a and tree[idx_b] == -1:
        return None

    path_indices = []
    curr = idx_b
    path_indices.append(curr)
    while curr != idx_a:
        edge_idx = tree[curr]
        if edge_idx == -1:
            return None
        edge = grafo.edge(edge_idx)
        pred = edge.fromVertex() if edge.toVertex() == curr else edge.toVertex()
        curr = pred
        path_indices.append(curr)

    path_indices.reverse()
    return [grafo.vertex(idx).point() for idx in path_indices]


def route_stops(paradas_em_ordem):
    """
    Orquestra o roteamento para a sequência de paradas fornecida.
    Obtém as vias do OSM via Overpass, constrói o grafo viário e calcula
    o caminho mais curto (shortest_path) entre cada par consecutivo de paradas.
    Se algum trecho falhar ou estiver desconectado, usa a reta equivalente
    entre o par de paradas.

    :param paradas_em_ordem: Lista de paradas (dicionários com stop_lat/stop_lon,
                             objetos QgsPointXY ou outros formatos).
    :return: Lista de objetos QgsPointXY representando o traçado completo e contínuo.
    """
    if not paradas_em_ordem:
        return []

    def to_qgspoint(p):
        if isinstance(p, QgsPointXY):
            return p
        if isinstance(p, dict):
            lat = p.get("stop_lat") or p.get("lat") or p.get("y")
            lon = p.get("stop_lon") or p.get("lon") or p.get("x")
            if lat is not None and lon is not None:
                return QgsPointXY(float(lon), float(lat))
        if hasattr(p, "x") and hasattr(p, "y"):
            return QgsPointXY(p.x(), p.y())
        if isinstance(p, (tuple, list)) and len(p) >= 2:
            return QgsPointXY(float(p[0]), float(p[1]))
        raise ValueError("Formato de ponto inválido")

    # Converter todas as paradas válidas para QgsPointXY
    pontos = []
    for p in paradas_em_ordem:
        try:
            pt = to_qgspoint(p)
            pontos.append(pt)
        except Exception:
            continue

    if len(pontos) < 2:
        return pontos

    # Formata as paradas como dicionários esperados por fetch_ways_for_stops
    paradas_formatadas = [{"stop_lat": pt.y(), "stop_lon": pt.x()} for pt in pontos]

    elementos_osm = []
    try:
        elementos_osm = fetch_ways_for_stops(paradas_formatadas)
    except Exception:
        pass

    grafo = None
    if elementos_osm:
        try:
            grafo = build_road_graph(elementos_osm)
        except Exception:
            pass

    resultado = []
    for i in range(len(pontos) - 1):
        pt_a = pontos[i]
        pt_b = pontos[i+1]

        caminho = None
        if grafo and grafo.vertexCount() > 0:
            try:
                caminho = shortest_path(grafo, pt_a, pt_b)
            except Exception:
                pass

        if not caminho or len(caminho) < 2:
            # Fallback silencioso: linha reta entre pt_a e pt_b
            caminho = [pt_a, pt_b]

        if not resultado:
            resultado.extend(caminho)
        else:
            resultado.extend(caminho[1:])

    return resultado


