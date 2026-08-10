# -*- coding: utf-8 -*-
"""
map_tools — Ferramentas auxiliares de mapa e basemap para o SIG-Bus
(Fase 8, passos 81 e 82; decisões 49 e 50).
"""
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterLayer,
)
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt.QtCore import Qt

OSM_TILE_URL = (
    "type=xyz&url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png"
    "&zmax=19&zmin=0"
)
# Nome canônico: é por ele que ensure_osm_basemap reconhece a camada que já
# criou antes e evita duplicá-la (decisão 50).
OSM_LAYER_NAME = "OpenStreetMap (SIG-Bus)"


def to_wgs84(ponto, crs_origem):
    """Converte um ponto do CRS de origem para EPSG:4326 e devolve (lon, lat).

    Devolve as coordenadas do ponto sem conversão quando a origem já é
    EPSG:4326 ou quando a transformação falha — nunca levanta exceção.
    """
    destino = QgsCoordinateReferenceSystem("EPSG:4326")
    try:
        if crs_origem is None or crs_origem == destino:
            return ponto.x(), ponto.y()
        transformado = QgsCoordinateTransform(
            crs_origem, destino, QgsProject.instance()).transform(ponto)
        return transformado.x(), transformado.y()
    except Exception:
        return ponto.x(), ponto.y()


class PickStopPointTool(QgsMapToolEmitPoint):
    """Marca uma parada clicando no canvas do QGIS (decisão 49).

    Chama ``callback(lon, lat)`` — sempre em EPSG:4326, qualquer que seja o
    CRS do projeto — no clique com o botão esquerdo. Clique com o botão
    direito cancela sem chamar o callback; o ESC é tratado por quem ativa a
    ferramenta, junto com a restauração do ``mapTool`` anterior.
    """

    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self._canvas = canvas
        self._callback = callback
        self.canvasClicked.connect(self._on_canvas_clicked)

    def _on_canvas_clicked(self, point, button):
        if button == Qt.MouseButton.RightButton:
            return
        lon, lat = to_wgs84(point, self._canvas.mapSettings().destinationCrs())
        self._callback(lon, lat)


def ensure_osm_basemap(project=None):
    """Garante um fundo de referência OSM no projeto, sem nunca duplicá-lo
    nem cobrir os dados do usuário (decisão 50).

    Devolve a camada canônica se ela já existir; não cria nada se o projeto
    já tiver qualquer raster servindo de fundo; caso contrário cria o XYZ da
    OSM e o insere no **fim** da árvore de camadas. Devolve ``None`` quando
    não há nada a criar ou a criação falha. Nunca levanta exceção.
    """
    try:
        if project is None:
            project = QgsProject.instance()

        existentes = project.mapLayersByName(OSM_LAYER_NAME)
        if existentes:
            return existentes[0]

        for camada in project.mapLayers().values():
            if isinstance(camada, QgsRasterLayer) and camada.isValid():
                return None

        layer = QgsRasterLayer(OSM_TILE_URL, OSM_LAYER_NAME, "wms")
        if not layer.isValid():
            return None

        # addToLegend=False + insert no fim da árvore: o fundo nunca entra
        # por cima das camadas de dados já carregadas.
        project.addMapLayer(layer, False)
        root = project.layerTreeRoot()
        root.insertLayer(len(root.children()), layer)
        return layer
    except Exception:
        return None
