# -*- coding: utf-8 -*-
"""Testes de `cnefe_padrao.py`: normalização de endereço para o padrão CNEFE
(decisão 169). Módulo puro, não importa Qt nem QGIS."""
import sys
import unittest

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from sig_bus.cnefe_padrao import (
    normalizar_texto,
    normalizar_logradouro_cnefe,
    normalizar_numero,
    normalizar_municipio,
    normalizar_uf,
)


class TestNormalizarTexto(unittest.TestCase):

    def test_caixa_alta_sem_acento_sem_pontuacao(self):
        self.assertEqual(
            normalizar_texto("Av. Dr. Cristiano Guimarães"),
            "AV DR CRISTIANO GUIMARAES",
        )

    def test_vazio_e_none(self):
        self.assertEqual(normalizar_texto(""), "")
        self.assertEqual(normalizar_texto(None), "")

    def test_espacos_em_excesso_colapsados(self):
        self.assertEqual(normalizar_texto("  Rua   das   Flores  "), "RUA DAS FLORES")


class TestNormalizarLogradouroCnefe(unittest.TestCase):

    def test_caso_medido_na_base_de_belo_horizonte(self):
        """Caso real da base do CNEFE de Belo Horizonte (decisão 169)."""
        self.assertEqual(
            normalizar_logradouro_cnefe("Av. Dr. Cristiano Guimarães"),
            "AVENIDA DOUTOR CRISTIANO GUIMARAES",
        )

    def test_tipo_e_titulo_padre(self):
        self.assertEqual(
            normalizar_logradouro_cnefe("R. Padre Eustáquio"),
            "RUA PADRE EUSTAQUIO",
        )

    def test_expressao_de_mais_de_uma_palavra(self):
        self.assertEqual(
            normalizar_logradouro_cnefe("Pça N. Sra. de Fátima"),
            "PRACA NOSSA SENHORA DE FATIMA",
        )

    def test_nao_regressao_dresde_nao_e_abreviatura_de_doutor(self):
        """`RUA DRESDE` tem que continuar `RUA DRESDE`: a via existe de
        verdade em Belo Horizonte e `DRESDE` começa com as letras `DR`, mas
        não é abreviatura de `DOUTOR` — a expansão de título é por palavra
        inteira (comparação exata), nunca por prefixo."""
        self.assertEqual(normalizar_logradouro_cnefe("RUA DRESDE"), "RUA DRESDE")

    def test_entrada_vazia(self):
        self.assertEqual(normalizar_logradouro_cnefe(""), "")


class TestNormalizarNumero(unittest.TestCase):

    def test_numero_simples(self):
        self.assertEqual(normalizar_numero("210"), 210)

    def test_numero_com_complemento(self):
        self.assertEqual(normalizar_numero("210-A"), 210)

    def test_numero_ja_inteiro(self):
        self.assertEqual(normalizar_numero(210), 210)

    def test_sem_numero_vira_none(self):
        self.assertIsNone(normalizar_numero("s/n"))
        self.assertIsNone(normalizar_numero("SN"))
        self.assertIsNone(normalizar_numero(""))
        self.assertIsNone(normalizar_numero(None))


class TestNormalizarMunicipio(unittest.TestCase):

    def test_belo_horizonte(self):
        self.assertEqual(normalizar_municipio("Belo Horizonte"), "BELO HORIZONTE")


class TestNormalizarUf(unittest.TestCase):

    def test_sigla_minuscula(self):
        self.assertEqual(normalizar_uf("mg"), "MG")

    def test_nome_por_extenso(self):
        self.assertEqual(normalizar_uf("Minas Gerais"), "MG")
        self.assertEqual(normalizar_uf("São Paulo"), "SP")

    def test_vazio(self):
        self.assertEqual(normalizar_uf(""), "")


if __name__ == '__main__':
    unittest.main()
