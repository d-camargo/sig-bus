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
        :param source_gpkg: Caminho absoluto para o arquivo feed.gpkg de origem.
        """
        self.source_path = source_gpkg
        directory = os.path.dirname(source_gpkg)
        self.edit_path = os.path.join(directory, "feed_edit.gpkg")

    def is_active(self):
        """
        Verifica se a cópia de trabalho de edição existe no disco.
        :return: True se feed_edit.gpkg existir, False caso contrário.
        """
        return os.path.exists(self.edit_path)

    def enter(self, overwrite=False):
        """
        Entra no modo de edição copiando o GeoPackage original para a cópia de trabalho.
        :param overwrite: Se True, sobrescreve a cópia de trabalho se já existir.
        :return: True se a cópia foi criada com sucesso, False caso contrário.
        """
        if self.is_active() and not overwrite:
            return False

        try:
            shutil.copyfile(self.source_path, self.edit_path)
            return True
        except Exception:
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
