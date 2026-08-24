# -*- coding: utf-8 -*-
"""Geocodificação pela base local do CNEFE (decisões 168, 170, 173).

Primeiro degrau da cascata quando o endereço é brasileiro e há base do
município carregada. Cada consulta é uma busca indexada em SQLite (0,1 ms
medido), sem rede, sem chave e sem limite de requisição — contra 1 s por
requisição por host do Nominatim (decisão 67), que no pior caso medido gasta
7 s numa única parada.

Ordem dos degraus (decisão 168):

===== ============================================ ================ =========
Degrau Chave                                        `geocodebr`      Preciso
===== ============================================ ================ =========
1      logradouro + número + bairro                 ``dn03``         sim
2      logradouro + número (média por ``n_casos``)  ``dn04``         sim
3      número **mais próximo** na mesma via         ``da04``         sim
4      logradouro corrigido por similaridade        ``pn0*``         sim
5      centroide da via (com/sem bairro)            ``dl03``/``dl04``  não
===== ============================================ ================ =========

O centroide do **município** (``dm01``) fica de fora de propósito: colocaria a
parada no centro da cidade sem o usuário perceber — no Belo Horizonte medido o
desvio declarado é 13,4 km.

Nomenclatura dos tipos de acerto reaproveitada do `geocodebr` (Ipea/ITpS,
licença MIT); dados do CNEFE/IBGE.

Não importa Qt nem QGIS.
"""

import logging
import sqlite3
from difflib import get_close_matches

from .address_format import parse_address
from .cnefe_base import BaseInvalida, abrir_base
from .cnefe_padrao import (
    normalizar_logradouro_cnefe, normalizar_numero, normalizar_texto,
)

_log = logging.getLogger("SIG-Bus.cnefe")

#: Mesmo corte de similaridade já praticado em `street_index.py`.
CORTE_SIMILARIDADE = 0.80


