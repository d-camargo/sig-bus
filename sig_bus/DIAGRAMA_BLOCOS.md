# Diagrama de Blocos — Documentação técnica

Funcionalidade do plugin **SIG-Bus** que visualiza, de forma interativa, a
distribuição temporal das viagens de uma ou mais linhas e a **alocação de frota**
(blocos) inferida a partir do GTFS.

- **Autor:** Diego Camargo · **Versão da feature:** 1 (Modo Viagens + Modo Blocos)
- **Entrada na UI:** diálogo do SIG-Bus → botão **“Diagrama de Blocos”**
- **Documentos de projeto:** `PLANEJAMENTO_DIAGRAMA.md` e `ARQUITETURA_DIAGRAMA.md`
  (na raiz do repositório de trabalho)

---

## 1. Motivação (aspecto de transportes)

O planejamento operacional de transporte público trabalha com três objetos encadeados:

- **Viagem (*trip*)** — uma realização orientada de uma linha, de um terminal a outro,
  com horários de partida/chegada em cada parada.
- **Bloco (*block*)** — a sequência de viagens executadas por **um mesmo veículo** ao
  longo do dia, da saída à recolha na garagem. É o que dimensiona a **frota**.
- **Headway** — o intervalo entre partidas sucessivas de uma mesma linha/sentido; é a
  frequência que o passageiro efetivamente sente no ponto.

Um diagrama de blocos (também *Marey chart* / gráfico tempo–veículo) expõe esses três
de uma vez: no eixo X o tempo do dia; no eixo Y as viagens organizadas por
linha/sentido (Modo Viagens) ou por veículo (Modo Blocos). Permite ler **picos,
ociosidade, encadeamento e tamanho de frota** — dados que um mapa geográfico não mostra.

### 1.1 A restrição central: o feed **não tem `block_id`**

No GTFS, o campo que diz qual veículo opera quais viagens é `trips.block_id`. O feed da
BHTrans usado no projeto **não traz esse campo** (`trips.txt` =
`route_id, service_id, trip_id, trip_headsign, direction_id, shape_id`).

Consequência de projeto: **não há blocos para ler — eles são inferidos**. Isso define
os dois modos da ferramenta:

| Modo | O que mostra | Natureza |
|------|--------------|----------|
| **Viagens** | Faixa por (linha, sentido); uma barra por viagem | Determinístico (lê o GTFS) |
| **Blocos** | Faixa por veículo inferido; gaps de ociosidade | **Estimado** (heurística) |

O Modo Blocos é rotulado *“estimado”* na UI: é uma reconstrução plausível da escala,
não a programação oficial da operadora.

---

## 2. Conceitos de transporte usados no código

| Conceito | Campo GTFS / derivação | Onde aparece |
|----------|------------------------|--------------|
| Linha | `routes.route_short_name` (ex.: `101`) | chave de seleção e join |
| Sentido | `trips.direction_id` (`0`=ida, `1`=volta) | faixa / espessura da barra |
| Tipo de dia | `trips.service_id` | filtro; agrupa a inferência |
| Início da viagem | `MIN(stop_sequence)` → `departure_time` | barra (X inicial) |
| Fim da viagem | `MAX(stop_sequence)` → `arrival_time` | barra (X final) |
| Terminais | `stop_id` da 1ª/última parada | casamento no encadeamento |
| Layover | gap entre fim de uma viagem e início da próxima | parâmetro do bloco |
| Deadhead | reposicionamento sem passageiros (terminais diferentes) | parâmetro do bloco |
| Headway | `start(viagem) − start(viagem anterior da mesma linha+sentido)` | indicador na seleção |

> **Horários ≥ 24h:** o GTFS representa serviço pós-meia-noite como `25:30:00`. Todo o
> código converte horário em **segundos desde 00:00** (`parse_gtfs_time`), nunca tratando
> como relógio — ordenar/encadear por string quebraria a virada do dia.

---

## 3. Arquitetura (aspecto de código)

Separação em três camadas, padrão **MVC** — o que torna a futura edição (arrastar
viagens entre veículos) uma extensão, não uma reescrita.

```
Interface (Controller)   block_diagram_dialog.py   → orquestra; UI em Python puro
        │ params                         ▲ render(Schedule)
        ▼                                │
Core (Model)             block_core.py   → leitura, modelo, inferência (QgsTask)
        │ lê                              │
        ▼                                │
   feed.gpkg (SQLite)        Engine (View) block_scene.py + block_view.py
                                          → QGraphicsScene de itens clicáveis
```

### 3.1 Arquivos

| Arquivo | Camada | Responsabilidade |
|---------|--------|------------------|
| `block_core.py` | Core | `Trip`/`Block`/`BlockParams`/`Schedule`, `ScheduleReader`, `BlockBuilder`, `BlockDiagramTask` |
| `block_scene.py` | Engine | `BlockScene`, `TripItem`, layout, cores, headway |
| `block_view.py` | Engine | `BlockView`: zoom, pan, export PNG/SVG |
| `block_diagram_dialog.py` | Interface | janela, controles, painel de detalhes |
| `SigBus_dialog.py` | Integração | botão “Diagrama de Blocos” + `diagramaClicked()` |

