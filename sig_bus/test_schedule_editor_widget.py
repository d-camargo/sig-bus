# -*- coding: utf-8 -*-
"""Passo 201: o editor de horários (diagrama + matriz sobre o mesmo rascunho).

Roda com QApplication real, como test_block_scene_headway.py — exige
QT_QPA_PLATFORM=offscreen.
"""
import unittest

from qgis.PyQt.QtWidgets import QApplication

from sig_bus.schedule_editor_widget import ScheduleEditorWidget


def grade():
    """Duas viagens de três paradas, 30 min de percurso, 30 min de headway."""
    linhas = []
    for trip_id, saidas in (
        ("T1", ["06:00:00", "06:15:00", "06:30:00"]),
        ("T2", ["06:30:00", "06:45:00", "07:00:00"]),
    ):
        for i, hora in enumerate(saidas, start=1):
            linhas.append({
                "trip_id": trip_id,
                "stop_id": "S{}".format(i),
                "stop_sequence": i,
                "arrival_time": hora,
                "departure_time": hora,
            })
    return linhas


class TestScheduleEditorWidget(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.widget = ScheduleEditorWidget(
            grade(), route_short_name="101", direction_id="0",
            trip_headsign="Terminal", stops=[{"stop_id": "S1", "stop_name": "Praça"}])

    def _celula(self, trip_id, stop_seq):
        col = self.widget.trip_ids().index(trip_id) + 1
        linha = [i for i, s in enumerate(self.widget.grid.table_obj.stops)
                 if s["stop_id"] == "S{}".format(stop_seq)][0]
        return self.widget.grid.item(linha, col)

    def _seleciona(self, trip_id, endpoint='first'):
        item = self.widget.schedule_scene._trip_items[trip_id]
        self.widget.schedule_scene.select_trip_item(item, endpoint=endpoint)

    # --- montagem -----------------------------------------------------
    def test_matriz_nasce_com_uma_coluna_por_viagem_e_cabecalho_legivel(self):
        grid = self.widget.grid
        self.assertEqual(grid.columnCount(), 3)  # Parada + 2 viagens
        self.assertEqual(grid.horizontalHeaderItem(0).text(), "Parada")
        self.assertEqual(grid.horizontalHeaderItem(1).text(), "V1\n06:00")
        self.assertEqual(grid.horizontalHeaderItem(2).text(), "V2\n06:30")
        # O trip_id sai do rótulo e vira tooltip (decisão 135).
        self.assertEqual(grid.horizontalHeaderItem(1).toolTip(), "T1")
        # Nome da parada na primeira coluna, stop_id no tooltip (decisão 136).
        self.assertEqual(grid.item(0, 0).text(), "Praça")
        self.assertEqual(grid.item(0, 0).toolTip(), "S1")
        # O diagrama nasce com as duas viagens.
        self.assertEqual(set(self.widget.schedule_scene._trip_items), {"T1", "T2"})

    # --- escrita pelo diagrama ---------------------------------------
    def test_nudge_maior_move_so_o_extremo_e_a_celula_acompanha(self):
        self._seleciona("T1", endpoint='first')
        self.widget.schedule_view.nudgeKeyPressed.emit('>')

        # Saída deslocada de 15 min (passo padrão do spin); chegada intacta.
        self.assertEqual(self._celula("T1", 1).text(), "06:15:00")
        self.assertEqual(self._celula("T1", 3).text(), "06:30:00")

    def test_nudge_mais_move_a_viagem_inteira_preservando_a_duracao(self):
        self._seleciona("T1")
        self.widget.schedule_view.nudgeKeyPressed.emit('+')

        self.assertEqual(self._celula("T1", 1).text(), "06:15:00")
        self.assertEqual(self._celula("T1", 2).text(), "06:30:00")
        self.assertEqual(self._celula("T1", 3).text(), "06:45:00")
        # A outra viagem não se mexeu.
        self.assertEqual(self._celula("T2", 1).text(), "06:30:00")

    # --- escrita pela matriz ------------------------------------------
    def test_celula_editada_desloca_a_viagem_inteira_e_redesenha(self):
        recebidos = []
        self.widget.scheduleChanged.connect(lambda: recebidos.append(1))

        self._celula("T1", 2).setText("06:47:00")

        # 06:15 -> 06:47 são 32 min em toda a viagem (decisão 112).
        self.assertEqual(self._celula("T1", 1).text(), "06:32:00")
        self.assertEqual(self._celula("T1", 3).text(), "07:02:00")
        self.assertEqual(len(recebidos), 1)
        # O diagrama acompanhou o rascunho.
        item = self.widget.schedule_scene._trip_items["T1"]
        self.assertEqual(item.trip.start_time_s, 6 * 3600 + 32 * 60)

    def test_celula_ilegivel_bloqueia_sem_mexer_no_rascunho(self):
        self._celula("T1", 1).setText("seis e meia")

        self.assertTrue(self.widget.illegible_times())
        self.assertEqual(self.widget.changed_rows(), [])

    # --- o que grava ---------------------------------------------------
    def test_changed_rows_vazio_ate_alguem_mexer(self):
        self.assertEqual(self.widget.changed_rows(), [])

        self._seleciona("T2")
        self.widget.schedule_view.nudgeKeyPressed.emit('+')

        alterados = self.widget.changed_rows()
        self.assertEqual({st["trip_id"] for st in alterados}, {"T2"})
        self.assertEqual(len(alterados), 3)
        self.assertEqual(sorted(st["departure_time"] for st in alterados),
                         ["06:45:00", "07:00:00", "07:15:00"])

    def test_set_stop_times_troca_o_rascunho_inteiro(self):
        nova = [st for st in grade() if st["trip_id"] == "T1"]
        self.widget.set_stop_times(nova)

        self.assertEqual(self.widget.trip_ids(), ["T1"])
        self.assertEqual(self.widget.grid.columnCount(), 2)

    # --- enquadramento (decisão 109) -----------------------------------
    def test_escala_da_view_sobrevive_a_um_nudge(self):
        self.widget.schedule_view.fit_all()
        escala_antes = self.widget.schedule_view.transform().m11()

        self._seleciona("T1")
        self.widget.schedule_view.nudgeKeyPressed.emit('+')

        self.assertAlmostEqual(
            self.widget.schedule_view.transform().m11(), escala_antes, places=5)


if __name__ == "__main__":
    unittest.main()
