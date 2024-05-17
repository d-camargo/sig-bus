import sys

from qgis.core import QgsApplication, QgsProcessingFeedback
from qgis.analysis import QgsNativeAlgorithms

QgsApplication.setPrefixPath(r'F:/Program Files/QGIS-3.22.5/apps/qgis-ltr/python', True)
qgs = QgsApplication([], False)
qgs.initQgis()

# Add the path to processing so we can import it next
sys.path.append(r'F:/Program Files/QGIS-3.22.5/apps/qgis-ltr/python/plugins')
# Imports usually should be at the top of a script but this unconventional
# order is necessary here because QGIS has to be initialized first
import processing
from processing.core.Processing import Processing

Processing.initialize()
QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
feedback = QgsProcessingFeedback()

airport = r'F:\01_PyQGIS\EXEMPLO_PYTHON_QGIS\ne_10m_airports.shp'
output = r'F:\01_PyQGIS\EXEMPLO_PYTHON_QGIS\congonhas.shp'
expression = "name LIKE '%Congonhas%'"

congonhas = processing.run(
    'native:extractbyexpression',
    {'INPUT': airport, 'EXPRESSION': expression, 'OUTPUT': output},
    feedback=feedback
)['OUTPUT']

print(congonhas)
print("ok")