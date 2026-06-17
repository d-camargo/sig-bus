# -*- coding: utf-8 -*-
"""
/***************************************************************************
 block_scene — engine gráfica do Diagrama de Blocos (SIG-Bus)
                                 A QGIS plugin
 View do MVC: traduz um Schedule (block_core) numa QGraphicsScene de itens
 clicáveis. Não conhece sqlite/gpkg — recebe o modelo e desenha.
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

from qgis.PyQt.QtCore import Qt, QRectF, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor, QFont, QPen
from qgis.PyQt.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from .block_core import fmt_hms

# Paleta qualitativa (mesma família usada no relatório), cor por linha.
_PALETTE = [
    '#E41A1C', '#377EB8', '#4DAF4A', '#984EA3', '#FF7F00',
    '#A65628', '#F781BF', '#1B9E77', '#666666', '#00CED1',
]

_DIR_LABEL = {'0': 'ida', '1': 'volta', '': 's/ sentido'}

# Geometria do desenho (px no espaço da cena; o zoom é da view)
LEFT_MARGIN = 96      # faixa dos rótulos de linha/sentido
TOP_MARGIN = 30       # eixo de tempo
LANE_HEIGHT = 24
LANE_GAP = 6
DEFAULT_PX_PER_SEC = 0.022   # ~79 px por hora

# Empilhamento dentro de uma faixa (linha, sentido): viagens que se sobrepõem
# no tempo vão para sub-linhas distintas, para não ficarem "encavaladas".
SUB_ROW_H = 16        # altura da barra de cada viagem
SUB_ROW_GAP = 3       # espaço vertical entre sub-linhas
LANE_VPAD = 5         # respiro acima/abaixo do conteúdo da faixa


class TimeAxisMapper:
    """Converte tempo(s)↔x(px) e índice de faixa→y(px)."""

    def __init__(self, t_min, t_max, px_per_sec=DEFAULT_PX_PER_SEC,
                 left=LEFT_MARGIN, top=TOP_MARGIN,
                 lane_h=LANE_HEIGHT, lane_gap=LANE_GAP):
        self.t_min = t_min
        self.t_max = t_max
        self.px_per_sec = px_per_sec
        self.left = left
        self.top = top
        self.lane_h = lane_h
        self.lane_gap = lane_gap

    def x(self, t):
        return self.left + (t - self.t_min) * self.px_per_sec

    def t_from_x(self, x):
        return self.t_min + (x - self.left) / self.px_per_sec

    def y(self, lane_idx):
        return self.top + lane_idx * (self.lane_h + self.lane_gap)

    def content_width(self):
        return (self.t_max - self.t_min) * self.px_per_sec


class TripItem(QGraphicsRectItem):
    """Barra de uma viagem. Clicável (emite scene.tripClicked) e com tooltip."""

    def __init__(self, trip, rect, color):
        super().__init__(rect)
        self.trip = trip
        self._base_brush = QBrush(color)
        self._base_pen = QPen(color.darker(140))
        self._base_pen.setWidthF(0.6)
        self.setBrush(self._base_brush)
        self.setPen(self._base_pen)
        self.setAcceptHoverEvents(True)
        self.setToolTip(self._tooltip())
        self.setCursor(Qt.PointingHandCursor)

    def _tooltip(self):
        t = self.trip
        return ('Linha {} ({})\n{} → {}\nViagem: {}'.format(
            t.route_short_name, _DIR_LABEL.get(t.direction_id, t.direction_id),
            fmt_hms(t.start_time_s), fmt_hms(t.end_time_s), t.trip_id))

    def set_highlighted(self, on):
        pen = QPen(QColor('#111111')) if on else self._base_pen
        if on:
            pen.setWidthF(1.6)
        self.setPen(pen)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(self._base_brush.color().lighter(115)))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(self._base_brush)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        sc = self.scene()
        if sc is not None and hasattr(sc, 'tripClicked'):
            sc.select_trip_item(self)
            sc.tripClicked.emit(self.trip)
        super().mousePressEvent(event)


class BlockScene(QGraphicsScene):
    """Cena do diagrama. set_schedule(schedule) (re)desenha tudo."""

    tripClicked = pyqtSignal(object)   # Trip

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mapper = None
        self._selected_item = None
        self._route_colors = {}
        self._block_colors = {}
        self._mode = 'trips'
        self._idle_segments = []
        self._trip_items = {}       # trip_id -> TripItem
        self._prev_trip = {}        # trip_id -> viagem anterior (mesma linha+sentido)
        self._headway_items = []    # itens do indicador de headway (seleção)

    # ------------------------------------------------------------------
    def select_trip_item(self, item):
        if self._selected_item is not None and self._selected_item is not item:
            try:
                self._selected_item.set_highlighted(False)
            except RuntimeError:
                pass   # item já removido
        self._selected_item = item
        item.set_highlighted(True)
        self._show_headway(item.trip)

    # ------------------------------------------------------------------
    def _clear_headway(self):
        for it in self._headway_items:
            try:
                self.removeItem(it)
            except RuntimeError:
                pass
        self._headway_items = []

    def _show_headway(self, trip):
        """Desenha (só no Modo Blocos) a pontilhada do headway da viagem
        selecionada: liga o início da viagem ANTERIOR da mesma linha+sentido
        ao início da viagem selecionada, com o valor em minutos."""
        self._clear_headway()
        if self._mode != 'blocks':
            return
        prev = self._prev_trip.get(trip.trip_id)
        if prev is None:
            return
        sel_item = self._trip_items.get(trip.trip_id)
        prev_item = self._trip_items.get(prev.trip_id)
        if sel_item is None or prev_item is None:
            return

        r_sel = sel_item.sceneBoundingRect()
        r_prev = prev_item.sceneBoundingRect()
        x1, y1 = r_prev.left(), r_prev.center().y()
        x2, y2 = r_sel.left(), r_sel.center().y()

        pen = QPen(QColor('#111111'))
        pen.setStyle(Qt.DashLine)
        pen.setWidthF(1.2)
        self._headway_items.append(self.addLine(x1, y1, x2, y2, pen))
        # marcadores verticais nos dois inícios
        for x, yc in ((x1, y1), (x2, y2)):
            self._headway_items.append(self.addLine(x, yc - 6, x, yc + 6, pen))

        mins = round((trip.start_time_s - prev.start_time_s) / 60.0)
        label = QGraphicsSimpleTextItem('headway {} min'.format(mins))
        f = QFont('Sans Serif', 8)
        f.setBold(True)
        label.setFont(f)
        label.setBrush(QBrush(QColor('#111111')))
        br = label.boundingRect()
        label.setPos((x1 + x2) / 2.0 - br.width() / 2.0, min(y1, y2) - 18)
        self.addItem(label)
        self._headway_items.append(label)
        for it in self._headway_items:
            it.setZValue(25)

    def _color_for_route(self, route_short_name):
        if route_short_name not in self._route_colors:
            idx = len(self._route_colors) % len(_PALETTE)
            self._route_colors[route_short_name] = QColor(_PALETTE[idx])
        return self._route_colors[route_short_name]

    def _color_for_block(self, block_id):
        """Cor por veículo (Modo Blocos). Distribui os matizes pelo ângulo
        áureo → cores bem distintas mesmo com dezenas de veículos."""
        if block_id not in self._block_colors:
            hue = int((len(self._block_colors) * 137.508) % 360)
            self._block_colors[block_id] = QColor.fromHsv(hue, 170, 200)
        return self._block_colors[block_id]

    # ------------------------------------------------------------------
    def set_schedule(self, schedule, px_per_sec=DEFAULT_PX_PER_SEC):
        """Desenha o Schedule. Dois modos:

        - 'trips':  faixa por (linha, sentido); viagens sobrepostas empilham
                    em sub-linhas.
        - 'blocks': faixa por veículo inferido; as viagens de um bloco não se
                    sobrepõem (uma sub-linha), com conectores pontilhados de
                    ociosidade entre viagens consecutivas.
        Em ambos: cor por linha, sentido pela espessura da barra."""
        self.clear()
        self._selected_item = None
        self._route_colors = {}
        self._block_colors = {}
        self._idle_segments = []
        self._trip_items = {}
        self._prev_trip = {}
        self._headway_items = []
        self._mode = getattr(schedule, 'mode', 'trips')

        trips = schedule.trips
        t_min, t_max = schedule.time_bounds
        self.mapper = TimeAxisMapper(t_min, t_max, px_per_sec)

        if not trips:
            txt = self.addText('Nenhuma viagem para exibir.')
            txt.setDefaultTextColor(QColor('#666666'))
            txt.setPos(LEFT_MARGIN, TOP_MARGIN)
            self.setSceneRect(0, 0, 400, 120)
            return

        # Mapa do headway: para cada viagem, a anterior da mesma (linha, sentido).
        by_linedir = {}
        for t in trips:
            by_linedir.setdefault((t.route_short_name, t.direction_id), []).append(t)
        for group in by_linedir.values():
            group.sort(key=lambda t: t.start_time_s)
            for i in range(1, len(group)):
                self._prev_trip[group[i].trip_id] = group[i - 1]

        if self._mode == 'blocks' and schedule.blocks:
            lanes = self._lanes_from_blocks(schedule.blocks)
        else:
            self._mode = 'trips'
            lanes = self._lanes_from_trips(trips)

        self._layout_and_draw(lanes, t_min, t_max)

    def _lanes_from_trips(self, trips):
        """[(label, lane_trips)] — uma faixa por (linha, sentido)."""
        by_lane = {}
        for t in trips:
            by_lane.setdefault(t.lane_key, []).append(t)
        keys = sorted(by_lane, key=lambda k: (self._route_sort(k[0]), k[1]))
        out = []
        for route, direction in keys:
            label = '{} ▸ {}'.format(route, _DIR_LABEL.get(direction, direction))
            out.append((label, by_lane[(route, direction)]))
        return out

    def _lanes_from_blocks(self, blocks):
        """[(label, block_trips)] — uma faixa por veículo, ordenada por início."""
        ordered = sorted(blocks, key=lambda b: (b.span[0], b.block_id))
        out = []
        for b in ordered:
            lines = sorted({t.route_short_name for t in b.trips},
                           key=self._route_sort)
            if len(lines) <= 2:
                label = '{} · {}'.format(b.block_id, ','.join(lines))
            else:
                label = '{} · {}+{}'.format(b.block_id, lines[0], len(lines) - 1)
            out.append((label, b.trips))
        return out

    def _layout_and_draw(self, lanes, t_min, t_max):
        """Empilha cada faixa em sub-linhas e desenha tudo. Comum aos 2 modos
        (blocos não se sobrepõem → uma sub-linha por faixa)."""
        m = self.mapper
        lane_boxes = []     # (label, y_top, lane_h)
        placements = []     # (trip, y)
        y = m.top + LANE_VPAD
        for label, lane_trips in lanes:
            rows = self._assign_rows(lane_trips)
            n_rows = (max(r for _, r in rows) + 1) if rows else 1
            lane_h = n_rows * SUB_ROW_H + (n_rows - 1) * SUB_ROW_GAP
            for trip, sub in rows:
                placements.append((trip, y + sub * (SUB_ROW_H + SUB_ROW_GAP)))
            if self._mode == 'blocks':
                self._collect_idle(lane_trips, y)
            lane_boxes.append((label, y, lane_h))
            y += lane_h + 2 * LANE_VPAD
        total_h = y
        right = m.x(t_max)

        self._draw_lanes(lane_boxes, right)
        self._draw_time_axis(t_min, t_max, total_h)
        self._draw_idle()
        self._draw_trips(placements)

        self.setSceneRect(0, 0, right + 16, total_h + 8)

    def _collect_idle(self, lane_trips, y):
        """Registra os trechos ociosos (gaps) entre viagens consecutivas de um
        veículo, para desenhar o conector pontilhado."""
        ordered = sorted(lane_trips, key=lambda t: t.start_time_s)
        yc = y + SUB_ROW_H / 2.0
        for a, b in zip(ordered, ordered[1:]):
            self._idle_segments.append(
                (self.mapper.x(a.end_time_s), yc,
                 self.mapper.x(b.start_time_s), yc))

    def _draw_idle(self):
        if not self._idle_segments:
            return
        pen = QPen(QColor('#9aa6b2'))
        pen.setStyle(Qt.DotLine)
        pen.setWidthF(0.8)
        for x0, y0, x1, y1 in self._idle_segments:
            if x1 > x0:
                line = self.addLine(x0, y0, x1, y1, pen)
                line.setZValue(0)
        self._idle_segments = []

    @staticmethod
    def _assign_rows(lane_trips):
        """Empacota as viagens de uma faixa em sub-linhas (greedy interval
        packing). Devolve [(trip, sub_row)]: a viagem reaproveita uma sub-linha
        cuja última viagem já terminou; senão, abre uma nova."""
        ordered = sorted(lane_trips,
                         key=lambda t: (t.start_time_s, t.end_time_s))
        row_end = []        # fim (s) da última viagem de cada sub-linha
        out = []
        for t in ordered:
            placed = False
            for i, end in enumerate(row_end):
                if t.start_time_s >= end:
                    row_end[i] = t.end_time_s
                    out.append((t, i))
                    placed = True
                    break
            if not placed:
                row_end.append(t.end_time_s)
                out.append((t, len(row_end) - 1))
        return out

    def _bar_color(self, trip):
        """Cor da barra. No Modo Blocos: por veículo (cada bloco uma cor). No
        Modo Viagens: por linha. O sentido é sempre dado pela ESPESSURA da
        barra (ver _draw_trips), não pela cor."""
        if self._mode == 'blocks' and trip.block_id:
            return self._color_for_block(trip.block_id)
        return self._color_for_route(trip.route_short_name)

    @staticmethod
    def _route_sort(route_short_name):
        try:
            return (0, int(route_short_name), '')
        except (ValueError, TypeError):
            return (1, 0, str(route_short_name))

    # ------------------------------------------------------------------
    def _draw_lanes(self, lane_boxes, right):
        m = self.mapper
        label_font = QFont('Sans Serif', 8)
        for idx, (label_text, y_top, lane_h) in enumerate(lane_boxes):
            top = y_top - LANE_VPAD
            height = lane_h + 2 * LANE_VPAD
            # Fundo alternado para legibilidade
            bg = QGraphicsRectItem(QRectF(m.left, top, right - m.left, height))
            bg.setBrush(QBrush(QColor('#f4f6f8' if idx % 2 == 0 else '#e9edf1')))
            bg.setPen(QPen(Qt.NoPen))
            bg.setZValue(-10)
            self.addItem(bg)

            label = QGraphicsSimpleTextItem(label_text)
            label.setFont(label_font)
            label.setBrush(QBrush(QColor('#222222')))
            br = label.boundingRect()
            label.setPos(m.left - 8 - br.width(),
                         top + (height - br.height()) / 2)
            self.addItem(label)

    def _draw_time_axis(self, t_min, t_max, total_h):
        m = self.mapper
        axis_font = QFont('Sans Serif', 7)
        grid_pen = QPen(QColor('#c8d0d8'))
        grid_pen.setWidthF(0.5)

        first_h = int(t_min // 3600)
        last_h = int(t_max // 3600) + 1
        for h in range(first_h, last_h + 1):
            x = m.x(h * 3600)
            if x < m.left - 0.5:
                continue
            line = self.addLine(x, m.top, x, total_h, grid_pen)
            line.setZValue(-5)
            lbl = QGraphicsSimpleTextItem('{}h'.format(h))
            lbl.setFont(axis_font)
            lbl.setBrush(QBrush(QColor('#555555')))
            lbl.setPos(x + 2, m.top - 16)
            self.addItem(lbl)
        # Linha de base do eixo
        base_pen = QPen(QColor('#8a97a3'))
        base_pen.setWidthF(0.8)
        self.addLine(m.left, m.top, m.x(t_max), m.top, base_pen)

    def _draw_trips(self, placements):
        m = self.mapper
        for trip, y in placements:
            x0 = m.x(trip.start_time_s)
            x1 = m.x(trip.end_time_s)
            w = max(3.0, x1 - x0)   # garante clicabilidade de viagens curtas
            # Sentido pela espessura: ida cheia, volta mais fina (centralizada).
            if trip.direction_id == '1':
                h = SUB_ROW_H * 0.5
                y_bar = y + (SUB_ROW_H - h) / 2.0
            else:
                h = float(SUB_ROW_H)
                y_bar = float(y)
            rect = QRectF(x0, y_bar, w, h)
            item = TripItem(trip, rect, self._bar_color(trip))
            item.setZValue(10)
            self.addItem(item)
            self._trip_items[trip.trip_id] = item
