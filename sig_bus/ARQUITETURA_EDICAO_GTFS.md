# Arquitetura — Edição de GTFS (PyQGIS)

**Projeto:** SIG-Bus (plugin QGIS) · **Data:** 2026-06-19
**Branch:** `feature/editar-gtfs`
**Documento irmão (referência de estilo):** [ARQUITETURA_DIAGRAMA.md](../../ARQUITETURA_DIAGRAMA.md)

Funcionalidade nova: **editar parâmetros de um GTFS já carregado e exportar uma nova
versão em `.zip`**, pronta para qualquer plataforma (Google Maps, validadores, etc.).
Segue o mesmo padrão **MVC em camadas** do Diagrama de Blocos, para ser uma extensão
do plugin e não uma ilha.

---

## 1. Decisões de projeto (tomadas em 2026-06-19)

Estas escolhas guiam toda a arquitetura abaixo:

1. **Motor de edição: híbrido.** O plugin *guia* (combobox + filtro), *protege* os
   campos de chave (IDs/FKs) e *valida*; a edição em si acontece na **tabela de
   atributos nativa do QGIS** (ganhamos buffer de edição, undo/redo, busca e
   calculadora de campos de graça) e, para o espacial, na **edição de vértices do
   canvas**.
2. **Onde editar: cópia de trabalho.** As edições acontecem num `feed_edit.gpkg`,
   cópia do `feed.gpkg` da análise. Uma edição pela metade nunca corrompe a análise,
   e dá para descartar tudo.
3. **Integridade: proteger chaves + validar na exportação.** Campos de ID ficam
   *read-only*; a checagem de integridade referencial e de formato roda no momento de
   gerar o `.zip`.
4. **Exportação: normalizar tudo.** A saída é GTFS o mais aderente possível à spec
   (ordem canônica de colunas, `calendar.txt`/`calendar_dates.txt` corretos, remoção
   de campos não-padrão). Isso conserta a esquisitice do feed da BHTrans (cujo
   `calendar.txt` vem em formato de `calendar_dates`).
5. **`stop_times`: só subconjunto filtrado.** Nunca carregar a tabela inteira
   (~136 MB / milhões de linhas) na GUI — edita-se por linha/viagem via filtro. A
   exportação reemite a tabela toda via *streaming*.

---

## 2. Visão geral (MVC em três camadas)

```
┌─────────────────────────────────────────────────────────────────────┐
│  INTERFACE (Controller)        gtfs_edit_dialog.py + aba na .ui       │
│  - combobox Tabela / combobox Campo-filtro                           │
│  - botões: Entrar no modo edição · Abrir p/ edição · Editar no mapa  │
│            Validar · Descartar · Exportar .zip                       │
│  - trava campos protegidos (editFormConfig.setReadOnly)             │
│  - abre tabela de atributos nativa / ativa edição de vértices       │
└───────────────┬───────────────────────────────────┬──────────────────┘
                │ parâmetros                         │ usa
                ▼                                    ▼
┌──────────────────────────────┐      ┌──────────────────────────────────┐
│  CORE (Model)                │      │  SPEC GTFS                        │
│  gtfs_edit_core.py           │ ───► │  gtfs_schema.py                   │
│  - WorkingCopy (criar/descar)│ usa  │  - colunas canônicas + ordem      │
│  - GtfsValidator (FK+formato)│      │  - obrigatórias/opcionais         │
│  - GtfsExporter (QgsTask)    │      │  - editável vs. protegida (IDs)   │
└───────────────┬──────────────┘      └──────────────────────────────────┘
                │ lê/grava
                ▼
        ┌───────────────┐   cópia de   ┌───────────────┐
        │  feed.gpkg     │ ───────────► │ feed_edit.gpkg │ ──► feed_novo.zip
        │  (análise)     │              │  (edição)      │     (export normaliz.)
        └───────────────┘              └───────────────┘
```

**`gtfs_schema.py` é a fonte única da verdade.** Alimenta ao mesmo tempo: (a) a
whitelist de campos editáveis na UI, (b) a validação, e (c) a ordem das colunas na
exportação normalizada. Mexer na spec num lugar só propaga para os três usos.

