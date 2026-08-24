# -*- coding: utf-8 -*-
"""Contrato e construção da base local do CNEFE (decisões 165-167, 172).

O DuckDB é opcional só da *geração* da base (decisão 166); estes testes nunca
tocam rede nem exigem o pacote `duckdb` instalado — `construir_base` recebe um
dublê que simula o comportamento do `duckdb.connect()` gravando as tabelas via
`sqlite3` puro, do mesmo jeito que o `ATTACH ... TYPE SQLITE` faria de verdade.
`abrir_base`/`descrever_base` são exercitados contra bases montadas à mão com
`sqlite3`, sem qualquer duplê — são só leitura, nunca precisam do DuckDB."""
import os
import sqlite3
import sys
import tempfile
import unittest

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from sig_bus.cnefe_base import (
    DATA_RELEASE,
    VERSAO_ESQUEMA,
    TABELAS_PARQUET,
    DuckDbAusente,
    BaseInvalida,
    url_parquet,
    construir_base,
    abrir_base,
    descrever_base,
)

try:
    import duckdb as _duckdb_real  # noqa: F401
    _TEM_DUCKDB = True
except ImportError:
    _TEM_DUCKDB = False


class TestConstantesEUrlParquet(unittest.TestCase):
    """Espelham `data_release` de `geocodebr/R/cache.R` (decisão 165) — se estes
    valores mudarem sem querer, todo mundo baixa a URL errada em silêncio."""

    def test_data_release(self):
        self.assertEqual(DATA_RELEASE, "v0.4.1")

    def test_versao_esquema(self):
        self.assertEqual(VERSAO_ESQUEMA, 1)

    def test_tabelas_parquet(self):
        self.assertEqual(
            TABELAS_PARQUET,
            {
                "enderecos": "municipio_logradouro_numero_localidade",
                "logradouros": "municipio_logradouro_localidade",
            },
        )

    def test_url_parquet_enderecos(self):
        url = url_parquet("enderecos")
        self.assertTrue(
            url.startswith("https://github.com/ipeaGIT/padronizacao_cnefe/releases/download/")
        )
        self.assertTrue(url.endswith("/v0.4.1/municipio_logradouro_numero_localidade.parquet"))


class TestDuckDbAusente(unittest.TestCase):
    """Sem o DuckDB instalado, `construir_base` tem que apontar o caminho de
    instalação em vez de estourar um erro de importação cru (decisão 166)."""

    @unittest.skipIf(_TEM_DUCKDB, "duckdb está instalado nesta máquina")
    def test_sem_duckdb_levanta_com_instrucao_de_instalacao(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = os.path.join(tmp, "cnefe_bh.sqlite")
            with self.assertRaises(DuckDbAusente) as ctx:
                construir_base("MG", "Belo Horizonte", destino)
            self.assertIn("pip install duckdb", str(ctx.exception))


class _FakeCon(object):
    """Dublê da conexão do DuckDB: em vez de baixar parquet nenhum, grava as
    tabelas destino via `sqlite3` puro assim que vê o `CREATE TABLE destino.*`
    — é o mesmo efeito que o `ATTACH ... TYPE SQLITE` real produziria."""

    def __init__(self, destino):
        self.destino = destino
        self.sqls = []
        self.fechada = False

    def execute(self, sql, params=None):
        self.sqls.append((sql, params))
        if sql.startswith("CREATE TABLE destino."):
            tabela = sql.split("CREATE TABLE destino.", 1)[1].split(" ", 1)[0]
            conn = sqlite3.connect(self.destino)
            if tabela == "enderecos":
                conn.execute(
                    "CREATE TABLE enderecos (estado TEXT, municipio TEXT, logradouro TEXT, "
                    "numero INTEGER, localidade TEXT, lat REAL, lon REAL, desvio_metros REAL, "
                    "n_casos INTEGER, endereco_completo TEXT)"
                )
                conn.execute(
                    "INSERT INTO enderecos VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("MG", "BELO HORIZONTE", "RUA TESTE", 100, "CENTRO",
                     -19.9, -43.9, 5.0, 1, "RUA TESTE, 100"),
                )
            else:
                conn.execute(
                    "CREATE TABLE logradouros (estado TEXT, municipio TEXT, logradouro TEXT, "
                    "localidade TEXT, lat REAL, lon REAL, desvio_metros REAL, n_casos INTEGER, "
                    "endereco_completo TEXT)"
                )
            conn.commit()
            conn.close()
        return self

    def close(self):
        self.fechada = True


