# -*- coding: utf-8 -*-
"""
/***************************************************************************
 gtfs_edit_core — núcleo de edição de dados GTFS do SIG-Bus
                                 A QGIS plugin
 Gerencia o ciclo de vida da cópia de trabalho (Working Copy) do GeoPackage
 do GTFS para edição, sem dependências do ambiente QGIS GUI nesta fatia.
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

import os
import shutil


class WorkingCopy(object):
    """
    Gerencia a cópia de trabalho do GeoPackage para edição do GTFS.
    A cópia é criada no mesmo diretório do arquivo original.
    """

    def __init__(self, source_gpkg):
        """
        Construtor da classe.
        :param source_gpkg: Caminho absoluto para o arquivo feed.gpkg de origem ou diretório.
        """
        if source_gpkg and os.path.isdir(source_gpkg):
            self.source_path = None
            directory = source_gpkg
        else:
            self.source_path = source_gpkg
            directory = os.path.dirname(source_gpkg) if source_gpkg else ""
        self.edit_path = os.path.join(directory, "feed_edit.gpkg") if directory else ""

    def is_active(self):
        """
        Verifica se a cópia de trabalho de edição existe no disco.
        :return: True se feed_edit.gpkg existir, False caso contrário.
        """
        return bool(self.edit_path and os.path.exists(self.edit_path))

    def enter(self, overwrite=False):
        """
        Entra no modo de edição copiando o GeoPackage original para a cópia de trabalho.
        :param overwrite: Se True, sobrescreve a cópia de trabalho se já existir.
        :return: True se a cópia foi criada com sucesso, False caso contrário.
        """
        if self.is_active() and not overwrite:
            return False

        if not self.source_path or not self.edit_path:
            return False

        try:
            shutil.copyfile(self.source_path, self.edit_path)
            return True
        except Exception:
            return False

    def enter_empty(self, overwrite=False):
        """
        Cria um GeoPackage vazio com a estrutura de tabelas do GTFS.
        :param overwrite: Se True, sobrescreve a cópia de trabalho se já existir.
        :return: True se criado com sucesso, False caso contrário.
        """
        edit_path = self.edit_path

        if not edit_path:
            return False

        if os.path.exists(edit_path):
            if not overwrite:
                return False
            try:
                os.remove(edit_path)
            except OSError:
                return False

        try:
            from osgeo import ogr, osr
            try:
                from . import gtfs_schema
            except ImportError:
                try:
                    import gtfs_schema
                except ImportError:
                    from sig_bus import gtfs_schema

            driver = ogr.GetDriverByName("GPKG")
            if driver is None:
                return False

            ds = driver.CreateDataSource(edit_path)
            if ds is None:
                return False

            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4326)

            # Criar as tabelas do esquema GTFS + shapes_point
            tables = list(gtfs_schema.GTFS_FILES.keys())
            if "shapes_point" not in tables:
                tables.append("shapes_point")

            for table_name in tables:
                if table_name in ("stops", "shapes_point"):
                    geom_type = ogr.wkbPoint
                    layer_srs = srs
                elif table_name == "shapes":
                    geom_type = ogr.wkbLineString
                    layer_srs = srs
                else:
                    geom_type = ogr.wkbNone
                    layer_srs = None

                lyr = ds.CreateLayer(table_name, srs=layer_srs, geom_type=geom_type)
                if not lyr:
                    raise RuntimeError("Falha ao criar camada '{}'".format(table_name))

                # Cria os campos da tabela
                columns = gtfs_schema.column_order(table_name)
                for col in columns:
                    field_defn = ogr.FieldDefn(col, ogr.OFTString)
                    lyr.CreateField(field_defn)

            # Fecha/salva o datasource
            ds = None
            return True

        except Exception:
            # Se falhar a criação, removemos o arquivo incompleto se ele foi criado
            if os.path.exists(edit_path):
                try:
                    os.remove(edit_path)
                except OSError:
                    pass
            return False

    def discard(self):
        """
        Descarta a cópia de trabalho, apagando o arquivo temporário de edição.
        :return: True se o arquivo foi excluído com sucesso, False caso contrário.
        """
        if self.is_active():
            try:
                os.remove(self.edit_path)
                return True
            except Exception:
                return False
        return False
