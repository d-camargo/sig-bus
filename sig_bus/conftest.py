import sys
import os
import types
from unittest.mock import MagicMock

# Define Mock Classes
class QgsPointXY:
    def __init__(self, x=0.0, y=0.0):
        if isinstance(x, QgsPointXY):
            self._x = x.x()
            self._y = x.y()
        else:
            self._x = float(x)
            self._y = float(y)
    def x(self):
        return self._x
    def y(self):
        return self._y
    def distance(self, other):
        import math
        return math.sqrt((self._x - other.x())**2 + (self._y - other.y())**2)

class QgsGeometry:
    def __init__(self, points=None):
        self._points = points or []
    @classmethod
    def fromPolylineXY(cls, polyline):
        return cls(polyline)
    @classmethod
    def fromPointXY(cls, pt):
        return cls([pt])
    def isEmpty(self):
        return len(self._points) == 0
    def asPolyline(self):
        return self._points
    def asPoint(self):
        return self._points[0] if self._points else None

class QgsField:
    def __init__(self, name, field_type=None):
        self._name = name
        self._type = field_type
    def name(self):
        return self._name

class QVariant:
    String = "String"
    Int = "Int"
    Double = "Double"

class QgsFeature:
    def __init__(self):
        self._geom = None
        self._attrs = []
        self._fields_dict = {}
    def setGeometry(self, geom):
        self._geom = geom
    def geometry(self):
        return self._geom
    def setAttributes(self, attrs):
        self._attrs = attrs
    def __getitem__(self, key):
        if isinstance(key, int):
            return self._attrs[key]
        return self._fields_dict.get(key)

class MockDataProvider:
    def __init__(self, layer):
        self._layer = layer
    def addAttributes(self, fields):
        for field in fields:
            self._layer._fields.append(field)
    def addFeature(self, feat):
        for i, val in enumerate(feat._attrs):
            if i < len(self._layer._fields):
                field_name = self._layer._fields[i].name()
                feat._fields_dict[field_name] = val
        self._layer._features.append(feat)
    def addFeatures(self, feats):
        for feat in feats:
            self.addFeature(feat)

class QgsVectorLayer:
    def __init__(self, uri="", name="", provider_lib=""):
        self._uri = uri
        self._name = name
        self._provider_name = provider_lib
        self._features = []
        self._fields = []
        if "|layername=" in uri:
            db_path, layer_name = uri.split("|layername=")
            from osgeo import ogr
            import os
            if os.path.exists(db_path):
                ds = ogr.Open(db_path, 0)
                if ds:
                    lyr = ds.GetLayerByName(layer_name)
                    if lyr:
                        layer_defn = lyr.GetLayerDefn()
                        field_count = layer_defn.GetFieldCount()
                        fields = [layer_defn.GetFieldDefn(i).GetName() for i in range(field_count)]
                        for feat_ogr in lyr:
                            feat = QgsFeature()
                            attrs = []
                            for f_name in fields:
                                val = feat_ogr.GetField(f_name)
                                feat._fields_dict[f_name] = val
                                attrs.append(val)
                            feat.setAttributes(attrs)
                            geom_ogr = feat_ogr.GetGeometryRef()
                            if geom_ogr:
                                geom_name = geom_ogr.GetGeometryName().lower()
                                if "point" in geom_name:
                                    pt = QgsPointXY(geom_ogr.GetX(), geom_ogr.GetY())
                                    feat.setGeometry(QgsGeometry.fromPointXY(pt))
                                elif "line" in geom_name:
                                    pts = []
                                    for pt_idx in range(geom_ogr.GetPointCount()):
                                        ogr_pt = geom_ogr.GetPoint(pt_idx)
                                        pts.append(QgsPointXY(ogr_pt[0], ogr_pt[1]))
                                    feat.setGeometry(QgsGeometry.fromPolylineXY(pts))
                            self._features.append(feat)
                    ds = None
    def isValid(self):
        return True
    def featureCount(self):
        return len(self._features)
    def getFeatures(self):
        return self._features
    def dataProvider(self):
        return MockDataProvider(self)
    def updateFields(self):
        pass
    def updateExtents(self):
        pass
    def crs(self):
        return "EPSG:4326"

class QgsMessageLog:
    @staticmethod
    def logMessage(message, tag="", level=0):
        pass

class Qgis:
    Info = 0
    Success = 1
    Warning = 2
    Critical = 3

class QgsCoordinateTransformContext:
    def __init__(self):
        pass

