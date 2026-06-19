# -*- coding: utf-8 -*-
"""
/***************************************************************************
 BlockDiagramDialog — Diagrama de Blocos (SIG-Bus)
                                 A QGIS plugin
 Controller do MVC: orquestra a leitura (block_core) e o desenho
 (block_scene/block_view). UI montada em Python (sem .ui).
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

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from qgis.utils import iface

from .block_core import (
    BlockDiagramTask,
    BlockParams,
    ScheduleReader,
    fmt_hms,
    DAY_MAX_S,
)
from .block_scene import BlockScene, _DIR_LABEL
from .block_view import BlockView


def _terminal_dest(scene, trip):
    """Texto do terminal de destino: nome do headsign + sigla de 3 letras
    (ex.: 'ESTACAO DIAMANTE (DIA)'). Sem headsign, devolve '—'."""
    name = trip.trip_headsign or '—'
    code = scene.terminal_code(trip.trip_headsign)
    return '{} ({})'.format(name, code) if code else name


class BlockDiagramDialog(QWidget):
    """Janela do Diagrama de Blocos (Modo Viagens — fatia vertical).

    Recebe o caminho do GeoPackage do GTFS; lista as linhas, monta o diagrama
    em segundo plano e permite clicar nas viagens para ver detalhes."""

    def __init__(self, gpkg_path, parent=None):
        super().__init__(parent, Qt.Window)
        self.gpkg_path = gpkg_path
        self.reader = ScheduleReader(gpkg_path)
        self._task = None
        self._schedule = None

        self.setWindowTitle('SIG-Bus — Diagrama de Blocos')
        self.resize(1100, 640)
        self._build_ui()
        self._populate_routes()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        # --- Painel de controles (esquerda) ---------------------------
        controls = QWidget()
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(6, 6, 6, 6)

        cl.addWidget(QLabel('Linhas (seleção múltipla):'))
        self.route_list = QListWidget()
        self.route_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.route_list.itemSelectionChanged.connect(self._on_routes_changed)
        cl.addWidget(self.route_list, 1)

        form = QFormLayout()
        self.service_combo = QComboBox()
        form.addRow('Serviço (dia):', self.service_combo)

        dir_box = QHBoxLayout()
        self.chk_ida = QCheckBox('Ida')
        self.chk_volta = QCheckBox('Volta')
        self.chk_ida.setChecked(True)
        self.chk_volta.setChecked(True)
        dir_box.addWidget(self.chk_ida)
        dir_box.addWidget(self.chk_volta)
        form.addRow('Sentido:', self._wrap(dir_box))

        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 30)
        self.spin_start.setValue(0)
        self.spin_start.setSuffix(' h')
        self.spin_end = QSpinBox()
        self.spin_end.setRange(0, 30)
        self.spin_end.setValue(30)
        self.spin_end.setSuffix(' h')
        win_box = QHBoxLayout()
        win_box.addWidget(self.spin_start)
        win_box.addWidget(QLabel('até'))
        win_box.addWidget(self.spin_end)
        form.addRow('Janela:', self._wrap(win_box))
        cl.addLayout(form)

        mode_group = QGroupBox('Modo')
        mg = QVBoxLayout(mode_group)
        self.radio_viagens = QRadioButton('Viagens (tempo × linha/sentido)')
        self.radio_blocos = QRadioButton('Blocos / frota (estimado)')
        self.radio_viagens.setChecked(True)
        self.radio_blocos.setToolTip(
            'Infere veículos encadeando viagens (o feed não tem block_id). '
            'Estimativa, não a escala oficial da operadora.')
        mg.addWidget(self.radio_viagens)
        mg.addWidget(self.radio_blocos)

        # Parâmetros do Modo Blocos (visíveis só quando 'Blocos' está marcado)
        self.block_params_box = QWidget()
        bp = QFormLayout(self.block_params_box)
        bp.setContentsMargins(0, 4, 0, 0)
        self.spin_lay_min = QSpinBox()
        self.spin_lay_min.setRange(0, 120)
        self.spin_lay_min.setValue(5)
        self.spin_lay_min.setSuffix(' min')
        self.spin_lay_max = QSpinBox()
        self.spin_lay_max.setRange(1, 240)
        self.spin_lay_max.setValue(45)
        self.spin_lay_max.setSuffix(' min')
        self.chk_deadhead = QCheckBox('Permitir deadhead\n(encadear terminais diferentes)')
        self.chk_relaxed = QCheckBox('Relaxado (só tempo;\nfrota mínima teórica)')
        # Estimativa do tempo de retorno (deadhead) pela distância entre
        # terminais: velocidade do veículo vazio × fator de sinuosidade.
        self.spin_dh_speed = QDoubleSpinBox()
        self.spin_dh_speed.setRange(5.0, 80.0)
        self.spin_dh_speed.setSingleStep(1.0)
        self.spin_dh_speed.setValue(25.0)
        self.spin_dh_speed.setSuffix(' km/h')
        self.spin_dh_speed.setToolTip(
            'Velocidade do veículo vazio no retorno entre terminais.')
        self.spin_circuity = QDoubleSpinBox()
        self.spin_circuity.setRange(1.0, 3.0)
        self.spin_circuity.setSingleStep(0.1)
        self.spin_circuity.setValue(1.4)
        self.spin_circuity.setToolTip(
            'Impedância: razão entre o trajeto real e a distância em reta '
            'entre os terminais.')
        bp.addRow('Layover mín.:', self.spin_lay_min)
        bp.addRow('Layover máx.:', self.spin_lay_max)
        bp.addRow(self.chk_deadhead)
        bp.addRow('Veloc. retorno:', self.spin_dh_speed)
        bp.addRow('Sinuosidade:', self.spin_circuity)
        bp.addRow(self.chk_relaxed)
        mg.addWidget(self.block_params_box)
        self.block_params_box.setVisible(False)
        self.radio_blocos.toggled.connect(self.block_params_box.setVisible)
        # Os campos de deadhead só fazem sentido com 'Permitir deadhead'.
        self.spin_dh_speed.setEnabled(False)
        self.spin_circuity.setEnabled(False)
        self.chk_deadhead.toggled.connect(self.spin_dh_speed.setEnabled)
        self.chk_deadhead.toggled.connect(self.spin_circuity.setEnabled)
        cl.addWidget(mode_group)

        self.btn_gerar = QPushButton('Gerar diagrama')
        self.btn_gerar.clicked.connect(self._generate)
        cl.addWidget(self.btn_gerar)

        btn_row = QHBoxLayout()
        self.btn_export = QPushButton('Exportar…')
        self.btn_export.clicked.connect(self._export)
        self.btn_export.setEnabled(False)
        self.btn_reset = QPushButton('Reset zoom')
        self.btn_reset.clicked.connect(lambda: self.view.reset_zoom())
        btn_row.addWidget(self.btn_export)
        btn_row.addWidget(self.btn_reset)
        cl.addLayout(btn_row)

        controls.setMaximumWidth(280)
        splitter.addWidget(controls)

        # --- Diagrama (centro) ----------------------------------------
        self.scene = BlockScene()
        self.scene.tripClicked.connect(self._show_details)
        self.view = BlockView()
        self.view.setScene(self.scene)
        splitter.addWidget(self.view)

        # --- Detalhes (direita) ---------------------------------------
        self.details = QTextBrowser()
        self.details.setMinimumWidth(220)
        self.details.setMaximumWidth(320)
        self.details.setHtml(self._details_placeholder())
        splitter.addWidget(self.details)

        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 600, 240])

        self.status = QLabel('Selecione linhas e clique em “Gerar diagrama”.')
        self.status.setStyleSheet('color: #444; padding: 2px 4px;')
        root.addWidget(self.status)

    @staticmethod
    def _wrap(layout):
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    # ------------------------------------------------------------------
    def _populate_routes(self):
        try:
            routes = self.reader.list_routes()
        except Exception as e:   # noqa: BLE001
            self.status.setText('Erro ao listar linhas: {}'.format(e))
            return
        self.route_list.clear()
        self.route_list.addItems(routes)
        self.status.setText('{} linhas disponíveis.'.format(len(routes)))

    def _on_routes_changed(self):
        names = [i.text() for i in self.route_list.selectedItems()]
        self.service_combo.clear()
        self.service_combo.addItem('Todos os serviços', None)
        if not names:
            return
        try:
            for svc in self.reader.list_services(names):
                self.service_combo.addItem(svc, svc)
        except Exception:   # noqa: BLE001
            pass

    def _collect_directions(self):
        dirs = set()
        if self.chk_ida.isChecked():
            dirs.add('0')
        if self.chk_volta.isChecked():
            dirs.add('1')
        return dirs

    # ------------------------------------------------------------------
    def _generate(self):
        names = [i.text() for i in self.route_list.selectedItems()]
        if not names:
            self.status.setText('Escolha ao menos uma linha.')
            return
        dirs = self._collect_directions()
        if not dirs:
            self.status.setText('Marque Ida e/ou Volta.')
            return
        h0, h1 = self.spin_start.value(), self.spin_end.value()
        if h1 <= h0:
            self.status.setText('A janela de tempo é inválida (fim ≤ início).')
            return

        svc = self.service_combo.currentData()
        service_ids = [svc] if svc else None

        mode = 'blocks' if self.radio_blocos.isChecked() else 'trips'
        params = None
        if mode == 'blocks':
            lmin = self.spin_lay_min.value() * 60
            lmax = self.spin_lay_max.value() * 60
            if lmax <= lmin:
                self.status.setText('Layover máx. deve ser maior que o mín.')
                return
            params = BlockParams(
                layover_min_s=lmin, layover_max_s=lmax,
                allow_deadhead=self.chk_deadhead.isChecked(),
                relaxed=self.chk_relaxed.isChecked(),
                deadhead_speed_kmh=self.spin_dh_speed.value(),
                circuity_factor=self.spin_circuity.value())

        self.btn_gerar.setEnabled(False)
        self.status.setText('Montando diagrama em segundo plano…')

        self._task = BlockDiagramTask(
            self.gpkg_path, names, service_ids=service_ids,
            directions=dirs, t_min=h0 * 3600, t_max=min(h1 * 3600, DAY_MAX_S),
            mode=mode, params=params)
        self._task.finishedOk.connect(self._on_schedule)
        self._task.failed.connect(self._on_failed)
        QgsApplication.taskManager().addTask(self._task)

    def _on_schedule(self, schedule):
        self._schedule = schedule
        self.btn_gerar.setEnabled(True)
        self.scene.set_schedule(schedule)
        # Enquadra tudo: garante que ida e volta apareçam (faixas de ida muito
        # altas, de linhas movimentadas, escondiam a volta abaixo da tela).
        self.view.fit_all()
        n = len(schedule.trips)
        self.btn_export.setEnabled(n > 0)
        if schedule.mode == 'blocks':
            fleet = schedule.fleet_size or 0
            msg = '{} viagens · {} veículos (blocos estimados).'.format(n, fleet)
        else:
            n_lanes = len({t.lane_key for t in schedule.trips})
            msg = '{} viagens em {} faixa(s) (linha × sentido).'.format(n, n_lanes)
        if schedule.warnings:
            msg += '  ⚠ ' + ' '.join(schedule.warnings)
        self.status.setText(msg)

    def _on_failed(self, message):
        self.btn_gerar.setEnabled(True)
        self.status.setText('Falha: {}'.format(message))
        if iface is not None:
            iface.messageBar().pushMessage(
                'SIG-Bus', 'Diagrama: {}'.format(message), duration=8)

    # ------------------------------------------------------------------
    def _show_details(self, trip):
        rows = [
            ('Linha', trip.route_short_name),
            ('Sentido', _DIR_LABEL.get(trip.direction_id, trip.direction_id)),
            ('Bloco/veículo', trip.block_id or '—'),
            ('Início', fmt_hms(trip.start_time_s)),
            ('Fim', fmt_hms(trip.end_time_s)),
            ('Duração', fmt_hms(trip.duration_s)),
            ('Nº de paradas', str(trip.n_stops)),
            # Terminal de destino = trip_headsign (nome canônico do feed) +
            # sigla de 3 letras (convenção própria, gerada no diagrama). O
            # GTFS da BHTrans não tem código de terminal; os stop_id de
            # origem/destino ficam abaixo como referência técnica.
            ('Terminal destino', _terminal_dest(self.scene, trip)),
            ('Parada origem (id)', trip.start_stop_id),
            ('Parada destino (id)', trip.end_stop_id),
            ('service_id', trip.service_id),
            ('shape_id', trip.shape_id),
            ('trip_id', trip.trip_id),
        ]
        html = ['<h3 style="margin:4px 0">Viagem</h3>',
                '<table cellspacing="0" cellpadding="3">']
        for k, v in rows:
            html.append(
                '<tr><td style="color:#666">{}</td>'
                '<td><b>{}</b></td></tr>'.format(k, v))
        html.append('</table>')
        self.details.setHtml(''.join(html))

    @staticmethod
    def _details_placeholder():
        return ('<p style="color:#888">Clique numa viagem do diagrama para '
                'ver os detalhes.</p>'
                '<p style="color:#aaa;font-size:11px">Roda do mouse: zoom · '
                'Botão do meio: arrastar.</p>')

    # ------------------------------------------------------------------
    def _export(self):
        if self._schedule is None:
            return
        path, sel = QFileDialog.getSaveFileName(
            self, 'Exportar diagrama', os.path.dirname(self.gpkg_path or ''),
            'PNG (*.png);;SVG (*.svg)')
        if not path:
            return
        if path.lower().endswith('.svg') or 'svg' in sel.lower():
            if not path.lower().endswith('.svg'):
                path += '.svg'
            ok = self.view.export_svg(path)
            if not ok:
                self.status.setText('SVG indisponível (QtSvg ausente). Use PNG.')
                return
        else:
            if not path.lower().endswith('.png'):
                path += '.png'
            ok = self.view.export_png(path)
        self.status.setText(
            'Exportado: {}'.format(path) if ok else 'Falha ao exportar.')
