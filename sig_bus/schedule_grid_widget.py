# -*- coding: utf-8 -*-
"""
/***************************************************************************
 schedule_grid_widget — Grade editável de horários do SIG-Bus
                                 A QGIS plugin
 QTableWidget que exibe a matriz de horários (paradas x viagens) de um
 sentido de uma linha e sabe extrair, sozinho, só as células realmente
 editadas em relação à grade original — usado por "Ajustar Horários" na
 aba "Edição GTFS".
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

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QTableWidget, QTableWidgetItem

from .schedule_table_core import build_schedule_table, format_time_str
from .schedule_edit_core import to_seconds, from_seconds


class ScheduleGridWidget(QTableWidget):
    """
    Grade de horários (paradas x viagens) de um sentido de uma linha.
    Monta a grade a partir de schedule_table_core.build_schedule_table() e
    expõe collect_changes() para que o chamador (o diálogo "Ajustar
    Horários") monte o "Aplicar ao feed" em cima do widget, sem reabrir a
    grade original célula a célula.
    """

    def __init__(self, stop_times, route_short_name="", direction_id="", parent=None):
        super().__init__(parent)
        self.table_obj = build_schedule_table(
            stop_times, route_short_name=route_short_name, direction_id=direction_id)
        self._build_grid()

    def _build_grid(self):
        headers, rows = self.table_obj.to_grid(time_format="HH:MM:SS")
        self.headers = headers
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(rows))

        for r_idx, row_vals in enumerate(rows):
            for c_idx, val in enumerate(row_vals):
                item = QTableWidgetItem(str(val))
                if c_idx == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(r_idx, c_idx, item)

    def collect_changes(self):
        """
        Compara a grade atual com a original e devolve só o que mudou.

        Preserva a parada em si (arrival != departure em feed de terceiros):
        o tempo parado anda junto com a saída (decisão 118).

        :return: Tupla (alterados, grade_validacao, ilegiveis):
                 - alterados: linhas de stop_times prontas para apply_stop_times.
                 - grade_validacao: grade completa (alteradas + originais) para
                   validate_draft_times.
                 - ilegiveis: mensagens "trip / parada: valor" para horários
                   fora do formato HH:MM:SS.
        """
        alterados = []
        grade_validacao = []
        ilegiveis = []
        table_obj = self.table_obj
        headers = self.headers

        for r_idx in range(self.rowCount()):
            if r_idx >= len(table_obj.stops):
                continue
            stop_id = table_obj.stops[r_idx]["stop_id"]
            for c_idx in range(1, self.columnCount()):
                if c_idx >= len(headers):
                    continue
                trip_id = headers[c_idx]
                item = self.item(r_idx, c_idx)
                celula = table_obj.matrix.get((stop_id, trip_id))
                if not item or not celula:
                    continue

                val = item.text().strip()
                original = format_time_str(celula.get("departure_time"), fmt="HH:MM:SS")
                arr_original = celula.get("arrival_time") or celula.get("departure_time")
                seq = celula.get("stop_sequence")

                if not val or val == "-" or val == original:
                    grade_validacao.append({
                        "trip_id": trip_id, "stop_sequence": seq,
                        "arrival_time": arr_original,
                        "departure_time": celula.get("departure_time"),
                    })
                    continue

                try:
                    novo_s = to_seconds(val)
                except (ValueError, AttributeError, IndexError):
                    ilegiveis.append("{} / parada {}: '{}'".format(trip_id, stop_id, val))
                    continue

                parado_s = max(0, to_seconds(celula.get("departure_time")) - to_seconds(arr_original))
                novo_dep = from_seconds(novo_s)
                novo_arr = from_seconds(novo_s - parado_s)
                alterados.append({
                    "trip_id": trip_id, "stop_sequence": seq,
                    "arrival_time": novo_arr, "departure_time": novo_dep,
                })
                grade_validacao.append({
                    "trip_id": trip_id, "stop_sequence": seq,
                    "arrival_time": novo_arr, "departure_time": novo_dep,
                })

        return alterados, grade_validacao, ilegiveis
