# SIG-Bus — QGIS Plugin for Public Transport Analysis

*[Português](#sig-bus--plugin-qgis-para-análise-de-transporte-público) | English*

A QGIS plugin that integrates **GTFS** (*General Transit Feed Specification*) data
with **passenger boarding demand** data per bus stop, enabling visualisation and
allocation of passenger loads along route alignments.

Developed as part of the undergraduate research project PIBIC DPPG 113/2021.

## Features

The GTFS reader is **built-in** (`gtfs_reader.py`), adapted from the *GTFS Loader*
plugin by CTU GeoForAll Lab (GPL v2+). No external plugin is required.

### Demand analysis

- **Check GTFS:** validates the `.zip` feed and synthesises `calendar.txt` from
  `calendar_dates.txt` when the feed only provides the latter.
- **Load GTFS:** imports the feed into a GeoPackage via GDAL (streaming — memory-
  efficient for large feeds). Builds the route alignments layer (`shapes`) and
  creates join indexes.
- **Insert demand:** imports a boarding-by-stop/hour CSV into a GeoPackage
  (`sigt.gpkg`).
- **Filter data:** given a selected route (`route_short_name`), highlights the
  alignment in `shapes`, filters `dados_demanda`, and loads stop-level timetables
  (`horarios_paradas`) in the background.
- **Allocate Demand:** distributes boardings from the CSV across the segments
  (links) of the route, producing the `tramos_demanda` layer with:
  - `embarques` — boardings allocated to the upstream stop of the link
  - `passageiros_acum` — cumulative passenger load on the bus at that link
  - `n_viagens` — GTFS trips that departed within the selected hour
- **Hour selector:** filters the allocation by time slot (0 h–23 h) or the full
  daily total. When an hour is selected, the dominant shape among trips that
  *departed* in that hour is used.
- **Reconnect GeoPackage:** restores GTFS layers to the project without
  reprocessing the feed (useful after closing and reopening QGIS).

### Build GTFS

- **Build GTFS:** creates a GTFS feed from scratch via an interactive assistant (see [sig_bus/GUIA_CONSTRUIR_GTFS.md](sig_bus/GUIA_CONSTRUIR_GTFS.md)):
  - **Agency and Routes:** define the transit operator and route details.
  - **Geocoded Stops:** search stop addresses through a geocoding cascade — Google (optional, requires an API key) → Nominatim → Photon → an Overpass-based street-name corrector — showing a status label with the source (`✓ localizado (Nominatim)`, `✓ localizado (via: <real name> — OSM)`); addresses follow a suggested pattern (`Street, Number - Neighborhood`). An address that isn't found never blocks the flow.
  - **Batch Import:** load stops via CSV (see [sig_bus/MODELO_PARADAS_CSV.md](sig_bus/MODELO_PARADAS_CSV.md)).
  - **Mark on the Map:** click directly on the canvas to place a stop, for rural points without a geocodable address.
  - **Sequence:** arrange the stops in the correct visiting order.
  - **Timetables:** generate trips from a frequency rule, then fine-tune them trip by trip (see *Block Diagram* below) before anything is written.
  - **Review and save:** the route is written to an isolated `feed_edit.gpkg`, then validated and exported by the same engine as *Edit GTFS*.
  - **OSM Routing:** route alignments (`shapes`) follow the real OpenStreetMap street network between consecutive stops; a straight line is used as a fallback only on the segments the fetched network does not cover or connect.
  - **Dual progress bar:** shows how far the feed is from a **minimum** GTFS (required files and fields) and, beyond that, from a **complete** one (optional fields, `shapes`, second direction), naming what is still missing at each step.

### Edit and export GTFS

- **Edit GTFS:** allows editing GTFS fields and geometry in an isolated working copy (`feed_edit.gpkg`), with built-in validation and normalized export (see [sig_bus/GUIA_EDICAO_GTFS.md](sig_bus/GUIA_EDICAO_GTFS.md)).

### Block Diagram

- **Block Diagram:** a time × distance chart of the operation, in two modes — *Trips mode* (one bar per GTFS trip) and *Blocks mode*, in which the vehicle blocks are **inferred** by chaining trips, because the BHTrans feed carries no `trips.block_id`. See [sig_bus/DIAGRAMA_BLOCOS.md](sig_bus/DIAGRAMA_BLOCOS.md).
- **Headway dimension line:** selecting a trip draws a technical-drawing dimension line between two consecutive departures of the same route and direction, labelled with the measure alone (e.g. `12 min`).
- **Departure ruler:** one short tick per departure along the foot of the time axis — outbound on the upper band, inbound on the lower one — so peak and off-peak read straight from the density of ticks.
- **Fine schedule tuning:** with a trip selected, `>` and `<` shift only the departure or only the arrival, while `+` and `-` shift the whole trip preserving its duration. In the *Build GTFS* wizard the adjustment happens in memory, before the route is written, and applies to every day covered by the `calendar` of that `service_id`.
- **PDF Report:** generates an A4 landscape print layout with the map of the filtered route, legend, header, and two bar charts (outbound and inbound) of boardings grouped by K-means cluster.

## Documentation

| Document | What it answers |
|---|---|
| [`sig_bus/DOCUMENTACAO.md`](sig_bus/DOCUMENTACAO.md) | What each button does, output layer fields, and known limitations (EN + PT-BR) |
| [`sig_bus/METHODS.md`](sig_bus/METHODS.md) | Theoretical foundation of the demand allocation method (EN) |
| [`sig_bus/DIAGRAMA_BLOCOS.md`](sig_bus/DIAGRAMA_BLOCOS.md) | How to read the Block Diagram, its two modes, and the block inference (PT-BR) |
| [`sig_bus/GUIA_CONSTRUIR_GTFS.md`](sig_bus/GUIA_CONSTRUIR_GTFS.md) | Step-by-step of the "Build GTFS" wizard (PT-BR) |
| [`sig_bus/GUIA_EDICAO_GTFS.md`](sig_bus/GUIA_EDICAO_GTFS.md) | Step-by-step of the "Edit GTFS" tab and its common errors (PT-BR) |
| [`sig_bus/MODELO_PARADAS_CSV.md`](sig_bus/MODELO_PARADAS_CSV.md) | Column layout of the CSV for batch stop import (PT-BR) |
| [`sig_bus/ARQUITETURA_CONSTRUIR_GTFS.md`](sig_bus/ARQUITETURA_CONSTRUIR_GTFS.md) | Internal design of GTFS creation (PT-BR) |
| [`sig_bus/ARQUITETURA_EDICAO_GTFS.md`](sig_bus/ARQUITETURA_EDICAO_GTFS.md) | Internal design of GTFS editing (PT-BR) |

Version-by-version history is in [`CHANGELOG.md`](CHANGELOG.md); the current
version is the one declared in `sig_bus/metadata.txt`.

## Repository Structure

```
.
├── CHANGELOG.md            # version-by-version history
├── docs/
│   ├── gtfsfiles.zip       # sample GTFS feed for testing
│   └── PyQGIS_PIBIC.pdf    # original research documentation
└── sig_bus/                # plugin code (install into QGIS)
    ├── __init__.py
    ├── SigBus.py            # plugin main class
    ├── SigBus_dialog.py     # dialog logic + background tasks
    ├── SigBus_dialog_base.ui
    ├── gtfs_reader.py       # built-in GTFS reader
    ├── gtfs_schema.py       # single source of truth for the GTFS spec
    ├── gtfs_builder_core.py # builds a feed from scratch (progress, expansion)
    ├── gtfs_edit_core.py    # isolated working copy (feed_edit.gpkg)
    ├── gtfs_validator.py    # referential and format integrity checks
    ├── gtfs_export.py       # normalized export to .zip
    ├── geocoding.py         # geocoding cascade (Google/Nominatim/Photon)
    ├── geocoding_config.py  # provider mode and API key in QSettings
    ├── street_index.py      # Overpass-based street-name corrector
    ├── address_format.py    # suggested address pattern
    ├── osm_routing.py       # shapes over the real OSM street network
    ├── map_tools.py         # place a stop by clicking the canvas
    ├── stops_csv.py         # batch stop import from CSV
    ├── schedule_edit_core.py # in-memory schedule fine tuning
    ├── block_core.py        # Block Diagram model and block inference
    ├── block_scene.py       # Block Diagram drawing (bars, headway, ruler)
    ├── block_view.py        # Block Diagram view: zoom, pan, shortcuts
    ├── block_diagram_dialog.py # Block Diagram window
    ├── test_*.py            # test suite, runs outside QGIS
    ├── conftest.py          # qgis module stubs used by the suite
    ├── scripts/check_qgis_compat.py # manual probe against the installed QGIS
    ├── ARQUITETURA_CONSTRUIR_GTFS.md # technical architecture for GTFS creation (PT-BR)
    ├── ARQUITETURA_EDICAO_GTFS.md # technical architecture for GTFS editing (PT-BR)
    ├── DIAGRAMA_BLOCOS.md   # Block Diagram documentation (PT-BR)
    ├── DOCUMENTACAO.md      # detailed feature documentation (EN + PT-BR)
    ├── GUIA_CONSTRUIR_GTFS.md # user guide for GTFS creation (PT-BR)
    ├── GUIA_EDICAO_GTFS.md  # user guide for GTFS editing (PT-BR)
    ├── METHODS.md           # theoretical foundation of the allocation method
    ├── MODELO_PARADAS_CSV.md # documentation for CSV stops batch import (PT-BR)
    ├── modelo_paradas.csv   # template file for batch stops import
    ├── metadata.txt
    ├── icon.png
    └── resources.py / resources.qrc
```

## Requirements

- QGIS 3.34 LTR through 4.x — runs on both Qt 5 (QGIS 3.x) and Qt 6 (QGIS 4.x)
  (declared range `3.34` – `4.99`; probed on 3.34.4, tested on 3.44 and 4.2)
- QGIS built-in Python (no external dependencies beyond QGIS itself)

## Installation

1. Copy the `sig_bus/` folder to the QGIS plugins directory:
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. Enable the **SIG-Bus** plugin under *Plugins → Manage and Install Plugins →
   Installed*.
3. Access it via *Plugins → SIG-Bus*.

## Geocoding configuration

Configuring a **Google Maps API key is optional**. Without any key the OSM
cascade (Nominatim → Photon → Overpass street-name corrector) keeps working
exactly as before — nothing to set up.

- The key and the provider mode are stored in QGIS's `QSettings`
  (`SIG-Bus/geocoding/google_api_key` and `SIG-Bus/geocoding/provider`, handled
  by `geocoding_config.py`) — never in the project and never in the feed.
- Provider mode: `auto` tries Google first when a key is configured and falls
  back to the OSM cascade; `osm` ignores any key and uses the OSM cascade only.
- The key is **never** written to `feed_edit.gpkg` (which is shared) and never
  reaches the QGIS log — every logged URL is redacted to `key=***`.

## Workflow

The plugin has three main entry paths. Paths (b) and (c) share the **same** validator and export engine.

### a) Analyze an existing feed

```
Check GTFS → Load GTFS → Insert demand
→ Select route → Filter data
→ Choose hour → Allocate Demand
```

See `sig_bus/DOCUMENTACAO.md` for a detailed description of each step, output
layer fields, and known limitations. For the theoretical background of the
demand allocation method, see `sig_bus/METHODS.md`.

### b) Build a GTFS from scratch

```
Build GTFS → Route wizard → Export .zip
```

See [`sig_bus/GUIA_CONSTRUIR_GTFS.md`](sig_bus/GUIA_CONSTRUIR_GTFS.md) for the user guide.

### c) Edit a loaded feed

```
Edit GTFS → Edit data → Validate → Export .zip
```

See [`sig_bus/GUIA_EDICAO_GTFS.md`](sig_bus/GUIA_EDICAO_GTFS.md) for the user guide.

## Sample Data

`docs/gtfsfiles.zip` contains a GTFS feed for testing.
Expected demand data follows the SIU-BHTrans format
(`;`-delimited CSV, columns `0`–`23` with hourly boardings).

## Tests

The test suite runs entirely **outside QGIS**, on stubs of the `qgis` modules
(`sig_bus/conftest.py`) — no QGIS installation is required. From the repository
root:

```
python3 -m pytest sig_bus -q
```

Besides the unit tests, the suite carries regression guards:
`test_qt6_compat.py` (unqualified enums, which break QGIS 4),
`test_metadata.py` (declared QGIS version range and a closed CHANGELOG matching
`metadata.txt`) and `test_readme.py` (relative links in this file, and the two
halves staying in step). `sig_bus/scripts/check_qgis_compat.py` is a manual
probe against an installed QGIS and does not run under pytest.

## Release Process

To package and release a new version of the SIG-Bus plugin:

1. **Update version:** Edit `sig_bus/metadata.txt` to increment `version=X.Y` (keeping `qgisMinimumVersion=3.34`, `qgisMaximumVersion=4.99` and `supportsQt6=True` — without the maximum, QGIS assumes `3.99` and rejects every QGIS 4.x).
2. **Update Changelog:** Add release notes under a new version heading in `CHANGELOG.md`.
3. **Run Test Suite:** Execute `pytest` to verify all tests and guards pass.
4. **Probe the installed QGIS:** Run `python3 sig_bus/scripts/check_qgis_compat.py` against the QGIS you are targeting — it imports every module, builds a `QgsField`, checks the qualified-enum inventory and loads the `.ui`, printing `OK`/`FAIL` per item.
5. **Package Plugin:** Create the distribution `.zip` archive using `qgis-plugin-ci` or `make package`:
   - Via `qgis-plugin-ci`: `qgis-plugin-ci package <version>`
   - Via `make`: `cd sig_bus && make package VERSION=v<version>`
6. **Tag and Publish:** Create and push a Git tag (e.g. `git tag -a v0.5 -m "Release 0.5" && git push origin v0.5`) and upload the generated `.zip` to QGIS Plugin Repository or GitHub Releases.

## Author

Diego Camargo — <diegocamargo.bft@gmail.com>  
Repository: <https://github.com/d-camargo/sig-bus>

---

# SIG-Bus — Plugin QGIS para Análise de Transporte Público

*Português | [English](#sig-bus--qgis-plugin-for-public-transport-analysis)*

Plugin do QGIS que integra dados **GTFS** (*General Transit Feed Specification*)
com dados de **demanda de embarque** por ponto de ônibus, permitindo visualizar
e alocar a carga de passageiros ao longo dos traçados das linhas.

Desenvolvido no contexto do projeto de Iniciação Científica PIBIC DPPG 113/2021.

## Funcionalidades

O leitor de GTFS é **embutido** (`gtfs_reader.py`), adaptado do plugin
*GTFS Loader* do CTU GeoForAll Lab (GPL v2+). Nenhum plugin externo é
necessário.

### Análise de demanda

- **Verificar GTFS:** valida o `.zip` e sintetiza `calendar.txt` a partir de
  `calendar_dates.txt` quando necessário.
- **Executar GTFS:** importa o feed para um GeoPackage via GDAL (streaming —
  eficiente em memória para feeds grandes). Constrói a camada de linhas
  (`shapes`) e cria índices de join.
- **Inserir demanda:** importa CSV de embarque por ponto/hora para GeoPackage
  (`sigt.gpkg`).
- **Filtrar dados:** a partir da linha selecionada (`route_short_name`), destaca
  o traçado em `shapes`, filtra `dados_demanda` e carrega horários por parada
  (`horarios_paradas`) em segundo plano.
- **Alocar Demanda:** distribui os embarques do CSV nos segmentos (tramos) da
  linha, gerando a camada `tramos_demanda` com os campos:
  - `embarques` — embarques alocados à parada de origem do tramo
  - `passageiros_acum` — carga acumulada no ônibus naquele trecho
  - `n_viagens` — viagens GTFS que iniciaram na hora selecionada
- **Seletor de hora:** filtra a alocação por faixa horária (0h–23h) ou pelo
  total diário. Quando uma hora é selecionada, usa o shape dominante entre as
  viagens que *iniciaram* naquela hora.
- **Reconectar GeoPackage:** restaura as camadas GTFS ao projeto sem
  reprocessar o feed (útil após fechar e reabrir o QGIS).

### Construir GTFS

- **Construir GTFS:** permite criar um feed GTFS do zero por meio de um assistente interativo (veja [sig_bus/GUIA_CONSTRUIR_GTFS.md](sig_bus/GUIA_CONSTRUIR_GTFS.md)):
  - **Agência e Rotas:** defina a operadora de transporte e os detalhes da linha.
  - **Paradas Geocodificadas:** busca o endereço da parada por uma cascata de geocodificação — Google (opcional, com chave de API) → Nominatim → Photon → corretor de nomes de rua via Overpass — mostrando um rótulo de status com a procedência (`✓ localizado (Nominatim)`, `✓ localizado (via: <nome real> — OSM)`); os endereços seguem um padrão sugerido (`Logradouro, Número - Bairro`). Um endereço não encontrado nunca bloqueia o fluxo.
  - **Importação em Lote:** carregue paradas via arquivo CSV (veja o guia do modelo em [sig_bus/MODELO_PARADAS_CSV.md](sig_bus/MODELO_PARADAS_CSV.md)).
  - **Marcação no Mapa:** clique diretamente no canvas para posicionar uma parada, para pontos rurais sem endereço geocodificável.
  - **Sequência:** ordene as paradas no trajeto da linha.
  - **Horários:** gere viagens por regra de frequência e depois ajuste-as viagem a viagem (veja *Diagrama de Blocos* abaixo) antes de qualquer gravação.
  - **Revisão e salvar:** a linha é gravada num `feed_edit.gpkg` isolado e segue para o mesmo validador e o mesmo exportador da *Edição GTFS*.
  - **Traçado via OSM:** o traçado (`shapes`) segue a rede viária real do OpenStreetMap entre paradas consecutivas; a linha reta é usada como fallback apenas nos trechos que a malha buscada não cobre ou não conecta.
  - **Barra de progresso dupla:** mostra o quanto falta para um GTFS **mínimo** (arquivos e campos obrigatórios) e, além dele, para um GTFS **completo** (campos opcionais, `shapes`, segundo sentido), nomeando o que ainda falta a cada etapa.

### Editar e exportar GTFS

- **Edição GTFS:** permite editar campos e geometria em uma cópia de trabalho isolada (`feed_edit.gpkg`), com validação integrada e exportação normalizada (veja [sig_bus/GUIA_EDICAO_GTFS.md](sig_bus/GUIA_EDICAO_GTFS.md)).

### Diagrama de Blocos

- **Diagrama de Blocos:** gráfico tempo × faixa da operação, em dois modos — *Modo Viagens* (uma barra por viagem do GTFS) e *Modo Blocos*, em que os blocos de veículo são **inferidos** encadeando viagens, porque o feed da BHTrans não traz `trips.block_id`. Veja [sig_bus/DIAGRAMA_BLOCOS.md](sig_bus/DIAGRAMA_BLOCOS.md).
- **Cota de headway:** ao selecionar uma viagem, o intervalo até a saída seguinte da mesma linha e sentido é desenhado como cota de desenho técnico, rotulada só com a medida (ex.: `12 min`).
- **Régua de saídas:** um traço curto por partida na base do eixo de tempo — ida na banda de cima, volta na de baixo —, de modo que o pico e o vale se leem pela densidade dos traços.
- **Ajuste fino de horários:** com uma viagem selecionada, `>` e `<` deslocam só a saída ou só a chegada, enquanto `+` e `-` deslocam a viagem inteira preservando a duração. No assistente *Construir GTFS* o ajuste acontece em memória, antes de a linha ser gravada, e vale para todos os dias cobertos pelo `calendar` daquele `service_id`.
- **Relatório PDF:** gera um layout de impressão A4 paisagem com o mapa da linha filtrada, legenda, cabeçalho e dois gráficos de barras (ida e volta) dos embarques agrupados por cluster K-means.

## Documentação

| Documento | O que responde |
|---|---|
| [`sig_bus/DOCUMENTACAO.md`](sig_bus/DOCUMENTACAO.md) | O que cada botão faz, campos das camadas de saída e limitações conhecidas (EN + PT-BR) |
| [`sig_bus/METHODS.md`](sig_bus/METHODS.md) | Embasamento teórico do método de alocação de demanda (EN) |
| [`sig_bus/DIAGRAMA_BLOCOS.md`](sig_bus/DIAGRAMA_BLOCOS.md) | Como ler o Diagrama de Blocos, seus dois modos e a inferência de blocos (PT-BR) |
| [`sig_bus/GUIA_CONSTRUIR_GTFS.md`](sig_bus/GUIA_CONSTRUIR_GTFS.md) | Passo a passo do assistente "Construir GTFS" (PT-BR) |
| [`sig_bus/GUIA_EDICAO_GTFS.md`](sig_bus/GUIA_EDICAO_GTFS.md) | Passo a passo da aba "Edição GTFS" e seus erros comuns (PT-BR) |
| [`sig_bus/MODELO_PARADAS_CSV.md`](sig_bus/MODELO_PARADAS_CSV.md) | Formato das colunas do CSV de importação de paradas em lote (PT-BR) |
| [`sig_bus/ARQUITETURA_CONSTRUIR_GTFS.md`](sig_bus/ARQUITETURA_CONSTRUIR_GTFS.md) | Desenho interno da criação de GTFS (PT-BR) |
| [`sig_bus/ARQUITETURA_EDICAO_GTFS.md`](sig_bus/ARQUITETURA_EDICAO_GTFS.md) | Desenho interno da edição de GTFS (PT-BR) |

O histórico versão a versão está no [`CHANGELOG.md`](CHANGELOG.md); a versão
corrente é a declarada em `sig_bus/metadata.txt`.

## Estrutura do Repositório

```
.
├── CHANGELOG.md            # histórico versão a versão
├── docs/
│   ├── gtfsfiles.zip       # GTFS de exemplo para testes
│   └── PyQGIS_PIBIC.pdf    # documentação da pesquisa de origem
└── sig_bus/                # código do plugin (instalar no QGIS)
    ├── __init__.py
    ├── SigBus.py            # classe principal do plugin
    ├── SigBus_dialog.py     # lógica da janela + tarefas de fundo
    ├── SigBus_dialog_base.ui
    ├── gtfs_reader.py       # leitor GTFS embutido
    ├── gtfs_schema.py       # fonte única da verdade da spec GTFS
    ├── gtfs_builder_core.py # constrói um feed do zero (progresso, expansão)
    ├── gtfs_edit_core.py    # cópia de trabalho isolada (feed_edit.gpkg)
    ├── gtfs_validator.py    # integridade referencial e de formato
    ├── gtfs_export.py       # exportação normalizada para .zip
    ├── geocoding.py         # cascata de geocodificação (Google/Nominatim/Photon)
    ├── geocoding_config.py  # modo de provedor e chave de API no QSettings
    ├── street_index.py      # corretor de nomes de rua via Overpass
    ├── address_format.py    # padrão de endereço sugerido
    ├── osm_routing.py       # shapes sobre a rede viária real do OSM
    ├── map_tools.py         # marcação de parada por clique no canvas
    ├── stops_csv.py         # importação de paradas em lote via CSV
    ├── schedule_edit_core.py # ajuste fino de horários em memória
    ├── block_core.py        # modelo do Diagrama de Blocos e inferência
    ├── block_scene.py       # desenho do diagrama (barras, cota, régua)
    ├── block_view.py        # view do diagrama: zoom, pan, atalhos
    ├── block_diagram_dialog.py # janela do Diagrama de Blocos
    ├── test_*.py            # suíte de testes, roda fora do QGIS
    ├── conftest.py          # stubs dos módulos qgis usados pela suíte
    ├── scripts/check_qgis_compat.py # sondagem manual contra o QGIS instalado
    ├── ARQUITETURA_CONSTRUIR_GTFS.md # arquitetura técnica para criação de GTFS (PT-BR)
    ├── ARQUITETURA_EDICAO_GTFS.md # arquitetura técnica para edição de GTFS (PT-BR)
    ├── DIAGRAMA_BLOCOS.md   # documentação do Diagrama de Blocos (PT-BR)
    ├── DOCUMENTACAO.md      # documentação detalhada das funcionalidades (EN + PT-BR)
    ├── GUIA_CONSTRUIR_GTFS.md # guia do usuário para criação de GTFS (PT-BR)
    ├── GUIA_EDICAO_GTFS.md  # guia do usuário para edição de GTFS (PT-BR)
    ├── METHODS.md           # embasamento teórico do método de alocação
    ├── MODELO_PARADAS_CSV.md # documentação do modelo de importação de paradas em CSV
    ├── modelo_paradas.csv   # arquivo modelo de exemplo para importação em lote
    ├── metadata.txt
    ├── icon.png
    └── resources.py / resources.qrc
```

## Requisitos

- QGIS 3.34 LTR até a série 4.x — roda tanto em Qt 5 (QGIS 3.x) quanto em
  Qt 6 (QGIS 4.x) (faixa declarada `3.34` – `4.99`; sondado no 3.34.4,
  testado em 3.44 e 4.2)
- Python embutido do QGIS (sem dependências externas além do QGIS)

## Instalação

1. Copie a pasta `sig_bus/` para o diretório de plugins do QGIS:
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. Ative o plugin **SIG-Bus** em *Complementos → Gerenciar e Instalar
   Complementos → Instalados*.
3. Acesse via *Complementos → SIG-Bus*.

## Configuração da Geocodificação

Configurar uma **chave da API do Google Maps é opcional**. Sem chave nenhuma, a
cascata OSM (Nominatim → Photon → corretor de nomes de rua via Overpass)
continua funcionando igual — não há nada a preparar.

- A chave e o modo de provedor ficam no `QSettings` do QGIS
  (`SIG-Bus/geocoding/google_api_key` e `SIG-Bus/geocoding/provider`, tratados
  por `geocoding_config.py`) — nunca no projeto e nunca no feed.
- Modo de provedor: `auto` tenta o Google primeiro quando há chave configurada e
  cai para a cascata OSM; `osm` ignora qualquer chave e usa só a cascata OSM.
- A chave **nunca** é gravada no `feed_edit.gpkg` (que é compartilhado) nem
  chega ao log do QGIS — toda URL registrada é redigida para `key=***`.

## Fluxo de Uso

O plugin possui três caminhos principais de entrada. Os caminhos (b) e (c) terminam no **mesmo** validador e no mesmo exportador.

### a) Analisar um feed existente

```
Verificar GTFS → Executar GTFS → Inserir demanda
→ Selecionar linha → Filtrar dados
→ Escolher hora → Alocar Demanda
```

Veja `sig_bus/DOCUMENTACAO.md` para descrição detalhada de cada etapa,
campos das camadas de saída e limitações conhecidas. Para o embasamento
teórico do método de alocação de demanda, veja `sig_bus/METHODS.md`.

### b) Construir um GTFS do zero

```
Construir GTFS → Assistente por linha → Exportar .zip
```

Veja [`sig_bus/GUIA_CONSTRUIR_GTFS.md`](sig_bus/GUIA_CONSTRUIR_GTFS.md) para o guia do usuário.

### c) Editar um feed carregado

```
Edição GTFS → Editar dados → Validar → Exportar .zip
```

Veja [`sig_bus/GUIA_EDICAO_GTFS.md`](sig_bus/GUIA_EDICAO_GTFS.md) para o guia do usuário.

## Dados de Exemplo

`docs/gtfsfiles.zip` contém um feed GTFS para testes.
Os dados de demanda esperados seguem o formato do SIU-BHTrans
(CSV separado por `;`, colunas `0`–`23` com embarques por hora).

## Testes

A suíte de testes roda inteiramente **fora do QGIS**, sobre stubs dos módulos
`qgis` (`sig_bus/conftest.py`) — não é necessária instalação do QGIS. A partir
da raiz do repositório:

```
python3 -m pytest sig_bus -q
```

Além dos testes de unidade, a suíte carrega guardas de regressão:
`test_qt6_compat.py` (enum não qualificado, que quebra o QGIS 4),
`test_metadata.py` (faixa de versão declarada e CHANGELOG fechado, casando com
o `metadata.txt`) e `test_readme.py` (links relativos deste arquivo e simetria
entre as duas metades). O `sig_bus/scripts/check_qgis_compat.py` é sondagem
manual contra um QGIS instalado e não roda no pytest.

## Ritual de Release

Para empacotar e publicar uma nova versão do plugin SIG-Bus:

1. **Atualizar versão:** Edite `sig_bus/metadata.txt` para incrementar `version=X.Y` (mantendo `qgisMinimumVersion=3.34`, `qgisMaximumVersion=4.99` e `supportsQt6=True` — sem o máximo, o QGIS assume `3.99` e recusa todo QGIS 4.x).
2. **Atualizar Changelog:** Registre as novidades em `CHANGELOG.md` sob o cabeçalho da nova versão.
3. **Executar Testes:** Rode `pytest` no repositório para garantir que todos os testes e guardas passem.
4. **Sondar o QGIS instalado:** Rode `python3 sig_bus/scripts/check_qgis_compat.py` contra o QGIS alvo — ele importa cada módulo, constrói um `QgsField`, confere o inventário de enums qualificados e carrega o `.ui`, imprimindo `OK`/`FAIL` item a item.
5. **Empacotar o Plugin:** Gere o arquivo `.zip` para distribuição usando `qgis-plugin-ci` ou `make package`:
   - Via `qgis-plugin-ci`: `qgis-plugin-ci package <versao>`
   - Via `make`: `cd sig_bus && make package VERSION=v<versao>`
6. **Publicar e Taggear:** Crie e envie a tag Git (ex.: `git tag -a v0.5 -m "Release 0.5" && git push origin v0.5`) e faça o upload do `.zip` gerado para o repositório de plugins do QGIS ou GitHub Releases.

## Autor

Diego Camargo — <diegocamargo.bft@gmail.com>  
Repositório: <https://github.com/d-camargo/sig-bus>
