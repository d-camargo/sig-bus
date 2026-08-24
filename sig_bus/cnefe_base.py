# -*- coding: utf-8 -*-
"""Contrato e construção da base local de endereços do CNEFE (decisões 165-167, 172).

A base é **local, por município, em SQLite**. O conjunto completo do CNEFE
padronizado pesa ~1,5 GB em parquet — inviável embutir ou baixar dentro do
QGIS. Mas o SIG-Bus é naturalmente um feed, um município: a base de Belo
Horizonte inteira sai em ~10 s e ocupa 44 MB com índice, e é lida pelo
`sqlite3` da biblioteca padrão.

O DuckDB é dependência **opcional da preparação, nunca da geocodificação**
(decisão 166): `construir_base` recebe o módulo injetado, e quem só consulta a
base (`abrir_base`, `descrever_base`, `cnefe_geocoder`) usa apenas `sqlite3`.
Sem DuckDB em lugar nenhum, o plugin funciona como sempre funcionou.

Duas tabelas, não oito (decisão 167): endereço de parada de ônibus quase nunca
traz CEP, então só entram as tabelas de referência de `dn03/dn04/da04`
(`enderecos`) e de `dl04` (`logradouros`).

Os parquets e a nomenclatura dos tipos de acerto vêm do `geocodebr`
(Ipea/ITpS, licença MIT); os dados são do CNEFE/IBGE, dado aberto.

Não importa Qt nem QGIS.
"""

import os
import sqlite3
from datetime import datetime

from .cnefe_padrao import normalizar_municipio, normalizar_uf


#: Release dos parquets padronizados, espelhando `data_release` de
#: `geocodebr/R/cache.R`. Subir aqui quando o Ipea publicar release novo.
DATA_RELEASE = "v0.4.1"

#: Versão do esquema gravado pelo `construir_base`. Base com versão diferente
#: é recusada com mensagem clara em vez de dar erro de SQL.
VERSAO_ESQUEMA = 1

URL_BASE_PARQUET = (
    "https://github.com/ipeaGIT/padronizacao_cnefe/releases/download/{release}/{arquivo}.parquet"
)

#: tabela local → parquet de referência do `geocodebr`.
TABELAS_PARQUET = {
    "enderecos": "municipio_logradouro_numero_localidade",
    "logradouros": "municipio_logradouro_localidade",
}

#: Colunas trazidas de cada parquet. `numero` só existe na tabela de endereços.
COLUNAS = {
    "enderecos": (
        "estado", "municipio", "logradouro", "numero", "localidade",
        "lat", "lon", "desvio_metros", "n_casos", "endereco_completo",
    ),
    "logradouros": (
        "estado", "municipio", "logradouro", "localidade",
        "lat", "lon", "desvio_metros", "n_casos", "endereco_completo",
    ),
}


class DuckDbAusente(Exception):
    """O DuckDB não está disponível — só afeta quem quer **gerar** a base."""


class BaseInvalida(Exception):
    """A base apontada não existe, não tem o esquema esperado ou é de outra versão."""


def url_parquet(tabela, release=DATA_RELEASE):
    """URL do parquet de referência de uma das tabelas de `TABELAS_PARQUET`."""
    return URL_BASE_PARQUET.format(release=release, arquivo=TABELAS_PARQUET[tabela])


def _resolver_duckdb(duckdb=None):
    if duckdb is not None:
        return duckdb
    try:
        import duckdb as _duckdb
    except ImportError:
        raise DuckDbAusente(
            "O DuckDB é necessário apenas para GERAR a base do município "
            "(consultar a base já pronta não precisa dele).\n\n"
            "Instale com:\n    pip install duckdb\n\n"
            "Ou gere a base fora do QGIS, em qualquer Python 3.9+:\n"
            "    python3 scripts/preparar_base_cnefe.py "
            "--estado MG --municipio \"Belo Horizonte\" --saida ~/cnefe_bh.sqlite"
        )
    return _duckdb


