# SIG-Bus — Plugin QGIS para Análise de Transporte Público

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
    ├── DOCUMENTACAO.md      # documentação detalhada das funcionalidades
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
campos das camadas de saída e limitações conhecidas.

## Dados de Exemplo

`docs/gtfsfiles.zip` contém um feed GTFS para testes.
Os dados de demanda esperados seguem o formato do SIU-BHTrans
(CSV separado por `;`, colunas `0`–`23` com embarques por hora).

## Autor

Diego Camargo — <diegocamargo.bft@gmail.com>  
Repositório: <https://github.com/d-camargo/sig-bus>
