# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GtfsReader — leitor de GTFS para o SIG-Bus
                                 A QGIS plugin
 Carrega um GTFS (.zip) num GeoPackage, criando camadas vetoriais.
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

Baseado no leitor GTFS do plugin "GTFS Loader":
    copyright (C) 2020-2021 by CTU GeoForAll Lab
    https://github.com/ctu-geoforall-lab/qgis-gtfs-plugin
    licenciado sob a GNU General Public License v2 ou posterior.

Adaptado e revisado para o SIG-Bus por Diego Camargo (2022/2026):
    - cópia para dentro do plugin, eliminando a dependência do plugin externo;
    - API atualizada (writeAsVectorFormatV3) com tratamento de erro;
    - limpeza de diretório explícita (sem __del__);
    - construção genérica das linhas a partir de shapes.txt
      (sem a coloração específica do transporte de Praga/PID).
"""

import os
import shutil
import sqlite3
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    Qgis,
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVirtualLayerDefinition,
)

LOG_TAG = 'SIG-Bus'

# Camadas adicionadas ao projeto como camadas de mapa. As demais tabelas
# (stop_times, fare_*, agency, etc.) ficam no GeoPackage para os joins.
ESSENTIAL_LAYERS = ['stops', 'shapes', 'routes', 'trips', 'calendar']

# Camadas mínimas esperadas num GTFS válido (ver gtfs.org). calendar OU
# calendar_dates é condicionalmente obrigatório; aqui exigimos calendar
# porque o restante do fluxo do SIG-Bus depende dele.
REQUIRED_LAYERS = ['agency', 'routes', 'trips', 'stop_times', 'stops', 'calendar']


class GtfsError(Exception):
    """Erro de leitura/escrita de um feed GTFS."""
    pass


class GtfsReader:
    """Extrai um GTFS (.zip) e grava suas tabelas num GeoPackage.

    Uso típico::

        reader = GtfsReader('/caminho/feed.zip')
        try:
            layers = reader.write('/caminho/feed.gpkg')
        finally:
            reader.cleanup()
    """

    def __init__(self, input_zip):
        self.input_zip = input_zip
        self.dir_name = Path(Path(self.input_zip).name).stem
        self.dir_path = Path(self.input_zip).parent.joinpath(self.dir_name)

    def cleanup(self):
        """Mantida por compatibilidade. A versão atual lê o GTFS direto do
        .zip (via /vsizip/ do GDAL), sem extrair para disco, então em geral
        não há nada a limpar."""
        if self.dir_path.exists():
            shutil.rmtree(self.dir_path, ignore_errors=True)

    # Arquivos com geometria: nome -> (campo X, campo Y, nome da camada de saída)
    SPATIAL = {
        'stops': ('stop_lon', 'stop_lat', 'stops'),
        'shapes': ('shape_pt_lon', 'shape_pt_lat', 'shapes_point'),
    }

    def write(self, output_file):
        """Escreve o GTFS no GeoPackage ``output_file`` e devolve os nomes
        das camadas criadas. Levanta :class:`GtfsError` em caso de falha."""
        ext = Path(output_file).suffix
        if ext != '.gpkg':
            raise GtfsError("Formato de saída não suportado: {}".format(ext))

        # Recria o GeoPackage do zero para evitar camadas/índices obsoletos.
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError as e:
                raise GtfsError("Não foi possível recriar {}: {}"
                                .format(output_file, e))

        try:
            txt_files = self._list_txt()
        except (BadZipFile, FileNotFoundError, PermissionError,
                IsADirectoryError) as e:
            raise GtfsError(e)

        layer_names = self._write_gpkg(txt_files, output_file)
        self._check_required_layers(layer_names)
        return layer_names

    def _list_txt(self):
        """Lista os .txt do .zip e devolve pares (nome, caminho /vsizip/).

        Não extrai nada para disco — o GDAL lê de dentro do .zip."""
        with ZipFile(self.input_zip) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith('.txt')]
        if not names:
            raise GtfsError("Nenhum arquivo .txt encontrado no GTFS.")
        zip_abs = os.path.abspath(self.input_zip)
        return [(Path(n).stem, '/vsizip/' + zip_abs + '/' + n) for n in names]

    def _write_gpkg(self, txt_files, output_file):
        """Grava cada .txt como uma camada/tabela do GeoPackage usando o
        GDAL (VectorTranslate). stops e shapes viram camadas de pontos.

        Usa GDAL em vez de QgsVectorFileWriter porque o stop_times costuma
        ter dezenas/centenas de MB: o GDAL faz a conversão em streaming, com
        baixo uso de memória, ao passo que o caminho via provider do QGIS
        carregava feição a feição e podia esgotar a memória."""
        layer_names = []
        created = False  # vira True após a primeira tabela criada com sucesso
        for stem, src_path in txt_files:
            if stem in self.SPATIAL:
                xfield, yfield, out_name = self.SPATIAL[stem]
            else:
                xfield = yfield = None
                out_name = stem
            try:
                # A primeira importação bem-sucedida cria o GeoPackage; as
                # demais o atualizam (accessMode='update').
                self._gdal_import(src_path, output_file, out_name,
                                  xfield=xfield, yfield=yfield,
                                  create=not created)
                layer_names.append(out_name)
                created = True
            except Exception as e:  # noqa: BLE001 — GDAL levanta RuntimeError
                # Tabela problemática (ex.: feed_info.txt vazio/atípico) não
                # deve abortar o feed inteiro — registra e segue.
                QgsMessageLog.logMessage(
                    "Tabela ignorada ({}): {}".format(out_name, e),
                    LOG_TAG, Qgis.Warning)

        if not created:
            raise GtfsError("Nenhuma tabela do GTFS pôde ser importada.")
        return layer_names

    @staticmethod
    def _gdal_import(src_path, gpkg_path, layer_name,
                     xfield=None, yfield=None, create=False):
        """Importa um .txt (CSV) para o GeoPackage via GDAL.

        AUTODETECT_TYPE=NO mantém todos os campos como texto — essencial para
        preservar IDs com zeros à esquerda e garantir que as chaves de join
        (stop_id, trip_id) tenham o mesmo tipo em todas as tabelas."""
        from osgeo import gdal
        gdal.UseExceptions()

        open_opts = ['AUTODETECT_TYPE=NO', 'EMPTY_STRING_AS_NULL=NO']
        translate_kw = dict(format='GPKG', layerName=layer_name)
        if xfield and yfield:
            open_opts += ['X_POSSIBLE_NAMES=' + xfield,
                          'Y_POSSIBLE_NAMES=' + yfield,
                          'KEEP_GEOM_COLUMNS=YES']
            translate_kw.update(srcSRS='EPSG:4326', dstSRS='EPSG:4326',
                                geometryType='POINT')
        if not create:
            # Anexa uma nova camada ao GeoPackage já existente.
            translate_kw['accessMode'] = 'update'

        # Força o driver CSV: a auto-detecção do GDAL falha em .txt atípicos
        # (ex.: feed_info.txt com uma única linha de dados).
        src = gdal.OpenEx(src_path, gdal.OF_VECTOR,
                          allowed_drivers=['CSV'], open_options=open_opts)
        if src is None:
            raise RuntimeError("GDAL não conseguiu abrir {}".format(src_path))
        try:
            out = gdal.VectorTranslate(
                gpkg_path, src,
                options=gdal.VectorTranslateOptions(**translate_kw))
            if out is None:
                raise RuntimeError("VectorTranslate retornou None")
            out = None  # fecha/flush
        finally:
            src = None

    def _check_required_layers(self, layer_names):
        missing = [n for n in REQUIRED_LAYERS if n not in layer_names]
        if missing:
            QgsMessageLog.logMessage(
                "Camadas GTFS obrigatórias ausentes: {}".format(missing),
                LOG_TAG, Qgis.Warning)
        else:
            QgsMessageLog.logMessage(
                "Todas as camadas GTFS obrigatórias estão presentes.",
                LOG_TAG, Qgis.Success)

    def build_shapes_line(self, gpkg_path):
        """Constrói as linhas (polilinhas) a partir da camada de pontos
        'shapes_point', agrupando por shape_id e ordenando por
        shape_pt_sequence. Grava a camada 'shapes' no GeoPackage e a devolve.

        Versão genérica de ``_connect_shapes`` do GTFS Loader, sem a
        coloração e o ``shape_id_short`` específicos de Praga (PID).
        Devolve ``None`` se não houver camada de shapes."""
        src_uri = gpkg_path + '|layername=shapes_point'
        points = QgsVectorLayer(src_uri, 'shapes_point', 'ogr')
        if not points.isValid() or points.featureCount() == 0:
            QgsMessageLog.logMessage(
                "Sem shapes_point; pulando construção das linhas.",
                LOG_TAG, Qgis.Info)
            return None

        # Agrupa pontos por shape_id, guardando (sequência, ponto).
        grouped = {}
        for feat in points.getFeatures():
            shape_id = feat['shape_id']
            seq = feat['shape_pt_sequence']
            geom = feat.geometry()
            if geom.isEmpty():
                continue
            try:
                seq = int(seq)
            except (TypeError, ValueError):
                seq = 0
            grouped.setdefault(shape_id, []).append((seq, geom.asPoint()))

        line_layer = QgsVectorLayer(
            "LineString?crs=epsg:4326", "shapes_line", "memory")
        provider = line_layer.dataProvider()
        provider.addAttributes([QgsField("shape_id", QVariant.String)])
        line_layer.updateFields()

        for shape_id, pts in grouped.items():
            pts.sort(key=lambda sp: sp[0])
            polyline = [QgsPointXY(p) for _seq, p in pts]
            if len(polyline) < 2:
                continue
            feat = QgsFeature()
            feat.setGeometry(QgsGeometry.fromPolylineXY(polyline))
            feat.setAttributes([shape_id])
            provider.addFeature(feat)
        line_layer.updateExtents()

        ctx = QgsCoordinateTransformContext()
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = 'GPKG'
        options.layerName = 'shapes'
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            line_layer, gpkg_path, ctx, options)
        if result[0] != QgsVectorFileWriter.NoError:
            raise GtfsError(
                "Falha ao gravar a camada de linhas (cód. {}: {})"
                .format(result[0], result[1]))

        return QgsVectorLayer(gpkg_path + '|layername=shapes', 'shapes', 'ogr')


def create_join_indexes(gpkg_path):
    """Cria índices nas chaves de join (trip_id, stop_id) dentro do
    GeoPackage. Sem isso, a camada virtual de horários fica muito lenta.

    O GeoPackage é um banco SQLite, então usamos sqlite3 diretamente.
    Índices em tabelas/colunas ausentes são ignorados."""
    statements = [
        ("stop_times", "CREATE INDEX IF NOT EXISTS idx_st_trip "
                       "ON stop_times(trip_id)"),
        ("stop_times", "CREATE INDEX IF NOT EXISTS idx_st_stop "
                       "ON stop_times(stop_id)"),
        ("trips", "CREATE INDEX IF NOT EXISTS idx_trips_trip "
                  "ON trips(trip_id)"),
        ("trips", "CREATE INDEX IF NOT EXISTS idx_trips_shape "
                  "ON trips(shape_id)"),
        ("stops", "CREATE INDEX IF NOT EXISTS idx_stops_stop "
                  "ON stops(stop_id)"),
    ]
    try:
        with sqlite3.connect(gpkg_path) as conn:
            existing = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table, sql in statements:
                if table in existing:
                    try:
                        conn.execute(sql)
                    except sqlite3.OperationalError as e:
                        QgsMessageLog.logMessage(
                            "Índice ignorado ({}): {}".format(table, e),
                            LOG_TAG, Qgis.Info)
    except sqlite3.Error as e:
        QgsMessageLog.logMessage(
            "Falha ao criar índices: {}".format(e), LOG_TAG, Qgis.Warning)


def stop_events_virtual_layer(gpkg_path, shape_id=None, name='horarios_paradas'):
    """Monta a camada VIRTUAL de horários por viagem.

    Faz, sob demanda (sem materializar), o join:
        stop_times ⋈ trips (trip_id) ⋈ stops (stop_id)
    produzindo um ponto por (viagem, parada) na coordenada da parada, com
    horários e shape_id.

    O filtro por ``shape_id`` é embutido no próprio join (cláusula WHERE),
    para o SQLite usar o índice de trips(shape_id) e processar só as viagens
    daquela linha — não o feed inteiro. Sem ``shape_id`` a camada vem vazia
    (WHERE 1=0), para nunca tentar desenhar milhões de pontos de uma vez.

    Devolve a camada (pode ser inválida se faltarem tabelas — o chamador
    deve checar isValid())."""
    if shape_id is None:
        where = "WHERE 1=0"
    else:
        # Escapa aspas simples para evitar quebra de SQL.
        safe = str(shape_id).replace("'", "''")
        where = "WHERE t.shape_id = '{}'".format(safe)

    definition = QgsVirtualLayerDefinition()
    definition.addSource('stop_times', gpkg_path + '|layername=stop_times', 'ogr')
    definition.addSource('stops', gpkg_path + '|layername=stops', 'ogr')
    definition.addSource('trips', gpkg_path + '|layername=trips', 'ogr')
    query = (
        "SELECT st.rowid AS uid, "
        "t.trip_id, t.route_id, t.shape_id, t.service_id, "
        "st.stop_id, st.stop_sequence, st.arrival_time, st.departure_time, "
        "s.stop_name, s.geometry "
        "FROM stop_times AS st "
        "JOIN trips AS t ON st.trip_id = t.trip_id "
        "JOIN stops AS s ON st.stop_id = s.stop_id "
        + where
    )
    definition.setQuery(query)
    definition.setGeometryField('geometry')
    definition.setUid('uid')
    return QgsVectorLayer(definition.toString(), name, 'virtual')