class _FakeDuckDb(object):
    """Dublê do módulo `duckdb`: só precisa expor `.connect()`."""

    def __init__(self, con):
        self._con = con

    def connect(self, *a, **kw):
        return self._con


class _DuckDbQueQuebraSeUsado(object):
    """Prova de que `construir_base` recusa destino já existente **antes** de
    tocar no DuckDB — se `connect()` for chamado, o teste falha."""

    def connect(self, *a, **kw):
        raise AssertionError("não deveria ter chamado duckdb.connect() com destino já existente")


class TestConstruirBaseComFakeDuckDb(unittest.TestCase):

    def _construir(self):
        tmp = tempfile.TemporaryDirectory()
        destino = os.path.join(tmp.name, "cnefe_bh.sqlite")
        fake_con = _FakeCon(destino)
        resultado = construir_base(
            "MG", "Belo Horizonte", destino, duckdb=_FakeDuckDb(fake_con)
        )
        return tmp, destino, fake_con, resultado

    def test_carrega_httpfs_e_sqlite(self):
        tmp, destino, fake_con, resultado = self._construir()
        try:
            comandos = [sql for sql, _params in fake_con.sqls]
            self.assertIn("LOAD httpfs", comandos)
            self.assertIn("LOAD sqlite", comandos)
            self.assertTrue(any(c.startswith("ATTACH") for c in comandos))
            self.assertTrue(any(destino in c for c in comandos if c.startswith("ATTACH")))
        finally:
            tmp.cleanup()

    def test_cria_as_duas_tabelas_destino(self):
        tmp, destino, fake_con, resultado = self._construir()
        try:
            comandos = [sql for sql, _params in fake_con.sqls]
            self.assertTrue(any(c.startswith("CREATE TABLE destino.enderecos") for c in comandos))
            self.assertTrue(any(c.startswith("CREATE TABLE destino.logradouros") for c in comandos))
        finally:
            tmp.cleanup()

    def test_filtro_recebe_uf_e_municipio_normalizados(self):
        tmp, destino, fake_con, resultado = self._construir()
        try:
            for sql, params in fake_con.sqls:
                if sql.startswith("CREATE TABLE destino."):
                    self.assertIsNotNone(params)
                    url, uf, mun = params
                    self.assertEqual(uf, "MG")
                    self.assertEqual(mun, "BELO HORIZONTE")
        finally:
            tmp.cleanup()

    def test_resultado_devolvido_bate_com_descrever_base(self):
        tmp, destino, fake_con, resultado = self._construir()
        try:
            self.assertEqual(resultado["municipio"], "BELO HORIZONTE")
            self.assertEqual(resultado["estado"], "MG")
            self.assertEqual(resultado["data_release"], "v0.4.1")
            self.assertEqual(resultado["versao_esquema"], "1")
        finally:
            tmp.cleanup()


