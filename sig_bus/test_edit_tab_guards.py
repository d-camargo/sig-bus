# -*- coding: utf-8 -*-
"""Passo 195: guarda de regressão da aba "Edição GTFS" (decisões 137, 138, 142).

No estilo de varredura de texto de `test_qt6_compat.py`: o diálogo inteiro não
é instanciável fora do QGIS, então o que se verifica aqui é a fonte de
`SigBus_dialog.py`. Falha se:

(a) `enter_empty(` voltar a ser chamado fora de `_ensure_build_working_copy` —
    criar a cópia de trabalho por efeito colateral da troca de aba sequestra o
    modo de edição de quem só espiou o assistente (decisão 137);
(b) `button_edit_enter.setEnabled(False)` voltar a existir — o "Entrar no modo
    edição" desabilitado é beco sem saída (decisão 138);
(c) `editOpenClicked` voltar a chamar `self.close()` — o plugin tem que voltar
    quando a tabela de atributos fecha, não sumir (decisão 142).
"""
import inspect
import os
import re
import unittest
from unittest.mock import MagicMock

from sig_bus.SigBus_dialog import SigBusDialog

DIALOG_PY = os.path.join(os.path.dirname(__file__), "SigBus_dialog.py")


def _fonte():
    with open(DIALOG_PY, encoding="utf-8") as fh:
        return fh.read()


class TestEditTabGuards(unittest.TestCase):
    # (a) decisão 137 -------------------------------------------------
    def test_enter_empty_so_dentro_de_ensure_build_working_copy(self):
        fonte = _fonte()
        no_arquivo = len(re.findall(r"\benter_empty\(", fonte))
        no_metodo = len(re.findall(
            r"\benter_empty\(", inspect.getsource(SigBusDialog._ensure_build_working_copy)))
        self.assertGreaterEqual(no_metodo, 1, "_ensure_build_working_copy deixou de criar a cópia vazia")
        self.assertEqual(
            no_arquivo, no_metodo,
            "enter_empty() só pode ser chamado por _ensure_build_working_copy (decisão 137)")

    def test_on_tab_changed_nao_cria_copia_de_trabalho(self):
        fonte = inspect.getsource(SigBusDialog._on_tab_changed)
        self.assertNotIn("enter_empty", fonte)
        self.assertNotIn("WorkingCopy(", fonte)

    def test_troca_de_aba_nao_deixa_working_copy(self):
        dialog = SigBusDialog.__new__(SigBusDialog)
        dialog._working_copy = None
        dialog.tabWidget = MagicMock()
        dialog.tabWidget.tabText.return_value = "Construir GTFS"
        dialog._update_build_progress = MagicMock()
        dialog._load_agency_data = MagicMock()
        dialog._update_build_nav_buttons = MagicMock()

        dialog._on_tab_changed(0)

        self.assertIsNone(dialog._working_copy)
        dialog._update_build_progress.assert_called_once()
        dialog._load_agency_data.assert_called_once()
        dialog._update_build_nav_buttons.assert_called_once()

    def test_save_agency_e_pagina_paradas_garantem_a_copia(self):
        """A cópia vazia nasce nos pontos que gravam, não na troca de aba."""
        self.assertIn("_ensure_build_working_copy",
                      inspect.getsource(SigBusDialog._on_save_agency_clicked))
        self.assertIn("_ensure_build_working_copy",
                      inspect.getsource(SigBusDialog._on_build_next_clicked))

    # (b) decisão 138 -------------------------------------------------
    def test_botao_entrar_nunca_desabilitado(self):
        self.assertNotIn("button_edit_enter.setEnabled(False)", _fonte())

    def test_status_diz_de_onde_veio_a_copia(self):
        dialog = SigBusDialog.__new__(SigBusDialog)
        for atributo in ("label_edit_status", "button_edit_enter", "combo_edit_table",
                         "button_edit_open", "button_edit_validate", "button_edit_export",
                         "button_edit_discard", "label_edit_route", "combo_edit_route",
                         "label_edit_trip", "combo_edit_trip", "button_edit_schedule"):
            setattr(dialog, atributo, MagicMock())
        dialog._populate_edit_routes = MagicMock()

        wc = MagicMock()
        wc.is_active.return_value = True
        wc.edit_path = "/tmp/feed_edit.gpkg"

        # Cópia vinda de um feed carregado: o rótulo nomeia a origem.
        wc.source_path = "/tmp/bhtrans.gpkg"
        dialog._working_copy = wc
        dialog._refresh_edit_status()
        texto = dialog.label_edit_status.setText.call_args[0][0]
        self.assertIn("feed_edit.gpkg", texto)
        self.assertIn("bhtrans.gpkg", texto)
        dialog.button_edit_enter.setEnabled.assert_called_with(True)

        # Cópia vazia do assistente: o rótulo avisa que é rascunho.
        wc.source_path = None
        dialog._refresh_edit_status()
        self.assertIn("assistente", dialog.label_edit_status.setText.call_args[0][0])
        dialog.button_edit_enter.setEnabled.assert_called_with(True)

        # Sem edição nenhuma: o botão continua clicável.
        dialog._working_copy = None
        dialog._refresh_edit_status()
        dialog.button_edit_enter.setEnabled.assert_called_with(True)

    def test_pergunta_do_entrar_explica_cada_resposta(self):
        fonte = inspect.getsource(SigBusDialog.editEnterClicked)
        self.assertIn("Sim = recriar", fonte)
        self.assertIn("Não = retomar", fonte)

    # (c) decisão 142 -------------------------------------------------
    def test_edit_open_esconde_e_devolve_o_plugin(self):
        fonte = inspect.getsource(SigBusDialog.editOpenClicked)
        self.assertNotIn("self.close()", fonte)
        self.assertIn("self.hide()", fonte)
        self.assertIn("_on_edit_table_closed", fonte)

    def test_volta_pergunta_por_edicao_nao_gravada(self):
        fonte = inspect.getsource(SigBusDialog._on_edit_table_closed)
        for esperado in ("self.show()", "self.raise_()", "self.activateWindow()",
                         "isModified()", "commitChanges()", "_refresh_edit_status()"):
            self.assertIn(esperado, fonte)


if __name__ == "__main__":
    unittest.main()
