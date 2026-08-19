#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monta as páginas derivadas do site de documentação do SIG-Bus.

A documentação canônica continua morando em `sig_bus/` (é a pasta que se copia
para o QGIS, e é ela que o `README.md` linka — decisão 159). Este gerador
**copia** esses `.md` para dentro de `docs/`, com o nome que o site usa, e
reescreve os links relativos para o novo arranjo. As páginas geradas não vão
para o git (decisão 160): rode este script antes de qualquer `mkdocs build` /
`mkdocs serve`.

Uso:

    python3 scripts/build_docs_site.py            # gera em docs/
    python3 scripts/build_docs_site.py -d /tmp/x  # gera em outro destino
"""
import argparse
import posixpath
import re
from pathlib import Path

# Página do site (relativa ao destino) para cada `.md` canônico do repositório.
# `sig_bus/GUIA_EDICAO_GTFS_RASCUNHO.md` está fora de propósito: é rascunho
# superado pelo guia final e não se publica (decisão 159).
MAPA = {
    'sig_bus/GUIA_CONSTRUIR_GTFS.md': 'guias/construir-gtfs.md',
    'sig_bus/GUIA_EDICAO_GTFS.md': 'guias/editar-gtfs.md',
    'sig_bus/MODELO_PARADAS_CSV.md': 'guias/paradas-csv.md',
    'sig_bus/DOCUMENTACAO.md': 'referencia/funcionalidades.md',
    'sig_bus/METHODS.md': 'referencia/metodo.md',
    'sig_bus/DIAGRAMA_BLOCOS.md': 'referencia/diagrama-de-blocos.md',
    'sig_bus/ARQUITETURA_CONSTRUIR_GTFS.md': 'arquitetura/construir-gtfs.md',
    'sig_bus/ARQUITETURA_EDICAO_GTFS.md': 'arquitetura/editar-gtfs.md',
    'CHANGELOG.md': 'changelog.md',
}

# O README é bilíngue e vira duas páginas, partido no título da metade em
# português (decisão 162). O mesmo divisor que `test_readme.py` usa.
README = 'README.md'
README_DIVISOR = '\n# SIG-Bus — Plugin QGIS'
README_PT = 'visao-geral.md'
README_EN = 'en/overview.md'

# Âncoras de troca de língua do README: depois do corte cada metade virou uma
# página, então a âncora vira link para a outra página.
ANCORAS_ENTRE_LINGUAS = {
    '#sig-bus--plugin-qgis-para-análise-de-transporte-público': README_PT,
    '#sig-bus--qgis-plugin-for-public-transport-analysis': README_EN,
}

_RAW = 'https://github.com/d-camargo/sig-bus/raw/main/'

# Alvos que não são página: ficam no GitHub e viram URL absoluta.
ARQUIVOS_BRUTOS = {
    'sig_bus/modelo_paradas.csv': _RAW + 'sig_bus/modelo_paradas.csv',
    'docs/gtfsfiles.zip': _RAW + 'docs/gtfsfiles.zip',
    'docs/PyQGIS_PIBIC.pdf': _RAW + 'docs/PyQGIS_PIBIC.pdf',
}

_LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)\s]+)\)')


class LinkDesconhecido(Exception):
    """Link relativo sem destino no site — melhor estourar que publicar link morto."""


def _reescrever_links(texto, origem, pagina):
    """Reescreve os `](alvo)` de `texto`.

    `origem` é o caminho do arquivo de partida relativo à raiz do repositório
    (para resolver o alvo); `pagina` é o caminho da página gerada relativo ao
    destino (para calcular o link relativo de saída).
    """
    dir_origem = posixpath.dirname(origem)
    dir_pagina = posixpath.dirname(pagina)

    def _troca(m):
        rotulo, alvo = m.group(1), m.group(2)
        if alvo.startswith(('http://', 'https://', 'mailto:')):
            return m.group(0)
        if alvo.startswith('#'):
            outra = ANCORAS_ENTRE_LINGUAS.get(alvo)
            if outra is None:
                return m.group(0)  # âncora dentro da própria página
            return '[%s](%s)' % (rotulo, posixpath.relpath(outra, dir_pagina or '.'))

        caminho, _, ancora = alvo.partition('#')
        ancora = '#' + ancora if ancora else ''
        resolvido = posixpath.normpath(posixpath.join(dir_origem, caminho))

        if resolvido.startswith('..'):
            # Alvo fora do repositório (`sig_bus/ARQUITETURA_EDICAO_GTFS.md`
            # cita um documento irmão que não se publica aqui): não há página
            # para apontar, então o rótulo fica e o link cai.
            return rotulo
        if resolvido in MAPA:
            destino = posixpath.relpath(MAPA[resolvido], dir_pagina or '.')
            return '[%s](%s%s)' % (rotulo, destino, ancora)
        if resolvido in ARQUIVOS_BRUTOS:
            return '[%s](%s%s)' % (rotulo, ARQUIVOS_BRUTOS[resolvido], ancora)
        raise LinkDesconhecido(
            'link sem destino no site: %r em %s (resolve para %r) — '
            'acrescente ao MAPA ou a ARQUIVOS_BRUTOS em '
            'scripts/build_docs_site.py' % (alvo, origem, resolvido))

    return _LINK_RE.sub(_troca, texto)


def _escrever(destino, pagina, texto):
    caminho = Path(destino) / pagina
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding='utf-8')


def gerar(raiz, destino):
    """Copia a documentação canônica de `raiz` para `destino` como páginas do site.

    Devolve a lista das páginas geradas (caminhos relativos a `destino`).
    """
    raiz = Path(raiz)
    destino = Path(destino)
    geradas = []

    for origem, pagina in MAPA.items():
        texto = (raiz / origem).read_text(encoding='utf-8')
        _escrever(destino, pagina, _reescrever_links(texto, origem, pagina))
        geradas.append(pagina)

    texto = (raiz / README).read_text(encoding='utf-8')
    if README_DIVISOR not in texto:
        raise LinkDesconhecido(
            'divisor %r não encontrado no README.md — o corte EN/PT-BR '
            'depende dele' % README_DIVISOR)
    metade_en, metade_pt = texto.split(README_DIVISOR, 1)
    for pagina, metade in ((README_EN, metade_en),
                           (README_PT, README_DIVISOR.lstrip('\n') + metade_pt)):
        _escrever(destino, pagina, _reescrever_links(metade, README, pagina))
        geradas.append(pagina)

    return geradas


def main(argv=None):
    raiz_padrao = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description='Gera as páginas derivadas do site de documentação do SIG-Bus.')
    parser.add_argument('-r', '--raiz', default=str(raiz_padrao),
                        help='raiz do repositório (padrão: %(default)s)')
    parser.add_argument('-d', '--destino', default=None,
                        help='diretório do site (padrão: <raiz>/docs)')
    args = parser.parse_args(argv)

    raiz = Path(args.raiz)
    destino = Path(args.destino) if args.destino else raiz / 'docs'
    geradas = gerar(raiz, destino)
    print('%d páginas geradas em %s' % (len(geradas), destino))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
