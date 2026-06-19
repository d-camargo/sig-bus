# Histórico de versões — SIG-Bus

Plugin QGIS de análise de transporte público (PIBIC DPPG 113/2021). Este arquivo
detalha, por versão, **o que foi feito e por quê** — tanto do ponto de vista de
**transporte público** quanto de **código**. Serve de base para os posts do blog
do projeto.

O plugin carrega um feed **GTFS** num **GeoPackage**, importa **dados de demanda**
(CSV), aloca embarques nos tramos das linhas, gera **relatórios em PDF** e desenha
o **Diagrama de Blocos** (alocação de frota). Feed de referência nos testes: o da
**BHTrans** (Belo Horizonte).

---

## v0.4 — Refino do Diagrama de Blocos e reorganização da interface

Versão focada em **legibilidade** do diagrama e em **fidelidade do modelo de frota**.

### Interface em abas

A janela principal do plugin foi reorganizada em **duas abas**, seguindo o fluxo
de trabalho:

- **Entrada de dados** — carregar o GTFS (.zip), carregar a demanda (.csv) e
  *Reconectar GeoPackage* (que é, por definição, uma operação de fonte de dados).
- **Análise** — escolher a linha, *Filtrar dados*, *Alocar Demanda*, *Gerar
  Relatório* e *Diagrama de Blocos*.

A barra de *Ajuda* + *OK/Cancelar* ficou comum às duas abas. O botão do diagrama,
antes criado em tempo de execução por código, passou a viver no próprio `.ui`.

### Eixo de tempo mais legível

No diagrama, o eixo de tempo ganhou:

- **Linhas tracejadas nas meias-horas** (12:30, 13:30…), subordinadas visualmente
  às linhas cheias das horas — ajudam a situar viagens no meio da hora.
- **Rótulos de hora em cima e embaixo**, para referência nas duas pontas do
  diagrama (útil quando ele fica alto, com muitas faixas).

### Terminais: nome e sigla

O feed da BHTrans **não tem código/sigla de terminal**, mas o `trip_headsign`
(destino da viagem) está sempre preenchido (184 destinos distintos). A partir dele:

- O **tooltip** e o **painel de detalhes** mostram o terminal de destino legível
  (ex.: `ESTACAO DIAMANTE`).
- Cada terminal recebe uma **sigla de 3 letras** gerada por convenção própria
  (`DIAMANTE → DIA`, `SAO GABRIEL → SAG`), **única dentro do diagrama** (colisões
  resolvidas automaticamente, ex.: `BARREIRO`=BAR vs `MOVE BARREIRO`=BRR). A sigla
  é impressa **dentro da barra** da viagem (elidida e recortada à barra), servindo
  de rótulo compacto; o nome completo aparece no tooltip/detalhes como legenda.

### Sentido por hachura (não mais por espessura)

Antes, a viagem de **volta** era desenhada mais fina que a de **ida** — o que a
deixava sem espaço para a sigla. Agora **ambos os sentidos têm altura cheia** e o
sentido é diferenciado por uma **hachura diagonal** na volta (mesma cor da linha).
Assim a sigla cabe nos dois sentidos e a leitura visual fica mais clara.

### Deadhead estimado pela distância entre terminais (correção de modelo)

A maior correção da versão. No **Modo Blocos**, a opção *Permitir deadhead* deixa um
veículo encadear viagens que **começam em terminais diferentes** do que ele terminou.
Antes, esse encadeamento **não cobrava tempo de deslocamento** — o veículo "se
teletransportava" e a frota estimada saía **menor que a real**.

Aproveitando que estamos num **SIG**, o tempo de retorno passou a ser estimado pela
**geometria dos terminais**:

```
dist_reta     = haversine(terminal_B, terminal_A)   # coordenadas da camada stops
tempo_retorno = (dist_reta × fator_sinuosidade) / velocidade_do_veículo_vazio
```

E o modelo do intervalo entre viagens virou fisicamente correto:

```
gap = deadhead (viagem vazia B→A)  +  layover (tempo ocioso no terminal)
encadeia se:  layover_mín ≤ (gap − deadhead) ≤ layover_máx
```

— ou seja, **o tempo de viagem não é mais confundido com ociosidade**. Dois novos
parâmetros na interface (visíveis com *Permitir deadhead*): **velocidade do veículo
vazio** (padrão 25 km/h) e **fator de sinuosidade**/impedância reta→trajeto (padrão
1,4). Quando um terminal não tem coordenada, o deadhead é considerado instantâneo e
um aviso é emitido.

> **Limitação assumida:** a distância é em **reta geodésica** (não há rede de ruas
> carregada no plugin); o fator de sinuosidade aproxima o trajeto real. Distância de
> rede fica para a F2.

### Achados sobre o feed (verificados no dado)

- **2 em cada 3 linhas só têm ida**: 206 de 308 linhas têm apenas `direction_id=0`
  (são **alimentadoras** — levam à estação, o retorno é outra linha/integração). As
  102 bidirecionais são principalmente as **troncais/diametrais** (séries 1xxx/2xxx).
  Um diagrama "sem volta" geralmente é o **dado**, não bug — o leitor agora **avisa**
  quando o sentido pedido não existe nas linhas selecionadas.
