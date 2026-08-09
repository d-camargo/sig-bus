#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sondagem de compatibilidade contra o QGIS **real** desta máquina (passo 145).

Diferente de `test_qt6_compat.py`, que é varredura de texto e roda sob os mocks
do `conftest.py`, este script roda fora do pytest e **de fato importa** o QGIS
instalado: é a única forma de descobrir se a faixa declarada no `metadata.txt`
(3.34 – 4.99) corresponde ao que o pacote consegue fazer aqui.

    python3 sig_bus/scripts/check_qgis_compat.py

Imprime a versão detectada e um `OK`/`FAIL` por item, e sai com código ≠ 0 se
houver qualquer `FAIL`. A saída é item a item de propósito: esta máquina só tem
uma das pontas da faixa, e quem roda o mesmo comando na outra (o QGIS 4.2 do
usuário) precisa conseguir ler o que passou e o que não passou.
"""
import glob
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.dirname(SCRIPTS_DIR)
REPO_DIR = os.path.dirname(PACKAGE_DIR)
PACKAGE_NAME = os.path.basename(PACKAGE_DIR)

# Widgets do .ui só instanciam com uma plataforma Qt disponível; offscreen
# dispensa servidor gráfico.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_results = []


def check(label, fn):
    """Roda `fn`, imprime `OK`/`FAIL` e guarda o resultado."""
    try:
        detalhe = fn()
    except Exception as exc:                      # a falha é o dado aqui
        print('  FAIL  {}: {}: {}'.format(label, type(exc).__name__, exc))
        _results.append(False)
        return False
    print('  ok    {}{}'.format(label, ' — {}'.format(detalhe) if detalhe else ''))
    _results.append(True)
    return True


def package_modules():
    """Módulos importáveis do pacote (sem os testes e sem o conftest)."""
    for path in sorted(glob.glob(os.path.join(PACKAGE_DIR, '*.py'))):
        name = os.path.basename(path)[:-3]
        if name == 'conftest' or name.startswith('test_'):
            continue
        yield name


def check_imports():
    print('\n-- import dos módulos do pacote')
    import importlib
    for name in package_modules():
        check(name + '.py',
              lambda n=name: (importlib.import_module(
                  '{}.{}'.format(PACKAGE_NAME, n)) and None))


def check_field_types():
    print('\n-- tipo de campo resolvido por capacidade (gtfs_reader)')
    from qgis.core import QgsField
    from sig_bus.gtfs_reader import FIELD_INT, FIELD_STRING
    check('QgsField(nome, FIELD_STRING)',
          lambda: QgsField('stop_id', FIELD_STRING).name())
    check('QgsField(nome, FIELD_INT)',
          lambda: QgsField('stop_sequence', FIELD_INT).name())


def check_enums():
    """Inventário dos enums qualificados que o pacote usa. Acessar o atributo é
    a sondagem: no PyQt5/QGIS antigo o enum qualificado pode não existir."""
    print('\n-- enums qualificados usados pelo pacote')
    from qgis.core import (Qgis, QgsBlockingNetworkRequest, QgsTask,
                           QgsVectorFileWriter)
    from qgis.analysis import QgsVectorLayerDirector
    from qgis.core import QgsLayoutExporter
    from qgis.PyQt.QtCore import Qt

    inventario = [
        ('Qgis.LayoutUnit.Millimeters', lambda: Qgis.LayoutUnit.Millimeters),
        ('Qgis.MessageLevel.Critical', lambda: Qgis.MessageLevel.Critical),
        ('QgsTask.Flag.CanCancel', lambda: QgsTask.Flag.CanCancel),
        ('QgsVectorFileWriter.WriterError.NoError',
         lambda: QgsVectorFileWriter.WriterError.NoError),
        ('QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile',
         lambda: QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile),
        ('QgsLayoutExporter.ExportResult.Success',
         lambda: QgsLayoutExporter.ExportResult.Success),
        ('QgsBlockingNetworkRequest.ErrorCode.NoError',
         lambda: QgsBlockingNetworkRequest.ErrorCode.NoError),
        ('QgsVectorLayerDirector.Direction.DirectionBoth',
         lambda: QgsVectorLayerDirector.Direction.DirectionBoth),
        ('Qt.AlignmentFlag.AlignTop', lambda: Qt.AlignmentFlag.AlignTop),
        ('Qt.ItemDataRole.UserRole', lambda: Qt.ItemDataRole.UserRole),
    ]
    for label, getter in inventario:
        check(label, lambda g=getter: int(g()))


def check_ui():
    """Carrega o .ui: é onde moram os widgets do QGIS (QgsFeaturePickerWidget,
    QgsFieldComboBox, QgsFileWidget, QgsMapLayerComboBox)."""
    print('\n-- carga do SigBus_dialog_base.ui (QT_QPA_PLATFORM=offscreen)')
    ui_path = os.path.join(PACKAGE_DIR, 'SigBus_dialog_base.ui')

    def load():
        from qgis.PyQt import uic
        from qgis.PyQt.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        form, _base = uic.loadUiType(ui_path)
        return form.__name__

    check('uic.loadUiType(SigBus_dialog_base.ui)', load)


def main():
    if REPO_DIR not in sys.path:
        sys.path.insert(0, REPO_DIR)

    from qgis.core import Qgis, QgsApplication
    # Uma QgsApplication precisa existir para os widgets do .ui e para o
    # pkgDataPath() abaixo resolver.
    QgsApplication.instance() or QgsApplication([], False)

    # Dentro do QGIS o `processing` vem do diretório de plugins da instalação;
    # fora dele é preciso pôr esse diretório no path, senão os módulos que o
    # importam falhariam por ambiente, não por incompatibilidade.
    plugins_dir = os.path.join(QgsApplication.pkgDataPath(), 'python', 'plugins')
    if os.path.isdir(plugins_dir) and plugins_dir not in sys.path:
        sys.path.append(plugins_dir)

    from qgis.PyQt.QtCore import QT_VERSION_STR
    print('QGIS {} (QGIS_VERSION_INT={}) | Qt {} | python {}'.format(
        Qgis.QGIS_VERSION, Qgis.QGIS_VERSION_INT, QT_VERSION_STR,
        sys.version.split()[0]))
    print('pacote: {} (em {})'.format(PACKAGE_NAME, PACKAGE_DIR))

    check_imports()
    check_field_types()
    check_enums()
    check_ui()

    falhas = _results.count(False)
    print('\n{} itens, {} falha(s).'.format(len(_results), falhas))
    return 1 if falhas else 0


if __name__ == '__main__':
    sys.exit(main())
