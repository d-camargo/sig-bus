# SIG-Bus — Feature Documentation

*[Português](#sig-bus--documentação-de-funcionalidades) | English*

**Version:** 0.2  
**Author:** Diego Camargo  
**Project:** PIBIC DPPG 113/2021  
**Last updated:** 2026-05-29

---

## Table of Contents

1. [Overview](#1-overview)
2. [Workflow](#2-workflow)
3. [GTFS Section](#3-gtfs-section)
4. [Demand Data Section](#4-demand-data-section)
5. [Filter and Analysis Section](#5-filter-and-analysis-section)
6. [Demand Allocation](#6-demand-allocation)
7. [Output Layers](#7-output-layers)
8. [Data Architecture](#8-data-architecture)
9. [Known Limitations](#9-known-limitations)

---

## 1. Overview

SIG-Bus is a QGIS plugin for public transport analysis. It integrates data in GTFS
(*General Transit Feed Specification*) format with passenger boarding demand data
per bus stop, enabling visualisation, filtering, and allocation of passenger loads
along route alignments.

The GTFS reader is built into the plugin (`gtfs_reader.py`), adapted from the
*GTFS Loader* plugin by CTU GeoForAll Lab (GPL v2+). No external plugin is required.

---

## 2. Workflow

```
1. Check GTFS (.zip)         → corrects calendar if necessary
          ↓
2. Load GTFS                 → writes to GeoPackage, adds layers to project
          ↓
3. Select demand CSV         → Insert
          ↓
4. Select layer + field      → choose route in the feature picker
          ↓
5. Filter data               → highlights alignment + filters demand + loads timetables
          ↓
6. Choose hour + Allocate    → generates link layer with load per segment
```

QGIS can be closed and reopened after step 2. Use **Reconnect GeoPackage** to
restore layers without reprocessing the GTFS feed.

---

## 3. GTFS Section

### Check GTFS (`gtfs_insert_button`)

Verifies whether the GTFS `.zip` contains `calendar.txt`. If the feed only provides
`calendar_dates.txt` (exception-based feeds), the plugin synthesises a weekly
`calendar.txt` from the effective service dates and produces `gtfs_corrigido.zip`
alongside the original.

> The BHTrans GTFS feed (2024) already contains `calendar.txt`; this step is not
> mandatory for that feed.

### Load GTFS (`button_gtfsgo`)

Imports the GTFS `.zip` into a GeoPackage (`.gpkg`) with the same base name,
saved in the same folder. Internal steps:

1. Imports each `.txt` from the feed as a table in the GeoPackage via GDAL
   (streaming — memory-efficient for large `stop_times` files).
2. Builds the `shapes` (polyline) layer by grouping and sorting `shapes_point`
   records by `shape_id` and `shape_pt_sequence`.
3. Creates SQLite indexes on join keys (`trip_id`, `stop_id`, `shape_id`) to
   speed up subsequent queries.

**Layers added to the project:** `stops`, `shapes`, `routes`, `trips`, `calendar`.  
Tables `stop_times`, `agency`, `fare_*`, etc. remain in the GeoPackage for joins only.

**Link key:** the `route_short_name` field in the `routes` table holds the
human-readable route code (e.g. `"101"`). All demand↔GTFS integration uses this field.

> **Note on `shape_id`:** In the BHTrans GTFS the `shape_id` is a sequential integer
> (`"1"` to `"1109"`), unrelated to the route number. The demand↔GTFS join **never**
> uses `shape_id` directly — it always goes through `LINHA = route_short_name`.

---

## 4. Demand Data Section

### Select CSV and Insert (`data_insert_button`)

Imports the demand CSV (delimiter `;`, encoding `windows-1252`, coordinates in
SIRGAS 2000 / EPSG:31983) into the GeoPackage `sigt.gpkg`, saved in the same
folder as the CSV.

**Expected CSV columns:**

| Column | Type | Description |
|--------|------|-------------|
| `SIU` | text | Boarding point code |
| `LINHA` | text | Route code (join key with `route_short_name`) |
| `SUBLINHA` | text | Sub-route (variant) |
| `PC` | integer | Direction: `1` = outbound, `2` = inbound |
| `Seq` | integer | Stop sequence along the route |
| `0` … `23` | integer | Boardings per hour slot |
| ` Total geral ` | integer | Daily total (column name includes spaces) |
| `Latitude.WGS84` | decimal | Stop latitude in WGS84 |
| `Longitude.WGS84` | decimal | Stop longitude in WGS84 |
| `X` | decimal | Easting in SIRGAS 2000 UTM 23S |
| `Y` | decimal | Northing in SIRGAS 2000 UTM 23S |

> `LINHA` is a text field — some routes have alphanumeric codes such as `"1404A"`.
> SQL filters use quotes: `LINHA = '101'`.

---

## 5. Filter and Analysis Section

### Route picker

Uses `QgsMapLayerComboBox` (layer) + `QgsFieldComboBox` (field) +
`QgsFeaturePickerWidget` (value). Expected flow:

1. Select the **`routes`** layer in the layer combo.
2. Select the **`route_short_name`** field in the field combo.
3. Type or pick the route code in the feature picker (e.g. `101`).

### Filter data (`filterButton`)

Given the selected `route_short_name`:

1. Queries `routes` → `route_id` → `trips.shape_id` (all shapes for the route).
2. Applies a subset filter to the `shapes` layer: `shape_id IN ('671', '672', ...)`
   — highlights the route alignment.
3. Applies a filter to the `dados_demanda` layer: `LINHA = '101'`.
4. Launches `_HorariosTask` in the background: loads timetables for all trips of
   the route as a point layer `horarios_paradas` (join `stop_times ⋈ trips ⋈ stops`).

### Reconnect GeoPackage (`button_reconnect`)

After closing and reopening QGIS, memory layers (`horarios_paradas`,
`tramos_demanda`) are lost. This button:

1. Locates the GTFS GeoPackage via 4 cascading strategies:
   - `self._gpkg_path` (current session)
   - `gpkg_path` property saved in the `.qgs`/`.qgz` project file
   - `source()` of GTFS layers already present in the project
   - File dialog (manual fallback)
2. Re-adds to the project any essential layers (`stops`, `shapes`, `routes`,
   `trips`, `calendar`) that are missing, without duplicating existing ones.

---

## 6. Demand Allocation

### Hour selector (`combo_hora`) and Allocate Demand (`button_alocar`)

The selector offers `Total geral` (full-day demand) or a specific hour `00h`–`23h`
(matching the CSV hour slot).

Clicking **Allocate Demand** launches the `_AlocacaoTask` background task:

#### Step 1 — Stop coordinates
Reads `stop_id`, `stop_name`, latitude, and longitude from the `stops` layer via OGR.

#### Step 2 — Demand read
Connects to `sigt.gpkg` and runs a `SELECT` on `dados_demanda`, filtering by `LINHA`
and reading the correct column:
- `Total geral` → column ` Total geral ` (name detected via `PRAGMA table_info`)
- `07h` → column `7`

> `SELECT` on a spatial table via `sqlite3` is safe. Only `INSERT`/`UPDATE` triggers
> the spatial index (RTree) and requires the QGIS/OGR API.

#### Step 3 — Dominant shape by direction and hour

For each direction (PC=1 → `direction_id=0`; PC=2 → `direction_id=1`):

- **With a specific hour selected:** finds the shape with the most trips
  *departing* in that hour (filters by the `departure_time` of the first stop
  of each trip):
  ```sql
  SELECT t.shape_id, COUNT(*) c
  FROM trips t
  JOIN stop_times st ON st.trip_id = t.trip_id
  WHERE t.route_id = ? AND t.direction_id = ?
    AND CAST(st.stop_sequence AS INTEGER) = (
      SELECT MIN(CAST(ss.stop_sequence AS INTEGER))
      FROM stop_times ss WHERE ss.trip_id = t.trip_id
    )
    AND CAST(SUBSTR(st.departure_time,1,2) AS INTEGER) = ?
  GROUP BY t.shape_id ORDER BY c DESC LIMIT 1
  ```
  If no trips exist for that hour, falls back to the overall dominant shape and
  logs a warning.

- **With `Total geral`:** uses the shape with the most trips across the full day.

This links the hourly demand to the trips that actually operated in that time slot,
enabling estimation of the **per-trip load** (`embarques ÷ n_viagens`).

#### Step 4 — Stop sequence for the dominant shape
Retrieves one trip from the dominant shape and its stop list sorted by
`stop_sequence`.

#### Step 5 — Spatial join: demand points → GTFS stops

For each demand point from the CSV, the nearest stop **in the filtered route's stop
sequence** is found by Euclidean distance in WGS84 decimal degrees. Boardings are
accumulated per stop.

**How the distance is calculated:**  
For a demand point at (λ₁, φ₁) and a GTFS stop at (λ₂, φ₂), the Euclidean distance
is `sqrt((λ₁−λ₂)² + (φ₁−φ₂)²)` in degrees. At Belo Horizonte's latitude (~20°S) one
degree of longitude equals ≈ 104 km and one degree of latitude ≈ 111 km, so the
aspect ratio distortion is less than 7%. For stops tens of metres apart this
introduces a sub-metre error — negligible at city scale.

**Where this can fail:**  
The algorithm matches each demand point to the geometrically closest stop, without
verifying whether that stop actually belongs to the correct sequence position for
the route. Two known failure cases:

1. **Shared stops between adjacent lines:** if two different routes stop at the
   same physical location (or within a few metres), a demand point may snap to a
   stop from the wrong route. This is partially mitigated because the candidate
   set is already restricted to the stops of the selected route's dominant shape.
2. **Parallel alignments with closely-spaced stops:** on corridors where two
   route alignments run side by side with stops less than ~30 m apart, the
   nearest-stop heuristic may assign a boarding to the wrong stop.

In practice, most urban bus stops are at least 50–100 m apart, so mismatches are
rare. The demand CSV already carries a `Seq` field (sequential position of the
stop along the route) that could be used in a future version for a more robust
route-constrained join.

#### Step 6 — Segment generation and accumulated load

For each consecutive pair of stops `A → B`:

```
embarques[A]          = boardings assigned to stop A
passageiros_acum[A→B] = Σ embarques[stops 0..A]
```

`passageiros_acum` is the **estimated passenger load on the bus** at that segment.
It assumes no alighting occurs before the end of the line, making it an **upper
bound** on the actual load. See [Known Limitations](#9-known-limitations) and
`METHODS.md` for a full discussion of the load profile model.

---

## 7. Output Layers

### `horarios_paradas` (points, memory)

Generated by `_HorariosTask` when **Filter data** is clicked.

| Field | Type | Description |
|-------|------|-------------|
| `stop_id` | text | Stop ID (GTFS) |
| `stop_sequence` | text | Stop order within the trip |
| `arrival_time` | text | Arrival time (`HH:MM:SS`) |
| `departure_time` | text | Departure time (`HH:MM:SS`) |
| `trip_id` | text | Trip ID |
| `shape_id` | text | Shape ID |
| `direction_id` | text | Direction (`0` = outbound, `1` = inbound) |
| `service_id` | text | Service ID (calendar) |
| `stop_name` | text | Stop name |
| `linha` | text | `route_short_name` |

> Memory layer: **lost when QGIS is closed**. Run **Filter data** again after reconnecting.

### `tramos_demanda` (lines, memory)

Generated by `_AlocacaoTask` when **Allocate Demand** is clicked.

| Field | Type | Description |
|-------|------|-------------|
| `seq_from` | integer | `stop_sequence` of the origin stop |
| `stop_id_from` | text | Origin stop ID |
| `stop_name_from` | text | Origin stop name |
| `stop_id_to` | text | Destination stop ID |
| `stop_name_to` | text | Destination stop name |
| `embarques` | integer | Boardings assigned to the origin stop |
| `passageiros_acum` | integer | Cumulative passenger load at this segment |
| `pc` | text | Direction from the demand data (`1`=outbound, `2`=inbound) |
| `sentido` | text | `"ida"` (outbound) or `"volta"` (inbound) |
| `linha` | text | Route code (`route_short_name`) |
| `hora` | text | Hour slot used (`"Total"` or `"07h"`) |
| `n_viagens` | integer | GTFS trips that departed in this hour/direction |

> Memory layer: **lost when QGIS is closed**. Run **Allocate Demand** again after reconnecting.

#### Recommended symbology

- **Boardings per stop:** graduated symbology on `embarques` (identifies stops with
  the highest boarding demand).
- **Segment load:** graduated symbology on `passageiros_acum` (identifies the most
  loaded links — more useful for fleet sizing).
- **Split by direction:** filter by `sentido = 'ida'` or `sentido = 'volta'` before
  applying symbology.

---

## 8. Data Architecture

### Two GeoPackages

| File | Contents | Created by |
|------|----------|------------|
| `<gtfs_name>.gpkg` | `stops`, `shapes`, `shapes_point`, `routes`, `trips`, `stop_times`, `calendar`, etc. | **Load GTFS** |
| `sigt.gpkg` | `dados_demanda` | **Insert** (demand section) |

`sigt.gpkg` is saved in the same folder as the demand CSV. The GTFS GeoPackage is
saved in the same folder as the `.zip`.

### Demand ↔ GTFS join

```
dados_demanda.LINHA  ──→  routes.route_short_name  ──→  route_id
                                                           │
                                                        trips (route_id, direction_id)
                                                           │
                                                 dominant shape (COUNT trips)
                                                           │
                                              stop_times (trip_id) ──→ stops
```

**PC (demand) → `direction_id` (GTFS):**

| PC | Direction | `direction_id` |
|----|-----------|---------------|
| 1 | Outbound | 0 |
| 2 | Inbound | 1 |

> Some routes have PC=2 in the demand data but only `direction_id=0` in the GTFS
> (e.g. route 1170). The plugin logs a warning without interrupting the allocation.

### Session persistence

The GTFS GeoPackage path is saved in the project properties (`SIG-Bus/gpkg_path`).
When QGIS is reopened and the `.qgs`/`.qgz` project is loaded, **Reconnect GeoPackage**
retrieves the path automatically without a file dialog.

---

## 9. Known Limitations

| Limitation | Impact | Context |
|-----------|--------|---------|
| No alighting data | `passageiros_acum` grows monotonically — it is an **upper bound** on the real load | The demand CSV records boardings only |
| Simplified spatial join | Euclidean distance in WGS84 (not network distance) | Adequate for city scale; may fail for stops <30 m apart on parallel alignments |
| Single representative trip per shape | Stop sequence comes from one trip of the dominant shape | Itinerary variations within the same shape are ignored |
| Memory output layers | `horarios_paradas` and `tramos_demanda` are not saved in the `.qgz` | Must be regenerated after reopening QGIS |
| `departure_time` > 23 h in GTFS | Early-morning trips may have `departure_time = "24:15:00"` | `SUBSTR(...,1,2)` returns `"24"`, which does not match hour `0`; those trips are excluded from `n_viagens` for `00h` |

### Spatial join — additional detail

The nearest-stop matching (Step 5 of the allocation) operates on Euclidean distance
in WGS84 without verifying sequence alignment. This is acceptable in most cases
because:

- The candidate set is already restricted to the stops of the selected route's
  dominant shape (wrong-route snapping is prevented for most configurations).
- Urban bus stops are typically spaced 150–400 m apart, making the probability of
  a mismatch low.

The limitation becomes relevant on **BRT corridors and shared-platform terminals**,
where multiple routes stop at the same pole within a few metres. In those cases,
visually inspecting the `tramos_demanda` layer for unexpected zero-boarding segments
is recommended.

A future improvement would use the `Seq` field already present in the demand CSV
to enforce route-order matching, reducing spatial ambiguity to direction errors only.

---
---

# SIG-Bus — Documentação de Funcionalidades

*Português | [English](#sig-bus--feature-documentation)*

**Versão:** 0.2  
**Autor:** Diego Camargo  
**Projeto:** PIBIC DPPG 113/2021  
**Última atualização:** 2026-05-29

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Fluxo de Trabalho](#2-fluxo-de-trabalho)
3. [Seção GTFS](#3-seção-gtfs)
4. [Seção Dados de Demanda](#4-seção-dados-de-demanda)
5. [Seção de Filtro e Análise](#5-seção-de-filtro-e-análise)
6. [Alocação de Demanda](#6-alocação-de-demanda)
7. [Camadas de Saída](#7-camadas-de-saída)
8. [Arquitetura dos Dados](#8-arquitetura-dos-dados)
9. [Limitações Conhecidas](#9-limitações-conhecidas)

---

## 1. Visão Geral

O SIG-Bus é um plugin QGIS para análise de transporte público que integra dados no
formato GTFS (*General Transit Feed Specification*) com dados de demanda de embarque
por ponto de ônibus. Ele permite visualizar, filtrar e alocar a demanda de passageiros
ao longo dos traçados das linhas.

O leitor de GTFS é embutido no plugin (`gtfs_reader.py`), adaptado do plugin
*GTFS Loader* do CTU GeoForAll Lab (GPL v2+). Nenhum plugin externo é necessário.

---

## 2. Fluxo de Trabalho

```
1. Verificar GTFS (.zip)       → corrige calendar se necessário
          ↓
2. Executar GTFS               → grava no GeoPackage, adiciona camadas ao projeto
          ↓
3. Selecionar CSV de demanda   → Inserir
          ↓
4. Selecionar camada + campo   → escolher linha no picker
          ↓
5. Filtrar dados               → destaca traçado + filtra demanda + carrega horários
          ↓
6. Escolher hora + Alocar Demanda → gera camada de tramos com carga por segmento
```

O QGIS pode ser fechado e reaberto após o passo 2. Use **Reconectar GeoPackage**
para restaurar as camadas sem reprocessar o GTFS.

---

## 3. Seção GTFS

### Verificar GTFS (`gtfs_insert_button`)

Verifica se o `.zip` do GTFS contém `calendar.txt`. Caso o feed traga apenas
`calendar_dates.txt` (feeds que operam por exceção), o plugin sintetiza um
`calendar.txt` semanal a partir das datas de operação efetiva e gera o arquivo
`gtfs_corrigido.zip` ao lado do original.

> O GTFS da BHTrans (2024) já contém `calendar.txt`; este passo não é obrigatório
> para esse feed.

### Executar GTFS (`button_gtfsgo`)

Importa o `.zip` do GTFS para um GeoPackage (`.gpkg`) com o mesmo nome do arquivo,
gravado na mesma pasta. As etapas internas são:

1. Importa cada `.txt` do feed como tabela no GeoPackage via GDAL (streaming —
   eficiente em memória para `stop_times` grandes).
2. Constrói a camada `shapes` (polilinha) agrupando e ordenando os pontos de
   `shapes_point` por `shape_id` e `shape_pt_sequence`.
3. Cria índices SQLite nas chaves de join (`trip_id`, `stop_id`, `shape_id`) para
   acelerar consultas posteriores.

**Camadas adicionadas ao projeto:** `stops`, `shapes`, `routes`, `trips`, `calendar`.  
As tabelas `stop_times`, `agency`, `fare_*` etc. ficam no GeoPackage apenas para joins.

**Chave de ligação:** o campo `route_short_name` da tabela `routes` corresponde ao
código da linha (ex.: `"101"`). Toda a integração demanda↔GTFS passa por esse campo.

> **Nota sobre `shape_id`:** No GTFS da BHTrans o `shape_id` é numérico sequencial
> (`"1"` a `"1109"`), sem relação direta com o número da linha. O join demanda↔GTFS
> **nunca** usa `shape_id` diretamente — usa sempre `LINHA = route_short_name`.

---

## 4. Seção Dados de Demanda

### Selecionar CSV e Inserir (`data_insert_button`)

Importa o CSV de demanda (delimitador `;`, encoding `windows-1252`, coordenadas em
SIRGAS 2000 / EPSG:31983) para o GeoPackage `sigt.gpkg`, gravado na mesma pasta
do CSV.

**Colunas esperadas no CSV:**

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `SIU` | texto | Código do ponto de embarque |
| `LINHA` | texto | Código da linha (chave de join com `route_short_name`) |
| `SUBLINHA` | texto | Sub-linha (variante) |
| `PC` | inteiro | Sentido: `1` = ida, `2` = volta |
| `Seq` | inteiro | Sequência do ponto na linha |
| `0` … `23` | inteiro | Embarques por faixa horária (hora cheia) |
| ` Total geral ` | inteiro | Total diário (nome com espaços) |
| `Latitude.WGS84` | decimal | Latitude do ponto em WGS84 |
| `Longitude.WGS84` | decimal | Longitude do ponto em WGS84 |
| `X` | decimal | Coordenada X em SIRGAS 2000 UTM 23S |
| `Y` | decimal | Coordenada Y em SIRGAS 2000 UTM 23S |

> `LINHA` é campo texto — há linhas alfanuméricas como `"1404A"`. Filtros SQL usam
> aspas: `LINHA = '101'`.

---

## 5. Seção de Filtro e Análise

### Picker de linha

Usa `QgsMapLayerComboBox` (camada) + `QgsFieldComboBox` (campo) +
`QgsFeaturePickerWidget` (valor). O fluxo esperado:

1. Selecionar a camada **`routes`** no combo de camadas.
2. Selecionar o campo **`route_short_name`** no combo de campos.
3. Digitar ou selecionar o código da linha no picker (ex.: `101`).

### Filtrar dados (`filterButton`)

A partir do `route_short_name` selecionado:

1. Consulta `routes` → `route_id` → `trips.shape_id` (todos os shapes da linha).
2. Aplica filtro de subconjunto na camada `shapes`: `shape_id IN ('671', '672', ...)`
   — destaca o traçado da linha.
3. Aplica filtro na camada `dados_demanda`: `LINHA = '101'`.
4. Dispara `_HorariosTask` em segundo plano: carrega os horários de todas as viagens
   da linha como camada de pontos `horarios_paradas`
   (join `stop_times ⋈ trips ⋈ stops`).

### Reconectar GeoPackage (`button_reconnect`)

Após fechar e reabrir o QGIS as camadas de memória (`horarios_paradas`,
`tramos_demanda`) somem. Este botão:

1. Localiza o GeoPackage do GTFS por 4 estratégias em cascata:
   - `self._gpkg_path` (sessão atual)
   - Propriedade `gpkg_path` salva no projeto `.qgs`/`.qgz`
   - `source()` de camadas GTFS já presentes no projeto
   - Diálogo de arquivo (fallback manual)
2. Readiciona ao projeto as camadas essenciais (`stops`, `shapes`, `routes`,
   `trips`, `calendar`) que estiverem ausentes, sem duplicar as existentes.

---

## 6. Alocação de Demanda

### Seletor de hora (`combo_hora`) e Alocar Demanda (`button_alocar`)

O seletor oferece `Total geral` (demanda diária) ou uma hora específica `00h`–`23h`
(faixa horária do CSV).

Ao clicar em **Alocar Demanda**, a tarefa `_AlocacaoTask` executa em segundo plano:

#### Passo 1 — Coordenadas das paradas
Lê `stop_id`, `stop_name`, latitude e longitude da camada `stops` via OGR.

#### Passo 2 — Leitura da demanda
Conecta ao `sigt.gpkg` e faz `SELECT` na tabela `dados_demanda`, filtrando por
`LINHA` e lendo a coluna correta:
- `Total geral` → coluna ` Total geral ` (nome detectado por `PRAGMA table_info`)
- `07h` → coluna `7`

> `SELECT` em tabela espacial via `sqlite3` é seguro. Apenas `INSERT`/`UPDATE`
> dispara os gatilhos do índice espacial (RTree) e requer a API QGIS/OGR.

#### Passo 3 — Shape dominante por sentido e hora

Para cada sentido (PC=1 → `direction_id=0`; PC=2 → `direction_id=1`):

- **Com hora específica selecionada:** busca o shape com mais viagens **iniciando**
  nessa hora (filtra pelo `departure_time` da primeira parada de cada viagem):
  ```sql
  SELECT t.shape_id, COUNT(*) c
  FROM trips t
  JOIN stop_times st ON st.trip_id = t.trip_id
  WHERE t.route_id = ? AND t.direction_id = ?
    AND CAST(st.stop_sequence AS INTEGER) = (
      SELECT MIN(CAST(ss.stop_sequence AS INTEGER))
      FROM stop_times ss WHERE ss.trip_id = t.trip_id
    )
    AND CAST(SUBSTR(st.departure_time,1,2) AS INTEGER) = ?
  GROUP BY t.shape_id ORDER BY c DESC LIMIT 1
  ```
  Se não houver viagens nessa hora, usa o shape dominante geral e registra aviso.

- **Com `Total geral`:** usa o shape com mais viagens no dia inteiro.

Isso vincula a demanda horária às viagens que realmente operaram naquela faixa,
permitindo estimar a **carga por viagem** (`embarques ÷ n_viagens`).

#### Passo 4 — Sequência de paradas do shape dominante

Recupera uma viagem do shape dominante e sua lista de paradas ordenada por
`stop_sequence`.

#### Passo 5 — Join espacial demanda → paradas

Para cada ponto de demanda do CSV, encontra a parada **da sequência da linha
filtrada** mais próxima por distância euclidiana em coordenadas WGS84. Os
embarques são acumulados por parada.

**Como a distância é calculada:**  
Para um ponto de demanda em (λ₁, φ₁) e uma parada GTFS em (λ₂, φ₂), a distância
euclidiana é `sqrt((λ₁−λ₂)² + (φ₁−φ₂)²)` em graus decimais. Na latitude de Belo
Horizonte (~20°S), um grau de longitude equivale a ~104 km e um grau de latitude
a ~111 km, resultando em distorção de aspecto inferior a 7%. Para paradas separadas
por dezenas de metros, isso introduz erro submétrico — negligenciável na escala
intra-urbana.

**Onde o método pode falhar:**  
O algoritmo vincula cada ponto de demanda à parada geometricamente mais próxima,
sem verificar se essa parada pertence à posição correta na sequência da rota.
Dois casos de falha conhecidos:

1. **Paradas compartilhadas entre linhas adjacentes:** se duas rotas diferentes
   param no mesmo local físico (ou a poucos metros), um ponto de demanda pode ser
   associado a uma parada de rota errada. Isso é parcialmente mitigado porque o
   conjunto candidato já está restrito às paradas do shape dominante da linha
   selecionada.
2. **Alinhamentos paralelos com paradas muito próximas:** em corredores onde dois
   traçados correm lado a lado com paradas a menos de ~30 m de distância, a
   heurística de parada mais próxima pode atribuir um embarque à parada errada.

Na prática, a maioria das paradas urbanas de ônibus está separada por 50–100 m ou
mais, tornando erros de correspondência raros. O CSV de demanda já traz o campo
`Seq` (posição sequencial do ponto na linha) que poderia ser usado em versão futura
para um join mais robusto com restrição de rota.

#### Passo 6 — Geração de segmentos e passageiros acumulados

Para cada par de paradas consecutivas `A → B`:

```
embarques[A]       = embarques alocados à parada A
passageiros_acum[A→B] = Σ embarques[stops 0..A]
```

O campo `passageiros_acum` representa a **carga estimada no ônibus** no segmento,
assumindo que nenhum passageiro desce antes do fim da linha — ou seja, é um
**limite superior** da carga real. Veja [Limitações Conhecidas](#9-limitações-conhecidas)
e `METHODS.md` para discussão completa do modelo de perfil de carga.

---

## 7. Camadas de Saída

### `horarios_paradas` (pontos, memória)

Gerada por `_HorariosTask` ao clicar em **Filtrar dados**.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `stop_id` | texto | ID da parada (GTFS) |
| `stop_sequence` | texto | Ordem da parada na viagem |
| `arrival_time` | texto | Horário de chegada (`HH:MM:SS`) |
| `departure_time` | texto | Horário de partida (`HH:MM:SS`) |
| `trip_id` | texto | ID da viagem |
| `shape_id` | texto | ID do traçado |
| `direction_id` | texto | Sentido (`0` = ida, `1` = volta) |
| `service_id` | texto | ID do serviço (calendário) |
| `stop_name` | texto | Nome da parada |
| `linha` | texto | `route_short_name` |

> Camada de memória: **desaparece ao fechar o QGIS**. Use **Filtrar dados** novamente
> após reconectar.

### `tramos_demanda` (linhas, memória)

Gerada por `_AlocacaoTask` ao clicar em **Alocar Demanda**.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `seq_from` | inteiro | `stop_sequence` da parada de origem |
| `stop_id_from` | texto | ID da parada de origem |
| `stop_name_from` | texto | Nome da parada de origem |
| `stop_id_to` | texto | ID da parada de destino |
| `stop_name_to` | texto | Nome da parada de destino |
| `embarques` | inteiro | Embarques alocados à parada de origem |
| `passageiros_acum` | inteiro | Carga acumulada no ônibus nesse tramo |
| `pc` | texto | Sentido original da demanda (`1`=ida, `2`=volta) |
| `sentido` | texto | `"ida"` ou `"volta"` |
| `linha` | texto | Código da linha (`route_short_name`) |
| `hora` | texto | Faixa horária usada (`"Total"` ou `"07h"`) |
| `n_viagens` | inteiro | Viagens GTFS que iniciaram nessa hora/sentido |

> Camada de memória: **desaparece ao fechar o QGIS**. Use **Alocar Demanda**
> novamente após reconectar.

#### Simbologia recomendada

- **Embarques por parada:** simbologia graduada no campo `embarques` (identifica
  pontos com maior demanda de embarque).
- **Carga no tramo:** simbologia graduada no campo `passageiros_acum` (identifica
  os trechos mais carregados — mais útil para dimensionamento de frota).
- **Divisão por sentido:** filtrar por `sentido = 'ida'` ou `sentido = 'volta'`
  antes de aplicar a simbologia.

---

## 8. Arquitetura dos Dados

### Dois GeoPackages

| Arquivo | Conteúdo | Gerado por |
|---------|----------|------------|
| `<nome_do_gtfs>.gpkg` | `stops`, `shapes`, `shapes_point`, `routes`, `trips`, `stop_times`, `calendar`, etc. | **Executar GTFS** |
| `sigt.gpkg` | `dados_demanda` | **Inserir** (seção demanda) |

O `sigt.gpkg` é gravado na mesma pasta do CSV de demanda. O GeoPackage do GTFS é
gravado na mesma pasta do `.zip`.

### Join demanda ↔ GTFS

```
dados_demanda.LINHA  ──→  routes.route_short_name  ──→  route_id
                                                           │
                                                        trips (route_id, direction_id)
                                                           │
                                                 shape dominante (COUNT trips)
                                                           │
                                              stop_times (trip_id) ──→ stops
```

**PC da demanda → `direction_id` do GTFS:**

| PC | Sentido | `direction_id` |
|----|---------|---------------|
| 1 | Ida | 0 |
| 2 | Volta | 1 |

> Algumas linhas têm PC=2 na demanda mas apenas `direction_id=0` no GTFS (ex.:
> linha 1170). O plugin registra aviso sem interromper a alocação.

### Persistência entre sessões

O caminho do GeoPackage do GTFS é salvo nas propriedades do projeto
(`SIG-Bus/gpkg_path`). Ao reabrir o QGIS e carregar o projeto `.qgs`/`.qgz`,
o **Reconectar GeoPackage** recupera o caminho automaticamente sem diálogo de
arquivo.

---

## 9. Limitações Conhecidas

| Limitação | Impacto | Contexto |
|-----------|---------|---------|
| Sem dados de desembarque | `passageiros_acum` cresce monotonicamente — é o **limite superior** da carga real | O CSV de demanda registra apenas embarques |
| Join espacial simplificado | Distância euclidiana em WGS84 (não distância ao longo da rede) | Adequado para escala intra-urbana; pode falhar em paradas com menos de ~30 m de separação em alinhamentos paralelos |
| Uma viagem representativa por shape | A sequência de paradas vem de uma única viagem do shape dominante | Variações de itinerário dentro do mesmo shape são ignoradas |
| Camadas de saída em memória | `horarios_paradas` e `tramos_demanda` não persistem no `.qgz` | Reprocessar após reabrir o QGIS |
| `departure_time` > 23h no GTFS | Viagens de madrugada podem ter `departure_time = "24:15:00"` | A extração da hora por `SUBSTR(...,1,2)` retorna `"24"`, que não casa com hora `0`; essas viagens não são contadas em `n_viagens` para `00h` |

### Join espacial — detalhamento

O pareamento por parada mais próxima (Passo 5 da alocação) opera por distância
euclidiana em WGS84 sem verificar alinhamento de sequência. Isso é aceitável na
maioria dos casos porque:

- O conjunto candidato já está restrito às paradas do shape dominante da linha
  selecionada (a associação à rota errada é prevenida para a maioria das configurações).
- Paradas urbanas de ônibus costumam ter espaçamento de 150–400 m, tornando baixa
  a probabilidade de erro de correspondência.

A limitação torna-se relevante em **corredores de BRT e terminais de plataforma
compartilhada**, onde múltiplas rotas param no mesmo poste a poucos metros de
distância. Nesses casos, recomenda-se inspecionar visualmente a camada
`tramos_demanda` em busca de segmentos com zero embarques inesperados.

Uma melhoria futura utilizaria o campo `Seq` já presente no CSV de demanda para
forçar o pareamento por ordem de rota, reduzindo a ambiguidade espacial apenas a
erros de sentido.
