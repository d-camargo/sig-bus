# -*- coding: utf-8 -*-
"""
Testes de unidade para sig_bus/schedule_table_core.py
"""

import pytest
from sig_bus.schedule_table_core import (
    format_time_str,
    ScheduleTable,
    build_schedule_table,
)


def test_format_time_str():
    assert format_time_str("06:30:00", fmt="HH:MM") == "06:30"
    assert format_time_str("06:30:00", fmt="HH:MM:SS") == "06:30:00"
    assert format_time_str("8:5", fmt="HH:MM") == "08:05"
    assert format_time_str("25:15:45", fmt="HH:MM") == "25:15"
    assert format_time_str(None) == ""
    assert format_time_str("") == ""


def test_build_schedule_table_empty():
    table = build_schedule_table([], route_short_name="100", direction_id="0")
    assert isinstance(table, ScheduleTable)
    assert table.stops == []
    assert table.trips == []
    assert table.matrix == {}
    assert table.route_short_name == "100"
    assert table.direction_id == "0"

    headers, rows = table.to_grid()
    assert headers == ["Parada"]
    assert rows == []


def test_build_schedule_table_basic():
    stop_times = [
        {"trip_id": "T1", "stop_id": "S1", "stop_sequence": 1, "departure_time": "06:00:00"},
        {"trip_id": "T1", "stop_id": "S2", "stop_sequence": 2, "departure_time": "06:15:00"},
        {"trip_id": "T2", "stop_id": "S1", "stop_sequence": 1, "departure_time": "06:30:00"},
        {"trip_id": "T2", "stop_id": "S2", "stop_sequence": 2, "departure_time": "06:45:00"},
    ]
    stops = [
        {"stop_id": "S1", "stop_name": "Terminal A"},
        {"stop_id": "S2", "stop_name": "Estacao B"},
    ]

    table = build_schedule_table(stop_times, stops=stops, route_short_name="100", direction_id="0")

    assert len(table.trips) == 2
    assert [t["trip_id"] for t in table.trips] == ["T1", "T2"]
    assert len(table.stops) == 2
    assert table.stops[0]["stop_name"] == "Terminal A"
    assert table.stops[1]["stop_name"] == "Estacao B"

    assert table.get_time("S1", "T1") == "06:00:00"
    assert table.get_time("S2", "T2") == "06:45:00"
    assert table.get_time("S2", "NONEXISTENT") is None

    headers, rows = table.to_grid(time_format="HH:MM", empty_cell="-")
    assert headers == ["Parada", "V1\n06:00", "V2\n06:30"]
    assert rows == [
        ["Terminal A", "06:00", "06:30"],
        ["Estacao B", "06:15", "06:45"],
    ]


def test_to_grid_cabecalho_ordinal_e_horario():
    stop_times = [
        {"trip_id": "T1", "stop_id": "S1", "stop_sequence": 1, "departure_time": "06:10:00"},
        {"trip_id": "T2", "stop_id": "S1", "stop_sequence": 1, "departure_time": "06:30:00"},
    ]

    table = build_schedule_table(stop_times, route_short_name="100", direction_id="0")

    headers, _ = table.to_grid()
    assert headers == ["Parada", "V1\n06:10", "V2\n06:30"]


def test_to_grid_ordena_viagens_por_horario_mesmo_fora_de_ordem():
    stop_times = [
        # T2 aparece primeiro na lista de entrada, mas sai depois de T1.
        {"trip_id": "T2", "stop_id": "S1", "stop_sequence": 1, "departure_time": "07:00:00"},
        {"trip_id": "T1", "stop_id": "S1", "stop_sequence": 1, "departure_time": "06:00:00"},
    ]

    table = build_schedule_table(stop_times, route_short_name="100", direction_id="0")

    assert [t["trip_id"] for t in table.trips] == ["T1", "T2"]
    headers, _ = table.to_grid()
    assert headers == ["Parada", "V1\n06:00", "V2\n07:00"]


def test_column_trip_ids_casa_com_as_colunas_de_to_grid():
    stop_times = [
        {"trip_id": "T2", "stop_id": "S1", "stop_sequence": 1, "departure_time": "07:00:00"},
        {"trip_id": "T1", "stop_id": "S1", "stop_sequence": 1, "departure_time": "06:00:00"},
    ]

    table = build_schedule_table(stop_times, route_short_name="100", direction_id="0")
    headers, _ = table.to_grid()
    trip_ids = table.column_trip_ids()

    assert len(trip_ids) == len(headers) - 1
    for i, trip_id in enumerate(trip_ids):
        coluna_header = headers[i + 1]
        # A coluna i (0-based) corresponde ao trip_id que produz o mesmo
        # horário de partida mostrado no rótulo dessa coluna.
        hora_no_header = coluna_header.split("\n")[1]
        assert table.get_time("S1", trip_id) == f"{hora_no_header}:00"


def test_to_grid_viagem_sem_horario_legivel_cai_em_ordinal_sozinho():
    stop_times = [
        {"trip_id": "T1", "stop_id": "S1", "stop_sequence": 1, "departure_time": None},
    ]

    table = build_schedule_table(stop_times, route_short_name="100", direction_id="0")

    headers, rows = table.to_grid()
    assert headers == ["Parada", "V1"]
    assert rows == [["S1", "-"]]
