# -*- coding: utf-8 -*-
"""Testes do núcleo puro de edição de horários (Fase 12, passos 120-124)."""
import unittest

from sig_bus.schedule_edit_core import (
    to_seconds,
    from_seconds,
    expand_frequency_to_stop_times,
    expand_bands_to_stop_times,
    validate_bands,
    trips_from_stop_times,
    headways,
    validate_draft_times,
    shift_trip,
    shift_trip_endpoint,
    schedule_from_draft,
    diff_stop_times,
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

    # --- passo 169: faixas horárias ----------------------------------
    def test_uma_faixa_reproduz_expand_frequency(self):
        faixas = [{"hora_inicio": "06:00:00", "hora_fim": "07:00:00",
                   "intervalo_min": 30, "duracao_min": 30}]
        trips_f, st_f = expand_bands_to_stop_times(["S1", "S2"], faixas, prefix="L1_0")
        trips_r, st_r = expand_frequency_to_stop_times(
            ["S1", "S2"], "06:00:00", "07:00:00", 30, duracao_min=30, prefix="L1_0")
        self.assertEqual(trips_f, trips_r)
        self.assertEqual(st_f, st_r)

    def test_tres_faixas_geram_o_headway_de_cada_trecho(self):
        faixas = [
            {"hora_inicio": "06:00:00", "hora_fim": "07:00:00", "intervalo_min": 15, "duracao_min": 40},
            {"hora_inicio": "07:15:00", "hora_fim": "09:15:00", "intervalo_min": 30, "duracao_min": 30},
            {"hora_inicio": "09:45:00", "hora_fim": "10:45:00", "intervalo_min": 15, "duracao_min": 40},
        ]
        trips, stop_times = expand_bands_to_stop_times(["S1", "S2"], faixas, prefix="L1_0")
        saidas = [v["start_s"] for v in trips_from_stop_times(stop_times)]
        diffs = [b - a for a, b in zip(saidas, saidas[1:])]
        self.assertEqual(len(trips), 5 + 5 + 5)
        self.assertEqual(diffs[:4], [900, 900, 900, 900])
        self.assertEqual(diffs[5:8], [1800, 1800, 1800])

    def test_fronteira_entre_faixas_nao_duplica_saida(self):
        faixas = [
            {"hora_inicio": "06:00:00", "hora_fim": "09:00:00", "intervalo_min": 60, "duracao_min": 30},
            {"hora_inicio": "09:00:00", "hora_fim": "11:00:00", "intervalo_min": 60, "duracao_min": 40},
        ]
        trips, stop_times = expand_bands_to_stop_times(["S1", "S2"], faixas, prefix="L1_0")
        saidas = [v["start_s"] for v in trips_from_stop_times(stop_times)]
        self.assertEqual(len(saidas), len(set(saidas)))
        self.assertEqual(len(trips), 6)   # 06,07,08,09,10,11 — 09:00 uma única vez
        self.assertEqual(len({t["trip_id"] for t in trips}), 6)

    def test_duracao_por_faixa_aparece_na_chegada(self):
        faixas = [
            {"hora_inicio": "06:00:00", "hora_fim": "06:00:00", "intervalo_min": 60, "duracao_min": 30},
            {"hora_inicio": "09:00:00", "hora_fim": "09:00:00", "intervalo_min": 60, "duracao_min": 50},
        ]
        _, stop_times = expand_bands_to_stop_times(["S1", "S2"], faixas)
        chegadas = {st["trip_id"]: st["arrival_time"]
                    for st in stop_times if st["stop_sequence"] == 2}
        self.assertEqual(sorted(chegadas.values()), ["06:30:00", "09:50:00"])

    def test_faixas_em_tupla(self):
        faixas = [("06:00:00", "06:30:00", 30, 20), ("07:00:00", "07:30:00", 30, 20)]
        trips, _ = expand_bands_to_stop_times(["S1", "S2"], faixas)
        self.assertEqual(len(trips), 4)

    def test_validate_bands(self):
        erros, _ = validate_bands([])
        self.assertTrue(erros)

        erros, avisos = validate_bands([
            {"hora_inicio": "06:00:00", "hora_fim": "09:00:00", "intervalo_min": 15, "duracao_min": 40},
            {"hora_inicio": "09:00:00", "hora_fim": "16:00:00", "intervalo_min": 30, "duracao_min": 30},
        ])
        self.assertEqual((erros, avisos), ([], []))   # faixas encostadas passam

        erros, _ = validate_bands([{"hora_inicio": "09:00:00", "hora_fim": "06:00:00",
                                    "intervalo_min": 30, "duracao_min": 30}])
        self.assertIn("fim é anterior", erros[0])

        erros, _ = validate_bands([{"hora_inicio": "06:00:00", "hora_fim": "09:00:00",
                                    "intervalo_min": 0, "duracao_min": 30}])
        self.assertIn("intervalo", erros[0])

        erros, _ = validate_bands([{"hora_inicio": "06:00:00", "hora_fim": "09:00:00",
                                    "intervalo_min": 30, "duracao_min": 0}])
        self.assertIn("duração", erros[0])

        erros, _ = validate_bands([
            {"hora_inicio": "06:00:00", "hora_fim": "10:00:00", "intervalo_min": 15, "duracao_min": 40},
            {"hora_inicio": "09:00:00", "hora_fim": "16:00:00", "intervalo_min": 30, "duracao_min": 30},
        ])
        self.assertEqual(len(erros), 1)
        self.assertIn("faixa 2 (09:00–16:00) sobrepõe a faixa 1", erros[0])

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

    # --- passo 199 ----------------------------------------------------
    def test_diff_stop_times_sem_alteracoes(self):
        self.assertEqual(diff_stop_times(GRADE_3X30, GRADE_3X30), [])

    def test_diff_stop_times_com_alteracao(self):
        atual = grade(
            ("T1", ["06:05:00", "06:15:00", "06:30:00"]),
            ("T2", ["06:30:00", "06:45:00", "07:00:00"]),
            ("T3", ["07:00:00", "07:15:00", "07:30:00"]),
        )
        diff = diff_stop_times(GRADE_3X30, atual)
        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0]["trip_id"], "T1")
        self.assertEqual(diff[0]["arrival_time"], "06:05:00")

    def test_diff_stop_times_ignora_linha_nova(self):
        # T4 não existe no original: viagem nova é ignorada (esta tela não
        # cria viagem). T1 some no atual: também é ignorado (não apaga
        # viagem) — nenhuma das duas entra no resultado.
        atual = grade(
            ("T4", ["08:00:00", "08:15:00"]),
        )
        atual += [st for st in GRADE_3X30 if st["trip_id"] in ("T2", "T3")]
        diff = diff_stop_times(GRADE_3X30, atual)
        self.assertEqual(diff, [])

    def test_diff_stop_times_vazios(self):
        self.assertEqual(diff_stop_times([], []), [])
        self.assertEqual(diff_stop_times(GRADE_3X30, []), [])
        self.assertEqual(diff_stop_times([], GRADE_3X30), [])

    def test_diff_stop_times_viagem_inteira_deslocada(self):
        atual = grade(
            ("T1", ["06:15:00", "06:30:00", "06:45:00"]),
            ("T2", ["06:30:00", "06:45:00", "07:00:00"]),
            ("T3", ["07:00:00", "07:15:00", "07:30:00"]),
        )
        diff = diff_stop_times(GRADE_3X30, atual)
        self.assertEqual([st["trip_id"] for st in diff], ["T1", "T1", "T1"])
        self.assertEqual([st["arrival_time"] for st in diff],
                          ["06:15:00", "06:30:00", "06:45:00"])

    def test_diff_stop_times_ordem_de_entrada_nao_importa(self):
        atual = grade(
            ("T1", ["06:05:00", "06:15:00", "06:30:00"]),
            ("T2", ["06:30:00", "06:45:00", "07:00:00"]),
            ("T3", ["07:00:00", "07:15:00", "07:30:00"]),
        )
        original_embaralhado = list(reversed(GRADE_3X30))
        atual_embaralhado = list(reversed(atual))

        diff_normal = diff_stop_times(GRADE_3X30, atual)
        diff_embaralhado = diff_stop_times(original_embaralhado, atual_embaralhado)

        self.assertEqual(
            {(st["trip_id"], st["arrival_time"]) for st in diff_normal},
            {(st["trip_id"], st["arrival_time"]) for st in diff_embaralhado},
        )


if __name__ == "__main__":
    unittest.main()