### 3.2 Por que `QGraphicsView`/`QGraphicsScene`

- Interação nativa: **clique, hover, seleção, zoom e pan** (e *drag* para a edição futura).
- **Zero dependências** — Qt está sempre no QGIS; **matplotlib não está disponível**
  nesta instalação (o relatório do plugin já usa `QPainter` pelo mesmo motivo).
- Exporta para PNG (`QImage`) e SVG (`QSvgGenerator`) com o mesmo código.

---

## 4. Camada de dados (`block_core.py`)

### 4.1 Modelo

- `Trip` — viagem atômica: `trip_id, route_short_name, direction_id, service_id,
  shape_id, start_time_s, end_time_s, start_stop_id, end_stop_id, n_stops, block_id`.
- `Block` — `block_id` + lista de `Trip`; propriedades `span` e `idle_seconds`.
- `Schedule` — objeto que a Engine renderiza: `trips`, `blocks`, `fleet_size`, `mode`,
  `warnings`; `time_bounds` calcula os limites do eixo X com folga.

### 4.2 Leitura (`ScheduleReader`)

Lê via `sqlite3` direto no GeoPackage (mesmo padrão de `_AlocacaoTask`). Pontos críticos:

- **`stop_times.txt` tem ~136 MB** → a leitura é restrita às linhas selecionadas
  (`route_id IN (...)`) e usa os índices `idx_st_trip` criados por
  `create_join_indexes()`. **Nunca** varre a tabela inteira nem itera feição-a-feição.
- A primeira/última parada de cada viagem é obtida pela **ordem canônica**
  (`stop_sequence`), não pelo horário — robusto a dados fora de ordem.
- `route_short_name → route_id` pode ser **1→N** (a mesma linha tem vários `route_id`);
  o `IN (...)` cobre todos.

### 4.3 Inferência de blocos (`BlockBuilder`)

Heurística gulosa de **frota mínima** (problema de cobertura de viagens por veículos):

```
para cada viagem (em ordem de início):
    candidatos = veículos livres v tais que
        gap = trip.start − v.free
        gap ≥ layover_mín
        E (relaxado OU gap ≤ layover_máx)
        E (deadhead/relaxado OU v.local == trip.terminal_origem)
    se há candidatos: escolhe o de MAIOR v.free  (menos ocioso)
    senão: abre um veículo novo
    atualiza v: local = trip.terminal_destino, free = trip.fim
nº de veículos = nº de blocos
```

Características de transporte embutidas:

- **Encadeamento por `service_id`** — não mistura dia útil com domingo (assinaturas de
  frota distintas).
- **Cruza linhas** — um veículo pode passar da linha 101 para a 102 se o terminal casar
  (frota compartilhada); é o ganho do modo multi-linha.
- **Parâmetros** (`BlockParams`): `layover_min_s` (5 min), `layover_max_s` (45 min),
  `allow_deadhead` (encadeia terminais diferentes), `relaxed` (ignora o teto de layover →
  **frota mínima teórica**, limite inferior).

A frota = `len(blocks)`. Com vários serviços selecionados, a contagem é **somada por
serviço** e um aviso recomenda escolher um único serviço para o número real.

### 4.4 Concorrência (`BlockDiagramTask`)

Subclasse de `QgsTask` (padrão `_GtfsLoadTask`/`_AlocacaoTask`): I/O pesado em `run()`
(thread de fundo), entrega do `Schedule` em `finished()` (thread da GUI) via sinais
`finishedOk`/`failed`. A GUI nunca congela.

---

## 5. Engine gráfica (`block_scene.py`, `block_view.py`)

### 5.1 Mapeamento e layout

- `TimeAxisMapper` converte tempo↔X e índice de faixa→Y.
- **Empacotamento em sub-linhas** (`_assign_rows`): dentro de uma faixa, viagens que se
  sobrepõem no tempo vão para sub-linhas distintas (greedy interval packing). Sem isso,
  viagens simultâneas ficariam “encavaladas” e não clicáveis. No Modo Viagens, o nº de
  sub-linhas no pico de uma faixa ≈ **viagens simultâneas** daquele sentido.

### 5.2 Codificação visual

| Atributo visual | Modo Viagens | Modo Blocos |
|-----------------|--------------|-------------|
| Faixa (eixo Y) | (linha, sentido) — `101 ▸ ida` | veículo — `V1 · 101` |
| **Cor** da barra | por **linha** | por **veículo** (matizes pelo ângulo áureo) |
| **Espessura** | ida cheia, volta fina | idem |
| Conectores pontilhados | — | **ociosidade** entre viagens do veículo |

