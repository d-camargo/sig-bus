# -*- coding: utf-8 -*-
"""Guarda de regressão Qt6: nenhum enum do Qt5/QGIS 3 em forma não
qualificada pode voltar ao pacote por copy-paste de código antigo
(decisão 41 e decisão 55, PLAN.md). Varredura de texto pura — não importa PyQt nem
QGIS, roda em qualquer ambiente.

Exceção por linha (decisão 90): ``# qt6-compat: <justificativa>`` no fim da
linha isenta **aquela** linha das violações. A justificativa é obrigatória —
pragma vazio não isenta nada, para a exceção não virar um jeito silencioso de
desligar a guarda."""
import glob
import os
import re

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCLUDED_FILES = {'conftest.py', 'test_qt6_compat.py'}

# Qt.<Membro> fora da forma qualificada Qt.<Enum>.<Membro>.
QT_MEMBER_RE = re.compile(r'\bQt\.\w+(?:\.\w+)?\b')

# Demais enums/API cuja forma curta (não qualificada) deve ter desaparecido:
# (regex da forma antiga, forma qualificada correta a sugerir na falha).
LEGACY_PATTERNS = [
    # Importar PyQt5 direto explode num QGIS 4/Qt6 ("PyQt5 classes cannot be
    # imported in a QGIS build based on Qt6"). Vale para arquivo gerado também
    # — `pyrcc5` emite `from PyQt5 import QtCore`, e o `resources_rc.py` que
    # ele produz é importado pelo smoke do gate.
    (re.compile(r'\b(?:from|import)\s+PyQt[45]\b'),
     'qgis.PyQt (wrapper independente de versão)'),
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


# Supressão por linha: `# qt6-compat:` seguido de justificativa não vazia.
_SUPPRESS_RE = re.compile(r'#\s*qt6-compat:\s*\S')


def _is_exempt(line):
    """Só isenta com justificativa: `# qt6-compat:` sozinho não vale."""
    return bool(_SUPPRESS_RE.search(line))


def _scan_lines(lines):
    """Violações de uma sequência de linhas: `(lineno, achado, forma correta)`."""
    violations = []
    for lineno, line in enumerate(lines, start=1):
        if _is_exempt(line):
            continue
        for match in QT_MEMBER_RE.finditer(line):
            text = match.group(0)
            if text.count('.') < 2:
                member = text.split('.', 1)[1]
                violations.append((lineno, text, 'Qt.<Enum>.%s' % member))
        for pattern, fix in LEGACY_PATTERNS:
            for match in pattern.finditer(line):
                violations.append((lineno, match.group(0), fix))
    return violations


def _scan(path):
    with open(path, encoding='utf-8') as handle:
        return _scan_lines(handle.readlines())


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


def test_pragma_isenta_so_a_linha_e_so_com_justificativa():
    """Passo 140: o próprio pragma, sobre strings em memória."""
    # Sem pragma: continua violação.
    assert _scan_lines(['f = QVariant.String\n'])

    # Com pragma justificado: isenta.
    assert not _scan_lines(
        ['f = QVariant.String  # qt6-compat: fallback QGIS<3.38\n'])

    # Pragma sem justificativa não isenta nada.
    assert _scan_lines(['f = QVariant.String  # qt6-compat:\n'])
    assert _scan_lines(['f = QVariant.String  # qt6-compat\n'])

    # A isenção vale só para a linha que a carrega.
    achados = _scan_lines([
        'a = QVariant.String  # qt6-compat: fallback QGIS<3.38\n',
        'b = QVariant.Int\n',
    ])
    assert [lineno for lineno, _, _ in achados] == [2]
