# -*- coding: utf-8 -*-
"""Passos 211-212: a janela cabe na tela em que abre (decisões 148-154).

As funções de conta não importam Qt e são testadas sem QApplication. Só o
último bloco (`preparar_janela`) instancia widget de verdade — exige
QT_QPA_PLATFORM=offscreen, como test_schedule_editor_widget.py.
"""
import unittest

from sig_bus.ui_geometry import (
    ajustar_ao_disponivel,
    cabe_na_tela,
    divisao_splitter,
    divisao_vertical,
)


class TestAjustarAoDisponivel(unittest.TestCase):
    def test_tela_grande_devolve_o_desejado_intacto(self):
        # Monitor de 2560x1440: nada de esticar a janela, ela nasce como pedida.
        self.assertEqual(ajustar_ao_disponivel(1180, 620, 2560, 1440),
                         (1180, 620))

    def test_tela_menor_que_o_desejado_encolhe_com_margem(self):
        # Notebook de 1366x768 com a barra de tarefas já descontada: o desejado
        # ainda cabe, então nada muda.
        self.assertEqual(ajustar_ao_disponivel(1180, 620, 1366, 728),
                         (1180, 620))
        # Área útil menor que o desejado: encolhe, e sobra a margem.
        w, h = ajustar_ao_disponivel(1180, 620, 1200, 600)
        self.assertEqual((w, h), (1200 - 48, 600 - 48))

    def test_tela_minuscula_nunca_devolve_zero_nem_negativo(self):
        for disp in ((40, 30), (1, 1), (0, 0)):
            w, h = ajustar_ao_disponivel(1180, 620, *disp)
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)
            if disp[0] > 0:
                self.assertLessEqual(w, disp[0])
                self.assertLessEqual(h, disp[1])


class TestDivisaoSplitter(unittest.TestCase):
    def test_divisao_folgada_respeita_a_fracao_e_soma_o_total(self):
        esq, dir_ = divisao_splitter(900)
        self.assertEqual(esq + dir_, 900)
        self.assertEqual(esq, 495)          # 55% de 900
        self.assertGreaterEqual(esq, 340)
        self.assertGreaterEqual(dir_, 280)

    def test_divisao_apertada_divide_em_vez_de_zerar_um_lado(self):
        esq, dir_ = divisao_splitter(400)   # não comporta 340 + 280
        self.assertEqual(esq + dir_, 400)
        self.assertGreater(esq, 0)
        self.assertGreater(dir_, 0)

    def test_largura_no_limite_dos_minimos(self):
        esq, dir_ = divisao_splitter(620)   # exatamente 340 + 280
        self.assertEqual([esq, dir_], [340, 280])


class TestDivisaoVertical(unittest.TestCase):
    def test_divisao_folgada_respeita_a_fracao_e_soma_o_total(self):
        topo, base = divisao_vertical(1000)
        self.assertEqual(topo + base, 1000)
        self.assertEqual(topo, 450)         # 45% de 1000
        self.assertGreaterEqual(topo, 170)
        self.assertGreaterEqual(base, 230)

    def test_altura_no_limite_dos_minimos(self):
        topo, base = divisao_vertical(400)  # exatamente 170 + 230
        self.assertEqual([topo, base], [170, 230])

    def test_divisao_apertada_divide_em_vez_de_zerar_um_lado(self):
        topo, base = divisao_vertical(300)  # não comporta 170 + 230
        self.assertEqual(topo + base, 300)
        self.assertGreater(topo, 0)
        self.assertGreater(base, 0)


class TestCabeNaTela(unittest.TestCase):
    def test_geometria_salva_que_cabe(self):
        self.assertTrue(cabe_na_tela(100, 80, 1180, 620, 0, 0, 1920, 1080))

    def test_geometria_salva_que_nao_cabe(self):
        # Janela deixada num monitor externo, reaberta no notebook.
        self.assertFalse(cabe_na_tela(2000, 80, 1180, 620, 0, 0, 1366, 768))
        self.assertFalse(cabe_na_tela(0, 0, 1180, 620, 0, 0, 1000, 620))

    def test_geometria_degenerada_nao_cabe(self):
        self.assertFalse(cabe_na_tela(0, 0, 0, 620, 0, 0, 1920, 1080))


