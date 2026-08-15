# -*- coding: utf-8 -*-
"""
/***************************************************************************
 schedule_editor_widget — Editor de horários do SIG-Bus
                                  A QGIS plugin
 Editor único das duas telas de horário: a matriz paradas × viagens em cima e
 o diagrama de blocos embaixo, sobre a mesma lista de stop_times em
 memória. Usado pela página "Horários" do assistente "Construir GTFS" e pela
 janela "Ajustar horários" da aba "Edição GTFS".
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

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSpinBox,
    QPushButton,
    QSplitter,
)

from .block_view import BlockView
from .block_scene import BlockScene
from .schedule_grid_widget import ScheduleGridWidget
from .ui_geometry import divisao_vertical
from .schedule_edit_core import (
    diff_stop_times,
    from_seconds,
    headways,
    schedule_from_draft,
    shift_trip,
    shift_trip_endpoint,
    to_seconds,
    trips_from_stop_times,
)


class ScheduleEditorWidget(QWidget):
    """
    Editor de horários: a matriz (`ScheduleGridWidget`) em cima e o diagrama
    (`BlockScene`/`BlockView`) embaixo, empilhados num `QSplitter` vertical
    (decisão 155), do mesmo sentido, sobre um único rascunho de `stop_times`
    em memória.

    Há um caminho de escrita só: tanto os atalhos do diagrama ('>'/'<'/'+'/'-')
    quanto a célula editada na matriz desembocam em `shift_trip` /
    `shift_trip_endpoint` do `schedule_edit_core`. Depois de cada mudança o
    diagrama é redesenhado preservando o enquadramento e a matriz é remontada a
    partir do rascunho.

    Quem grava usa `changed_rows()` — o diff contra o `stop_times` como ele
    chegou —, nunca a grade inteira.
    """

    scheduleChanged = pyqtSignal()

    def __init__(self, stop_times=None, route_short_name="", direction_id="0",
                 trip_headsign="", service_id="", stops=None, parent=None):
        super().__init__(parent)
        self._route_short_name = route_short_name or ""
        self._direction_id = direction_id if direction_id is not None else "0"
        self._trip_headsign = trip_headsign or ""
        self._service_id = service_id or ""
        self._stops = list(stops or [])
        self._original = [dict(st) for st in (stop_times or [])]
        self._draft = [dict(st) for st in (stop_times or [])]
        self._ilegiveis = {}
        self._rebuilding = False
        self._syncing = False
        self._desenhou = False
        self._trip_selecionada = None
        self._endpoint_selecionado = None

        self._build_ui()
        self._redraw(force_fit=True)

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------
    def _build_ui(self):
        layout_main = QVBoxLayout(self)
        layout_main.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setChildrenCollapsible(False)
        layout_main.addWidget(self.splitter)

        self.painel_diagrama = QWidget()
        layout_diagrama = QVBoxLayout(self.painel_diagrama)
        layout_diagrama.setContentsMargins(0, 0, 4, 0)

        linha_ajuste = QHBoxLayout()
        self.spin_schedule_step = QSpinBox()
        self.spin_schedule_step.setRange(1, 30)
        self.spin_schedule_step.setValue(15)
        self.spin_schedule_step.setSuffix(" minutos")
        self.btn_fit_all = QPushButton("Enquadrar tudo")
        linha_ajuste.addWidget(QLabel("Passo:"))
        linha_ajuste.addWidget(self.spin_schedule_step)
        linha_ajuste.addWidget(self.btn_fit_all)
        linha_ajuste.addStretch()
        layout_diagrama.addLayout(linha_ajuste)

        # Sem quebra de linha, é esta frase que dita a largura mínima do painel
        # e alargaria a janela inteira (decisão 150).
        self.label_instrucoes = QLabel(
            "Clique numa viagem (metade esquerda = saída, metade direita = chegada). "
            "Atalhos: <b>&gt;</b>/<b>&lt;</b> movem só a saída ou a chegada; "
            "<b>+</b>/<b>-</b> movem a viagem inteira.")
        self.label_instrucoes.setWordWrap(True)
        layout_diagrama.addWidget(self.label_instrucoes)

        self.schedule_scene = BlockScene()
        self.schedule_view = BlockView()
        self.schedule_view.setScene(self.schedule_scene)
        self.schedule_view.setMinimumHeight(200)
        self.schedule_view.setMinimumWidth(320)
        layout_diagrama.addWidget(self.schedule_view, 1)

        self.label_schedule_status = QLabel("")
        layout_diagrama.addWidget(self.label_schedule_status)

        self.btn_fit_all.clicked.connect(self.schedule_view.fit_all)
        self.schedule_view.nudgeKeyPressed.connect(self._on_nudge_key)
        self.schedule_scene.tripClicked.connect(self._on_trip_clicked)

        self.grid = ScheduleGridWidget(
            self._draft,
            route_short_name=self._route_short_name,
            direction_id=self._direction_id,
            stops=self._stops)
        self.grid.itemChanged.connect(self._on_cell_edited)
        self.grid.currentCellChanged.connect(self._on_grid_current_cell_changed)

        self.grid.setMinimumHeight(140)

        self.splitter.addWidget(self.grid)
        self.splitter.addWidget(self.painel_diagrama)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes(divisao_vertical(620))

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def stop_times(self):
        """Rascunho corrente — cópia, para o chamador não mexer no de dentro."""
        return [dict(st) for st in self._draft]

    def set_stop_times(self, stop_times, force_fit=True):
        """
        Troca o rascunho inteiro (é o caminho de 'restaurar frequência
        regular' do assistente). O snapshot usado por `changed_rows()` não
        muda: ele é o `stop_times` como chegou do feed.
        """
        self._draft = [dict(st) for st in (stop_times or [])]
        self._redraw(force_fit=force_fit)

    def set_context(self, route_short_name=None, direction_id=None,
                    trip_headsign=None, service_id=None):
        """
        Atualiza os rótulos que o diagrama usa (linha, sentido, headsign e
        serviço). O assistente preenche isso conforme o usuário avança; só
        vale a partir do próximo redesenho.
        """
        if route_short_name is not None:
            self._route_short_name = route_short_name
        if direction_id is not None:
            self._direction_id = direction_id
        if trip_headsign is not None:
            self._trip_headsign = trip_headsign
        if service_id is not None:
            self._service_id = service_id

    def trip_ids(self):
        """Os `trip_id` do rascunho, na ordem das colunas da matriz."""
        return self.grid.table_obj.column_trip_ids()

    def changed_rows(self):
        """Só as linhas cujo horário mudou em relação ao que veio do feed."""
        return diff_stop_times(self._original, self._draft)

    def validation_rows(self):
        """Rascunho inteiro, para `validate_draft_times`."""
        return [dict(st) for st in self._draft]

    def illegible_times(self):
        """Mensagens 'viagem / parada: valor' das células fora de HH:MM:SS."""
        return list(self._ilegiveis.values())

    # ------------------------------------------------------------------
    # Escrita: diagrama e matriz caem nas mesmas funções puras
    # ------------------------------------------------------------------
    def _on_nudge_key(self, tecla):
        """'+'/'-' deslocam a viagem inteira; '>'/'<' só o extremo
        selecionado (decisão 78). O passo vem do QSpinBox."""
        trip_item = self.schedule_scene._selected_item
        if trip_item is None:
            self.label_schedule_status.setText("Selecione uma viagem no diagrama.")
            return

        trip_id = trip_item.trip.trip_id
        endpoint = self.schedule_scene.selected_endpoint or 'first'
        passo_s = self.spin_schedule_step.value() * 60
        delta_s = passo_s if tecla in ('>', '+') else -passo_s

        if tecla in ('>', '<'):
            self._draft = shift_trip_endpoint(self._draft, trip_id, endpoint, delta_s)
        else:
            self._draft = shift_trip(self._draft, trip_id, delta_s)

        self._redraw()

        self._update_status(trip_id)
        self.scheduleChanged.emit()

    def _on_trip_clicked(self, trip):
        """Sincroniza a seleção do diagrama para a tabela (decisão 157)."""
        if self._rebuilding or self._syncing:
            return

        self._syncing = True
        try:
            trip_id = trip.trip_id
            trip_ids = self.grid.table_obj.column_trip_ids()
            if trip_id in trip_ids:
                coluna = trip_ids.index(trip_id) + 1
                linha_atual_ou_0 = max(0, self.grid.currentRow()) if self.grid.rowCount() > 0 else 0
                self.grid.setCurrentCell(linha_atual_ou_0, coluna)
                self._trip_selecionada = trip_id
                self._endpoint_selecionado = self.schedule_scene.selected_endpoint
                self._update_status(trip_id)
        finally:
            self._syncing = False

    def _on_grid_current_cell_changed(self, row, col, prev_row, prev_col):
        """Sincroniza a seleção da tabela para o diagrama (decisão 157)."""
        if self._rebuilding or self._syncing:
            return

        if col < 1:
            return

        self._syncing = True
        try:
            trip_ids = self.grid.table_obj.column_trip_ids()
            c_idx = col - 1
            if 0 <= c_idx < len(trip_ids):
                trip_id = trip_ids[c_idx]
                item = self.schedule_scene._trip_items.get(trip_id)
                if item is not None:
                    endpoint = self.schedule_scene.selected_endpoint or self._endpoint_selecionado or 'first'
                    self.schedule_scene.select_trip_item(item, endpoint=endpoint)
                    self._trip_selecionada = trip_id
                    self._endpoint_selecionado = self.schedule_scene.selected_endpoint
                    self._update_status(trip_id)
        finally:
            self._syncing = False

    def _on_cell_edited(self, item):
        """
        Célula editada desloca a viagem inteira (decisão 112): o usuário
        digita o horário que quer naquela parada e o resto da viagem
        acompanha, preservando os tempos de percurso.
        """
        if self._rebuilding:
            return

        c_idx = item.column()
        r_idx = item.row()
        if c_idx < 1:
            return

        table_obj = self.grid.table_obj
        trip_ids = table_obj.column_trip_ids()
        if c_idx - 1 >= len(trip_ids) or r_idx >= len(table_obj.stops):
            return

        trip_id = trip_ids[c_idx - 1]
        stop_id = table_obj.stops[r_idx]["stop_id"]
        celula = table_obj.matrix.get((stop_id, trip_id))
        if not celula:
            # Célula '-': a viagem não passa nessa parada. Digitar aqui não
            # cria parada nova (decisão 118).
            return

        texto = (item.text() or "").strip()
        chave = (trip_id, stop_id)
        try:
            novo_s = to_seconds(texto)
        except (ValueError, AttributeError, IndexError):
            self._ilegiveis[chave] = "{} / parada {}: '{}'".format(trip_id, stop_id, texto)
            return
        self._ilegiveis.pop(chave, None)

        delta_s = novo_s - to_seconds(celula.get("departure_time"))
        if delta_s == 0:
            return

        self._draft = shift_trip(self._draft, trip_id, delta_s)
        self._redraw()
        self._update_status(trip_id)
        self.scheduleChanged.emit()

    # ------------------------------------------------------------------
    # Redesenho
    # ------------------------------------------------------------------
    def _redraw(self, force_fit=False):
        """Redesenha o diagrama e remonta a matriz a partir do rascunho.

        O enquadramento é preservado (decisões 109-111): `fit_all()` só no
        primeiro desenho e quando o chamador pede."""
        # A cena é a fonte da verdade da seleção: os dois slots de sincronia
        # (decisão 157) já deixam diagrama e matriz apontando para a mesma
        # viagem antes de qualquer redesenho.
        if self.schedule_scene._selected_item is not None:
            self._trip_selecionada = self.schedule_scene._selected_item.trip.trip_id
            self._endpoint_selecionado = self.schedule_scene.selected_endpoint

        self._rebuilding = True
        try:
            self._ilegiveis.clear()
            self.grid.set_stop_times(self._draft, stops=self._stops)

            if not self._draft:
                self.schedule_scene.clear()
                self._desenhou = False
                self._trip_selecionada = None
                self._endpoint_selecionado = None
                return

            state = self.schedule_view.viewport_state()
            sched = schedule_from_draft(
                self._draft,
                route_short_name=self._route_short_name or "route",
                direction_id=self._direction_id,
                service_id=self._service_id,
                trip_headsign=self._trip_headsign,
            )
            self.schedule_scene.set_schedule(sched)

            if force_fit or not self._desenhou or not state:
                self.schedule_view.fit_all()
            else:
                self.schedule_view.restore_viewport(state)
            self._desenhou = True

            if self._trip_selecionada:
                item = self.schedule_scene._trip_items.get(self._trip_selecionada)
                if item is not None:
                    endpoint = self._endpoint_selecionado or 'first'
                    self.schedule_scene.select_trip_item(item, endpoint=endpoint)
                else:
                    self._trip_selecionada = None
                    self._endpoint_selecionado = None

                trip_ids = self.grid.table_obj.column_trip_ids()
                if self._trip_selecionada and self._trip_selecionada in trip_ids:
                    col_idx = trip_ids.index(self._trip_selecionada) + 1
                    row_idx = max(0, self.grid.currentRow()) if self.grid.rowCount() > 0 else 0
                    self.grid.setCurrentCell(row_idx, col_idx)
        finally:
            self._rebuilding = False

    def _update_status(self, trip_id):
        atual = next((v for v in trips_from_stop_times(self._draft)
                      if v["trip_id"] == trip_id), None)
        if atual is None:
            return
        texto = "Viagem {} · saída {} · chegada {}".format(
            atual["trip_id"], from_seconds(atual["start_s"]), from_seconds(atual["end_s"]))
        hw = headways(self._draft).get(trip_id)
        if hw is not None:
            texto += " · headway {} min".format(round(hw / 60.0))
        self.label_schedule_status.setText(texto)
