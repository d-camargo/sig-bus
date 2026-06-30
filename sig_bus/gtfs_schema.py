# -*- coding: utf-8 -*-
"""
/***************************************************************************
 gtfs_schema — esquema e especificação de colunas para edição do GTFS
                                 A QGIS plugin
 Descreve a especificação dos arquivos GTFS, incluindo colunas, ordem
 canônica, obrigatoriedade, editabilidade e chaves estrangeiras.
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

from collections import namedtuple

# Estrutura simples para representar os metadados de uma coluna do GTFS
Col = namedtuple("Col", "name editable required")

# Dicionário contendo a especificação das tabelas GTFS (nesta fatia apenas routes e trips)
GTFS_FILES = {
    "routes": {
        "columns": [
            Col("route_id", False, True),
            Col("agency_id", False, False),
            Col("route_short_name", True, False),
            Col("route_long_name", True, False),
            Col("route_type", True, True),
        ],
        "foreign_keys": [
            ("agency_id", "agency", "agency_id"),
        ],
    },
    "trips": {
        "columns": [
            Col("route_id", False, True),
            Col("service_id", False, True),
            Col("trip_id", False, True),
            Col("trip_headsign", True, False),
            Col("direction_id", True, False),
            Col("shape_id", False, False),
        ],
        "foreign_keys": [
            ("route_id", "routes", "route_id"),
            ("service_id", "calendar", "service_id"),
            ("shape_id", "shapes", "shape_id"),
        ],
    },
}


def editable_tables():
    """
    Retorna a lista de tabelas editáveis configuradas no esquema.
    """
    return list(GTFS_FILES.keys())


def editable_columns(table):
    """
    Retorna os nomes das colunas de uma tabela que são marcadas como editáveis.
    """
    if table not in GTFS_FILES:
        return []
    return [col.name for col in GTFS_FILES[table]["columns"] if col.editable]
