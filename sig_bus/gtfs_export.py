# -*- coding: utf-8 -*-
"""
/***************************************************************************
 gtfs_export — exportador de GeoPackage GTFS para arquivo .zip
                                 A QGIS plugin
 Realiza a exportação das tabelas editadas do GeoPackage para arquivos
 de texto formatados dentro de um arquivo ZIP normalizado.
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import csv
import os
import sqlite3
import tempfile
import zipfile

from . import gtfs_schema

LOG_TAG = 'SIG-Bus'


def _read_stop_coordinates(gpkg_path):
    """
    Lê stop_id -> (lat, lon) a partir da geometria da camada 'stops': a edição
    de vértices no canvas não atualiza as colunas de texto stop_lat/stop_lon.
    """
    layer = QgsVectorLayer(gpkg_path + '|layername=stops', 'stops', 'ogr')
    coords = {}
    if not layer.isValid():
        return coords
    for feat in layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        pt = geom.asPoint()
        coords[feat['stop_id']] = (pt.y(), pt.x())
    return coords


def _iter_shape_points(gpkg_path):
    """
    Gera linhas (shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence) a
    partir dos vértices da camada de linha 'shapes' — fonte da verdade da
    geometria, não a tabela crua 'shapes_point'.
    """
    layer = QgsVectorLayer(gpkg_path + '|layername=shapes', 'shapes', 'ogr')
    if not layer.isValid():
        return
    for feat in layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        shape_id = feat['shape_id']
        for i, pt in enumerate(geom.asPolyline()):
            yield [shape_id, pt.y(), pt.x(), i + 1]


class GtfsExporter(QgsTask):
    """
    Task executada em segundo plano para exportar o GeoPackage do GTFS normalizado.
    """

    def __init__(self, gpkg_path, out_zip):
        """
        Construtor da classe.
        :param gpkg_path: Caminho do GeoPackage de entrada.
        :param out_zip: Caminho do arquivo ZIP de destino.
        """
        # ponytail: QgsTask.CanCancel permite que o usuário aborte a exportação longa.
        super(GtfsExporter, self).__init__('Exportar GTFS', QgsTask.CanCancel)
        self.gpkg_path = gpkg_path
        self.out_zip = out_zip
        self._erro = None

    def run(self):
        """
        Executa a exportação em thread secundária.
        """
        try:
            conn = sqlite3.connect(self.gpkg_path)
            
            # ponytail: Configuração direta mapeando tabelas físicas para arquivos GTFS.
            # O booleano final indica se a tabela é obrigatória pela especificação GTFS.
            # ponytail: stops foi removida daqui para ser exportada separadamente via OGR
            # para preservar a geometria espacial editada no mapa.
            export_config = [
                ("agency", "agency", True),
                ("routes", "routes", True),
                ("trips", "trips", True),
                ("stop_times", "stop_times", True),
                ("shapes", "shapes", False),
            ]

            # Identifica quais tabelas de fato existem no GeoPackage
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tabelas_existentes = {row[0] for row in cursor.fetchall()}

            # ponytail: calendar_dates é opcional. Se a tabela do banco com esse nome
            # não existir mas 'calendar' existir, puxamos dela.
            if "calendar_dates" in tabelas_existentes:
                export_config.append(("calendar_dates", "calendar_dates", False))
            elif "calendar" in tabelas_existentes:
                export_config.append(("calendar", "calendar_dates", False))

            temp_dir = tempfile.TemporaryDirectory()
            arquivos_gerados = []

            # 1. Exporta stops usando osgeo.ogr para ler lon/lat diretamente da geometria
            stops_txt_path = self._export_stops_ogr(temp_dir.name)
            if stops_txt_path:
                arquivos_gerados.append((stops_txt_path, "stops.txt"))

            # 2. Exporta as demais tabelas via sqlite3
            for tab_name, gtfs_filename, obrigatoria in export_config:
                if self.isCanceled():
                    return False

                if tab_name not in tabelas_existentes:
                    if obrigatoria:
                        raise Exception("Tabela obrigatória '{}' não encontrada no GeoPackage.".format(tab_name))
                    continue

                # Obtém as colunas da tabela física
                cursor.execute("PRAGMA table_info({})".format(tab_name))
                colunas_fisicas = {row[1] for row in cursor.fetchall()}

                # ponytail: Filtra as colunas do schema para emitir apenas as que existem
                # fisicamente no banco de dados daquele feed.
                if tab_name == "shapes":
                    colunas_exportar = gtfs_schema.SHAPES_EXPORT_COLUMNS
                else:
                    ordem_schema = gtfs_schema.column_order(gtfs_filename)
                    colunas_exportar = [col for col in ordem_schema if col in colunas_fisicas]

                if not colunas_exportar:
                    continue

                txt_path = os.path.join(temp_dir.name, "{}.txt".format(gtfs_filename))
                
                # ponytail: Streaming direto no cursor para todas as tabelas (sem fetchall)
                # evita qualquer estouro de memória com tabelas gigantes como stop_times.
                with open(txt_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(colunas_exportar)

                    if tab_name == "shapes":
                        # ponytail: geometria é a fonte da verdade — lê os vértices
                        # da camada de linha via QGIS, como já faz build_shapes_line.
                        for row in _iter_shape_points(self.gpkg_path):
                            if self.isCanceled():
                                return False
                            writer.writerow(row)
                    else:
                        stop_coords = (
                            _read_stop_coordinates(self.gpkg_path)
                            if tab_name == "stops" else None
                        )
                        stop_id_idx = colunas_exportar.index('stop_id') if 'stop_id' in colunas_exportar else -1
                        lat_idx = colunas_exportar.index('stop_lat') if 'stop_lat' in colunas_exportar else -1
                        lon_idx = colunas_exportar.index('stop_lon') if 'stop_lon' in colunas_exportar else -1

                        query = "SELECT {} FROM {}".format(", ".join(colunas_exportar), tab_name)
                        for row in conn.execute(query):
                            if self.isCanceled():
                                return False

                            row_data = list(row)
                            if stop_coords and stop_id_idx >= 0:
                                coords = stop_coords.get(row_data[stop_id_idx])
                                if coords:
                                    if lat_idx >= 0:
                                        row_data[lat_idx] = coords[0]
                                    if lon_idx >= 0:
                                        row_data[lon_idx] = coords[1]
                            writer.writerow(row_data)

                arquivos_gerados.append((txt_path, "{}.txt".format(gtfs_filename)))

            conn.close()

            # ponytail: zipfile da stdlib empacota os arquivos de forma nativa e sem dependências
            with zipfile.ZipFile(self.out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                for txt_path, name_in_zip in arquivos_gerados:
                    if self.isCanceled():
                        return False
                    zf.write(txt_path, arcname=name_in_zip)

            return True

        except Exception as e:
            self._erro = str(e)
            return False

    def _export_stops_ogr(self, temp_dir_path):
        """
        Exporta a tabela stops usando osgeo.ogr para ler lon/lat diretamente da geometria.
        """
        ds = ogr.Open(self.gpkg_path)
        if not ds:
            raise Exception("Falha ao abrir GeoPackage via OGR.")
            
        lyr = ds.GetLayerByName('stops')
        if not lyr:
            raise Exception("Tabela obrigatória 'stops' não encontrada no GeoPackage.")

        # Obtém os nomes dos campos existentes na camada OGR
        layer_defn = lyr.GetLayerDefn()
        campos_fisicos = {layer_defn.GetFieldDefn(i).GetName() for i in range(layer_defn.GetFieldCount())}

        # Adiciona coordenadas virtuais stop_lat/stop_lon vindas da geometria
        ordem_schema = gtfs_schema.column_order('stops')
        colunas_exportar = [col for col in ordem_schema if col in campos_fisicos or col in ('stop_lat', 'stop_lon')]

        txt_path = os.path.join(temp_dir_path, "stops.txt")
        with open(txt_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(colunas_exportar)

            lyr.ResetReading()
            for feat in lyr:
                if self.isCanceled():
                    return None

                row = []
                geom = feat.GetGeometryRef()
                for col in colunas_exportar:
                    # ponytail: Se stop_lon/stop_lat constar no schema, extraímos
                    # as coordenadas diretamente da geometria do ponto (se não for nula).
                    if col == 'stop_lon' and geom and not geom.IsEmpty():
                        row.append(geom.GetX())
                    elif col == 'stop_lat' and geom and not geom.IsEmpty():
                        row.append(geom.GetY())
                    else:
                        if col in campos_fisicos:
                            row.append(feat.GetField(col))
                        else:
                            row.append(None)
                writer.writerow(row)
        return txt_path

    def finished(self, ok):
        """
        Executado na thread principal (GUI) após a conclusão do processamento.
        """
        if ok:
            QgsMessageLog.logMessage(
                "GTFS exportado com sucesso para: {}".format(self.out_zip),
                LOG_TAG, Qgis.Info
            )
        else:
            msg = "Falha ao exportar GTFS: {}".format(self._erro) if self._erro else "Exportação cancelada."
            QgsMessageLog.logMessage(msg, LOG_TAG, Qgis.Critical)