class QgsVectorFileWriter:
    NoError = 0
    ErrCreateDataSource = 1
    CreateOrOverwriteLayer = "CreateOrOverwriteLayer"
    class SaveVectorOptions:
        def __init__(self):
            self.driverName = "GPKG"
            self.layerName = ""
            self.actionOnExistingFile = None
    @staticmethod
    def writeAsVectorFormatV3(layer, path, transform_context, options):
        from osgeo import ogr
        ds = ogr.Open(path, 1)
        if not ds:
            return (QgsVectorFileWriter.ErrCreateDataSource, "Failed to open GeoPackage")
        lyr = ds.GetLayerByName(options.layerName)
        if lyr:
            ds.DeleteLayer(options.layerName)
            lyr = None
        if not lyr:
            from osgeo import osr
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)
            lyr = ds.CreateLayer(options.layerName, srs, ogr.wkbLineString)
            field_defn = ogr.FieldDefn("shape_id", ogr.OFTString)
            lyr.CreateField(field_defn)
        for feat in layer.getFeatures():
            ogr_feat = ogr.Feature(lyr.GetLayerDefn())
            ogr_feat.SetField("shape_id", str(feat["shape_id"]))
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                polyline = geom.asPolyline()
                ogr_geom = ogr.Geometry(ogr.wkbLineString)
                for pt in polyline:
                    ogr_geom.AddPoint(pt.x(), pt.y())
                ogr_feat.SetGeometry(ogr_geom)
            lyr.CreateFeature(ogr_feat)
        ds = None
        return (QgsVectorFileWriter.NoError, "Success")

class QgsVirtualLayerDefinition:
    def __init__(self):
        self._sources = []
        self._query = ""
    def addSource(self, name, source, provider):
        self._sources.append((name, source, provider))
    def setQuery(self, query):
        self._query = query
    def setGeometryField(self, field):
        pass
    def setUid(self, uid):
        pass
    def toString(self):
        return "virtual_layer"

# Graph related mocks
class QgsGraphVertex:
    def __init__(self, point):
        self._point = point
    def point(self):
        return self._point

class QgsGraphEdge:
    def __init__(self, from_v, to_v):
        self._from_v = from_v
        self._to_v = to_v
    def fromVertex(self):
        return self._from_v
    def toVertex(self):
        return self._to_v

class QgsGraph:
    def __init__(self):
        self._vertices = []
        self._edges = []
        self._adjacency = {}
    def addVertex(self, point):
        self._vertices.append(QgsGraphVertex(point))
        return len(self._vertices) - 1
    def addEdge(self, from_v, to_v, cost):
        edge = QgsGraphEdge(from_v, to_v)
        self._edges.append(edge)
        edge_idx = len(self._edges) - 1
        self._adjacency.setdefault(from_v, {})[to_v] = (edge_idx, cost)
        self._adjacency.setdefault(to_v, {})[from_v] = (edge_idx, cost)
        return edge_idx
    def vertexCount(self):
        return len(self._vertices)
    def vertex(self, idx):
        return self._vertices[idx]
    def edge(self, idx):
        return self._edges[idx]

class QgsGraphBuilder:
    def __init__(self, crs):
        self._graph = QgsGraph()
    def graph(self):
        return self._graph

class QgsVectorLayerDirector:
    DirectionBoth = 0
    def __init__(self, layer, directionFieldId, directDirectionValue, reverseDirectionValue, bothDirectionValue, defaultDirection):
        self._layer = layer
    def addStrategy(self, strategy):
        pass
    def makeGraph(self, builder, tied_points):
        graph = builder.graph()
        coord_map = {}
        def get_or_create_vertex(pt):
            key = (round(pt.x(), 6), round(pt.y(), 6))
            if key not in coord_map:
                v_idx = graph.addVertex(pt)
                coord_map[key] = v_idx
            return coord_map[key]
        for feat in self._layer.getFeatures():
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                polyline = geom.asPolyline()
                for i in range(len(polyline) - 1):
                    pt_a = polyline[i]
                    pt_b = polyline[i+1]
                    idx_a = get_or_create_vertex(pt_a)
                    idx_b = get_or_create_vertex(pt_b)
                    dist = pt_a.distance(pt_b)
                    graph.addEdge(idx_a, idx_b, dist)

class QgsNetworkDistanceStrategy:
    def __init__(self):
        pass

class QgsGraphAnalyzer:
    @staticmethod
    def dijkstra(graph, start_idx, strategy_idx=0):
        n = graph.vertexCount()
        tree = [-1] * n
        cost = [float('inf')] * n
        cost[start_idx] = 0.0
        import heapq
        pq = [(0.0, start_idx)]
        while pq:
            c, u = heapq.heappop(pq)
            if c > cost[u]:
                continue
            neighbors = graph._adjacency.get(u, {})
            for v, (edge_idx, edge_cost) in neighbors.items():
                new_cost = c + edge_cost
                if new_cost < cost[v]:
                    cost[v] = new_cost
                    tree[v] = edge_idx
                    heapq.heappush(pq, (new_cost, v))
        return tree, cost