def construir_base(estado, municipio, destino, duckdb=None, progresso=None):
    """Gera a base SQLite de um município a partir dos parquets do CNEFE.

    Lê só os *row groups* que interessam — os parquets estão ordenados por
    estado/município, então o filtro desce ao arquivo remoto em vez de baixar
    1,5 GB.

    :param estado: UF, por extenso ou sigla (`MG`, `Minas Gerais`).
    :param municipio: nome do município (`Belo Horizonte`).
    :param destino: caminho do arquivo `.sqlite` a criar; não pode existir.
    :param duckdb: módulo `duckdb` injetado (decisão 166). `None` tenta importar.
    :param progresso: callable opcional que recebe uma linha de texto.
    :return: dicionário de procedência, igual ao de `descrever_base`.
    :raises DuckDbAusente: sem DuckDB disponível.
    :raises BaseInvalida: destino já existente ou município sem endereço nenhum.
    """
    def _avisar(msg):
        if progresso:
            progresso(msg)

    uf = normalizar_uf(estado)
    mun = normalizar_municipio(municipio)
    if not uf or not mun:
        raise BaseInvalida("Informe o estado e o município.")

    if os.path.exists(destino):
        raise BaseInvalida(
            "Já existe um arquivo em {}. Apague-o ou escolha outro caminho — "
            "a base nunca é sobrescrita, para não destruir dado por engano.".format(destino)
        )

    _duckdb = _resolver_duckdb(duckdb)

    pasta = os.path.dirname(os.path.abspath(destino))
    if pasta and not os.path.isdir(pasta):
        os.makedirs(pasta)

    con = _duckdb.connect()
    try:
        _avisar("Preparando o DuckDB…")
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
        con.execute("INSTALL sqlite")
        con.execute("LOAD sqlite")
        con.execute("ATTACH '{}' AS destino (TYPE SQLITE)".format(destino.replace("'", "''")))

        for tabela in ("enderecos", "logradouros"):
            _avisar("Baixando {} de {}/{}…".format(tabela, uf, mun))
            colunas = ", ".join(COLUNAS[tabela])
            con.execute(
                "CREATE TABLE destino.{tabela} AS "
                "SELECT {colunas} FROM read_parquet(?) "
                "WHERE estado = ? AND municipio = ?".format(tabela=tabela, colunas=colunas),
                [url_parquet(tabela), uf, mun],
            )
    finally:
        con.close()

    _avisar("Criando índices…")
    conn = sqlite3.connect(destino)
    try:
        conn.execute("CREATE INDEX idx_enderecos_log_num ON enderecos (logradouro, numero)")
        conn.execute("CREATE INDEX idx_enderecos_log ON enderecos (logradouro)")
        conn.execute("CREATE INDEX idx_logradouros_log ON logradouros (logradouro)")
        conn.execute("CREATE TABLE metadata (chave TEXT PRIMARY KEY, valor TEXT)")
        conn.executemany(
            "INSERT INTO metadata (chave, valor) VALUES (?, ?)",
            [
                ("estado", uf),
                ("municipio", mun),
                ("data_release", DATA_RELEASE),
                ("gerado_em", datetime.now().isoformat(timespec="seconds")),
                ("versao_esquema", str(VERSAO_ESQUEMA)),
            ],
        )
        conn.commit()
        vazia = conn.execute("SELECT COUNT(*) FROM enderecos").fetchone()[0] == 0
    finally:
        conn.close()

    if vazia:
        os.remove(destino)
        raise BaseInvalida(
            "O CNEFE não tem endereço nenhum para {}/{}. Confira a grafia do "
            "município e a sigla do estado.".format(uf, mun)
        )

    _avisar("Base pronta.")
    return descrever_base(destino)


def abrir_base(caminho):
    """Abre a base em modo **somente-leitura** e valida o esquema.

    :raises BaseInvalida: arquivo ausente, sem as tabelas esperadas, sem
        `metadata` ou gravado por uma versão de esquema desconhecida.
    """
    if not caminho or not os.path.isfile(caminho):
        raise BaseInvalida("Base de endereços não encontrada em {}.".format(caminho or "(vazio)"))

    uri = "file:{}?mode=ro".format(caminho.replace("?", "%3f").replace("#", "%23"))
    try:
        # `check_same_thread=False` porque a geocodificação em lote roda num
        # `QgsTask`, em outra thread; a conexão é somente-leitura e o `sqlite3`
        # já serializa o acesso.
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        nomes = {
            linha[0] for linha in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    except sqlite3.Error as exc:
        raise BaseInvalida("Não foi possível ler a base {}: {}".format(caminho, exc))

    faltando = {"enderecos", "logradouros", "metadata"} - nomes
    if faltando:
        conn.close()
        raise BaseInvalida(
            "O arquivo {} não é uma base do CNEFE gerada pelo SIG-Bus "
            "(faltam as tabelas: {}).".format(caminho, ", ".join(sorted(faltando)))
        )

    try:
        meta = {l["chave"]: l["valor"] for l in conn.execute("SELECT chave, valor FROM metadata")}
    except sqlite3.Error as exc:
        conn.close()
        raise BaseInvalida("A tabela `metadata` da base {} está ilegível: {}".format(caminho, exc))

    versao = meta.get("versao_esquema")
    if str(versao) != str(VERSAO_ESQUEMA):
        conn.close()
        raise BaseInvalida(
            "A base {} foi gerada com o esquema {} e esta versão do SIG-Bus "
            "espera o {}. Gere a base de novo.".format(caminho, versao, VERSAO_ESQUEMA)
        )

    return conn


def descrever_base(caminho):
    """Procedência da base, para o diálogo de configuração exibir (decisão 172).

    :return: dict com `estado`, `municipio`, `data_release`, `gerado_em`,
        `versao_esquema`, `enderecos`, `logradouros` e `tamanho_bytes`.
    :raises BaseInvalida: mesmas condições de `abrir_base`.
    """
    conn = abrir_base(caminho)
    try:
        info = {l["chave"]: l["valor"] for l in conn.execute("SELECT chave, valor FROM metadata")}
        info["enderecos"] = conn.execute("SELECT COUNT(*) FROM enderecos").fetchone()[0]
        info["logradouros"] = conn.execute("SELECT COUNT(*) FROM logradouros").fetchone()[0]
    except sqlite3.Error as exc:
        raise BaseInvalida("Base {} ilegível: {}".format(caminho, exc))
    finally:
        conn.close()
    info["tamanho_bytes"] = os.path.getsize(caminho)
    return info