class TestConstruirBaseRecusaDestinoExistente(unittest.TestCase):
    """A base nunca é sobrescrita (mensagem do próprio módulo) — e a checagem
    tem que acontecer antes de qualquer uso do DuckDB."""

    def test_destino_ja_existente_levanta_sem_tocar_no_duckdb(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = os.path.join(tmp, "cnefe_bh.sqlite")
            open(destino, "w").close()
            with self.assertRaises(BaseInvalida):
                construir_base(
                    "MG", "Belo Horizonte", destino,
                    duckdb=_DuckDbQueQuebraSeUsado(),
                )


def _montar_base_valida(caminho, versao_esquema="1"):
    """Monta uma base SQLite mínima e válida à mão, sem duckdb nenhum."""
    conn = sqlite3.connect(caminho)
    conn.execute(
        "CREATE TABLE enderecos (estado TEXT, municipio TEXT, logradouro TEXT, "
        "numero INTEGER, localidade TEXT, lat REAL, lon REAL, desvio_metros REAL, "
        "n_casos INTEGER, endereco_completo TEXT)"
    )
    conn.executemany(
        "INSERT INTO enderecos VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("MG", "BELO HORIZONTE", "RUA TESTE", 100, "CENTRO",
             -19.9, -43.9, 5.0, 1, "RUA TESTE, 100"),
            ("MG", "BELO HORIZONTE", "RUA TESTE", 200, "CENTRO",
             -19.91, -43.91, 3.0, 2, "RUA TESTE, 200"),
        ],
    )
    conn.execute(
        "CREATE TABLE logradouros (estado TEXT, municipio TEXT, logradouro TEXT, "
        "localidade TEXT, lat REAL, lon REAL, desvio_metros REAL, n_casos INTEGER, "
        "endereco_completo TEXT)"
    )
    conn.execute(
        "INSERT INTO logradouros VALUES (?,?,?,?,?,?,?,?,?)",
        ("MG", "BELO HORIZONTE", "RUA TESTE", "CENTRO", -19.9, -43.9, 5.0, 3, "RUA TESTE"),
    )
    conn.execute("CREATE TABLE metadata (chave TEXT PRIMARY KEY, valor TEXT)")
    conn.executemany(
        "INSERT INTO metadata (chave, valor) VALUES (?, ?)",
        [
            ("estado", "MG"),
            ("municipio", "BELO HORIZONTE"),
            ("data_release", "v0.4.1"),
            ("gerado_em", "2026-08-20T10:00:00"),
            ("versao_esquema", versao_esquema),
        ],
    )
    conn.commit()
    conn.close()


class TestDescreverBase(unittest.TestCase):

    def test_base_valida_traz_contagens_e_metadados(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "cnefe_bh.sqlite")
            _montar_base_valida(caminho)

            info = descrever_base(caminho)

            self.assertEqual(info["enderecos"], 2)
            self.assertEqual(info["logradouros"], 1)
            self.assertEqual(info["estado"], "MG")
            self.assertEqual(info["municipio"], "BELO HORIZONTE")
            self.assertEqual(info["data_release"], "v0.4.1")
            self.assertEqual(info["versao_esquema"], "1")
            self.assertGreater(info["tamanho_bytes"], 0)

    def test_sem_tabela_metadata_levanta_citando_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "sem_metadata.sqlite")
            conn = sqlite3.connect(caminho)
            conn.execute("CREATE TABLE enderecos (estado TEXT)")
            conn.execute("CREATE TABLE logradouros (estado TEXT)")
            conn.commit()
            conn.close()

            with self.assertRaises(BaseInvalida) as ctx:
                descrever_base(caminho)
            self.assertIn("metadata", str(ctx.exception))

    def test_versao_esquema_futura_e_recusada(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "esquema_futuro.sqlite")
            _montar_base_valida(caminho, versao_esquema="99")

            with self.assertRaises(BaseInvalida):
                descrever_base(caminho)


class TestAbrirBase(unittest.TestCase):

    def test_arquivo_inexistente_levanta_base_invalida(self):
        with self.assertRaises(BaseInvalida):
            abrir_base("/tmp/nao/existe/arquivo_que_nao_existe.sqlite")

    def test_devolve_conexao_somente_leitura(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "cnefe_bh.sqlite")
            _montar_base_valida(caminho)

            conn = abrir_base(caminho)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute(
                        "INSERT INTO enderecos (estado, municipio) VALUES (?, ?)",
                        ("MG", "BELO HORIZONTE"),
                    )
            finally:
                conn.close()

    def test_sem_tabela_metadata_levanta_citando_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "sem_metadata.sqlite")
            conn = sqlite3.connect(caminho)
            conn.execute("CREATE TABLE enderecos (estado TEXT)")
            conn.execute("CREATE TABLE logradouros (estado TEXT)")
            conn.commit()
            conn.close()

            with self.assertRaises(BaseInvalida) as ctx:
                abrir_base(caminho)
            self.assertIn("metadata", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
