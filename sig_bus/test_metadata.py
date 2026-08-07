# -*- coding: utf-8 -*-
"""Passo 136: guarda do metadata.txt do plugin SIG-Bus.

Valida que o metadata.txt existe, possui a seção [general] e contém todos os
campos obrigatórios do QGIS, garantindo que a versão não regrida, esteja no
formato correto e que a compatibilidade com QGIS 3.40+ e Qt6 seja mantida.
"""
import configparser
import os
import re

METADATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata.txt")


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
    # Formato de versão (ex: 0.5, 0.5.1, etc.)
    assert re.match(r"^\d+\.\d+(\.\d+)?$", version), f"Formato de versão inválido: {version!r}"

    # Impedir regressão abaixo de 0.4
    parts = [int(p) for p in version.split(".")]
    assert parts >= [0, 4], f"Versão do plugin regrediu para abaixo de 0.4: {version}"


def test_metadata_qgis_qt6_compat():
    """Guarda para qgisMinimumVersion e supportsQt6 (QGIS >= 3.40 / Qt6)."""
    config = _read_metadata()
    general = config["general"]

    min_ver = general.get("qgisMinimumVersion", "").strip()
    assert min_ver, "qgisMinimumVersion deve estar definido"
    parts = [int(p) for p in min_ver.split(".")]
    assert parts >= [3, 40], f"qgisMinimumVersion deve ser no mínimo 3.40 (encontrado: {min_ver})"

    supports_qt6 = general.get("supportsQt6", "").strip().lower()
    assert supports_qt6 == "true", f"supportsQt6 deve ser True (encontrado: {supports_qt6!r})"