class TestPrepararJanela(unittest.TestCase):
    """Único bloco que toca Qt (passo 212)."""

    def setUp(self):
        from qgis.PyQt.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])

    def test_janela_absurda_termina_cabendo_na_area_util(self):
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtWidgets import QApplication, QDialog
        from sig_bus.ui_geometry import preparar_janela

        dialog = QDialog()
        preparar_janela(dialog, 4000, 3000)

        area = QApplication.primaryScreen().availableGeometry()
        self.assertLessEqual(dialog.width(), area.width())
        self.assertLessEqual(dialog.height(), area.height())
        self.assertGreater(dialog.width(), 0)
        self.assertGreater(dialog.height(), 0)

        flags = dialog.windowFlags()
        self.assertTrue(flags & Qt.WindowType.WindowMaximizeButtonHint)
        self.assertTrue(flags & Qt.WindowType.WindowMinimizeButtonHint)

    def test_sem_tela_resolvivel_apenas_redimensiona(self):
        from qgis.PyQt.QtWidgets import QDialog
        from sig_bus.ui_geometry import preparar_janela

        dialog = QDialog()
        preparar_janela(dialog, 800, 600, tela=_TelaQuebrada())
        self.assertEqual((dialog.width(), dialog.height()), (800, 600))


class _TelaQuebrada:
    """Tela que não sabe dizer sua área útil — headless não pode explodir."""

    def availableGeometry(self):
        raise RuntimeError("sem tela")


class TestRestaurarSeCouber(unittest.TestCase):
    def setUp(self):
        from qgis.PyQt.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])

    def test_sem_geometria_salva_nao_mexe_na_janela(self):
        from qgis.PyQt.QtWidgets import QDialog
        from sig_bus.ui_geometry import preparar_janela, restaurar_se_couber

        dialog = QDialog()
        preparar_janela(dialog, 640, 480)
        antes = (dialog.width(), dialog.height())
        self.assertFalse(restaurar_se_couber(dialog, None))
        self.assertEqual((dialog.width(), dialog.height()), antes)

    def test_geometria_que_cabe_volta_a_valer(self):
        from qgis.PyQt.QtWidgets import QDialog
        from sig_bus.ui_geometry import preparar_janela, restaurar_se_couber

        salvo = QDialog()
        salvo.resize(700, 400)
        salvo.move(20, 20)
        blob = salvo.saveGeometry()

        dialog = QDialog()
        preparar_janela(dialog, 1180, 620)
        self.assertTrue(restaurar_se_couber(dialog, blob))
        self.assertEqual((dialog.width(), dialog.height()), (700, 400))

    def test_geometria_maior_que_a_tela_nao_sobrevive(self):
        """Geometria salva num monitor grande não pode voltar como janela
        fora da tela do notebook (decisão 152). Não importa quem clampa —
        o Qt6 já encolhe a janela no próprio `restoreGeometry`, o Qt5 não e
        aí é o `restaurar_se_couber` que descarta —, o que a janela não pode
        é terminar maior que a área útil."""
        from qgis.PyQt.QtWidgets import QApplication, QDialog
        from sig_bus.ui_geometry import (
            cabe_na_tela, preparar_janela, restaurar_se_couber)

        area = QApplication.primaryScreen().availableGeometry()
        gigante = QDialog()
        gigante.resize(area.width() * 3, area.height() * 3)
        gigante.move(area.x(), area.y())
        blob = gigante.saveGeometry()

        dialog = QDialog()
        preparar_janela(dialog, 1180, 620)
        restaurar_se_couber(dialog, blob)

        g = dialog.frameGeometry()
        self.assertTrue(cabe_na_tela(g.x(), g.y(), g.width(), g.height(),
                                     area.x(), area.y(),
                                     area.width(), area.height()))


if __name__ == '__main__':
    unittest.main()