---

## 3. SPEC — `gtfs_schema.py`

Camada **sem dependência de Qt nem de PyQGIS** — só dados. Descreve a especificação
GTFS (ver https://gtfs.org/documentation/schedule/reference/) no recorte que o plugin
usa. Estrutura sugerida, por arquivo GTFS:

```python
# Esboço conceitual (não é o código final).
GTFS_FILES = {
    "routes": {
        "required": True,
        "columns": [  # ordem canônica de saída
            Col("route_id",        editable=False, required=True),   # chave
            Col("agency_id",       editable=False, required=False),  # FK
            Col("route_short_name", editable=True,  required=False),
            Col("route_long_name",  editable=True,  required=False),
            Col("route_type",      editable=True,  required=True, enum={0..12}),
            ...
        ],
        "foreign_keys": [("agency_id", "agency", "agency_id")],
    },
    "trips": {... "foreign_keys": [
        ("route_id", "routes", "route_id"),
        ("service_id", "calendar", "service_id"),
        ("shape_id", "shapes", "shape_id"),
    ]},
    "stop_times": {...}, "stops": {...}, "calendar": {...}, "shapes": {...},
    "agency": {...}, "calendar_dates": {...},
}
```

Campos **protegidos** (`editable=False`): toda chave primária e estrangeira
(`*_id`). Editar IDs quebraria a integridade referencial — fora do escopo desta
feature (seria uma operação de "renomear entidade", outra história).

---

## 4. CORE (Model) — `gtfs_edit_core.py`

Camada de lógica de dados + PyQGIS, **sem widgets**. Três responsabilidades:

### 4.1 `WorkingCopy`
- `enter()`: copia `feed.gpkg` → `feed_edit.gpkg` (ao lado, mesmo diretório). Se já
  existir, pergunta retomar/recriar (decisão da UI).
- `discard()`: apaga `feed_edit.gpkg`.
- `is_active()`: existe uma cópia de trabalho?
- Cópia é de arquivo (SQLite é um único arquivo) — barato e atômico.

### 4.2 `GtfsValidator`
Roda **na exportação** (decisão 3). Reporta erros (fatais → bloqueiam) e avisos
(→ apenas alertam), via `iface.messageBar()` + `QgsMessageLog` (`LOG_TAG='SIG-Bus'`).

- **Integridade referencial** (das `foreign_keys` do schema): toda `trip.route_id` ∈
  `routes`; `trip.service_id` ∈ `calendar`/`calendar_dates`; `trip.shape_id` ∈
  `shapes`; `stop_times.trip_id` ∈ `trips`; `stop_times.stop_id` ∈ `stops`.
  Implementação por SQL agregado (`LEFT JOIN ... WHERE x IS NULL`), nunca feição-a-feição.
- **Formato**: horários como segundos podendo passar de 24h (`25:30:00`); datas
  `YYYYMMDD`; lat/lon em faixas válidas; enums (`route_type`, `direction_id`,
  `exception_type`).

### 4.3 `GtfsExporter` (subclasse de `QgsTask`)
Lê do `feed_edit.gpkg` e escreve um `.zip` GTFS **normalizado** (decisão 4).
Trabalho pesado em `run()` (thread de fundo); só sinalização/UI em `finished()`.

- Para cada arquivo do schema: emite as colunas na **ordem canônica**, descartando
  campos não-padrão.
- **`shapes.txt`**: regenerado a partir dos **vértices da camada de linhas** `shapes`
  (cada vértice → uma linha `shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence`,
  sequência recriada). Lossless: cada ponto do `shapes_point` original já vira um
  vértice em `build_shapes_line`.
- **`stops.txt`**: `stop_lon`/`stop_lat` lidos da geometria do ponto.
- **`calendar`**: gera `calendar.txt` semanal (a partir do que `_calendar_from_dates`
  infere) **+** `calendar_dates.txt` para as exceções — conserta o feed da BHTrans.
- **`stop_times.txt`**: escrito via *streaming* (cursor `sqlite3` → `csv.writer`),
  sem carregar a tabela em memória.
- Empacota tudo num `.zip` (`zipfile`, um `.txt` por entrada).

---

## 5. INTERFACE (Controller) — `gtfs_edit_dialog.py` + aba na `.ui`

Nova aba **"Edição GTFS"** no diálogo principal (ou janela própria, a decidir na
implementação). Fluxo:

```
Aba "Edição GTFS"
 ├─ [Entrar no modo edição]  → WorkingCopy.enter(): feed.gpkg → feed_edit.gpkg
 ├─ Combobox "Tabela":  trips ▾            (só as editáveis do schema)
 ├─ Combobox "Campo/filtro": trip_headsign ▾
 ├─ [Abrir para edição] → carrega a camada do feed_edit.gpkg em modo de
 │                         edição na TABELA DE ATRIBUTOS NATIVA; IDs travados
 │                         via editFormConfig.setReadOnly(idx)
 ├─ (stops/shapes) [Editar no mapa] → startEditing() + ferramenta de vértices
 ├─ (stop_times)  → aplica subsetString por trip_id/linha ANTES de abrir
 ├─ [Validar]   → GtfsValidator (relatório no messageBar/log)
 ├─ [Descartar] → WorkingCopy.discard()
 └─ [Exportar .zip] → GtfsExporter (QgsTask) → feed_novo.zip
```

### Caminhos de edição
1. **Não-espacial (híbrido):** combobox Tabela → Campo/filtro → abre a camada na
   tabela de atributos nativa, com os IDs em *read-only*. A calculadora de campos
   nativa cobre edições em massa.
2. **Espacial (canvas):** `stops`/`shapes` → `startEditing()` + edição de vértices.
   Passa pela API do QGIS/OGR → respeita a regra de ouro do projeto: **nunca `UPDATE`
   sqlite cru em tabela com geometria** (quebra `ST_IsEmpty`).
3. **`stop_times` (filtrado):** `setSubsetString("trip_id IN (...)")` por linha/viagem
   antes de abrir — nunca a tabela inteira na GUI.

---

## 6. Padrões obrigatórios herdados (CLAUDE.md)

- I/O pesado em `QgsTask` (`run()` no fundo; `QgsProject`/camadas só em `finished()`).
- Tabelas grandes via `sqlite3` com SQL agregado + índices — nunca iterar `stop_times`
  feição-a-feição.
- Sem `UPDATE` sqlite cru em tabela com geometria → usar API QGIS/OGR.
- Feedback via `iface.messageBar()` e `QgsMessageLog` (`LOG_TAG='SIG-Bus'`).
- Docstrings em PT-BR, cabeçalho GPL nos arquivos `.py`.

---

## 7. Ordem de implementação (fatias finas e testáveis)

Fecha o ciclo **editar → exportar** cedo, com tabelas simples, antes de canvas e
`stop_times`:

1. **Esqueleto** — aba "Edição GTFS" + `WorkingCopy` (entrar/descartar) +
   `gtfs_schema` com 1–2 tabelas.  ← *fatia atual*
2. **Edição não-espacial** de uma tabela simples (ex.: `routes` →
   `route_short_name`/`route_long_name`) na tabela nativa, IDs travados.
3. **Exportador normalizado** (tabelas simples + calendar correto) → ciclo completo
   ponta a ponta.
4. **Edição espacial** (`stops`, depois `shapes`).
5. **`stop_times`** filtrado.
6. **`GtfsValidator`** completo na exportação.

---

## 8. Pontos em aberto (decidir durante a implementação)

- Aba no diálogo principal **vs.** janela própria (como o Diagrama de Blocos).
- Comportamento ao reentrar no modo edição com `feed_edit.gpkg` já existente
  (retomar vs. recriar).
- Onde gravar o `.zip` exportado (diálogo de "salvar como" vs. ao lado do feed).
- Tratamento de `agency_id` quando o feed tem uma única agência (campo opcional).
