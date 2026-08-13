# -*- coding: utf-8 -*-
"""Testes para operações de zoom no BlockView (passo 168)."""
import pytest
from qgis.PyQt.QtCore import QPoint, QPointF, Qt
from qgis.PyQt.QtGui import QWheelEvent
from qgis.PyQt.QtWidgets import QApplication, QGraphicsScene

from sig_bus.block_view import BlockView

_app = QApplication.instance() or QApplication([])


def _make_wheel_event(delta_y):
    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_wheel_event_zoom_in():
    view = BlockView()
    initial_scale = view._scale
    event = _make_wheel_event(120)
    view.wheelEvent(event)
    assert view._scale == pytest.approx(initial_scale * BlockView._ZOOM_STEP)


def test_wheel_event_zoom_out():
    view = BlockView()
    initial_scale = view._scale
    event = _make_wheel_event(-120)
    view.wheelEvent(event)
    assert view._scale == pytest.approx(initial_scale / BlockView._ZOOM_STEP)


def test_zoom_max_limit():
    view = BlockView()
    view._scale = BlockView._MAX_SCALE
    event = _make_wheel_event(120)
    view.wheelEvent(event)
    assert view._scale == BlockView._MAX_SCALE


def test_zoom_min_limit():
    view = BlockView()
    view._scale = BlockView._MIN_SCALE
    event = _make_wheel_event(-120)
    view.wheelEvent(event)
    assert view._scale == BlockView._MIN_SCALE


def test_reset_zoom():
    view = BlockView()
    view.scale(2.0, 2.0)
    view._scale = 2.0
    view.reset_zoom()
    assert view._scale == 1.0
    assert view.transform().isIdentity()


def test_fit_all():
    scene = QGraphicsScene(0, 0, 800, 400)
    view = BlockView()
    view.setScene(scene)
    view.resize(400, 200)
    view.show()
    view.fit_all()
    assert view._scale == pytest.approx(view.transform().m11())


def test_fit_all_sem_cena():
    view = BlockView()
    view.fit_all()  # Não deve lançar exceção quando a cena é None


def _schedule(deslocamento_s=0):
    """Grade mínima de 3 viagens para a cena (passo 168)."""
    from sig_bus.schedule_edit_core import expand_frequency_to_stop_times, schedule_from_draft
    _, stop_times = expand_frequency_to_stop_times(
        ["S1", "S2"], "06:00:00", "07:00:00", 30, duracao_min=30, prefix="L1_0")
    if deslocamento_s:
        from sig_bus.schedule_edit_core import shift_trip
        primeiro = stop_times[0]["trip_id"]
        stop_times = shift_trip(stop_times, primeiro, deslocamento_s)
    return schedule_from_draft(stop_times, route_short_name="L1", direction_id="0")


def test_viewport_state_preservado_entre_redesenhos():
    """Redesenhar com set_schedule() não pode desfazer o zoom (passo 167)."""
    from sig_bus.block_scene import BlockScene

    scene = BlockScene()
    view = BlockView()
    view.setScene(scene)
    view.resize(600, 300)
    view.show()

    scene.set_schedule(_schedule())
    view.fit_all()
    view.scale(2.0, 2.0)
    view._scale = view.transform().m11()
    escala_do_usuario = view.transform().m11()

    estado = view.viewport_state()
    scene.set_schedule(_schedule(deslocamento_s=3600))   # grade deslocada: sceneRect muda
    view.restore_viewport(estado)

    assert view.transform().m11() == pytest.approx(escala_do_usuario)
    assert view._scale == pytest.approx(escala_do_usuario)

    # E o "Enquadrar tudo" continua reenquadrando de fato — sem isto, um
    # restore_viewport() que não faz nada passaria despercebido.
    view.fit_all()
    assert view.transform().m11() != pytest.approx(escala_do_usuario)


def test_restore_viewport_sem_estado_nao_faz_nada():
    view = BlockView()
    view.scale(3.0, 3.0)
    view._scale = 3.0
    view.restore_viewport(None)
    assert view._scale == 3.0
