#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera a base local de endereços do CNEFE para um município (decisões 165-167, 172).

Este script roda **fora do QGIS**, em qualquer Python 3.9+, e baixa só os
`row groups` do CNEFE padronizado (`geocodebr`, Ipea/ITpS) que interessam ao
município pedido, gravando o resultado num `.sqlite` autocontido que o
SIG-Bus consulta depois com o `sqlite3` da biblioteca padrão. O DuckDB é
exigido **só para gerar** a base — o plugin, ao usá-la (geocodificação),
nunca precisa dele. Instale com:

    pip install duckdb

Exemplo de uso completo:

    python3 scripts/preparar_base_cnefe.py \\
        --estado MG --municipio "Belo Horizonte" --saida ~/cnefe_bh.sqlite

A base nunca é sobrescrita: se `--saida` já existir, o script recusa rodar.
"""

import argparse
import os
import sys

# Garante acesso ao pacote sig_bus quando o script roda direto, sem instalar
# o plugin no ambiente (mesmo espírito de scripts/build_docs_site.py).
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from sig_bus.cnefe_base import BaseInvalida, DuckDbAusente, construir_base


def criar_parser():
    """Cria e configura o analisador de argumentos da CLI."""
    parser = argparse.ArgumentParser(
        description="Gera a base local de endereços do CNEFE (IBGE) para um município do SIG-Bus."
    )
    parser.add_argument(
        "--estado",
        required=True,
        help="UF do município, por extenso ou sigla (ex.: MG, Minas Gerais).",
    )
    parser.add_argument(
        "--municipio",
        required=True,
        help='Nome do município (ex.: "Belo Horizonte").',
    )
    parser.add_argument(
        "--saida",
        required=True,
        help="Caminho do arquivo .sqlite a criar; não pode existir.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Não imprime o progresso nem o resumo final.",
    )
    return parser


def _resumo(info):
    """Monta o texto de resumo final a partir do dicionário de procedência."""
    tamanho_mb = info["tamanho_bytes"] / (1024 * 1024)
    linhas = [
        "Base gerada com sucesso.",
        "Município: {} ({})".format(info["municipio"], info["estado"]),
        "Endereços: {}".format(info["enderecos"]),
        "Logradouros: {}".format(info["logradouros"]),
        "Release dos dados: {}".format(info["data_release"]),
        "Gerado em: {}".format(info["gerado_em"]),
        "Tamanho do arquivo: {:.1f} MB".format(tamanho_mb),
    ]
    return "\n".join(linhas)


def main(argv=None):
    """Ponto de entrada principal da CLI."""
    parser = criar_parser()
    args = parser.parse_args(argv)

    def progresso(msg):
        if not args.quiet:
            print(msg)

    try:
        info = construir_base(
            estado=args.estado,
            municipio=args.municipio,
            destino=args.saida,
            progresso=progresso,
        )
    except (DuckDbAusente, BaseInvalida) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not args.quiet:
        print(_resumo(info))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