# Network related mocks
class QUrl:
    def __init__(self, url=""):
        self._url = url
    @staticmethod
    def toPercentEncoding(text):
        import urllib.parse
        encoded = urllib.parse.quote(text)
        class MockQByteArray:
            def __init__(self, val):
                self._val = val
            def data(self):
                return self._val.encode('utf-8')
        return MockQByteArray(encoded)

class QNetworkRequest:
    class KnownHeaders:
        ContentTypeHeader = 0
    def __init__(self, url=None):
        self._url = url
        self._headers = {}
    def setRawHeader(self, name, value):
        self._headers[name] = value
    def setHeader(self, name, value):
        self._headers[name] = value

class MockQNetworkReply:
    NoError = 0
    ConnectionRefusedError = 1
    def __init__(self, content):
        self._content = content
    def content(self):
        return self._content
    def error(self):
        return MockQNetworkReply.NoError

class QgsBlockingNetworkRequest:
    NoError = 0
    def __init__(self):
        self._reply = None
    def post(self, request, data, force):
        import urllib.request
        try:
            url_str = request._url._url if hasattr(request._url, '_url') else str(request._url)
            req = urllib.request.Request(url_str, data=data, method="POST")
            for k, v in request._headers.items():
                k_str = k.decode('utf-8') if isinstance(k, bytes) else str(k)
                v_str = v.decode('utf-8') if isinstance(v, bytes) else str(v)
                req.add_header(k_str, v_str)
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read()
                self._reply = MockQNetworkReply(content)
            return QgsBlockingNetworkRequest.NoError
        except Exception:
            return 1
    def reply(self):
        return self._reply

class QgsNetworkAccessManager:
    _instance = None
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    def blockingGet(self, request):
        import urllib.request
        try:
            url_str = request._url._url if hasattr(request._url, '_url') else str(request._url)
            req = urllib.request.Request(url_str, method="GET")
            for k, v in request._headers.items():
                k_str = k.decode('utf-8') if isinstance(k, bytes) else str(k)
                v_str = v.decode('utf-8') if isinstance(v, bytes) else str(v)
                req.add_header(k_str, v_str)
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read()
                return MockQNetworkReply(content)
        except Exception:
            reply = MockQNetworkReply(b'')
            reply.error = lambda: MockQNetworkReply.ConnectionRefusedError
            return reply

# Check if QGIS is installed, otherwise dynamically inject mocks
should_mock = 'FORCE_MOCK_QGIS' in os.environ
if not should_mock:
    try:
        import qgis.core
    except ImportError:
        should_mock = True

if should_mock:
    # Set up mock package hierarchy
    qgis_core_attrs = {
        'QgsPointXY': QgsPointXY,
        'QgsGeometry': QgsGeometry,
        'QgsField': QgsField,
        'QgsFeature': QgsFeature,
        'QgsVectorLayer': QgsVectorLayer,
        'QgsMessageLog': QgsMessageLog,
        'Qgis': Qgis,
        'QgsCoordinateTransformContext': QgsCoordinateTransformContext,
        'QgsVectorFileWriter': QgsVectorFileWriter,
        'QgsBlockingNetworkRequest': QgsBlockingNetworkRequest,
        'QgsNetworkAccessManager': QgsNetworkAccessManager,
        'QgsVirtualLayerDefinition': QgsVirtualLayerDefinition,
    }
    
    qgis_analysis_attrs = {
        'QgsVectorLayerDirector': QgsVectorLayerDirector,
        'QgsGraphBuilder': QgsGraphBuilder,
        'QgsNetworkDistanceStrategy': QgsNetworkDistanceStrategy,
        'QgsGraphAnalyzer': QgsGraphAnalyzer,
    }

    qgis_pyqt_core_attrs = {
        'QUrl': QUrl,
        'QVariant': QVariant,
    }

    qgis_pyqt_network_attrs = {
        'QNetworkRequest': QNetworkRequest,
        'QNetworkReply': MockQNetworkReply,
    }

    # Inject helper
    def make_module(name, attrs):
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        mod.__getattr__ = lambda name: MagicMock
        sys.modules[name] = mod
        return mod

    qgis = make_module('qgis', {})
    qgis_core = make_module('qgis.core', qgis_core_attrs)
    qgis_analysis = make_module('qgis.analysis', qgis_analysis_attrs)
    qgis_utils = make_module('qgis.utils', {'iface': MagicMock()})
    
    qgis.core = qgis_core
    qgis.analysis = qgis_analysis
    qgis.utils = qgis_utils
    
    qgis_pyqt = make_module('qgis.PyQt', {})
    qgis_pyqt_core = make_module('qgis.PyQt.QtCore', qgis_pyqt_core_attrs)
    qgis_pyqt_network = make_module('qgis.PyQt.QtNetwork', qgis_pyqt_network_attrs)
    
    qgis_pyqt.QtCore = qgis_pyqt_core
    qgis_pyqt.QtNetwork = qgis_pyqt_network
    qgis.PyQt = qgis_pyqt
