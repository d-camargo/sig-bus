# -*- coding: utf-8 -*-
"""Passo 107: a configuração de geocodificação mora no `QSettings` do usuário,
nunca no GeoPackage (decisão 62). Os testes injetam um `QSettings` de arquivo
temporário via `settings=` para não sujar a configuração real de quem roda."""
import os
import sys
import tempfile
import unittest

# Adiciona o diretório do projeto ao path
sys.path.insert(0, '/home/diego/projects/sig-bus')

from sig_bus.geocoding_config import (
    get_provider_mode, set_provider_mode,
    get_google_api_key, set_google_api_key,
)


class _SettingsFalso(object):
    """Dublê do `QSettings`: mesma interface (`value`/`setValue`) sem depender do
    Qt, para o teste rodar também com os mocks do conftest."""

    def __init__(self, inicial=None):
        self._dados = dict(inicial or {})

    def value(self, chave, default=None):
        return self._dados.get(chave, default)

    def setValue(self, chave, valor):
        self._dados[chave] = valor


class TestProviderMode(unittest.TestCase):

    def test_default_e_auto(self):
        self.assertEqual(get_provider_mode(settings=_SettingsFalso()), "auto")

    def test_ida_e_volta(self):
        s = _SettingsFalso()
        set_provider_mode("osm", settings=s)
        self.assertEqual(get_provider_mode(settings=s), "osm")
        set_provider_mode("auto", settings=s)
        self.assertEqual(get_provider_mode(settings=s), "auto")

    def test_modo_invalido_cai_no_default(self):
        s = _SettingsFalso({"SIG-Bus/geocoding/provider": "bing"})
        self.assertEqual(get_provider_mode(settings=s), "auto")

    def test_gravar_modo_invalido_grava_o_default(self):
        s = _SettingsFalso()
        set_provider_mode("bing", settings=s)
        self.assertEqual(get_provider_mode(settings=s), "auto")

    def test_valor_nao_textual_cai_no_default(self):
        s = _SettingsFalso({"SIG-Bus/geocoding/provider": object()})
        self.assertEqual(get_provider_mode(settings=s), "auto")


class TestGoogleApiKey(unittest.TestCase):

    def test_default_e_vazio(self):
        self.assertEqual(get_google_api_key(settings=_SettingsFalso()), "")

    def test_ida_e_volta(self):
        s = _SettingsFalso()
        set_google_api_key("AIza-CHAVE-DE-TESTE", settings=s)
        self.assertEqual(get_google_api_key(settings=s), "AIza-CHAVE-DE-TESTE")

    def test_chave_so_com_espacos_conta_como_ausente(self):
        s = _SettingsFalso({"SIG-Bus/geocoding/google_api_key": "   "})
        self.assertEqual(get_google_api_key(settings=s), "")

        s2 = _SettingsFalso()
        set_google_api_key("   ", settings=s2)
        self.assertEqual(get_google_api_key(settings=s2), "")

    def test_none_conta_como_ausente(self):
        s = _SettingsFalso({"SIG-Bus/geocoding/google_api_key": None})
        self.assertEqual(get_google_api_key(settings=s), "")

    def test_valor_nao_textual_conta_como_ausente(self):
        """Sem esta guarda um objeto qualquer viraria "chave" por `str()` e o
        plugin dispararia requisições faturáveis com credencial de mentira."""
        s = _SettingsFalso({"SIG-Bus/geocoding/google_api_key": object()})
        self.assertEqual(get_google_api_key(settings=s), "")


class TestQSettingsReal(unittest.TestCase):
    """Mesmo ida-e-volta contra um `QSettings` de verdade, em arquivo temporário
    — o dublê acima não provaria que a chave/formato batem com o Qt."""

    def test_ida_e_volta_em_arquivo_temporario(self):
        try:
            from qgis.PyQt.QtCore import QSettings
        except ImportError:
            self.skipTest("exige Qt real")
        if not hasattr(QSettings, "IniFormat"):
            self.skipTest("exige Qt real (rodando com os mocks do conftest)")

        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "teste.ini")
            s = QSettings(caminho, QSettings.Format.IniFormat)

            set_provider_mode("osm", settings=s)
            set_google_api_key("AIza-CHAVE-DE-TESTE", settings=s)
            s.sync()

            s2 = QSettings(caminho, QSettings.Format.IniFormat)
            self.assertEqual(get_provider_mode(settings=s2), "osm")
            self.assertEqual(get_google_api_key(settings=s2), "AIza-CHAVE-DE-TESTE")


if __name__ == '__main__':
    unittest.main()
