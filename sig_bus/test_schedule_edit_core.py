# -*- coding: utf-8 -*-
"""Testes do núcleo puro de edição de horários (Fase 12, passos 120-124)."""
import unittest

from sig_bus.schedule_edit_core import (
    to_seconds,
    from_seconds,
    expand_frequency_to_stop_times,
    trips_from_stop_times,
    headways,
    validate_draft_times,
    shift_trip,
    shift_trip_endpoint,
    schedule_from_draft,
)


def grade(*viagens):
    """Monta uma grade de stop_times a partir de (trip_id, [horários])."""
    linhas = []
    for trip_id, horarios in viagens:
        for seq, h in enumerate(horarios, start=1):
            linhas.append({
                "trip_id": trip_id,
                "arrival_time": h,
                "departure_time": h,
                "stop_id": "S{}".format(seq),
                "stop_sequence": seq,
            })
    return linhas


GRADE_3X30 = grade(
    ("T1", ["06:00:00", "06:15:00", "06:30:00"]),
    ("T2", ["06:30:00", "06:45:00", "07:00:00"]),
    ("T3", ["07:00:00", "07:15:00", "07:30:00"]),
)


class TestScheduleEditCore(unittest.TestCase):

    def test_to_seconds(self):
        self.assertEqual(to_seconds("00:00:00"), 0)
        self.assertEqual(to_seconds("06:30:15"), 23415)
        self.assertEqual(to_seconds("25:30:00"), 91800)
        self.assertEqual(to_seconds("08:15"), 29700)
        self.assertEqual(to_seconds(""), 0)
        self.assertEqual(to_seconds(None), 0)

    def test_from_seconds(self):
        self.assertEqual(from_seconds(0), "00:00:00")
        self.assertEqual(from_seconds(23415), "06:30:15")
        self.assertEqual(from_seconds(91800), "25:30:00")
        self.assertEqual(from_seconds(None), "00:00:00")

    def test_expand_frequency_to_stop_times(self):
        trips, stop_times = expand_frequency_to_stop_times(
            ["stopA", "stopB"], "06:00:00", "07:00:00", 30, prefix="L100_0"
        )
        self.assertEqual([t["trip_id"] for t in trips],
                         ["trip_L100_0_060000", "trip_L100_0_063000", "trip_L100_0_070000"])
        self.assertEqual(len(stop_times), 6)
        self.assertEqual(stop_times[0]["arrival_time"], "06:00:00")

    def test_expand_frequency_with_duracao(self):
        trips, stop_times = expand_frequency_to_stop_times(
            ["stopA", "stopB", "stopC"], "06:00:00", "06:00:00", 60, duracao_min=30
        )
        self.assertEqual(len(trips), 1)
        self.assertEqual([st["arrival_time"] for st in stop_times],
                         ["06:00:00", "06:15:00", "06:30:00"])

    # --- passo 120 ----------------------------------------------------
    def test_trips_from_stop_times(self):
        viagens = trips_from_stop_times(GRADE_3X30)
        self.assertEqual([v["trip_id"] for v in viagens], ["T1", "T2", "T3"])
        self.assertEqual([v["start_s"] for v in viagens],
                         [to_seconds("06:00:00"), to_seconds("06:30:00"), to_seconds("07:00:00")])
        self.assertEqual([v["end_s"] for v in viagens],
                         [to_seconds("06:30:00"), to_seconds("07:00:00"), to_seconds("07:30:00")])
        self.assertEqual([v["n_stops"] for v in viagens], [3, 3, 3])

    def test_trips_from_stop_times_ordena_por_saida(self):
        # A grade traz T2 antes de T1; o resumo sai em ordem de saída.
        invertida = grade(("T2", ["07:00:00"]), ("T1", ["06:00:00"]))
        self.assertEqual([v["trip_id"] for v in trips_from_stop_times(invertida)],
                         ["T1", "T2"])

    def test_headways(self):
        hw = headways(GRADE_3X30)
        self.assertIsNone(hw["T1"])
        self.assertEqual(hw["T2"], 1800)
        self.assertEqual(hw["T3"], 1800)

    # --- passo 121 ----------------------------------------------------
    def test_shift_trip_move_a_viagem_inteira(self):
        movida = shift_trip(GRADE_3X30, "T1", 900)
        t1 = [st["arrival_time"] for st in movida if st["trip_id"] == "T1"]
        self.assertEqual(t1, ["06:15:00", "06:30:00", "06:45:00"])
        # duração preservada
        self.assertEqual(to_seconds(t1[-1]) - to_seconds(t1[0]), 30 * 60)
        # nenhuma outra viagem se move
        self.assertEqual([st["arrival_time"] for st in movida if st["trip_id"] == "T2"],
                         ["06:30:00", "06:45:00", "07:00:00"])
        # a lista de entrada não é mutada
        self.assertEqual(GRADE_3X30[0]["arrival_time"], "06:00:00")

    def test_shift_trip_acima_de_24h(self):
        tarde = grade(("T1", ["23:50:00"]))
        self.assertEqual(shift_trip(tarde, "T1", 900)[0]["arrival_time"], "24:05:00")

    def test_shift_trip_recusa_antes_de_meia_noite(self):
        cedo = grade(("T1", ["00:05:00"]))
        self.assertEqual(shift_trip(cedo, "T1", -900)[0]["arrival_time"], "00:05:00")

    # --- passo 122 ----------------------------------------------------
    def test_shift_trip_endpoint_last(self):
        r = shift_trip_endpoint(GRADE_3X30, "T1", "last", 900)
        self.assertEqual([st["arrival_time"] for st in r if st["trip_id"] == "T1"],
                         ["06:00:00", "06:22:30", "06:45:00"])

    def test_shift_trip_endpoint_first(self):
        r = shift_trip_endpoint(GRADE_3X30, "T1", "first", 900)
        self.assertEqual([st["arrival_time"] for st in r if st["trip_id"] == "T1"],
                         ["06:15:00", "06:22:30", "06:30:00"])

    def test_shift_trip_endpoint_nunca_decresce(self):
        r = shift_trip_endpoint(GRADE_3X30, "T1", "first", 840)
        horarios = [to_seconds(st["arrival_time"]) for st in r if st["trip_id"] == "T1"]
        self.assertEqual(horarios, sorted(horarios))

    def test_shift_trip_endpoint_recusa_cruzamento(self):
        # +3600 na saída cruzaria a chegada: grade intacta
        r = shift_trip_endpoint(GRADE_3X30, "T1", "first", 3600)
        self.assertEqual([st["arrival_time"] for st in r if st["trip_id"] == "T1"],
                         ["06:00:00", "06:15:00", "06:30:00"])

    def test_shift_trip_endpoint_viagem_inexistente(self):
        r = shift_trip_endpoint(GRADE_3X30, "TX", "first", 900)
        self.assertEqual([st["arrival_time"] for st in r],
                         [st["arrival_time"] for st in GRADE_3X30])

    def test_shift_trip_endpoint_vazio(self):
        self.assertEqual(shift_trip_endpoint([], "T1", "first", 300), [])

    def test_shift_trip_endpoint_invalido(self):
        with self.assertRaises(ValueError):
            shift_trip_endpoint(GRADE_3X30, "T1", "middle", 300)

    # --- passo 123 ----------------------------------------------------
    def test_validate_draft_times_grade_limpa(self):
        erros, avisos = validate_draft_times(GRADE_3X30)
        self.assertEqual(erros, [])
        self.assertEqual(avisos, [])

    def test_validate_draft_times_viagem_invertida(self):
        invertida = grade(("T1", ["06:30:00", "06:15:00"]))
        erros, avisos = validate_draft_times(invertida)
        self.assertEqual(len(erros), 1)

    def test_validate_draft_times_ordem_trocada_e_aviso(self):
        # T2 empurrada para antes de T1: nenhum erro, um aviso.
        trocada = grade(
            ("T1", ["07:00:00", "07:30:00"]),
            ("T2", ["06:00:00", "06:30:00"]),
        )
        erros, avisos = validate_draft_times(trocada)
        self.assertEqual(erros, [])
        self.assertEqual(len(avisos), 1)

    def test_validate_draft_times_horario_ilegivel(self):
        ruim = grade(("T1", ["06:00:00", "ontem"]))
        erros, _ = validate_draft_times(ruim)
        self.assertTrue(erros)

    # --- passo 124 ----------------------------------------------------
    def test_schedule_from_draft(self):
        sched = schedule_from_draft(GRADE_3X30, "100", direction_id="0",
                                    service_id="S_UTEIS", trip_headsign="Centro")
        self.assertEqual(sched.mode, 'trips')
        self.assertEqual(len(sched.trips), 3)
        self.assertEqual([t.trip_id for t in sched.trips], ["T1", "T2", "T3"])
        self.assertEqual(sched.trips[0].start_time_s, to_seconds("06:00:00"))
        self.assertEqual(sched.trips[0].end_time_s, to_seconds("06:30:00"))
        self.assertEqual(sched.trips[0].duration_s, 1800)
        self.assertEqual({t.lane_key for t in sched.trips}, {("100", "0")})
        self.assertEqual([t.n_stops for t in sched.trips], [3, 3, 3])

    def test_schedule_from_draft_vazio(self):
        self.assertEqual(schedule_from_draft([], "100").trips, [])


if __name__ == "__main__":
    unittest.main()
