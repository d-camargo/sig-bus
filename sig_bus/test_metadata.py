# -*- coding: utf-8 -*-
"""Passo 136: guarda do metadata.txt do plugin SIG-Bus.

Valida que o metadata.txt existe, possui a seção [general] e contém todos os
campos obrigatórios do QGIS, garantindo que a versão não regrida, esteja no
formato correto e que a faixa declarada (QGIS 3.34 – 4.99, Qt5 e Qt6) seja
mantida. Inclui a guarda de CHANGELOG da decisão 93.
"""
import configparser
import os
import re

import pytest

METADATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata.txt")
CHANGELOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CHANGELOG.md")
# Formato de versão em três algarismos (ex: 0.8.1, 1.0.0) — padrão dos projetos
# da VPS. É a regra: a guarda e o teste da regra usam este mesmo regex (decisão 146).
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _read_metadata():
    assert os.path.exists(METADATA_PATH), f"Arquivo não encontrado: {METADATA_PATH}"
    config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    with open(METADATA_PATH, encoding="utf-8") as f:
        config.read_file(f)
    return config


def test_metadata_exists_and_parseable():
    config = _read_metadata()
    assert config.has_section("general"), "metadata.txt deve conter a seção [general]"


def test_metadata_mandatory_fields():
    config = _read_metadata()
    general = config["general"]

    mandatory_keys = [
        "name",
        "qgisMinimumVersion",
        "description",
        "version",
        "author",
        "email",
        "about",
        "tracker",
        "repository",
    ]

    for key in mandatory_keys:
        assert key in general, f"Campo obrigatório '{key}' ausente no metadata.txt"
        val = general[key].strip()
        assert val != "", f"Campo obrigatório '{key}' não pode ser vazio"


def test_metadata_version_guard():
    """Guarda que impede regressão de versão e formatos inválidos."""
    config = _read_metadata()
    general = config["general"]

    version = general.get("version", "").strip()
    assert version, "Versão do plugin não pode ser vazia"
    assert VERSION_RE.match(version), (
        f"Formato de versão inválido: {version!r} — versão deve ter três "
        "algarismos, X.Y.Z (padrão dos projetos da VPS; ver decisão 146)")

    # Impedir regressão abaixo de 0.4
    parts = [int(p) for p in version.split(".")]
    assert parts >= [0, 4], f"Versão do plugin regrediu para abaixo de 0.4: {version}"


def test_version_regex_exige_tres_algarismos():
    """Exercita a regra, não só o valor que estiver no metadata.txt hoje (decisão 146)."""
    for aceito in ("0.8.1", "1.0.0", "0.10.2"):
        assert VERSION_RE.match(aceito), f"deveria aceitar {aceito!r}"
    for recusado in ("0.8", "1", "0.8.1.2", "0.8.1a"):
        assert not VERSION_RE.match(recusado), f"deveria recusar {recusado!r}"


def _version_tuple(text):
    """'3.34' -> [3, 34]. Comparar por tupla de inteiros, nunca por string:
    em ordem lexicográfica '3.99' > '4.99', que é exatamente a armadilha aqui."""
    return [int(p) for p in text.split(".")]


def test_metadata_qgis_qt6_compat():
    """Guarda da faixa declarada: piso <= 3.34, teto >= 4.99, supportsQt6."""
    config = _read_metadata()
    general = config["general"]

    min_ver = general.get("qgisMinimumVersion", "").strip()
    assert min_ver, "qgisMinimumVersion deve estar definido"
    # Subir o piso volta a excluir o QGIS 3.34 (LTR do Ubuntu 24.04).
    assert _version_tuple(min_ver) <= [3, 34], (
        f"qgisMinimumVersion deve ser no máximo 3.34 (encontrado: {min_ver})")

    # Sem esta chave o QGIS assume <major do mínimo>.99 e recusa todo QGIS 4.x
    # — foi o que barrou o QGIS 4.2 do usuário na 0.5.
    max_ver = general.get("qgisMaximumVersion", "").strip()
    assert max_ver, "qgisMaximumVersion deve estar definido (ausente = teto 3.99)"
    assert _version_tuple(max_ver) >= [4, 99], (
        f"qgisMaximumVersion deve ser no mínimo 4.99 (encontrado: {max_ver})")

    supports_qt6 = general.get("supportsQt6", "").strip().lower()
    assert supports_qt6 == "true", f"supportsQt6 deve ser True (encontrado: {supports_qt6!r})"


_UNRELEASED_RE = re.compile(r"^#{1,3}\s*n[aã]o\s+lan[cç]ad", re.IGNORECASE)
_VERSION_HEADING_RE = re.compile(r"^#{1,3}\s*v?(\d+\.\d+(?:\.\d+)?)\b")


def test_changelog_fechado_e_alinhado_ao_metadata():
    """Decisão 93: nenhuma seção 'Não lançado' aberta, e a primeira seção de
    versão do CHANGELOG casa com o version= do metadata.txt."""
    if not os.path.exists(CHANGELOG_PATH):
        pytest.skip(f"CHANGELOG.md não encontrado em {CHANGELOG_PATH}")

    with open(CHANGELOG_PATH, encoding="utf-8") as f:
        linhas = f.read().splitlines()

    abertas = [ln for ln in linhas if _UNRELEASED_RE.match(ln)]
    assert not abertas, (
        "CHANGELOG.md tem seção 'Não lançado' aberta — feche no release: "
        f"{abertas}")

    primeira = next((m.group(1) for m in
                     (_VERSION_HEADING_RE.match(ln) for ln in linhas) if m), None)
    assert primeira, "CHANGELOG.md não tem nenhum cabeçalho de versão"

    version = _read_metadata()["general"].get("version", "").strip()
    assert primeira == version, (
        f"primeira seção do CHANGELOG.md ({primeira}) != "
        f"version= do metadata.txt ({version})")
