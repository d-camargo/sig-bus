# -*- coding: utf-8 -*-
"""Testes para o indicador de headway em cota do BlockScene."""
import os
import pytest
from qgis.PyQt.QtWidgets import QApplication, QGraphicsLineItem, QGraphicsSimpleTextItem
from sig_bus.block_scene import BlockScene
from sig_bus.block_core import Schedule, Trip, Block

# Garantir QApplication inicializado para QGraphicsScene
_app = QApplication.instance() or QApplication([])


def test_show_headway_cota():
    scene = BlockScene()
    
    trip1 = Trip(
        trip_id='t1', route_short_name='101', direction_id='0',
        service_id='s1', shape_id='shp1', trip_headsign='Destino A',
        start_time_s=28800, end_time_s=32400, start_stop_id='p1',
        end_stop_id='p2', n_stops=10, block_id='b1'
    )
    trip2 = Trip(
        trip_id='t2', route_short_name='101', direction_id='0',
        service_id='s1', shape_id='shp1', trip_headsign='Destino A',
        start_time_s=29400, end_time_s=33000, start_stop_id='p1',
        end_stop_id='p2', n_stops=10, block_id='b2'
    )
    
    b1 = Block(block_id='b1', trips=[trip1])
    b2 = Block(block_id='b2', trips=[trip2])
    
    schedule = Schedule(trips=[trip1, trip2], blocks=[b1, b2], mode='blocks')
    scene.set_schedule(schedule)
    
    # Selecionar a segunda viagem (headway em relação à primeira)
    item2 = scene._trip_items['t2']
    scene.select_trip_item(item2)
    
    # _headway_items deve conter:
    # - 2 linhas de chamada verticais
    # - 1 linha horizontal de cota
    # - 2 marcadores nos extremos da cota
    # - 1 rótulo de texto ("10 min")
    assert len(scene._headway_items) == 6
    
    lines = [it for it in scene._headway_items if isinstance(it, QGraphicsLineItem)]
    labels = [it for it in scene._headway_items if isinstance(it, QGraphicsSimpleTextItem)]
    
    assert len(lines) == 5
    assert len(labels) == 1
    assert labels[0].text() == '10 min'


def test_select_trip_endpoint():
    scene = BlockScene()
    
    trip1 = Trip(
        trip_id='t1', route_short_name='101', direction_id='0',
        service_id='s1', shape_id='shp1', trip_headsign='Destino A',
        start_time_s=28800, end_time_s=32400, start_stop_id='p1',
        end_stop_id='p2', n_stops=10, block_id='b1'
    )
    b1 = Block(block_id='b1', trips=[trip1])
    schedule = Schedule(trips=[trip1], blocks=[b1], mode='blocks')
    scene.set_schedule(schedule)
    
    item1 = scene._trip_items['t1']
    
    received_endpoint = []
    scene.endpointClicked.connect(lambda t, ep: received_endpoint.append((t.trip_id, ep)))
    
    scene.select_trip_endpoint(item1, 'first')
    assert scene.selected_endpoint == 'first'
    assert received_endpoint == [('t1', 'first')]
    
    scene.select_trip_endpoint(item1, 'last')
    assert scene.selected_endpoint == 'last'
    assert received_endpoint == [('t1', 'first'), ('t1', 'last')]
    
    with pytest.raises(ValueError):
        scene.select_trip_endpoint(item1, 'invalid')


def test_cota_tambem_no_modo_viagens():
    """Passo 125: a cota vale nos dois modos — a página de ajuste do
    assistente desenha em Modo Viagens."""
    scene = BlockScene()

    trip1 = Trip(
        trip_id='t1', route_short_name='101', direction_id='0',
        service_id='s1', shape_id='', trip_headsign='Destino A',
        start_time_s=28800, end_time_s=32400, start_stop_id='p1',
        end_stop_id='p2', n_stops=10
    )
    trip2 = Trip(
        trip_id='t2', route_short_name='101', direction_id='0',
        service_id='s1', shape_id='', trip_headsign='Destino A',
        start_time_s=29400, end_time_s=33000, start_stop_id='p1',
        end_stop_id='p2', n_stops=10
    )
    scene.set_schedule(Schedule(trips=[trip1, trip2], mode='trips'))

    scene.select_trip_item(scene._trip_items['t2'])
    lines = [it for it in scene._headway_items if isinstance(it, QGraphicsLineItem)]
    labels = [it for it in scene._headway_items if isinstance(it, QGraphicsSimpleTextItem)]
    assert len(lines) == 5
    assert labels[0].text() == '10 min'

    # A cota é reta: a linha horizontal tem os dois y iguais.
    horizontais = [ln for ln in lines if ln.line().y1() == ln.line().y2()
                   and ln.line().x1() != ln.line().x2()]
    assert len(horizontais) == 1


def test_nudge_key_emite_caracteres():
    """Passo 127/decisão 76: os atalhos são lidos de event.text()."""
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QKeyEvent
    from sig_bus.block_view import BlockView

    view = BlockView()
    emitidas = []
    view.nudgeKeyPressed.connect(emitidas.append)

    for texto, key in (('>', Qt.Key.Key_Greater), ('<', Qt.Key.Key_Less),
                       ('+', Qt.Key.Key_Plus), ('-', Qt.Key.Key_Minus)):
        view.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key,
                                     Qt.KeyboardModifier.NoModifier, texto))

    assert emitidas == ['>', '<', '+', '-']

    # Teclado numérico: text() vazio, mas a tecla é reconhecida pelo keycode.
    emitidas.clear()
    view.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Plus,
                                 Qt.KeyboardModifier.KeypadModifier, ''))
    assert emitidas == ['+']

    # Qualquer outra tecla não emite nada.
    emitidas.clear()
    view.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A,
                                 Qt.KeyboardModifier.NoModifier, 'a'))
    assert emitidas == []
