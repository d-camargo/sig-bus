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
    get_cnefe_base_path, set_cnefe_base_path,
    get_cnefe_habilitado, set_cnefe_habilitado,
    pasta_padrao_bases,
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


class TestCnefeBasePath(unittest.TestCase):
    """Caminho da base local do CNEFE (passo 7)."""

    def test_default_e_vazio(self):
        self.assertEqual(get_cnefe_base_path(settings=_SettingsFalso()), "")

    def test_ida_e_volta(self):
        s = _SettingsFalso()
        set_cnefe_base_path("/caminho/para/cnefe_bh.sqlite", settings=s)
        self.assertEqual(get_cnefe_base_path(settings=s), "/caminho/para/cnefe_bh.sqlite")

    def test_caminho_so_com_espacos_conta_como_ausente(self):
        s = _SettingsFalso({"SIG-Bus/geocoding/cnefe_base_path": "   "})
        self.assertEqual(get_cnefe_base_path(settings=s), "")

        s2 = _SettingsFalso()
        set_cnefe_base_path("   ", settings=s2)
        self.assertEqual(get_cnefe_base_path(settings=s2), "")

    def test_none_conta_como_ausente(self):
        s = _SettingsFalso({"SIG-Bus/geocoding/cnefe_base_path": None})
        self.assertEqual(get_cnefe_base_path(settings=s), "")

    def test_valor_nao_textual_conta_como_ausente(self):
        s = _SettingsFalso({"SIG-Bus/geocoding/cnefe_base_path": object()})
        self.assertEqual(get_cnefe_base_path(settings=s), "")


class TestCnefeHabilitado(unittest.TestCase):
    """Chave liga/desliga da base local (passo 7).

    O padrão é ligado, e isso não muda nada para quem não tem base: sem
    caminho configurado a base nunca é consultada."""

    def test_default_e_ligado(self):
        self.assertTrue(get_cnefe_habilitado(settings=_SettingsFalso()))

    def test_ida_e_volta(self):
        s = _SettingsFalso()
        set_cnefe_habilitado(False, settings=s)
        self.assertFalse(get_cnefe_habilitado(settings=s))
        set_cnefe_habilitado(True, settings=s)
        self.assertTrue(get_cnefe_habilitado(settings=s))

    def test_texto_do_ini_conta_como_booleano(self):
        """O `QSettings` em arquivo `.ini` devolve a string 'false'."""
        s = _SettingsFalso({"SIG-Bus/geocoding/cnefe_habilitado": "false"})
        self.assertFalse(get_cnefe_habilitado(settings=s))
        s = _SettingsFalso({"SIG-Bus/geocoding/cnefe_habilitado": "true"})
        self.assertTrue(get_cnefe_habilitado(settings=s))

    def test_valor_estranho_volta_ao_padrao(self):
        s = _SettingsFalso({"SIG-Bus/geocoding/cnefe_habilitado": object()})
        self.assertTrue(get_cnefe_habilitado(settings=s))


class TestPastaPadraoBases(unittest.TestCase):

    def test_termina_em_sig_bus_cnefe(self):
        caminho = pasta_padrao_bases()
        self.assertTrue(caminho.endswith(os.path.join("sig_bus", "cnefe")), caminho)


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
            set_cnefe_base_path("/caminho/para/cnefe_bh.sqlite", settings=s)
            set_cnefe_habilitado(False, settings=s)
            s.sync()

            s2 = QSettings(caminho, QSettings.Format.IniFormat)
            self.assertEqual(get_provider_mode(settings=s2), "osm")
            self.assertEqual(get_google_api_key(settings=s2), "AIza-CHAVE-DE-TESTE")
            self.assertEqual(get_cnefe_base_path(settings=s2), "/caminho/para/cnefe_bh.sqlite")
            self.assertFalse(get_cnefe_habilitado(settings=s2))


if __name__ == '__main__':
    unittest.main()

