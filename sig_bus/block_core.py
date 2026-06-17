# -*- coding: utf-8 -*-
"""
/***************************************************************************
 block_core — camada de dados do Diagrama de Blocos (SIG-Bus)
                                 A QGIS plugin
 Modelo de domínio (Trip/Block/Schedule), leitura do GeoPackage e tarefa
 de fundo. É a *fonte única da verdade* (Model do MVC): não conhece Qt
 widgets nem desenho — só dados.
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

Ver PLANEJAMENTO_DIAGRAMA.md e ARQUITETURA_DIAGRAMA.md na raiz do repositório.

Restrição do feed BHTrans: trips.txt NÃO tem block_id, então a alocação de
frota (Modo Blocos) é *inferida* (BlockBuilder, próximo incremento). Esta
fatia entrega o Modo Viagens (determinístico): uma barra por viagem no tempo.
"""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from qgis.core import Qgis, QgsMessageLog, QgsTask
from qgis.PyQt.QtCore import pyqtSignal

LOG_TAG = 'SIG-Bus'

# Limite superior do eixo de tempo: o GTFS admite horários ≥ 24h (serviço
# pós-meia-noite, ex.: '25:30:00'). 30h cobre com folga.
DAY_MAX_S = 30 * 3600


# --------------------------------------------------------------------------
# Utilitários de tempo
# --------------------------------------------------------------------------
def parse_gtfs_time(value) -> Optional[int]:
    """Converte 'H:MM:SS'/'HH:MM:SS' em segundos desde 00:00.

    Aceita horas ≥ 24 (ex.: '25:30:00' → 91800). Devolve None se inválido.
    Parsear para inteiro é obrigatório: ordenar/encadear por string de
    relógio quebra quando há serviço pós-meia-noite."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    parts = s.split(':')
    if len(parts) != 3:
        return None
    try:
        h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    return h * 3600 + m * 60 + sec


def fmt_hms(seconds: Optional[int]) -> str:
    """Segundos → 'HH:MM' (mantém horas ≥ 24 visíveis, ex.: '25:30')."""
    if seconds is None:
        return '--:--'
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return '{:02d}:{:02d}'.format(h, m)


def _natural_key(value):
    """Chave de ordenação natural: '101' < '102' < '850A' de forma intuitiva."""
    s = str(value)
    try:
        return (0, int(s), '')
    except ValueError:
        return (1, 0, s)


# --------------------------------------------------------------------------
# Modelo de domínio
# --------------------------------------------------------------------------
@dataclass
class Trip:
    """Uma viagem (unidade atômica do diagrama)."""
    trip_id: str
    route_short_name: str
    direction_id: str          # '0' ida, '1' volta (ou '')
    service_id: str
    shape_id: str
    trip_headsign: str
    start_time_s: int          # segundos desde 00:00
    end_time_s: int
    start_stop_id: str
    end_stop_id: str
    n_stops: int
    block_id: Optional[str] = None   # preenchido pela inferência (Modo Blocos)

    @property
    def duration_s(self) -> int:
        return max(0, self.end_time_s - self.start_time_s)

    @property
    def lane_key(self):
        """Chave da faixa no Modo Viagens: (linha, sentido)."""
        return (self.route_short_name, self.direction_id)


@dataclass
class BlockParams:
    """Parâmetros da inferência de blocos (Modo Blocos — próximo incremento)."""
    layover_min_s: int = 5 * 60
    layover_max_s: int = 45 * 60
    allow_deadhead: bool = False
    relaxed: bool = False


@dataclass
class Block:
    """Sequência de viagens atribuída a um veículo inferido."""
    block_id: str
    trips: list = field(default_factory=list)

    @property
    def span(self):
        if not self.trips:
            return (0, 0)
        return (min(t.start_time_s for t in self.trips),
                max(t.end_time_s for t in self.trips))

    @property
    def idle_seconds(self) -> int:
        ts = sorted(self.trips, key=lambda t: t.start_time_s)
        return sum(max(0, ts[i + 1].start_time_s - ts[i].end_time_s)
                   for i in range(len(ts) - 1))


@dataclass
class Schedule:
    """Objeto que a engine gráfica renderiza."""
    trips: list = field(default_factory=list)
    blocks: Optional[list] = None          # None no Modo Viagens
    fleet_size: Optional[int] = None
    mode: str = 'trips'                     # 'trips' | 'blocks'
    warnings: list = field(default_factory=list)

    @property
    def time_bounds(self):
        """(t_min, t_max) em segundos, com folga, para o eixo X."""
        if not self.trips:
            return (6 * 3600, 24 * 3600)
        lo = min(t.start_time_s for t in self.trips)
        hi = max(t.end_time_s for t in self.trips)
        pad = max(900, int((hi - lo) * 0.03))
        return (max(0, lo - pad), hi + pad)


# --------------------------------------------------------------------------
# Inferência de blocos (alocação de frota)
# --------------------------------------------------------------------------
class BlockBuilder:
    """Infere veículos (blocos) encadeando viagens — o GTFS da BHTrans não tem
    block_id. Heurística gulosa de frota mínima (ver PLANEJAMENTO §5):

    para cada viagem (em ordem de início), reaproveita o veículo livre mais
    'apertado' (maior free_time, menos ocioso) cujo encadeamento respeite o
    layover e o casamento de terminais; senão, abre um veículo novo.

    O encadeamento é feito *por service_id* (não se mistura dia útil com
    domingo) mas pode cruzar linhas (frota compartilhada), que é justamente o
    ganho do modo multi-linha."""

    def build(self, trips, params):
        """Devolve list[Block]. Preenche trip.block_id como efeito colateral."""
        groups = defaultdict(list)
        for t in trips:
            groups[t.service_id].append(t)
        blocks = []
        for svc in sorted(groups, key=_natural_key):
            blocks.extend(self._build_service(groups[svc], params,
                                              offset=len(blocks)))
        return blocks

    @staticmethod
    def _build_service(trips, params, offset=0):
        ordered = sorted(trips, key=lambda t: (t.start_time_s, t.end_time_s))
        # cada veículo: {'block', 'loc' (stop atual), 'free' (livre desde s)}
        vehicles = []
        skip_terminal = params.allow_deadhead or params.relaxed
        for t in ordered:
            best = None
            for v in vehicles:
                gap = t.start_time_s - v['free']
                if gap < params.layover_min_s:
                    continue
                # 'relaxado' ignora o teto de layover (frota mínima teórica).
                if not params.relaxed and gap > params.layover_max_s:
                    continue
                if not skip_terminal and v['loc'] != t.start_stop_id:
                    continue
                # Candidato: prefere o de maior free (menos tempo ocioso).
                if best is None or v['free'] > best['free']:
                    best = v
            if best is None:
                block = Block(
                    block_id='V{}'.format(offset + len(vehicles) + 1), trips=[])
                best = {'block': block, 'loc': None, 'free': None}
                vehicles.append(best)
            best['block'].trips.append(t)
            t.block_id = best['block'].block_id
            best['loc'] = t.end_stop_id
            best['free'] = t.end_time_s
        return [v['block'] for v in vehicles]


# --------------------------------------------------------------------------
# Leitura do GeoPackage
# --------------------------------------------------------------------------
class ScheduleReader:
    """Lê viagens do GeoPackage do GTFS via sqlite3 (padrão de _AlocacaoTask).

    Toda leitura é restrita às linhas selecionadas (route_id IN (...)) e usa
    os índices criados por create_join_indexes(); nunca varre stop_times
    inteiro (≈136 MB)."""

    def __init__(self, gpkg_path):
        self.gpkg = gpkg_path

    def list_routes(self) -> list:
        """route_short_name distintos, em ordem natural."""
        with sqlite3.connect(self.gpkg) as conn:
            rows = conn.execute(
                "SELECT DISTINCT route_short_name FROM routes "
                "WHERE route_short_name IS NOT NULL AND route_short_name <> ''"
            ).fetchall()
        return sorted((str(r[0]) for r in rows), key=_natural_key)

    def list_services(self, route_short_names) -> list:
        """service_id distintos das linhas dadas (para o seletor de dia)."""
        if not route_short_names:
            return []
        with sqlite3.connect(self.gpkg) as conn:
            route_ids = self._route_ids(conn, route_short_names)
            if not route_ids:
                return []
            ph = ','.join('?' * len(route_ids))
            rows = conn.execute(
                "SELECT DISTINCT service_id FROM trips "
                "WHERE route_id IN ({})".format(ph), route_ids).fetchall()
        return sorted((str(r[0]) for r in rows), key=_natural_key)

    @staticmethod
    def _route_ids(conn, route_short_names):
        """route_short_name → route_id (lista; uma linha pode ter vários)."""
        names = list(route_short_names)
        ph = ','.join('?' * len(names))
        rows = conn.execute(
            "SELECT route_id FROM routes WHERE route_short_name IN ({})"
            .format(ph), names).fetchall()
        return [r[0] for r in rows]

    def load_trips(self, route_short_names, service_ids=None,
                   directions=None, t_min=0, t_max=DAY_MAX_S):
        """Devolve (list[Trip], list[warnings]).

        route_short_names: iterável de linhas (ex.: ['101', '102']).
        service_ids:       None = todos; ou iterável de service_id.
        directions:        None = ambos; ou subconjunto de {'0','1'}.
        t_min/t_max:       janela de tempo em segundos; mantém viagens que a
                           sobrepõem."""
        names = [str(n) for n in route_short_names]
        if not names:
            return [], ['Nenhuma linha selecionada.']

        warnings = []
        with sqlite3.connect(self.gpkg) as conn:
            # route_id → route_short_name
            ph = ','.join('?' * len(names))
            route_rows = conn.execute(
                "SELECT route_id, route_short_name FROM routes "
                "WHERE route_short_name IN ({})".format(ph), names).fetchall()
            if not route_rows:
                return [], ["Linhas não encontradas em 'routes': {}".format(
                    ', '.join(names))]
            rid_to_short = {r[0]: str(r[1]) for r in route_rows}
            route_ids = list(rid_to_short.keys())

            # Metadados das viagens (tabela pequena)
            rph = ','.join('?' * len(route_ids))
            params = list(route_ids)
            svc_clause = ''
            if service_ids:
                svc = [str(s) for s in service_ids]
                svc_clause = ' AND service_id IN ({})'.format(','.join('?' * len(svc)))
                params += svc
            trip_rows = conn.execute(
                "SELECT trip_id, route_id, direction_id, service_id, "
                "shape_id, trip_headsign FROM trips "
                "WHERE route_id IN ({}){}".format(rph, svc_clause),
                params).fetchall()
            if not trip_rows:
                return [], ['Nenhuma viagem para os filtros escolhidos.']

            meta = {}
            for tr in trip_rows:
                meta[str(tr[0])] = {
                    'route_short_name': rid_to_short.get(tr[1], str(tr[1])),
                    'direction_id': str(tr[2]) if tr[2] is not None else '',
                    'service_id': str(tr[3]) if tr[3] is not None else '',
                    'shape_id': str(tr[4]) if tr[4] is not None else '',
                    'trip_headsign': str(tr[5]) if tr[5] is not None else '',
                }

            # stop_times das viagens dessas linhas — slice pequeno via índice.
            # Agregamos a primeira/última PARADA por stop_sequence (ordem
            # canônica da viagem), não por horário.
            st_rows = conn.execute(
                "SELECT st.trip_id, st.departure_time, st.arrival_time, "
                "st.stop_id, CAST(st.stop_sequence AS INTEGER) AS seq "
                "FROM stop_times st JOIN trips t ON st.trip_id = t.trip_id "
                "WHERE t.route_id IN ({}){}".format(rph, svc_clause),
                params).fetchall()

        # Agrega por viagem (em Python; só as linhas selecionadas).
        agg = {}   # trip_id -> dict
        for trip_id, dep, arr, stop_id, seq in st_rows:
            tid = str(trip_id)
            if tid not in meta:
                continue
            seq = seq if seq is not None else 0
            a = agg.get(tid)
            if a is None:
                a = {'min_seq': seq, 'max_seq': seq,
                     'dep': dep, 'arr': arr,
                     'start_stop': str(stop_id), 'end_stop': str(stop_id),
                     'n': 0}
                agg[tid] = a
            a['n'] += 1
            if seq <= a['min_seq']:
                a['min_seq'] = seq
                a['dep'] = dep
                a['start_stop'] = str(stop_id)
            if seq >= a['max_seq']:
                a['max_seq'] = seq
                a['arr'] = arr
                a['end_stop'] = str(stop_id)

        dirset = set(directions) if directions else None
        trips = []
        skipped_time = 0
        for tid, a in agg.items():
            m = meta[tid]
            if dirset is not None and m['direction_id'] not in dirset:
                continue
            start_s = parse_gtfs_time(a['dep'])
            end_s = parse_gtfs_time(a['arr'])
            if start_s is None or end_s is None:
                skipped_time += 1
                continue
            if end_s < start_s:        # defesa: dados invertidos
                start_s, end_s = end_s, start_s
            # Mantém se a viagem sobrepõe a janela [t_min, t_max].
            if start_s > t_max or end_s < t_min:
                continue
            trips.append(Trip(
                trip_id=tid,
                route_short_name=m['route_short_name'],
                direction_id=m['direction_id'],
                service_id=m['service_id'],
                shape_id=m['shape_id'],
                trip_headsign=m['trip_headsign'],
                start_time_s=start_s,
                end_time_s=end_s,
                start_stop_id=a['start_stop'],
                end_stop_id=a['end_stop'],
                n_stops=a['n'],
            ))

        if skipped_time:
            warnings.append(
                '{} viagem(ns) sem horário válido foram ignoradas.'.format(
                    skipped_time))
        if not trips:
            warnings.append('Nenhuma viagem na janela de tempo selecionada.')

        trips.sort(key=lambda t: (t.route_short_name, t.direction_id,
                                  t.start_time_s))
        return trips, warnings


# --------------------------------------------------------------------------
# Tarefa de fundo
# --------------------------------------------------------------------------
class BlockDiagramTask(QgsTask):
    """Lê as viagens (e, no futuro, infere blocos) fora da thread da GUI.

    Espelha _GtfsLoadTask/_AlocacaoTask: trabalho pesado em run(); entrega do
    Schedule em finished() (thread principal), via sinais."""

    finishedOk = pyqtSignal(object)    # Schedule
    failed = pyqtSignal(str)

    def __init__(self, gpkg_path, route_short_names, service_ids=None,
                 directions=None, t_min=0, t_max=DAY_MAX_S, mode='trips',
                 params=None):
        super().__init__('Montando diagrama de blocos', QgsTask.CanCancel)
        self.gpkg = gpkg_path
        self.route_short_names = list(route_short_names)
        self.service_ids = service_ids
        self.directions = directions
        self.t_min = t_min
        self.t_max = t_max
        self.mode = mode
        self.params = params or BlockParams()
        self._schedule = None
        self._error = None

    def run(self):
        try:
            self.setProgress(10)
            reader = ScheduleReader(self.gpkg)
            trips, warns = reader.load_trips(
                self.route_short_names, self.service_ids,
                self.directions, self.t_min, self.t_max)
            self.setProgress(60)
            schedule = Schedule(trips=trips, mode=self.mode, warnings=list(warns))
            if self.mode == 'blocks' and trips:
                schedule.blocks = BlockBuilder().build(trips, self.params)
                schedule.fleet_size = len(schedule.blocks)
                services = {t.service_id for t in trips}
                if len(services) > 1:
                    schedule.warnings.append(
                        '{} serviços (dias) na seleção; a frota é somada por '
                        'serviço. Selecione um único serviço para o número '
                        'real de veículos.'.format(len(services)))
            self._schedule = schedule
            self.setProgress(100)
        except Exception as e:   # noqa: BLE001 — reporta à GUI
            self._error = str(e)
            QgsMessageLog.logMessage(
                'Falha no diagrama: {}'.format(e), LOG_TAG, Qgis.Critical)
            return False
        return True

    def finished(self, ok):
        if ok and self._schedule is not None:
            self.finishedOk.emit(self._schedule)
        else:
            self.failed.emit(self._error or 'tarefa cancelada.')
