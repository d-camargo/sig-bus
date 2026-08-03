# -*- coding: utf-8 -*-
"""Testes para sig_bus/map_tools.py (Fase 8, passos 81 e 82)."""
import os

import pytest

# map_tools depende de qgis.gui e da reprojeção real do PROJ, que os mocks do
# conftest não cobrem: fora de um QGIS de verdade o módulo inteiro é pulado.
if os.environ.get('FORCE_MOCK_QGIS'):
    pytest.skip("exige QGIS real (rodando com os mocks do conftest)",
                allow_module_level=True)
pytest.importorskip("qgis.gui", reason="exige QGIS real")

from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY  # noqa: E402
from sig_bus.map_tools import (  # noqa: E402
    OSM_LAYER_NAME,
    ensure_osm_basemap,
    to_wgs84,
)


@pytest.fixture
def projeto_vazio():
    from qgis.core import QgsProject

    projeto = QgsProject.instance()
    for camada_id in list(projeto.mapLayers().keys()):
        projeto.removeMapLayer(camada_id)
    yield projeto
    for camada_id in list(projeto.mapLayers().keys()):
        projeto.removeMapLayer(camada_id)


def test_to_wgs84_identidade_em_4326():
    lon, lat = to_wgs84(
        QgsPointXY(-51.1794, -29.1634),
        QgsCoordinateReferenceSystem("EPSG:4326"))
    assert lon == pytest.approx(-51.1794, abs=1e-4)
    assert lat == pytest.approx(-29.1634, abs=1e-4)


def test_to_wgs84_reprojeta_de_utm_22s():
    # Ponto conhecido de Caxias do Sul (RS) em SIRGAS 2000 / UTM 22S.
    # Referência conferida fora do QGIS, direto no PROJ (osgeo.osr).
    lon, lat = to_wgs84(
        QgsPointXY(482000.0, 6771000.0),
        QgsCoordinateReferenceSystem("EPSG:31982"))
    assert lon == pytest.approx(-51.18514, abs=1e-4)
    assert lat == pytest.approx(-29.18954, abs=1e-4)


def test_ensure_osm_basemap_nao_duplica(projeto_vazio):
    primeira = ensure_osm_basemap(projeto_vazio)
    if primeira is None:
        pytest.skip("provedor XYZ indisponível neste ambiente")
    segunda = ensure_osm_basemap(projeto_vazio)

    assert segunda is primeira
    assert len(projeto_vazio.mapLayersByName(OSM_LAYER_NAME)) == 1


def test_ensure_osm_basemap_respeita_raster_existente(projeto_vazio):
    """Decisão 50: com um raster de fundo já no projeto, não acrescenta nada."""
    from qgis.core import QgsRasterLayer

    projeto_vazio.addMapLayer(
        QgsRasterLayer("type=xyz&url=http://exemplo/%7Bz%7D.png", "Fundo", "wms"))

    assert ensure_osm_basemap(projeto_vazio) is None
    assert projeto_vazio.mapLayersByName(OSM_LAYER_NAME) == []
