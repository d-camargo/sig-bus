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

from osgeo import ogr
from qgis.core import Qgis, QgsMessageLog, QgsTask
from . import gtfs_schema

LOG_TAG = 'SIG-Bus'


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
                ("shapes_point", "shapes", False),
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
                    
                    query = "SELECT {} FROM {}".format(", ".join(colunas_exportar), tab_name)
                    cursor_select = conn.execute(query)
                    for row in cursor_select:
                        if self.isCanceled():
                            return False
                        writer.writerow(row)

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
