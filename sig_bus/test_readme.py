# -*- coding: utf-8 -*-
"""Passo 165: guarda da decisão 107.

Confere só o que apodrece num README bilíngue: (a) todo link relativo
aponta para arquivo que existe, e (b) as duas metades (Inglês e Português)
têm a mesma estrutura de cabeçalhos. Nada sobre a redação do texto.
"""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(RAIZ, "README.md")

# Divisor das duas metades: o título em português, logo abaixo do '---'.
DIVISOR = "\n# SIG-Bus — Plugin QGIS"


def _ler_readme():
    assert os.path.exists(README_PATH), f"Arquivo não encontrado: {README_PATH}"
    with open(README_PATH, encoding="utf-8") as f:
        return f.read()


def _cabecalhos(texto):
    return [len(m.group(1)) for m in re.finditer(r"^(#+)\s", texto, re.M)]


def test_links_relativos_existem():
    """(a) Todo `](caminho)` que não seja URL nem âncora resolve para arquivo."""
    conteudo = _ler_readme()
    quebrados = []
    for alvo in re.findall(r"\]\(([^)]+)\)", conteudo):
        if alvo.startswith(("http://", "https://", "mailto:", "#")):
            continue
        caminho = alvo.split("#", 1)[0]
        if not caminho:
            continue
        if not os.path.exists(os.path.join(RAIZ, caminho)):
            quebrados.append(alvo)
    assert not quebrados, "Link(s) relativo(s) quebrado(s) no README.md: " + ", ".join(quebrados)


def test_metades_com_mesma_estrutura():
    """(b) As duas metades têm o mesmo número (e hierarquia) de cabeçalhos."""
    conteudo = _ler_readme()
    assert DIVISOR in conteudo, "Divisor da metade em português não encontrado."

    partes = conteudo.split(DIVISOR)
    assert len(partes) == 2, "README.md deve ter exatamente duas metades"

    en = _cabecalhos(partes[0])
    pt = _cabecalhos(DIVISOR + partes[1])

    assert len(en) == len(pt), (
        f"Defasagem estrutural: inglês tem {len(en)} cabeçalhos, "
        f"mas português tem {len(pt)}."
    )
    assert en == pt, "A hierarquia de cabeçalhos difere entre as duas línguas."