- **Não há campo de "tipo de linha"** no feed: `route_type=3` (ônibus) para todas as
  678 rotas. Alimentadora/troncal só dá para **inferir** (nº de dígitos da linha +
  disponibilidade de sentido).

### Arquivos tocados

`block_core.py`, `block_scene.py`, `block_diagram_dialog.py`, `SigBus_dialog.py`,
`SigBus_dialog_base.ui`, `metadata.txt`.

---

## v0.3 — Diagrama de Blocos (Gráfico de Alocação de Frota)

Introduz a feature do **Diagrama de Blocos**: um gráfico **tempo × faixa** em que
cada barra é uma viagem, clicável, com zoom/pan, construído sobre `QGraphicsView`
(porque o matplotlib está indisponível nesta instalação do QGIS).

### Conceito de transporte

Um *bloco* é a sequência de viagens atribuída a um mesmo **veículo** ao longo do dia.
Como o GTFS da BHTrans **não traz `block_id`**, a alocação de frota precisa ser
**inferida**. A feature oferece dois modos:

- **Modo Viagens** (determinístico): uma faixa por **(linha, sentido)**; viagens que
  se sobrepõem no tempo são empilhadas em sub-linhas (*interval packing* guloso) para
  não ficarem "encavaladas".
- **Modo Blocos** (inferência): encadeia viagens num mesmo veículo por heurística
  gulosa de **frota mínima**, respeitando *layover* (tempo de parada entre viagens) e
  casamento de terminais, podendo cruzar linhas (frota compartilhada). Cor por
  veículo; um indicador de **headway** (intervalo) aparece pontilhado na viagem
  selecionada.

### Arquitetura (MVC, 3 camadas)

- **Model** — `block_core.py`: `Trip`/`Block`/`Schedule`, `ScheduleReader` (leitura do
  GeoPackage via `sqlite3`, sem varrer `stop_times` inteiro), `BlockBuilder`
  (inferência) e `BlockDiagramTask` (`QgsTask` de fundo).
- **View** — `block_scene.py` (`QGraphicsScene`: barras, eixo, rótulos) e
  `block_view.py` (`QGraphicsView`: zoom/pan, exportar PNG/SVG).
- **Controller** — `block_diagram_dialog.py`: janela própria com os controles
  (seleção de linhas, dia/serviço, sentido, janela de tempo, parâmetros de bloco).

Detalhes técnicos em `DIAGRAMA_BLOCOS.md`.

### Notas de robustez

- Horários GTFS podem passar de **24h** (`25:30:00`): são tratados como **segundos**
  desde a meia-noite, não como relógio (encadear por string quebraria o pós-meia-noite).
- Toda a lógica de Model/inferência foi validada **fora do QGIS** (stubs + SQLite
  sintético); a camada Qt é testada visualmente dentro do QGIS.

---

## v0.2 — Base: GTFS → GeoPackage, demanda e relatório PDF

Reestruturação do projeto (de `tpu/` para `sig_bus/`) e consolidação do núcleo de
análise de demanda.

### Carga de dados

- **GTFS embutido**: `gtfs_reader.py` grava cada `.txt` do feed como tabela de um
  **GeoPackage** via **GDAL `VectorTranslate`** em streaming (necessário porque
  `stop_times.txt` tem ~136 MB). `stops`/`shapes` viram camadas de pontos; as linhas
  (`shapes`) são montadas a partir de `shapes_point`. Sem depender do plugin externo
  *GTFS Loader*.
- **`calendar.txt` atípico**: o feed traz colunas de `calendar_dates`; o plugin
  sintetiza um `calendar.txt` semanal a partir delas ("Verificar GTFS").
- **Demanda (CSV)**: EPSG:31983, encoding windows-1252, separador `;`, campos X/Y.

### Análise

- **Ligação demanda ↔ GTFS por `route_short_name`** (ex.: `101`), **não** por
  `shape_id` (o shape da BHTrans é numérico/sem semântica). Sentido por `PC`:
  `PC=1 → ida`, `PC=2 → volta`.
- **Alocação**: por sentido, usa o **shape dominante**, projeta os embarques na parada
  mais próxima e gera a camada `tramos_demanda` com `passageiros_acum` (carga
  acumulada ao longo da linha).
- **Relatório PDF**: `QgsPrintLayout` A4 paisagem, uma página por sentido, com **dois
  mapas** (carregamento graduado × clusters K-means) e gráfico de barras desenhado com
  `QPainter` (sem matplotlib).

### Padrões de engenharia firmados nesta base

- I/O pesado em `QgsTask` (trabalho na thread de fundo; mexer em `QgsProject` só na
  thread da GUI).
- Leitura de tabelas grandes via `sqlite3` com SQL agregado + índices; **nunca** iterar
  feição-a-feição em `stop_times`.
- Nada de `UPDATE` sqlite cru em tabela com geometria (quebra o `ST_IsEmpty` do
  GeoPackage); usar a API QGIS/OGR.
- Docstrings em PT-BR, cabeçalho GPL nos arquivos.

---

## Antes da v0.2 (arquivo morto)

Protótipos e scripts standalone (incluindo `Pandas_Demanda.py` e a pasta `tpu/`) estão
arquivados em `antigo/pyqgis_113-2021/` e **não** são a base de trabalho atual.
