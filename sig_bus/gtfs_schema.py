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

# ponytail: Namedtuple Col é a estrutura de dados mais simples e sem overhead
# para guardar os metadados de cada coluna na stdlib.
Col = namedtuple("Col", "name editable required")

# Dicionário contendo a especificação de todas as tabelas exportadas pelo GTFS
GTFS_FILES = {
    "agency": {
        "columns": [
            Col("agency_id", False, False),
            Col("agency_name", True, True),
            Col("agency_url", True, True),
            Col("agency_timezone", True, True),
            Col("agency_lang", True, False),
            Col("agency_phone", True, False),
        ],
        "foreign_keys": [],
    },
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
    "stops": {
        "columns": [
            Col("stop_id", False, True),
            Col("stop_code", True, False),
            Col("stop_name", True, True),
            Col("stop_desc", True, False),
            Col("stop_lat", True, True),
            Col("stop_lon", True, True),
            Col("zone_id", True, False),
            Col("location_type", True, False),
            Col("parent_station", False, False),
        ],
        "foreign_keys": [],
    },
    "stop_times": {
        "columns": [
            Col("trip_id", False, True),
            Col("arrival_time", True, True),
            Col("departure_time", True, True),
            Col("stop_id", False, True),
            Col("stop_sequence", True, True),
            Col("stop_headsign", True, False),
            Col("pickup_type", True, False),
            Col("drop_off_type", True, False),
            Col("timepoint", True, False),
        ],
        "foreign_keys": [
            ("trip_id", "trips", "trip_id"),
            ("stop_id", "stops", "stop_id"),
        ],
    },
    "calendar": {
        "columns": [
            Col("service_id", False, True),
            Col("monday", True, True),
            Col("tuesday", True, True),
            Col("wednesday", True, True),
            Col("thursday", True, True),
            Col("friday", True, True),
            Col("saturday", True, True),
            Col("sunday", True, True),
            Col("start_date", True, True),
            Col("end_date", True, True),
        ],
        "foreign_keys": [],
    },
    "calendar_dates": {
        "columns": [
            Col("service_id", False, True),
            Col("date", True, True),
            Col("exception_type", True, True),
        ],
        "foreign_keys": [],
    },
    "shapes": {
        "columns": [
            Col("shape_id", False, True),
        ],
        "foreign_keys": [],
    },
}

# ponytail: shapes.txt não tem colunas físicas de lat/lon/sequência (a camada
# editável 'shapes' só guarda shape_id — ver decisão do passo 5 do PLAN.md);
# a ordem de exportação fica aqui, não hardcoded em gtfs_export.py, para
# manter este módulo como fonte única da verdade (decisão 6 do PLAN.md).
SHAPES_EXPORT_COLUMNS = ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"]


def editable_tables():
    """
    Retorna a lista de tabelas editáveis configuradas no esquema.
    """
    # ponytail: Manter a lógica original simples, baseada nas chaves do dicionário.
    return list(GTFS_FILES.keys())


def editable_columns(table):
    """
    Retorna os nomes das colunas de uma tabela que são marcadas como editáveis.
    """
    if table not in GTFS_FILES:
        return []
    return [col.name for col in GTFS_FILES[table]["columns"] if col.editable]


def column_order(table):
    """
    Retorna a lista dos nomes das colunas na ordem canônica para uma dada tabela.
    """
    # ponytail: List comprehension direta e simples para extrair a ordem das colunas.
    if table not in GTFS_FILES:
        return []
    return [col.name for col in GTFS_FILES[table]["columns"]]
