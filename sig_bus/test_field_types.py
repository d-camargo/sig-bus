# -*- coding: utf-8 -*-
"""Passo 144: os dois ramos de `gtfs_reader._resolve_field_types()`.

O resolvedor sonda a **capacidade** do `QgsField` instalado em vez de cravar um
piso de versão (decisões 87-89). Os dois ramos são exercitados aqui com um
`QgsField` de mentira, para o teste não depender de qual QGIS está na máquina —
o ramo `QVariant` só acontece de verdade em QGIS < 3.38.
"""
from unittest.mock import patch

from qgis.core import QgsField
from qgis.PyQt.QtCore import QMetaType

from sig_bus.gtfs_reader import FIELD_INT, FIELD_STRING, _resolve_field_types


class _FakeQVariant:
    """`QVariant` do Qt5 o bastante para o fallback: no PyQt6 a classe real não
    tem `.String`/`.Int`, então importá-la aqui daria AttributeError."""
    String = 10
    Int = 2


def test_ramo_qmetatype_quando_qgsfield_aceita():
    """QgsField que aceita QMetaType.Type → os tipos vêm de QMetaType."""
    with patch('qgis.core.QgsField') as fake:
        fake.return_value = object()
        assert _resolve_field_types() == (QMetaType.Type.QString,
                                          QMetaType.Type.Int)
    fake.assert_called_once()


def test_ramo_qvariant_quando_qgsfield_recusa():
    """QgsField que levanta TypeError (o 3.34 real) → cai no QVariant, sem
    deixar exceção escapar."""
    with patch('qgis.core.QgsField', side_effect=TypeError(
            "argument 2 has unexpected type 'Type'")):
        with patch.dict('sys.modules',
                        {'qgis.PyQt.QtCore': _fake_qtcore_module()}):
            assert _resolve_field_types() == (_FakeQVariant.String,
                                              _FakeQVariant.Int)


def _fake_qtcore_module():
    """Módulo `qgis.PyQt.QtCore` de mentira, expondo só o QVariant do fallback."""
    import types
    mod = types.ModuleType('qgis.PyQt.QtCore')
    mod.QVariant = _FakeQVariant
    mod.QMetaType = QMetaType
    return mod


def test_constantes_exportadas_constroem_qgsfield():
    """O que o módulo exportou é utilizável como está (`SigBus_dialog` depende
    disso)."""
    assert QgsField('stop_id', FIELD_STRING).name() == 'stop_id'
    assert QgsField('stop_sequence', FIELD_INT).name() == 'stop_sequence'
