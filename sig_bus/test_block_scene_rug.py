# -*- coding: utf-8 -*-
"""Régua de saídas do Diagrama de Blocos (passos 150-152, decisões 97-101)."""
from qgis.PyQt.QtWidgets import (QApplication, QGraphicsLineItem,
                                 QGraphicsSimpleTextItem)

from sig_bus.block_core import Schedule, Trip
from sig_bus.block_scene import (BlockScene, RUG_BAND_GAP, RUG_H, RUG_TICK_H,
                                 RUG_TOP_GAP, departure_ticks)

_app = QApplication.instance() or QApplication([])


def _trip(trip_id, start_s, direction_id='0', dur_s=3600):
    return Trip(trip_id=trip_id, route_short_name='101',
                direction_id=direction_id, service_id='s1', shape_id='',
                trip_headsign='Destino A', start_time_s=start_s,
                end_time_s=start_s + dur_s, start_stop_id='p1',
                end_stop_id='p2', n_stops=10)


def _rug_lines(scene):
    return [it for it in scene._departure_items
            if isinstance(it, QGraphicsLineItem)]


def _rug_labels(scene):
    return [it.text() for it in scene._departure_items
            if isinstance(it, QGraphicsSimpleTextItem)]


# --------------------------------------------------------------- função pura

def test_departure_ticks_uma_entrada_por_viagem():
    trips = [_trip('t1', 28800), _trip('t2', 29700), _trip('t3', 30600)]
    assert len(departure_ticks(trips)) == 3


def test_departure_ticks_banda_por_sentido():
    ticks = departure_ticks([_trip('ida', 28800, '0'),
                             _trip('volta', 29700, '1')])
    assert ticks == [(28800, 'ida'), (29700, 'volta')]


def test_departure_ticks_direction_vazio_cai_em_ida():
    """direction_id vazio é 'ida', não uma terceira banda (decisão 98)."""
    assert departure_ticks([_trip('t1', 28800, '')]) == [(28800, 'ida')]


def test_departure_ticks_ordenado_por_horario():
    ticks = departure_ticks([_trip('t3', 30600), _trip('t1', 28800),
                             _trip('t2', 29700)])
    assert [t for t, _ in ticks] == [28800, 29700, 30600]


def test_departure_ticks_lista_vazia():
    assert departure_ticks([]) == []


# ---------------------------------------------------------------------- cena

def test_regua_um_traco_por_viagem():
    """3 idas + 2 voltas → 5 traços, cada um no x da própria saída."""
    trips = [_trip('i1', 25200, '0'), _trip('i2', 28800, '0'),
             _trip('i3', 32400, '0'), _trip('v1', 27000, '1'),
             _trip('v2', 30600, '1')]
    scene = BlockScene()
    scene.set_schedule(Schedule(trips=trips, mode='trips'))

    lines = _rug_lines(scene)
    assert len(lines) == 5

    xs = sorted(round(ln.line().x1(), 3) for ln in lines)
    esperado = sorted(round(scene.mapper.x(t.start_time_s), 3) for t in trips)
    assert xs == esperado


def test_regua_ida_acima_de_volta():
    """Toda ida fica estritamente acima de toda volta, e nenhum traço passa
    de RUG_TICK_H de altura."""
    scene = BlockScene()
    scene.set_schedule(Schedule(trips=[_trip('i1', 25200, '0'),
                                       _trip('i2', 28800, '0'),
                                       _trip('v1', 27000, '1'),
                                       _trip('v2', 30600, '1')],
                                mode='trips'))
    lines = _rug_lines(scene)
    tops = [min(ln.line().y1(), ln.line().y2()) for ln in lines]
    banda_ida = sorted(tops)[:2]
    banda_volta = sorted(tops)[2:]
    assert max(banda_ida) < min(banda_volta)
    assert min(banda_volta) - max(banda_ida) == RUG_TICK_H + RUG_BAND_GAP

    for ln in lines:
        assert abs(ln.line().y2() - ln.line().y1()) <= RUG_TICK_H


def test_regua_reserva_espaco_e_nao_invade_rotulo_de_hora():
    """O sceneRect cresce RUG_H, e nenhum traço de volta chega ao y do rótulo
    de hora inferior (que desce para total_h + RUG_H + 4)."""
    scene = BlockScene()
    scene.set_schedule(Schedule(trips=[_trip('i1', 28800, '0'),
                                       _trip('v1', 30600, '1')],
                                mode='trips'))
    lines = _rug_lines(scene)
    base_y = min(min(ln.line().y1(), ln.line().y2())
                 for ln in lines) - RUG_TOP_GAP   # total_h

    assert scene.sceneRect().height() == base_y + RUG_H + 24

    fundo_da_regua = max(max(ln.line().y1(), ln.line().y2()) for ln in lines)
    assert fundo_da_regua <= base_y + RUG_H
    assert fundo_da_regua < base_y + RUG_H + 4


def test_regua_so_ida_nao_ganha_rotulo_volta():
    """Diagrama só de ida não pendura o rótulo 'volta' (passo 152)."""
    scene = BlockScene()
    scene.set_schedule(Schedule(trips=[_trip('i1', 28800, '0'),
                                       _trip('i2', 30600, '0')],
                                mode='trips'))
    rotulos = _rug_labels(scene)
    assert 'ida' in rotulos
    assert 'volta' not in rotulos


def test_regua_rotula_as_duas_bandas_quando_ha_as_duas():
    scene = BlockScene()
    scene.set_schedule(Schedule(trips=[_trip('i1', 28800, '0'),
                                       _trip('v1', 30600, '1')],
                                mode='trips'))
    rotulos = _rug_labels(scene)
    assert 'ida' in rotulos
    assert 'volta' in rotulos


def test_regua_vazia_para_schedule_vazio():
    scene = BlockScene()
    scene.set_schedule(Schedule(trips=[], mode='trips'))
    assert scene._departure_items == []