A cor por veículo usa rotação de matiz de 137,5° (`QColor.fromHsv`) para manter cores
bem distintas mesmo com dezenas de veículos.

### 5.3 Indicador de headway (seleção)

Ao clicar numa viagem no **Modo Blocos**, desenha-se uma **pontilhada** ligando o início
da **viagem anterior da mesma linha+sentido** ao início da viagem selecionada, com
marcadores nos dois pontos e o rótulo `headway N min`. A viagem anterior é pré-computada
em `_prev_trip` (agrupando por `(linha, sentido)` e ordenando por início). Como essa
anterior costuma ser de **outro veículo**, a linha cruza faixas — exibindo visualmente o
intervalo entre partidas. A primeira viagem de cada linha/sentido não tem headway.

### 5.4 Interação (`block_view.py`)

- **Roda do mouse** → zoom (âncora sob o cursor); **botão do meio** → pan.
- `fit_all()` enquadra a cena inteira ao gerar — essencial porque uma faixa de ida muito
  alta (linha movimentada) escondia a faixa de volta abaixo da tela.
- Export **PNG** (`QImage`, 2×) e **SVG** (`QSvgGenerator`, se `QtSvg` presente).

---

## 6. Interface (`block_diagram_dialog.py`)

`QWidget` (janela) montado em Python — sem `.ui`. Layout em `QSplitter`:
**controles | diagrama | detalhes**.

- **Controles:** lista multi-seleção de linhas; serviço (dia); sentido (ida/volta);
  janela de tempo em horas (0–30 h, via `QSpinBox` — `QTimeEdit` não passa de 23:59 e o
  GTFS tem serviço pós-meia-noite); **rádios Viagens/Blocos**; parâmetros de bloco
  (layover mín/máx, deadhead, relaxado) visíveis só no Modo Blocos.
- **Diagrama:** a `BlockView`/`BlockScene`.
- **Detalhes:** ao clicar numa viagem, mostra linha, sentido, **bloco/veículo**,
  início/fim/duração, nº de paradas, terminais, headsign e IDs.
- **Status:** nº de viagens e faixas (Viagens) ou **nº de veículos** (Blocos), além de
  avisos.

### 6.1 Integração com o plugin

O botão é adicionado por código ao `QGridLayout` do diálogo principal (sem editar o
`.ui`). `diagramaClicked()` resolve o GeoPackage via `_resolve_gpkg()`, abre a janela
**parenteada à janela principal do QGIS** (para sobreviver ao fechamento do SIG-Bus) e
**fecha o diálogo do SIG-Bus**. O import dos módulos do diagrama é tardio: um problema
neles não impede o resto do plugin de carregar.

---

## 7. Fluxo de uso

1. Carregar o GTFS no plugin (gera o `feed.gpkg`) — ou “Reconectar GeoPackage”.
2. SIG-Bus → **Diagrama de Blocos** (o SIG-Bus fecha).
3. Selecionar a(s) linha(s); opcionalmente serviço, sentido e janela.
4. Escolher **Viagens** ou **Blocos** (neste, ajustar layover/deadhead/relaxado).
5. **Gerar diagrama.** Clicar nas barras para detalhes; no Modo Blocos, clicar mostra o
   headway. Roda = zoom; botão do meio = pan; **Exportar** = PNG/SVG.

> Para o nº de frota ser real, selecione **um único serviço** — com “Todos os serviços”
> a contagem é somada entre dias e há aviso.

---

## 8. Limitações e cuidados

- **Modo Blocos é estimativa** (sem `block_id`); sensível aos parâmetros de layover e ao
  casamento de terminais. Em feeds onde os terminais não casam exatamente, usar
  *deadhead* ou *relaxado*.
- **Deadhead simplificado** — não calcula tempo real de reposicionamento entre terminais.
- **GTFS estático** — reflete o *plano* da agência, não a operação real (atrasos,
  supressões). Integração com GTFS-Realtime fica como horizonte futuro.
- **Headway** aqui é o intervalo programado entre partidas da mesma linha/sentido; não
  considera paradas compartilhadas por várias linhas.

---

## 9. Testes

A camada de dados e o algoritmo (puro Python/SQLite) foram validados fora do QGIS com
*stubs* dos módulos `qgis`:

- `ScheduleReader`/`parse_gtfs_time`: 16 verificações (multi-linha, primeira/última
  parada por sequência, horas ≥ 24 h, filtros de sentido/janela/serviço).
- `BlockBuilder`: 12 verificações (casamento de terminal, deadhead, layover mín/máx,
  relaxado, frota = pico de simultâneas, separação por serviço, encadeamento entre
  linhas, ociosidade).
- Lógica de headway (`_prev_trip`): anterior correta por linha+sentido, sem headway na
  primeira viagem.

A camada Qt/GUI (cena, view, diálogo) é validada manualmente dentro do QGIS.
