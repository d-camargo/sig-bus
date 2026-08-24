# -*- coding: utf-8 -*-
"""Passos 5 e 6: os degraus do `CnefeGeocoder` contra uma base fabricada.

Nenhum teste aqui toca a rede nem precisa de `duckdb`: a base é um SQLite
montado à mão, com o mesmo esquema que `cnefe_base.construir_base` grava.
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, '/home/diego/projects/sig-bus')

from sig_bus.cnefe_base import VERSAO_ESQUEMA
from sig_bus.cnefe_geocoder import CnefeGeocoder


#: (logradouro, numero, localidade, lat, lon, desvio_metros, n_casos)
#: Avenida com 1020/1025/1032 em dois bairros — o caso medido de verdade é
#: `Avenida Amazonas, 1000`, que **não existe** no CNEFE e cai no 1020.
_ENDERECOS = [
    ("AVENIDA AMAZONAS", 1020, "CENTRO", -19.9210, -43.9400, 6.0, 4),
    ("AVENIDA AMAZONAS", 1025, "BARRO PRETO", -19.9220, -43.9450, 8.0, 2),
    ("AVENIDA AMAZONAS", 1032, "CENTRO", -19.9230, -43.9410, 5.0, 1),
    # Mesmo logradouro e número em dois bairros: é o empate que o degrau 2
    # (`dn04`) desfaz pela média ponderada por `n_casos`.
    ("RUA DOIS BAIRROS", 50, "CENTRO", -20.0000, -44.0000, 3.0, 3),
    ("RUA DOIS BAIRROS", 50, "SAVASSI", -20.0100, -44.0100, 7.0, 1),
    ("AVENIDA DOUTOR CRISTIANO GUIMARAES", 100, "PLANALTO", -19.8500, -43.9500, 4.0, 3),
]

#: (logradouro, localidade, lat, lon, desvio_metros, n_casos)
_LOGRADOUROS = [
    ("AVENIDA AMAZONAS", "CENTRO", -19.9225, -43.9425, 300.0, 7),
    ("RUA SO CENTROIDE", "CENTRO", -19.9300, -43.9300, 120.0, 10),
    ("AVENIDA DOUTOR CRISTIANO GUIMARAES", "PLANALTO", -19.8505, -43.9505, 250.0, 3),
]


def _montar_base(caminho, com_metadata=True):
    conn = sqlite3.connect(caminho)
    conn.execute(
        "CREATE TABLE enderecos (estado TEXT, municipio TEXT, logradouro TEXT, "
        "numero INTEGER, localidade TEXT, lat REAL, lon REAL, "
        "desvio_metros REAL, n_casos INTEGER, endereco_completo TEXT)")
    conn.execute(
        "CREATE TABLE logradouros (estado TEXT, municipio TEXT, logradouro TEXT, "
        "localidade TEXT, lat REAL, lon REAL, desvio_metros REAL, "
        "n_casos INTEGER, endereco_completo TEXT)")
    for log, num, loc, lat, lon, desvio, casos in _ENDERECOS:
        conn.execute(
            "INSERT INTO enderecos VALUES ('MG','BELO HORIZONTE',?,?,?,?,?,?,?,?)",
            (log, num, loc, lat, lon, desvio, casos,
             "{}, {} - {}".format(log, num, loc)))
    for log, loc, lat, lon, desvio, casos in _LOGRADOUROS:
        conn.execute(
            "INSERT INTO logradouros VALUES ('MG','BELO HORIZONTE',?,?,?,?,?,?,?)",
            (log, loc, lat, lon, desvio, casos, "{} - {}".format(log, loc)))
    if com_metadata:
        conn.execute("CREATE TABLE metadata (chave TEXT PRIMARY KEY, valor TEXT)")
        conn.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            [("estado", "MG"), ("municipio", "BELO HORIZONTE"),
             ("data_release", "v0.4.1"), ("gerado_em", "2026-08-20T00:00:00"),
             ("versao_esquema", str(VERSAO_ESQUEMA))])
    conn.commit()
    conn.close()
    return caminho


class _BaseFabricada(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = _montar_base(os.path.join(self._tmp.name, "bh.sqlite"))

    def tearDown(self):
        CnefeGeocoder.esquecer()
        self._tmp.cleanup()

    def geocode(self, endereco):
        return CnefeGeocoder.geocode(endereco, {}, self.base)


class TestDegrausComNumero(_BaseFabricada):

    def test_degrau_1_exato_com_bairro(self):
        """`dn03`: logradouro + número + bairro bate uma linha só."""
        r = self.geocode("Avenida Amazonas, 1020, Centro")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["tipo_resultado"], "dn03")
        self.assertEqual(r[0]["lat"], str(-19.9210))
        self.assertEqual(r[0]["desvio_metros"], 6.0)
        self.assertTrue(r[0]["preciso"])
        self.assertEqual(r[0]["provider"], "cnefe")
        self.assertEqual(r[0]["properties"]["street"], "AVENIDA AMAZONAS")

    def test_degrau_2_sem_bairro(self):
        """`dn04`: sem bairro, o número sozinho ainda resolve."""
        r = self.geocode("Av. Amazonas, 1025")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["tipo_resultado"], "dn04")
        self.assertEqual(r[0]["lat"], str(-19.9220))
        self.assertTrue(r[0]["preciso"])

    def test_degrau_2_media_ponderada_por_n_casos(self):
        """Mesmo número em dois bairros: média ponderada por `n_casos`.

        Pesos 3 e 1 → a coordenada fica a 3/4 do caminho para a variante mais
        frequente, não no meio."""
        r = self.geocode("Rua Dois Bairros, 50")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["tipo_resultado"], "dn04")
        esperado = (-20.0000 * 3 + -20.0100 * 1) / 4.0
        self.assertAlmostEqual(float(r[0]["lat"]), esperado, places=6)
        # O desvio declarado é a média dos desvios das linhas agregadas.
        self.assertAlmostEqual(r[0]["desvio_metros"], 5.0, places=6)
        # O endereço exibido é o da variante com mais casos.
        self.assertIn("CENTRO", r[0]["display_name"])

    def test_degrau_3_numero_mais_proximo(self):
        """`da04`: o caso medido — `Avenida Amazonas, 1000` não existe no
        CNEFE, e o mais próximo é o 1020, com desvio declarado de 6 m."""
        r = self.geocode("Avenida Amazonas, 1000")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["tipo_resultado"], "da04")
        self.assertEqual(r[0]["lat"], str(-19.9210))
        self.assertEqual(r[0]["desvio_metros"], 6.0)
        self.assertTrue(r[0]["preciso"])

    def test_abreviatura_expandida_para_o_padrao_cnefe(self):
        """`Av. Dr. ...` só acha porque o CNEFE grava tudo por extenso."""
        r = self.geocode("Av. Dr. Cristiano Guimarães, 100")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["properties"]["street"],
                         "AVENIDA DOUTOR CRISTIANO GUIMARAES")
        self.assertTrue(r[0]["preciso"])


class TestDegrauDeVia(_BaseFabricada):

    def test_sem_numero_devolve_via_imprecisa(self):
        """Degrau 5: centroide da via nunca conta como acerto preciso — é o
        que impede a cascata de parar aí (decisão 168)."""
        r = self.geocode("Rua Só Centroide")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["tipo_resultado"], "dl04")
        self.assertFalse(r[0]["preciso"])
        self.assertEqual(r[0]["desvio_metros"], 120.0)

    def test_sem_numero_com_bairro(self):
        r = self.geocode("Avenida Amazonas, Centro")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["tipo_resultado"], "dl03")
        self.assertFalse(r[0]["preciso"])


class TestDegrauCorretor(_BaseFabricada):
    """Degrau 4 (decisão 170): a correção de grafia passa a ser local."""

    def test_erro_de_digitacao_e_corrigido(self):
        r = self.geocode("Avenida Amazonaz, 1020")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["properties"]["street"], "AVENIDA AMAZONAS")
        self.assertEqual(r[0]["lat"], str(-19.9210))

    def test_candidato_corrigido_vem_marcado_como_palpite(self):
        """Prefixo `p` no `tipo_resultado` — é o que faz o rótulo da decisão
        59 avisar que aquilo é palpite, não acerto exato."""
        r = self.geocode("Avenida Amazonaz, 1020")
        self.assertTrue(r[0]["tipo_resultado"].startswith("p"), r[0]["tipo_resultado"])

    def test_nome_sem_parentesco_nao_acha(self):
        self.assertEqual(self.geocode("Rua Xilofone Zebra Quasar, 5"), [])

    def test_corrigir_logradouro_devolve_none_quando_ja_esta_certo(self):
        self.assertIsNone(
            CnefeGeocoder.corrigir_logradouro(self.base, "AVENIDA AMAZONAS"))


class TestNuncaLevanta(unittest.TestCase):
    """O geocodificador nunca levanta: erro vira lista vazia (passo 4)."""

    def tearDown(self):
        CnefeGeocoder.esquecer()

    def test_base_inexistente(self):
        self.assertEqual(
            CnefeGeocoder.geocode("Av. Amazonas, 1020", {}, "/nao/existe.sqlite"), [])

    def test_sem_caminho_de_base(self):
        self.assertEqual(CnefeGeocoder.geocode("Av. Amazonas, 1020", {}, None), [])

    def test_endereco_vazio(self):
        self.assertEqual(CnefeGeocoder.geocode("", {}, "/nao/existe.sqlite"), [])

    def test_arquivo_corrompido(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "lixo.sqlite")
            with open(caminho, "wb") as fh:
                fh.write(b"isto nao e um sqlite")
            self.assertEqual(
                CnefeGeocoder.geocode("Av. Amazonas, 1020", {}, caminho), [])

    def test_base_sem_metadata_e_recusada(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = _montar_base(
                os.path.join(tmp, "sem_meta.sqlite"), com_metadata=False)
            self.assertEqual(
                CnefeGeocoder.geocode("Av. Amazonas, 1020", {}, caminho), [])


class TestCacheDeConexao(_BaseFabricada):

    def test_conexao_reaproveitada_e_descartada(self):
        self.geocode("Avenida Amazonas, 1020")
        self.assertIn(self.base, CnefeGeocoder._conexoes)
        primeira = CnefeGeocoder._conexoes[self.base]

        self.geocode("Avenida Amazonas, 1032")
        self.assertIs(CnefeGeocoder._conexoes[self.base], primeira)

        CnefeGeocoder.esquecer(self.base)
        self.assertNotIn(self.base, CnefeGeocoder._conexoes)


if __name__ == '__main__':
    unittest.main()
