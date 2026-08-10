# -*- coding: utf-8 -*-
"""
/***************************************************************************
 schedule_edit_core — Núcleo de edição de horários do SIG-Bus
                                 A QGIS plugin
 Funções puras e utilitários para manipulação, geração e validação de
 horários (trips, stop_times e frequências) do GTFS.

 Sem dependência de Qt/QGIS no nível do módulo (decisão 74): tudo aqui é
 verificável por pytest fora do QGIS. A única exceção é
 schedule_from_draft(), que importa block_core sob demanda para montar o
 Schedule que a engine gráfica do Diagrama de Blocos renderiza.
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


def to_seconds(time_str):
    """
    Converte uma string de horário no formato 'HH:MM:SS' ou 'HH:MM' para segundos a partir da meia-noite.
    Suporta horários GTFS superiores a 24 horas (ex: '25:30:00').

    :param time_str: String de horário (ex: '06:30:00', '08:15').
    :return: Número inteiro de segundos.
    """
    if not time_str:
        return 0
    parts = time_str.split(':')
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    s = int(parts[2]) if len(parts) > 2 else 0
    return h * 3600 + m * 60 + s


def from_seconds(seconds):
    """
    Converte um número inteiro de segundos para uma string no formato 'HH:MM:SS'.
    Suporta horários GTFS superiores a 24 horas.

    :param seconds: Segundos a partir da meia-noite.
    :return: String no formato 'HH:MM:SS'.
    """
    if seconds is None or seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def expand_frequency_to_stop_times(stop_ids, hora_inicio, hora_fim, intervalo_min, duracao_min=None, prefix=None):
    """
    Função pura (sem I/O) que gera as viagens e as linhas de stop_times
    (trip_id, arrival_time, departure_time, stop_id, stop_sequence)
    para uma frequência regular.

    :param stop_ids: Lista de IDs das paradas na ordem do itinerário.
    :param hora_inicio: Horário da primeira viagem ('HH:MM:SS' ou 'HH:MM').
    :param hora_fim: Horário limite para início da última viagem.
    :param intervalo_min: Intervalo entre viagens sucessivas em minutos.
    :param duracao_min: Duração total prevista da viagem em minutos (opcional).
    :param prefix: Prefixo opcional para o trip_id (ex: '100_0').
    :return: Tupla (trips, stop_times), onde trips é uma lista de dicionários
             com {"trip_id": ...} e stop_times é uma lista de dicionários.
    """
    start_sec = to_seconds(hora_inicio)
    end_sec = to_seconds(hora_fim)
    step_sec = int(intervalo_min) * 60

    if step_sec <= 0 or not stop_ids:
        return [], []

    n_stops = len(stop_ids)
    duracao_sec = int(duracao_min) * 60 if duracao_min is not None else 0

    trips = []
    stop_times = []

    current_sec = start_sec
    while current_sec <= end_sec:
        time_str = from_seconds(current_sec)
        if prefix:
            trip_id = f"trip_{prefix}_{time_str.replace(':', '')}"
        else:
            trip_id = f"trip_{time_str.replace(':', '')}"

        trips.append({
            "trip_id": trip_id
        })

        for idx, stop_id in enumerate(stop_ids, start=1):
            if duracao_min is not None and n_stops > 1:
                # Interpola linearmente: parada 1 -> current_sec,
                # última parada -> current_sec + duracao_sec
                offset_sec = round(duracao_sec * (idx - 1) / (n_stops - 1))
                stop_time_str = from_seconds(current_sec + offset_sec)
            else:
                stop_time_str = time_str

            stop_times.append({
                "trip_id": trip_id,
                "arrival_time": stop_time_str,
                "departure_time": stop_time_str,
                "stop_id": stop_id,
                "stop_sequence": idx
            })

        current_sec += step_sec

    return trips, stop_times


# --------------------------------------------------------------------------
# Leitura da grade
# --------------------------------------------------------------------------
def _group_by_trip(stop_times):
    """
    Agrupa a grade por trip_id, na ordem em que cada viagem aparece na lista,
    com as paradas de cada viagem ordenadas por stop_sequence.

    :return: Lista de tuplas (trip_id, [linhas ordenadas]).
    """
    grupos = {}
    ordem = []
    for st in stop_times:
        tid = st.get("trip_id")
        if tid not in grupos:
            grupos[tid] = []
            ordem.append(tid)
        grupos[tid].append(st)
    return [(tid, sorted(grupos[tid], key=lambda s: int(s.get("stop_sequence", 0) or 0)))
            for tid in ordem]


def trips_from_stop_times(stop_times):
    """
    Resume a grade em uma viagem por trip_id, **em ordem de saída**.

    :param stop_times: Lista de dicionários de stop_times (todas as viagens).
    :return: Lista de dicionários {trip_id, start_s, end_s, n_stops}, em
             segundos desde 00:00.
    """
    viagens = []
    for tid, linhas in _group_by_trip(stop_times):
        primeira, ultima = linhas[0], linhas[-1]
        viagens.append({
            "trip_id": tid,
            "start_s": to_seconds(primeira.get("departure_time") or primeira.get("arrival_time")),
            "end_s": to_seconds(ultima.get("arrival_time") or ultima.get("departure_time")),
            "n_stops": len(linhas),
        })
    return sorted(viagens, key=lambda v: v["start_s"])


def headways(stop_times):
    """
    Intervalo (em segundos) entre a saída de cada viagem e a da viagem
    anterior **na ordem em que as viagens aparecem na grade** — a primeira
    fica com None.

    A ordem é a da grade, não a de saída, justamente para que um ajuste que
    jogue uma viagem para antes da anterior apareça como headway negativo
    (ver validate_draft_times).

    :param stop_times: Lista de dicionários de stop_times (todas as viagens).
    :return: Dicionário {trip_id: headway_s ou None}.
    """
    resultado = {}
    anterior_s = None
    for tid, linhas in _group_by_trip(stop_times):
        primeira = linhas[0]
        saida_s = to_seconds(primeira.get("departure_time") or primeira.get("arrival_time"))
        resultado[tid] = None if anterior_s is None else saida_s - anterior_s
        anterior_s = saida_s
    return resultado


# --------------------------------------------------------------------------
# Edição da grade (atalhos + / - e > / <)
# --------------------------------------------------------------------------
def _copia(stop_times):
    return [dict(st) for st in stop_times]


def shift_trip(stop_times, trip_id, delta_s):
    """
    Desloca a viagem inteira (todas as paradas, chegada e partida) em
    delta_s segundos, preservando a duração — atalhos '+' e '-'.

    Deslocamento que levaria alguma parada para antes de 00:00:00 é recusado:
    a grade volta inalterada.

    :param stop_times: Lista de dicionários de stop_times (todas as viagens).
    :param trip_id: ID da viagem a deslocar.
    :param delta_s: Deslocamento em segundos (positivo = mais tarde).
    :return: Nova lista de dicionários de stop_times (a de entrada não é mutada).
    """
    if not stop_times:
        return []

    delta_s = int(delta_s)
    alvo = [st for st in stop_times if st.get("trip_id") == trip_id]
    if not alvo:
        return _copia(stop_times)

    for st in alvo:
        if to_seconds(st.get("arrival_time")) + delta_s < 0 or \
                to_seconds(st.get("departure_time")) + delta_s < 0:
            return _copia(stop_times)

    updated = []
    for st in stop_times:
        st_copy = dict(st)
        if st_copy.get("trip_id") == trip_id:
            st_copy["arrival_time"] = from_seconds(to_seconds(st_copy.get("arrival_time")) + delta_s)
            st_copy["departure_time"] = from_seconds(to_seconds(st_copy.get("departure_time")) + delta_s)
        updated.append(st_copy)
    return updated


def shift_trip_endpoint(stop_times, trip_id, endpoint, delta_s):
    """
    Desloca só um extremo da viagem — a saída ('first') ou a chegada ('last')
    — e redistribui linearmente as paradas intermediárias entre os dois
    extremos resultantes: atalhos '>' e '<'.

    Recusa (devolvendo a grade original) o deslocamento que deixaria a saída
    igual ou posterior à chegada, ou que levaria a saída para antes de
    00:00:00. A sequência de horários da viagem nunca decresce.

    :param stop_times: Lista de dicionários de stop_times (todas as viagens).
    :param trip_id: ID da viagem cujo extremo será ajustado.
    :param endpoint: 'first' para a primeira parada da viagem, 'last' para a última.
    :param delta_s: Deslocamento em segundos (positivo = mais tarde).
    :return: Nova lista de dicionários de stop_times (a de entrada não é mutada).
    :raises ValueError: Se endpoint não for 'first' nem 'last'.
    """
    if endpoint not in ("first", "last"):
        raise ValueError(f"endpoint deve ser 'first' ou 'last', recebido: {endpoint!r}")

    if not stop_times:
        return []

    delta_s = int(delta_s)
    linhas = [st for st in stop_times if st.get("trip_id") == trip_id]
    if not linhas:
        return _copia(stop_times)

    linhas = sorted(linhas, key=lambda s: int(s.get("stop_sequence", 0) or 0))
    n = len(linhas)
    inicio_s = to_seconds(linhas[0].get("departure_time") or linhas[0].get("arrival_time"))
    fim_s = to_seconds(linhas[-1].get("arrival_time") or linhas[-1].get("departure_time"))

    if n == 1:
        # Viagem de uma parada só: não há extremos a cruzar.
        return shift_trip(stop_times, trip_id, delta_s)

    if endpoint == "first":
        inicio_s += delta_s
    else:
        fim_s += delta_s

    if inicio_s < 0 or inicio_s >= fim_s:
        return _copia(stop_times)

    # Redistribui as paradas intermediárias entre os dois extremos novos.
    novos = {}
    for i, st in enumerate(linhas):
        seq = int(st.get("stop_sequence", 0) or 0)
        novos[seq] = from_seconds(inicio_s + round((fim_s - inicio_s) * i / (n - 1)))

    updated = []
    for st in stop_times:
        st_copy = dict(st)
        if st_copy.get("trip_id") == trip_id:
            novo = novos.get(int(st_copy.get("stop_sequence", 0) or 0))
            if novo is not None:
                st_copy["arrival_time"] = novo
                st_copy["departure_time"] = novo
        updated.append(st_copy)
    return updated


# --------------------------------------------------------------------------
# Validação da grade em rascunho
# --------------------------------------------------------------------------
def validate_draft_times(stop_times):
    """
    Valida a grade ajustada à mão, antes de gravar.

    Erro (bloqueia o avanço): horário ilegível, sequência decrescente dentro
    de uma viagem, saída >= chegada.
    Aviso (só confirma): duas viagens com a mesma saída, headway <= 0 (ordem
    das viagens trocada pelo ajuste) e headway acima de 3x a mediana.

    :param stop_times: Lista de dicionários de stop_times (todas as viagens).
    :return: Tupla (erros, avisos), duas listas de mensagens.
    """
    erros = []
    avisos = []
    if not stop_times:
        return erros, avisos

    for tid, linhas in _group_by_trip(stop_times):
        anterior_s = None
        ilegivel = False
        erros_da_viagem = len(erros)
        for st in linhas:
            arr_str = st.get("arrival_time")
            dep_str = st.get("departure_time")
            try:
                arr_s = to_seconds(arr_str)
                dep_s = to_seconds(dep_str)
            except (ValueError, AttributeError, IndexError):
                erros.append("Viagem {}: horário ilegível ({!r} / {!r}).".format(tid, arr_str, dep_str))
                ilegivel = True
                break
            if arr_s > dep_s:
                erros.append("Viagem {}: chegada ({}) posterior à partida ({}) na mesma parada."
                             .format(tid, arr_str, dep_str))
            if anterior_s is not None and arr_s < anterior_s:
                erros.append("Viagem {}: horário {} anterior ao da parada anterior ({})."
                             .format(tid, arr_str, from_seconds(anterior_s)))
            anterior_s = dep_s

        if ilegivel or len(erros) > erros_da_viagem:
            continue   # a viagem já tem erro apontado — não repetir o mesmo defeito
        inicio_s = to_seconds(linhas[0].get("departure_time") or linhas[0].get("arrival_time"))
        fim_s = to_seconds(linhas[-1].get("arrival_time") or linhas[-1].get("departure_time"))
        if len(linhas) > 1 and inicio_s >= fim_s:
            erros.append("Viagem {}: saída ({}) igual ou posterior à chegada ({})."
                         .format(tid, from_seconds(inicio_s), from_seconds(fim_s)))

    if erros:
        return erros, avisos

    hw = headways(stop_times)
    saidas = {}
    for v in trips_from_stop_times(stop_times):
        saidas.setdefault(v["start_s"], []).append(v["trip_id"])
    for start_s, tids in saidas.items():
        if len(tids) > 1:
            avisos.append("Viagens {} saem no mesmo horário ({}).".format(
                ", ".join(tids), from_seconds(start_s)))

    valores = [v for v in hw.values() if v is not None]
    for tid, valor in hw.items():
        if valor is not None and valor <= 0:
            avisos.append("Viagem {}: sai antes da viagem anterior da grade "
                          "(headway de {} min).".format(tid, round(valor / 60.0)))
    positivos = sorted(v for v in valores if v > 0)
    if positivos:
        mediana = positivos[len(positivos) // 2]
        for tid, valor in hw.items():
            if valor is not None and valor > 3 * mediana:
                avisos.append("Viagem {}: headway de {} min, mais que o triplo do "
                              "intervalo típico ({} min).".format(
                                  tid, round(valor / 60.0), round(mediana / 60.0)))

    return erros, avisos


# --------------------------------------------------------------------------
# Ponte com a engine gráfica do Diagrama de Blocos
# --------------------------------------------------------------------------
def schedule_from_draft(stop_times, route_short_name, direction_id='0',
                        service_id='', trip_headsign=''):
    """
    Converte a grade em memória num block_core.Schedule (mode='trips'), com um
    block_core.Trip por viagem — sem tocar em sqlite3 nem no feed_edit.gpkg
    (o ScheduleReader continua sendo o único caminho para o diagrama que lê do
    GeoPackage).

    :param stop_times: Lista de dicionários de stop_times (todas as viagens).
    :param route_short_name: Nome curto da linha (ex: '100').
    :param direction_id: Sentido ('0' ida, '1' volta).
    :param service_id: Calendário ao qual estas viagens pertencem.
    :param trip_headsign: Letreiro da linha neste sentido.
    :return: block_core.Schedule com mode='trips'.
    """
    try:
        from .block_core import Trip, Schedule
    except ImportError:
        from block_core import Trip, Schedule

    trips = []
    for v in trips_from_stop_times(stop_times):
        linhas = [st for st in stop_times if st.get("trip_id") == v["trip_id"]]
        linhas = sorted(linhas, key=lambda s: int(s.get("stop_sequence", 0) or 0))
        trips.append(Trip(
            trip_id=v["trip_id"],
            route_short_name=str(route_short_name or ''),
            direction_id=str(direction_id if direction_id is not None else ''),
            service_id=str(service_id or ''),
            shape_id='',
            trip_headsign=str(trip_headsign or ''),
            start_time_s=v["start_s"],
            end_time_s=v["end_s"],
            start_stop_id=str(linhas[0].get("stop_id", "")),
            end_stop_id=str(linhas[-1].get("stop_id", "")),
            n_stops=v["n_stops"],
        ))
    return Schedule(trips=trips, mode='trips')
