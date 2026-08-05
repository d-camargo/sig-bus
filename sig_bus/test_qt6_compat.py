# -*- coding: utf-8 -*-
"""Guarda de regressão Qt6: nenhum enum do Qt5/QGIS 3 em forma não
qualificada pode voltar ao pacote por copy-paste de código antigo
(decisão 41 e decisão 55, PLAN.md). Varredura de texto pura — não importa PyQt nem
QGIS, roda em qualquer ambiente."""
import glob
import os
import re

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCLUDED_FILES = {'conftest.py', 'resources.py', 'test_qt6_compat.py'}

# Qt.<Membro> fora da forma qualificada Qt.<Enum>.<Membro>.
QT_MEMBER_RE = re.compile(r'\bQt\.\w+(?:\.\w+)?\b')

# Demais enums/API cuja forma curta (não qualificada) deve ter desaparecido:
# (regex da forma antiga, forma qualificada correta a sugerir na falha).
LEGACY_PATTERNS = [
    (re.compile(r'\bQVariant\.(?:String|Int)\b'),
     'QMetaType.Type.QString / QMetaType.Type.Int (QVariant.Type não existe mais no PyQt6)'),
    (re.compile(r'\bQgis\.(?:Critical|Info|Warning|Success)\b'),
     'Qgis.MessageLevel.<Critical|Info|Warning|Success>'),
    (re.compile(r'\bQgsTask\.CanCancel\b'), 'QgsTask.Flag.CanCancel'),
    (re.compile(r'\bQMessageBox\.(?:Yes|No)\b'), 'QMessageBox.StandardButton.<Yes|No>'),
    (re.compile(r'\bQPainter\.Antialiasing\b'), 'QPainter.RenderHint.Antialiasing'),
    (re.compile(r'\bQImage\.Format_\w*'), 'QImage.Format.Format_<...>'),
    (re.compile(r'\bQFrame\.(?:StyledPanel|Raised)\b'),
     'QFrame.Shape.StyledPanel / QFrame.Shadow.Raised'),
    (re.compile(r'\bQNetworkReply\.(?!NetworkError\b)[A-Z]\w*Error\b'),
     'QNetworkReply.NetworkError.<...>'),
    (re.compile(r'\bQgsBlockingNetworkRequest\.(?!ErrorCode\b)[A-Z]\w*(?:Error|NoError)\b'),
     'QgsBlockingNetworkRequest.ErrorCode.<...>'),
    (re.compile(r'\bQgsVectorFileWriter\.(?:NoError|Err\w+)\b'),
     'QgsVectorFileWriter.WriterError.<...>'),
    (re.compile(r'\bQgsVectorFileWriter\.CreateOrOverwrite\w*\b'),
     'QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwrite<...>'),
    (re.compile(r'\bQgsLayoutExporter\.(?!ExportResult\b)(?:Success|\w*Error)\b'),
     'QgsLayoutExporter.ExportResult.<...>'),
    (re.compile(r'\bQgsVectorLayerDirector\.(?!Direction\b)Direction\w+\b'),
     'QgsVectorLayerDirector.Direction.Direction<...>'),
    (re.compile(r'\.exec_\('), '.exec() (PyQt6 removeu o alias exec_)'),
]


def _source_files():
    for path in sorted(glob.glob(os.path.join(PACKAGE_DIR, '*.py'))):
        name = os.path.basename(path)
        if name in EXCLUDED_FILES:
            continue
        yield path


def _scan(path):
    violations = []
    with open(path, encoding='utf-8') as handle:
        for lineno, line in enumerate(handle, start=1):
            for match in QT_MEMBER_RE.finditer(line):
                text = match.group(0)
                if text.count('.') < 2:
                    member = text.split('.', 1)[1]
                    violations.append((lineno, text, 'Qt.<Enum>.%s' % member))
            for pattern, fix in LEGACY_PATTERNS:
                for match in pattern.finditer(line):
                    violations.append((lineno, match.group(0), fix))
    return violations


def test_no_legacy_qt5_enum_usage():
    failures = []
    for path in _source_files():
        rel = os.path.relpath(path, PACKAGE_DIR)
        for lineno, found, fix in _scan(path):
            failures.append(
                "sig_bus/%s:%d: '%s' não é a forma qualificada do Qt6 "
                "(use %s)" % (rel, lineno, found, fix)
            )
    assert not failures, (
        "Enum(s) de API antiga do Qt5/QGIS 3 encontrados:\n" + "\n".join(failures)
    )
