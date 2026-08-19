# -*- coding: utf-8 -*-
"""Guarda do gerador do site (`scripts/build_docs_site.py`).

As páginas do site não estão no git (decisão 160): a única coisa que impede um
gerador quebrado de chegar ao CI é este teste, que gera num `tmp_path` e confere
o resultado — sem precisar do MkDocs instalado.

Mora aqui, junto de `test_readme.py`, porque a suíte roda `pytest sig_bus`.
"""
import importlib.util
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GERADOR = os.path.join(RAIZ, "scripts", "build_docs_site.py")


def _carregar_gerador():
    """Importa o script por caminho: `scripts/` não é pacote."""
    spec = importlib.util.spec_from_file_location("build_docs_site", GERADOR)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


bds = _carregar_gerador()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    destino = tmp_path_factory.mktemp("site")
    paginas = bds.gerar(RAIZ, destino)
    return destino, paginas


def test_todas_as_paginas_do_mapa_saem_preenchidas(site):
    destino, paginas = site
    esperadas = set(bds.MAPA.values()) | {bds.README_PT, bds.README_EN}
    assert set(paginas) == esperadas

    for pagina in esperadas:
        caminho = destino / pagina
        assert caminho.exists(), f"página não gerada: {pagina}"
        assert caminho.read_text(encoding="utf-8").strip(), f"página vazia: {pagina}"


def test_nenhum_link_relativo_quebrado_dentro_do_destino(site):
    destino, paginas = site
    quebrados = []
    for pagina in paginas:
        texto = (destino / pagina).read_text(encoding="utf-8")
        for alvo in re.findall(r"\]\(([^)\s]+)\)", texto):
            if alvo.startswith(("http://", "https://", "mailto:", "#")):
                continue
            caminho = alvo.split("#", 1)[0]
            if not caminho:
                continue
            resolvido = os.path.normpath(
                os.path.join(destino, os.path.dirname(pagina), caminho))
            if not os.path.exists(resolvido):
                quebrados.append(f"{pagina} -> {alvo}")
    assert not quebrados, "link(s) relativo(s) quebrado(s) no site: " + ", ".join(quebrados)


def test_rascunho_nao_e_publicado(site):
    """Decisão 159: `GUIA_EDICAO_GTFS_RASCUNHO.md` é rascunho superado."""
    destino, _ = site
    assert "sig_bus/GUIA_EDICAO_GTFS_RASCUNHO.md" not in bds.MAPA

    encontrados = [
        os.path.join(raiz, nome)
        for raiz, _, nomes in os.walk(destino)
        for nome in nomes
        if "RASCUNHO" in nome.upper()
    ]
    assert not encontrados, f"rascunho copiado para o site: {encontrados}"

    marca = "RASCUNHO"
    with open(os.path.join(RAIZ, "sig_bus", "GUIA_EDICAO_GTFS_RASCUNHO.md"),
              encoding="utf-8") as f:
        assert marca in f.read().upper(), "marca de busca perdeu o sentido"


def test_readme_vira_duas_paginas_uma_por_lingua(site):
    """Decisão 162: o README parte no divisor; cada página fica com uma língua."""
    destino, _ = site
    pt = (destino / bds.README_PT).read_text(encoding="utf-8")
    en = (destino / bds.README_EN).read_text(encoding="utf-8")

    assert bds.README_DIVISOR not in pt
    assert bds.README_DIVISOR not in en

    assert pt.startswith("# SIG-Bus — Plugin QGIS")
    assert en.startswith("# SIG-Bus — QGIS Plugin")

    # Cada metade tem só o seu próprio título de nível 1.
    assert "# SIG-Bus — QGIS Plugin" not in pt
    assert "# SIG-Bus — Plugin QGIS" not in en

    # A âncora de troca de língua vira link para a outra página (o corte
    # deixou as duas metades em arquivos diferentes).
    assert "(en/overview.md)" in pt
    assert "(../visao-geral.md)" in en


def test_link_para_alvo_desconhecido_estoura(tmp_path):
    """Melhor falhar o build que publicar link morto."""
    with pytest.raises(bds.LinkDesconhecido):
        bds._reescrever_links(
            "veja o [inventado](sig_bus/NAO_EXISTE.md)",
            "README.md",
            "visao-geral.md",
        )


def test_link_para_arquivo_bruto_vira_url_do_github():
    reescrito = bds._reescrever_links(
        "baixe o [modelo](modelo_paradas.csv)",
        "sig_bus/MODELO_PARADAS_CSV.md",
        "guias/paradas-csv.md",
    )
    assert bds.ARQUIVOS_BRUTOS["sig_bus/modelo_paradas.csv"] in reescrito
