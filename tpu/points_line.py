import sys
from qgis._gui import QgsMapCanvas
from qgis.core import (QgsProject, QgsPathResolver)
from qgis.analysis import QgsNativeAlgorithms
from qgis.core import (
     QgsApplication,
     QgsProcessingFeedback,
     QgsVectorLayer
)
from qgis.core import QgsApplication, QgsProcessingFeedback
from qgis.analysis import QgsNativeAlgorithms

QgsApplication.setPrefixPath(r'F:/Program Files/QGIS-3.22.14/apps/qgis-ltr/python', True)
qgs = QgsApplication([], False)
qgs.initQgis()
# Add the path to processing so we can import it next
sys.path.append(r'F:/Program Files/QGIS-3.22.14/apps/qgis-ltr/python/plugins')

import processing
from processing.core.Processing import Processing

Processing.initialize()
QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())

registry = QgsProject.instance()
mapcanvas = QgsMapCanvas()
layer_path = [layer.source() for layer in registry.mapLayers().values()]
print("layer",layer_path)
print("registry",mapcanvas)
#myfilepath= layer[3].dataProvider().dataSourceUri()
names = [layer.name() for layer in QgsProject.instance().mapLayers().values()]
def search (lista, valor):
    return [(lista.index(x), x.index(valor)) for x in lista if valor in x]

pontos_path = layer_path[search(names,'pontos_1502 — pontos_1502_pc_2')[0]]
linha_path = layer_path[search(names,'pontos_1502 — linha_1502')[0]]

processing.run("native:snapgeometries",
               {'INPUT':pontos_path,'REFERENCE_LAYER':linha_path,'TOLERANCE':200,'BEHAVIOR':1,'OUTPUT':'TEMPORARY_OUTPUT'})


'''
feat_points = [feat for feat in points[0].getFeatures()]
feat_line = next(line.getFeatures())

new_points = []
pt = []
for feat in feat_points:
    geom = feat.geometry().asPoint()
    sqrdist, point, vertex = line.geometry().closestSegmentWithContext(geom)
    if sqrt(sqrdist) <= 5:
        new_points.append(point)
    else:
        new_points.append(pt)

epsg = points[0].crs().postgisSrid()

uri = "Point?crs=epsg:" + str(epsg) + "&field=id:integer""&index=yes"

mem_layer = QgsVectorLayer(uri,
                           'new_points',
                           'memory')

prov = mem_layer.dataProvider()

feats = [ QgsFeature() for i in range(len(new_points)) ]

for i, feat in enumerate(feats):
    feat.setAttributes([i])
    feat.setGeometry(QgsGeometry.fromPoint(new_points[i]))

prov.addFeatures(feats)

QgsMapLayerRegistry.instance().addMapLayer(mem_layer)'''