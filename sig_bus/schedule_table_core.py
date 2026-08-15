# -*- coding: utf-8 -*-
"""
/***************************************************************************
 schedule_table_core — Núcleo puro da tabela de horários do SIG-Bus
                                  A QGIS plugin
 Funções puras e utilitários sem dependência de Qt/QGIS para estruturar e
 formatar a matriz de horários (paradas x viagens) de uma linha.

 Contrato do módulo:
 - Lógica pura sem dependências de Qt/QGIS (decisão 117): totalmente testável via pytest.
 - Estrutura a matriz de horários (Stops x Trips) a partir de stop_times.
 - Fornece conversão formatada para exibição em grade (to_grid).
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

try:
    from .schedule_edit_core import to_seconds
except ImportError:
    from schedule_edit_core import to_seconds


def format_time_str(time_str, fmt="HH:MM"):
    """
    Formata uma string de horário GTFS (ex: '06:30:00' ou '25:15:00').

    :param time_str: String de horário no formato 'HH:MM:SS' ou 'HH:MM'.
    :param fmt: 'HH:MM' para omitir segundos, 'HH:MM:SS' para manter completo.
    :return: String formatada de horário ou string vazia se inválido/None.
    """
    if not time_str:
        return ""
    parts = str(time_str).strip().split(":")
    if len(parts) < 2:
        return str(time_str)

    h, m = parts[0], parts[1]
    if fmt == "HH:MM":
        return f"{h.zfill(2)}:{m.zfill(2)}"
    elif fmt == "HH:MM:SS":
        s = parts[2] if len(parts) > 2 else "00"
        return f"{h.zfill(2)}:{m.zfill(2)}:{s.zfill(2)}"
    return str(time_str)


class ScheduleTable:
    """
    Representação estruturada de uma matriz de horários (Stops x Trips).
    """

    def __init__(self, stops=None, trips=None, matrix=None, route_short_name="", direction_id=""):
        """
        :param stops: Lista de dicts com dados de paradas [{'stop_id': ..., 'stop_name': ..., 'stop_sequence': ...}].
        :param trips: Lista de dicts com dados de viagens [{'trip_id': ..., 'start_time': ..., 'end_time': ...}].
        :param matrix: Dict mapping (stop_id, trip_id) -> {'arrival_time': ..., 'departure_time': ...}.
        :param route_short_name: Nome curto da linha (ex: '100').
        :param direction_id: Sentido ('0', '1' ou '').
        """
        self.stops = stops or []
        self.trips = trips or []
        self.matrix = matrix or {}
        self.route_short_name = str(route_short_name or "")
        self.direction_id = str(direction_id if direction_id is not None else "")

    def get_time(self, stop_id, trip_id, field="departure_time"):
        """
        Obtém o horário para uma parada e viagem específicas na matriz.
        """
        cell = self.matrix.get((stop_id, trip_id))
        if cell:
            return cell.get(field) or cell.get("arrival_time")
        return None

    def to_grid(self, time_format="HH:MM", empty_cell="-"):
        """
        Converte a tabela em uma grade 2D (matriz de strings) pronta para exibição
        em tabela visual ou exportação.

        :param time_format: 'HH:MM' ou 'HH:MM:SS'.
        :param empty_cell: Caractere/string para células sem parada na viagem.
        :return: Tupla (headers, rows):
                 - headers: ['Parada', 'V1\n06:10', 'V2\n06:30', ...] — ordinal da
                   coluna (ordem cronológica de self.trips) + primeira saída em
                   HH:MM; sem a hora quando a viagem não tem 'start_time' legível.
                   Use column_trip_ids() para casar cada coluna com seu trip_id.
                 - rows: [['Ponto A', '06:00', '06:15'], ['Ponto B', '06:20', '-']]
        """
        headers = ["Parada"]
        for i, t in enumerate(self.trips, start=1):
            hora = format_time_str(t.get("start_time"), fmt="HH:MM")
            if hora:
                headers.append(f"V{i}\n{hora}")
            else:
                headers.append(f"V{i}")
        rows = []

        for stop in self.stops:
            stop_id = stop.get("stop_id", "")
            stop_name = stop.get("stop_name") or stop_id
            row = [stop_name]

            for trip in self.trips:
                trip_id = trip.get("trip_id", "")
                val = self.get_time(stop_id, trip_id, field="departure_time")
                if val:
                    formatted = format_time_str(val, fmt=time_format)
                    row.append(formatted)
                else:
                    row.append(empty_cell)

            rows.append(row)

        return headers, rows

    def column_trip_ids(self):
        """
        Devolve o trip_id de cada coluna de viagem, na mesma ordem das colunas
        de to_grid (sem a coluna "Parada"). Serve para casar coluna → viagem
        sem depender do texto do cabeçalho (que agora é um rótulo "V<n>\\nHH:MM").
        """
        return [t.get("trip_id", "") for t in self.trips]


def build_schedule_table(stop_times, stops=None, trips=None, route_short_name="", direction_id=""):
    """
    Constrói um objeto ScheduleTable a partir de uma lista de stop_times.

    :param stop_times: Lista de dicts [{'trip_id': ..., 'stop_id': ..., 'stop_sequence': ..., 'arrival_time': ..., 'departure_time': ...}]
    :param stops: (Opcional) Lista de dicts de paradas com 'stop_id' e 'stop_name'.
    :param trips: (Opcional) Lista de dicts de viagens.
    :param route_short_name: Identificador da linha.
    :param direction_id: Sentido da linha.
    :return: Instância de ScheduleTable.
    """
    if not stop_times:
        return ScheduleTable(stops=[], trips=[], matrix={}, route_short_name=route_short_name, direction_id=direction_id)

    # 1. Mapeamento e agregação por trip_id
    trips_map = {}
    stops_order = []
    seen_stops = set()
    stops_seq_acc = {}  # stop_id -> list of sequences to compute median/avg order
    matrix = {}

    for st in stop_times:
        tid = st.get("trip_id")
        sid = st.get("stop_id")
        seq = int(st.get("stop_sequence", 0) or 0)
        dep = st.get("departure_time") or st.get("arrival_time")
        arr = st.get("arrival_time") or st.get("departure_time")

        if not tid or not sid:
            continue

        matrix[(sid, tid)] = {
            "arrival_time": arr,
            "departure_time": dep,
            "stop_sequence": seq
        }

        if tid not in trips_map:
            trips_map[tid] = {"trip_id": tid, "start_time": dep, "end_time": arr, "first_seq": seq, "last_seq": seq}
        else:
            tinfo = trips_map[tid]
            if seq < tinfo["first_seq"]:
                tinfo["first_seq"] = seq
                tinfo["start_time"] = dep
            if seq > tinfo["last_seq"]:
                tinfo["last_seq"] = seq
                tinfo["end_time"] = arr

        if sid not in seen_stops:
            seen_stops.add(sid)
            stops_order.append(sid)
        stops_seq_acc.setdefault(sid, []).append(seq)

    # 2. Ordena paradas por menor sequência média observada
    stops_order.sort(key=lambda s: sum(stops_seq_acc[s]) / len(stops_seq_acc[s]))

    # Enriquece a lista de paradas com nomes: os passados em `stops` valem
    # primeiro; na falta deles, o nome que veio junto das próprias linhas de
    # stop_times (decisão 136 — load_route_stop_times traz stop_name no JOIN).
    stops_dict = {s.get("stop_id"): s for s in (stops or []) if s.get("stop_id")}
    nomes_das_linhas = {st.get("stop_id"): st.get("stop_name") for st in stop_times
                        if st.get("stop_id") and st.get("stop_name")}
    final_stops = []
    for sid in stops_order:
        sinfo = stops_dict.get(sid, {})
        final_stops.append({
            "stop_id": sid,
            "stop_name": sinfo.get("stop_name") or nomes_das_linhas.get(sid) or sid,
            "stop_sequence": round(sum(stops_seq_acc[sid]) / len(stops_seq_acc[sid]))
        })

    # 3. Ordena viagens por horário de saída (start_time)
    final_trips = list(trips_map.values())
    final_trips.sort(key=lambda t: to_seconds(t.get("start_time")))

    return ScheduleTable(
        stops=final_stops,
        trips=final_trips,
        matrix=matrix,
        route_short_name=route_short_name,
        direction_id=direction_id
    )