class CnefeGeocoder(object):
    """Consulta a base local do CNEFE. Nunca levanta exceção: erro vira `[]`."""

    #: caminho da base → conexão somente-leitura, reaproveitada na sessão.
    _conexoes = {}
    #: caminho da base → lista dos nomes distintos de logradouro (degrau 4).
    _nomes_vias = {}

    @classmethod
    def _conexao(cls, caminho_base):
        conn = cls._conexoes.get(caminho_base)
        if conn is None:
            conn = abrir_base(caminho_base)
            cls._conexoes[caminho_base] = conn
        return conn

    @classmethod
    def esquecer(cls, caminho_base=None):
        """Descarta conexões e índices em cache (base trocada na configuração)."""
        alvos = [caminho_base] if caminho_base else list(cls._conexoes)
        for alvo in alvos:
            conn = cls._conexoes.pop(alvo, None)
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            cls._nomes_vias.pop(alvo, None)

    # ---- degraus ---------------------------------------------------------

    @staticmethod
    def _candidato(linha, tipo_resultado, preciso, lat=None, lon=None, desvio=None):
        rua = linha["logradouro"]
        return {
            "lat": str(linha["lat"] if lat is None else lat),
            "lon": str(linha["lon"] if lon is None else lon),
            "display_name": linha["endereco_completo"] or rua,
            "properties": {"street": rua},
            "provider": "cnefe",
            "tipo_resultado": tipo_resultado,
            "desvio_metros": linha["desvio_metros"] if desvio is None else desvio,
            "preciso": preciso,
        }

    @classmethod
    def _por_numero(cls, conn, logradouro, numero, localidade):
        """Degraus 1 a 3: os três só valem quando há número."""
        if numero is None:
            return []

        # Degrau 1 (dn03): logradouro + número + bairro.
        if localidade:
            linhas = conn.execute(
                "SELECT * FROM enderecos WHERE logradouro = ? AND numero = ? AND localidade = ?",
                (logradouro, numero, localidade),
            ).fetchall()
            if linhas:
                return [cls._agregar(linhas, "dn03")]

        # Degrau 2 (dn04): logradouro + número, média ponderada por n_casos.
        linhas = conn.execute(
            "SELECT * FROM enderecos WHERE logradouro = ? AND numero = ?",
            (logradouro, numero),
        ).fetchall()
        if linhas:
            return [cls._agregar(linhas, "dn04")]

        # Degrau 3 (da04): número mais próximo na mesma via.
        linha = conn.execute(
            "SELECT * FROM enderecos WHERE logradouro = ? AND numero IS NOT NULL "
            "ORDER BY abs(numero - ?) LIMIT 1",
            (logradouro, numero),
        ).fetchone()
        if linha:
            return [cls._candidato(linha, "da04", True)]

        return []

    @classmethod
    def _agregar(cls, linhas, tipo_resultado):
        """Média de lat/lon ponderada por `n_casos` — a desambiguação do `dn04`.

        Com uma linha só (o caso comum) devolve a própria linha.
        """
        if len(linhas) == 1:
            return cls._candidato(linhas[0], tipo_resultado, True)

        pesos = [(l["n_casos"] or 1) for l in linhas]
        total = float(sum(pesos)) or 1.0
        lat = sum(l["lat"] * p for l, p in zip(linhas, pesos)) / total
        lon = sum(l["lon"] * p for l, p in zip(linhas, pesos)) / total
        desvios = [l["desvio_metros"] for l in linhas if l["desvio_metros"] is not None]
        desvio = sum(desvios) / float(len(desvios)) if desvios else None
        # O endereço exibido é o da variante com mais casos no CNEFE.
        principal = max(zip(linhas, pesos), key=lambda par: par[1])[0]
        return cls._candidato(principal, tipo_resultado, True, lat=lat, lon=lon, desvio=desvio)

    @classmethod
    def _por_via(cls, conn, logradouro, localidade):
        """Degrau 5 (dl03/dl04): centroide da via — resultado **impreciso**."""
        if localidade:
            linha = conn.execute(
                "SELECT * FROM logradouros WHERE logradouro = ? AND localidade = ?",
                (logradouro, localidade),
            ).fetchone()
            if linha:
                return [cls._candidato(linha, "dl03", False)]

        linha = conn.execute(
            "SELECT * FROM logradouros WHERE logradouro = ? ORDER BY n_casos DESC LIMIT 1",
            (logradouro,),
        ).fetchone()
        if linha:
            return [cls._candidato(linha, "dl04", False)]
        return []

    @classmethod
    def corrigir_logradouro(cls, caminho_base, logradouro):
        """Degrau 4 (decisão 170): corrige a grafia contra os nomes da base.

        O mesmo serviço do `_degrau_corretor` (decisão 68), mas offline e
        instantâneo: a lista de vias já está no disco, não precisa ir ao
        Overpass. Devolve o nome real do CNEFE ou `None`.
        """
        nomes = cls._nomes_vias.get(caminho_base)
        if nomes is None:
            conn = cls._conexao(caminho_base)
            nomes = [l[0] for l in conn.execute("SELECT DISTINCT logradouro FROM logradouros")]
            cls._nomes_vias[caminho_base] = nomes

        achados = get_close_matches(logradouro, nomes, n=1, cutoff=CORTE_SIMILARIDADE)
        if achados and achados[0] != logradouro:
            return achados[0]
        return None

    # ---- entrada ---------------------------------------------------------

    @classmethod
    def geocode(cls, endereco, contexto=None, caminho_base=None):
        """Candidatos do CNEFE para `endereco`, ou `[]`.

        Cada candidato traz `provider="cnefe"`, `tipo_resultado`,
        `desvio_metros` e `preciso` — a cascata de `geocoding.geocode` usa
        `preciso` para decidir se pode parar aí (decisão 168) e o diálogo usa
        `desvio_metros` para mostrar o "± N m" (decisão 173).
        """
        if not endereco or not caminho_base:
            return []

        try:
            conn = cls._conexao(caminho_base)

            partes = parse_address(endereco)
            logradouro = normalizar_logradouro_cnefe(partes.get("logradouro") or endereco)
            numero = normalizar_numero(partes.get("numero"))
            localidade = normalizar_texto(partes.get("bairro")) or None
            if not logradouro:
                return []

            achados = cls._por_numero(conn, logradouro, numero, localidade)
            if achados:
                return achados

            # Degrau 4: nome corrigido por similaridade, e volta aos degraus 1-3.
            corrigido = cls.corrigir_logradouro(caminho_base, logradouro)
            if corrigido:
                achados = cls._por_numero(conn, corrigido, numero, localidade)
                if achados:
                    for cand in achados:
                        # Prefixo `p` = palpite, para o rótulo da decisão 59 disparar.
                        cand["tipo_resultado"] = "p" + cand["tipo_resultado"][1:]
                    return achados

            # Degrau 5: centroide da via, marcado como impreciso.
            achados = cls._por_via(conn, logradouro, localidade)
            if not achados and corrigido:
                achados = cls._por_via(conn, corrigido, localidade)
                for cand in achados:
                    cand["tipo_resultado"] = "p" + cand["tipo_resultado"][1:]
            return achados

        except (BaseInvalida, sqlite3.Error, KeyError, TypeError, ValueError) as exc:
            _log.warning("CNEFE: consulta a %s falhou (%s)", caminho_base, exc)
            cls.esquecer(caminho_base)
            return []
