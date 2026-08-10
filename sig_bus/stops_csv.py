# -*- coding: utf-8 -*-
"""Módulo puro para o formato de lote (CSV) de paradas do assistente
"Construir GTFS".

Não importa Qt nem QGIS.
"""

import csv
import unicodedata

from .address_format import format_address

CSV_DELIMITER = ";"
CSV_HEADER = [
    "sequencia", "nome_parada", "logradouro", "numero", "bairro",
    "latitude", "longitude", "observacao",
]

_EXAMPLE_ROWS = [
    ["1", "Escola Municipal", "Rua Giuseppe Fórmolo", "210", "Centro",
     "", "", "Parada em frente à escola"],
    ["2", "Entroncamento da BR-101", "", "", "",
     "-29.1634", "-51.1794", "Parada rural, sem endereço cadastrado"],
]


def _normalize_header_cell(cell):
    """Normaliza um nome de coluna: minúsculas, sem acento, sem espaços nas pontas."""
    cell = (cell or "").strip().lower()
    nfkd = unicodedata.normalize("NFKD", cell)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def write_template(caminho):
    """Grava um modelo de CSV em lote de paradas em `caminho`.

    UTF-8 com BOM (abre corretamente no Excel/LibreOffice em pt-BR) e ponto
    como separador decimal em latitude/longitude.
    """
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=CSV_DELIMITER)
        writer.writerow(CSV_HEADER)
        for row in _EXAMPLE_ROWS:
            writer.writerow(row)


def parse_stops_csv(caminho):
    """Lê um CSV em lote de paradas.

    Retorna a tupla (linhas_ok, erros):
    - `linhas_ok`: lista de dicts com `sequencia`, `nome_parada`, `endereco`
      (já montado por `format_address`), `lat`/`lon` (`float` ou `None`) e
      `observacao`, ordenada por `sequencia`.
    - `erros`: lista de strings, uma por linha inválida, com o número da
      linha e o motivo.

    Tolera BOM, cabeçalho com acento/maiúscula trocada e colunas opcionais
    ausentes. Uma linha precisa ter endereço (`logradouro`) **ou**
    latitude/longitude — nunca nenhum dos dois.
    """
    linhas_ok = []
    erros = []

    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=CSV_DELIMITER)
        try:
            header = next(reader)
        except StopIteration:
            return [], ["Arquivo vazio."]

        normalized_header = [_normalize_header_cell(h) for h in header]
        expected = set(CSV_HEADER)
        col_index = {}
        for idx, name in enumerate(normalized_header):
            if name in expected and name not in col_index:
                col_index[name] = idx

        if not col_index:
            return [], [
                "Cabeçalho não reconhecido — confira se o delimitador do "
                "arquivo é ';' (ponto e vírgula) e se as colunas seguem o "
                "modelo."
            ]

        for line_num, row in enumerate(reader, start=2):
            if not any((cell or "").strip() for cell in row):
                continue  # linha em branco

            def get(col, _row=row):
                idx = col_index.get(col)
                if idx is None or idx >= len(_row):
                    return ""
                return (_row[idx] or "").strip()

            sequencia_raw = get("sequencia")
            try:
                sequencia = int(sequencia_raw) if sequencia_raw else None
            except ValueError:
                sequencia = None

            nome_parada = get("nome_parada")
            observacao = get("observacao")

            endereco = format_address({
                "logradouro": get("logradouro"),
                "numero": get("numero"),
                "bairro": get("bairro"),
            })

            lat_raw = get("latitude")
            lon_raw = get("longitude")

            def parse_coord(raw):
                if not raw:
                    return None, False
                try:
                    return float(raw.replace(",", ".")), False
                except ValueError:
                    return None, True

            lat, lat_invalida = parse_coord(lat_raw)
            lon, lon_invalida = parse_coord(lon_raw)

            if lat_invalida or lon_invalida:
                erros.append(
                    "Linha {}: latitude/longitude inválida ({!r}/{!r})."
                    .format(line_num, lat_raw, lon_raw)
                )
                continue

            if (lat is None) != (lon is None):
                erros.append(
                    "Linha {}: informe latitude e longitude juntas, ou "
                    "nenhuma das duas.".format(line_num)
                )
                continue

            if not endereco and lat is None:
                erros.append(
                    "Linha {}: sem endereço e sem latitude/longitude — "
                    "informe pelo menos um dos dois.".format(line_num)
                )
                continue

            linhas_ok.append({
                "sequencia": sequencia,
                "nome_parada": nome_parada,
                "endereco": endereco,
                "lat": lat,
                "lon": lon,
                "observacao": observacao,
            })

    linhas_ok.sort(key=lambda l: (l["sequencia"] is None, l["sequencia"]))
    return linhas_ok, erros
