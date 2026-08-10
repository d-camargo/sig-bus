"""Testes para sig_bus/address_format.py."""

import pytest
from sig_bus.address_format import (
    ADDRESS_PATTERN_HINT,
    ADDRESS_PLACEHOLDER,
    parse_address,
    format_address,
    normalizar_logradouro,
)


def test_constants():
    assert "Padrão:" in ADDRESS_PATTERN_HINT
    assert ADDRESS_PLACEHOLDER == "Rua Giuseppe Fórmolo, 210 - Centro"


def test_parse_address_completo():
    res = parse_address("Rua Giuseppe Fórmolo, 210 - Centro")
    assert res == {
        "logradouro": "Rua Giuseppe Fórmolo",
        "numero": "210",
        "bairro": "Centro",
    }


def test_parse_address_sem_bairro():
    res = parse_address("Rua Giuseppe Fórmolo, 210")
    assert res == {
        "logradouro": "Rua Giuseppe Fórmolo",
        "numero": "210",
        "bairro": None,
    }


def test_parse_address_sem_numero():
    res = parse_address("Rua Giuseppe Fórmolo - Centro")
    assert res == {
        "logradouro": "Rua Giuseppe Fórmolo",
        "numero": None,
        "bairro": "Centro",
    }


def test_parse_address_formato_errado_usuario():
    # Usuário testou digitando o município no lugar do bairro
    res = parse_address("Rua Giusepe Fórmolo, 210 - Caxias do Sul")
    assert res == {
        "logradouro": "Rua Giusepe Fórmolo",
        "numero": "210",
        "bairro": "Caxias do Sul",
    }


def test_parse_address_string_vazia():
    assert parse_address("") == {"logradouro": "", "numero": None, "bairro": None}
    assert parse_address("   ") == {"logradouro": "", "numero": None, "bairro": None}
    assert parse_address(None) == {"logradouro": "", "numero": None, "bairro": None}


def test_normalizar_logradouro_grafias_diferentes():
    assert normalizar_logradouro("Giusepe Fórmolo") != normalizar_logradouro("Giuseppe Fôrmolo")


def test_normalizar_logradouro_equivalentes():
    assert normalizar_logradouro("Rua  Fórmolo") == normalizar_logradouro("rua formolo")


def test_normalizar_logradouro_vazio():
    assert normalizar_logradouro("") == ""
    assert normalizar_logradouro(None) == ""


def test_roundtrip_entradas_canonicas():
    entradas = [
        "Rua Giuseppe Fórmolo, 210 - Centro",
        "Rua Giuseppe Fórmolo, 210",
        "Rua Giuseppe Fórmolo - Centro",
        "Rua Giuseppe Fórmolo",
        "",
    ]
    for entrada in entradas:
        parsed = parse_address(entrada)
        formatted = format_address(parsed)
        assert formatted == entrada, f"Falhou para entrada: {entrada!r} -> parsed {parsed!r} -> formatted {formatted!r}"
