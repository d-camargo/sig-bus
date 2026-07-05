# SIG-Bus — QGIS Plugin for Public Transport Analysis

*[Português](#sig-bus--plugin-qgis-para-análise-de-transporte-público) | English*

A QGIS plugin that integrates **GTFS** (*General Transit Feed Specification*) data
with **passenger boarding demand** data per bus stop, enabling visualisation and
allocation of passenger loads along route alignments.

Developed as part of the undergraduate research project PIBIC DPPG 113/2021.

## Features

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
- **Edit GTFS:** allows editing GTFS fields and geometry in an isolated working copy (`feed_edit.gpkg`), with built-in validation and normalized export (see [sig_bus/GUIA_EDICAO_GTFS.md](sig_bus/GUIA_EDICAO_GTFS.md)).

The GTFS reader is **built-in** (`gtfs_reader.py`), adapted from the *GTFS Loader*
plugin by CTU GeoForAll Lab (GPL v2+). No external plugin is required.

## Repository Structure

```
.
├── docs/
│   ├── gtfsfiles.zip       # sample GTFS feed for testing
│   └── PyQGIS_PIBIC.pdf    # original research documentation
└── sig_bus/                # plugin code (install into QGIS)
    ├── __init__.py
    ├── SigBus.py            # plugin main class
    ├── SigBus_dialog.py     # dialog logic + background tasks
    ├── SigBus_dialog_base.ui
    ├── gtfs_reader.py       # built-in GTFS reader
    ├── DOCUMENTACAO.md      # detailed feature documentation (EN + PT-BR)
    ├── GUIA_EDICAO_GTFS.md  # user guide for GTFS editing (PT-BR)
    ├── METHODS.md           # theoretical foundation of the allocation method
    ├── metadata.txt
    ├── icon.png
    └── resources.py / resources.qrc
```

## Requirements

- QGIS 3.0 or later (tested on 3.22 LTS and recent Flatpak builds)
- QGIS built-in Python (no external dependencies beyond QGIS itself)

## Installation

1. Copy the `sig_bus/` folder to the QGIS plugins directory:
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. Enable the **SIG-Bus** plugin under *Plugins → Manage and Install Plugins →
   Installed*.
3. Access it via *Plugins → SIG-Bus*.

## Workflow

```
Check GTFS → Load GTFS → Insert demand
→ Select route → Filter data
→ Choose hour → Allocate Demand
```

See `sig_bus/DOCUMENTACAO.md` for a detailed description of each step, output
layer fields, and known limitations. For the theoretical background of the
demand allocation method, see `sig_bus/METHODS.md`.

## Sample Data

`docs/gtfsfiles.zip` contains a GTFS feed for testing.
Expected demand data follows the SIU-BHTrans format
(`;`-delimited CSV, columns `0`–`23` with hourly boardings).

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
- **Edição GTFS:** permite editar campos e geometria em uma cópia de trabalho isolada (`feed_edit.gpkg`), com validação integrada e exportação normalizada (veja [sig_bus/GUIA_EDICAO_GTFS.md](sig_bus/GUIA_EDICAO_GTFS.md)).

O leitor de GTFS é **embutido** (`gtfs_reader.py`), adaptado do plugin
*GTFS Loader* do CTU GeoForAll Lab (GPL v2+). Nenhum plugin externo é
necessário.

## Estrutura do Repositório

```
.
├── docs/
│   ├── gtfsfiles.zip       # GTFS de exemplo para testes
│   └── PyQGIS_PIBIC.pdf    # documentação da pesquisa de origem
└── sig_bus/                # código do plugin (instalar no QGIS)
    ├── __init__.py
    ├── SigBus.py            # classe principal do plugin
    ├── SigBus_dialog.py     # lógica da janela + tarefas de fundo
    ├── SigBus_dialog_base.ui
    ├── gtfs_reader.py       # leitor GTFS embutido
    ├── DOCUMENTACAO.md      # documentação detalhada das funcionalidades (EN + PT-BR)
    ├── GUIA_EDICAO_GTFS.md  # guia do usuário para edição de GTFS (PT-BR)
    ├── METHODS.md           # embasamento teórico do método de alocação
    ├── metadata.txt
    ├── icon.png
    └── resources.py / resources.qrc
```

## Requisitos

- QGIS 3.0 ou superior (testado em 3.22 LTS e Flatpak recente)
- Python embutido do QGIS (sem dependências externas além do QGIS)

## Instalação

1. Copie a pasta `sig_bus/` para o diretório de plugins do QGIS:
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. Ative o plugin **SIG-Bus** em *Complementos → Gerenciar e Instalar
   Complementos → Instalados*.
3. Acesse via *Complementos → SIG-Bus*.

## Fluxo de Uso

```
Verificar GTFS → Executar GTFS → Inserir demanda
→ Selecionar linha → Filtrar dados
→ Escolher hora → Alocar Demanda
```

Veja `sig_bus/DOCUMENTACAO.md` para descrição detalhada de cada etapa,
campos das camadas de saída e limitações conhecidas. Para o embasamento
teórico do método de alocação de demanda, veja `sig_bus/METHODS.md`.

## Dados de Exemplo

`docs/gtfsfiles.zip` contém um feed GTFS para testes.
Os dados de demanda esperados seguem o formato do SIU-BHTrans
(CSV separado por `;`, colunas `0`–`23` com embarques por hora).

## Autor

Diego Camargo — <diegocamargo.bft@gmail.com>  
Repositório: <https://github.com/d-camargo/sig-bus>
