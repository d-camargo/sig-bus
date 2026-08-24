# -*- coding: utf-8 -*-
"""Normalização de endereço para o padrão do CNEFE (decisão 169).

O CNEFE (IBGE) grava o logradouro em caixa alta, sem acento e com o tipo e os
títulos **por extenso** — `AVENIDA DOUTOR CRISTIANO GUIMARAES`, nunca
`AV. DR. CRISTIANO GUIMARÃES`. Medido nos 12.563 nomes distintos da base de
Belo Horizonte: não existe um único `RUA DR ...`.

Este módulo é o contrário do `address_format`: lá se lê o que o usuário digitou
e se reescreve para a tela; aqui se joga fora acento, caixa e pontuação e se
**expande** a abreviatura, para bater com o dado do IBGE. São
responsabilidades opostas, por isso módulo separado — misturar as duas
quebraria o `normalizar_logradouro` de que a decisão 59 depende.

Formato de tabela e nomenclatura reaproveitados do `geocodebr` (Ipea/ITpS,
licença MIT, `R/utils.R`); os dados são do CNEFE/IBGE, dado aberto.

Não importa Qt nem QGIS.
"""

import re
import unicodedata


#: Tipos de logradouro que o CNEFE grava por extenso.
TIPOS_LOGRADOURO = {
    "R": "RUA",
    "AV": "AVENIDA",
    "AVD": "AVENIDA",
    "AVDA": "AVENIDA",
    "PC": "PRACA",
    "PCA": "PRACA",
    "PRC": "PRACA",
    "TV": "TRAVESSA",
    "TRAV": "TRAVESSA",
    "AL": "ALAMEDA",
    "ROD": "RODOVIA",
    "EST": "ESTRADA",
    "LG": "LARGO",
    "BC": "BECO",
}

#: Títulos e tratamentos que o CNEFE grava por extenso.
TITULOS = {
    "DR": "DOUTOR",
    "DRA": "DOUTORA",
    "PROF": "PROFESSOR",
    "PROFA": "PROFESSORA",
    "PE": "PADRE",
    "CEL": "CORONEL",
    "GAL": "GENERAL",
    "ENG": "ENGENHEIRO",
    "MAL": "MARECHAL",
    "PRES": "PRESIDENTE",
    "STO": "SANTO",
    "STA": "SANTA",
    "VER": "VEREADOR",
    "DES": "DESEMBARGADOR",
    "VISC": "VISCONDE",
}

#: Sequências de mais de uma palavra, aplicadas antes das tabelas acima.
EXPRESSOES = (
    (("N", "SRA"), ("NOSSA", "SENHORA")),
    (("NSA", "SRA"), ("NOSSA", "SENHORA")),
    (("NS", "SRA"), ("NOSSA", "SENHORA")),
)

#: Nome por extenso → sigla, para o usuário que digita "Minas Gerais".
_UFS = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM",
    "BAHIA": "BA", "CEARA": "CE", "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
    "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
    "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE",
    "PIAUI": "PI", "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN",
    "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE",
    "TOCANTINS": "TO",
}


def normalizar_texto(texto):
    """Caixa alta, sem acento, sem pontuação, espaços colapsados.

    `Av. Dr. Cristiano Guimarães` → `AV DR CRISTIANO GUIMARAES`.
    """
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.upper()
    t = re.sub(r"[^0-9A-Z]+", " ", t)
    return " ".join(t.split())


def normalizar_logradouro_cnefe(texto):
    """Normaliza e **expande** tipo e títulos, palavra a palavra.

    `Av. Dr. Cristiano Guimarães` → `AVENIDA DOUTOR CRISTIANO GUIMARAES`.

    A expansão é por palavra inteira, nunca por prefixo: `RUA DRESDE`
    continua `RUA DRESDE` — `DRESDE` começa com `DR` mas não é abreviatura de
    `DOUTOR`, e a via existe de verdade em Belo Horizonte.
    """
    palavras = normalizar_texto(texto).split()
    if not palavras:
        return ""

    for origem, destino in EXPRESSOES:
        n = len(origem)
        i = 0
        while i <= len(palavras) - n:
            if tuple(palavras[i:i + n]) == origem:
                palavras[i:i + n] = list(destino)
                i += len(destino)
            else:
                i += 1

    # O tipo só é expandido na primeira posição: `RUA PRACA DA LIBERDADE` não
    # deve virar coisa nenhuma, mas `AV` no meio de um nome é raro e ambíguo.
    if palavras[0] in TIPOS_LOGRADOURO:
        palavras[0] = TIPOS_LOGRADOURO[palavras[0]]

    return " ".join(TITULOS.get(p, p) for p in palavras)


def normalizar_numero(texto):
    """Devolve o número como `int`, ou `None` quando não houver número.

    `210` → `210`; `210-A` → `210`; `s/n`, `SN`, `""`, `None` → `None`.
    """
    if texto is None:
        return None
    if isinstance(texto, int) and not isinstance(texto, bool):
        return texto
    t = normalizar_texto(texto)
    if not t or t in ("SN", "S N", "SEM NUMERO"):
        return None
    m = re.search(r"\d+", t)
    if not m:
        return None
    try:
        return int(m.group(0))
    except ValueError:
        return None


def normalizar_municipio(texto):
    """`Belo Horizonte` → `BELO HORIZONTE` (é como o CNEFE grava)."""
    return normalizar_texto(texto)


def normalizar_uf(texto):
    """Sigla da UF em caixa alta; aceita o nome por extenso.

    `mg` → `MG`; `Minas Gerais` → `MG`; vazio → `""`.
    """
    t = normalizar_texto(texto)
    if not t:
        return ""
    if t in _UFS:
        return _UFS[t]
    return t
