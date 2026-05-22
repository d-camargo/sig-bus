# SIG-Bus — Documentação de Funcionalidades

**Versão:** 0.2  
**Autor:** Diego Camargo  
**Projeto:** PIBIC DPPG 113/2021  
**Última atualização:** 2026-05-22

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

O SIG-Bus é um plugin QGIS para análise de transporte público que integra dados no formato GTFS (*General Transit Feed Specification*) com dados de demanda de embarque por ponto de ônibus. Ele permite visualizar, filtrar e alocar a demanda de passageiros ao longo dos traçados das linhas.

O leitor de GTFS é embutido no plugin (`gtfs_reader.py`), adaptado do plugin *GTFS Loader* do CTU GeoForAll Lab (GPL v2+). Nenhum plugin externo é necessário.

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

O QGIS pode ser fechado e reaberto após o passo 2. Use **Reconectar GeoPackage** para restaurar as camadas sem reprocessar o GTFS.

---

## 3. Seção GTFS

### Verificar GTFS (`gtfs_insert_button`)

Verifica se o `.zip` do GTFS contém `calendar.txt`. Caso o feed traga apenas `calendar_dates.txt` (feeds que operam por exceção), o plugin sintetiza um `calendar.txt` semanal a partir das datas de operação efetiva e gera o arquivo `gtfs_corrigido.zip` ao lado do original.

> O GTFS da BHTrans (2024) já contém `calendar.txt`; este passo não é obrigatório para esse feed.

### Executar GTFS (`button_gtfsgo`)

Importa o `.zip` do GTFS para um GeoPackage (`.gpkg`) com o mesmo nome do arquivo, gravado na mesma pasta. As etapas internas são:

1. Importa cada `.txt` do feed como tabela no GeoPackage via GDAL (streaming — eficiente em memória para `stop_times` grandes).
2. Constrói a camada `shapes` (polilinha) agrupando e ordenando os pontos de `shapes_point` por `shape_id` e `shape_pt_sequence`.
3. Cria índices SQLite nas chaves de join (`trip_id`, `stop_id`, `shape_id`) para acelerar consultas posteriores.

**Camadas adicionadas ao projeto:** `stops`, `shapes`, `routes`, `trips`, `calendar`.  
As tabelas `stop_times`, `agency`, `fare_*` etc. ficam no GeoPackage apenas para joins.

**Chave de ligação:** o campo `route_short_name` da tabela `routes` corresponde ao código da linha (ex.: `"101"`). Toda a integração demanda↔GTFS passa por esse campo.

> **Nota sobre `shape_id`:** No GTFS da BHTrans o `shape_id` é numérico sequencial (`"1"` a `"1109"`), sem relação direta com o número da linha. O join demanda↔GTFS **nunca** usa `shape_id` diretamente — usa sempre `LINHA = route_short_name`.

---

## 4. Seção Dados de Demanda

### Selecionar CSV e Inserir (`data_insert_button`)

Importa o CSV de demanda (delimitador `;`, encoding `windows-1252`, coordenadas em SIRGAS 2000 / EPSG:31983) para o GeoPackage `sigt.gpkg`, gravado na mesma pasta do CSV.

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

> `LINHA` é campo texto — há linhas alfanuméricas como `"1404A"`. Filtros SQL usam aspas: `LINHA = '101'`.

---

## 5. Seção de Filtro e Análise

### Picker de linha

Usa `QgsMapLayerComboBox` (camada) + `QgsFieldComboBox` (campo) + `QgsFeaturePickerWidget` (valor). O fluxo esperado:

1. Selecionar a camada **`routes`** no combo de camadas.
2. Selecionar o campo **`route_short_name`** no combo de campos.
3. Digitar ou selecionar o código da linha no picker (ex.: `101`).

### Filtrar dados (`filterButton`)

A partir do `route_short_name` selecionado:

1. Consulta `routes` → `route_id` → `trips.shape_id` (todos os shapes da linha).
2. Aplica filtro de subconjunto na camada `shapes`: `shape_id IN ('671', '672', ...)` — destaca o traçado da linha.
3. Aplica filtro na camada `dados_demanda`: `LINHA = '101'`.
4. Dispara `_HorariosTask` em segundo plano: carrega os horários de todas as viagens da linha como camada de pontos `horarios_paradas` (join `stop_times ⋈ trips ⋈ stops`).

### Reconectar GeoPackage (`button_reconnect`)

Após fechar e reabrir o QGIS as camadas de memória (`horarios_paradas`, `tramos_demanda`) somem. Este botão:

1. Localiza o GeoPackage do GTFS por 4 estratégias em cascata:
   - `self._gpkg_path` (sessão atual)
   - Propriedade `gpkg_path` salva no projeto `.qgs`/`.qgz`
   - `source()` de camadas GTFS já presentes no projeto
   - Diálogo de arquivo (fallback manual)
2. Readiciona ao projeto as camadas essenciais (`stops`, `shapes`, `routes`, `trips`, `calendar`) que estiverem ausentes, sem duplicar as existentes.

---

## 6. Alocação de Demanda

### Seletor de hora (`combo_hora`) e Alocar Demanda (`button_alocar`)

O seletor oferece `Total geral` (demanda diária) ou uma hora específica `00h`–`23h` (faixa horária do CSV).

Ao clicar em **Alocar Demanda**, a tarefa `_AlocacaoTask` executa em segundo plano:

#### Passo 1 — Coordenadas das paradas
Lê `stop_id`, `stop_name`, latitude e longitude da camada `stops` via OGR.

#### Passo 2 — Leitura da demanda
Conecta ao `sigt.gpkg` (arquivo separado do GTFS) e faz `SELECT` na tabela `dados_demanda`, filtrando por `LINHA` e lendo a coluna correta:
- `Total geral` → coluna ` Total geral ` (nome detectado por `PRAGMA table_info`)
- `07h` → coluna `7`

> `SELECT` em tabela espacial via `sqlite3` é seguro. Apenas `INSERT`/`UPDATE` dispara os gatilhos do índice espacial (RTree) e requer a API QGIS/OGR.

#### Passo 3 — Shape dominante por sentido e hora

Para cada sentido (PC=1 → `direction_id=0`; PC=2 → `direction_id=1`):

- **Com hora específica selecionada:** busca o shape com mais viagens **iniciando** nessa hora (filtra pelo `departure_time` da primeira parada de cada viagem):
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

Isso vincula a demanda horária às viagens que realmente operaram naquela faixa, permitindo estimar a **carga por viagem** (`embarques ÷ n_viagens`).

#### Passo 4 — Sequência de paradas do shape dominante

Recupera uma viagem do shape dominante e sua lista de paradas ordenada por `stop_sequence`.

#### Passo 5 — Join espacial demanda → paradas

Para cada ponto de demanda do CSV, encontra a parada mais próxima por distância euclidiana em coordenadas WGS84 (suficiente para a escala intra-urbana). Acumula os embarques por parada.

#### Passo 6 — Geração de segmentos e passageiros acumulados

Para cada par de paradas consecutivas `A → B`:

```
embarques[A]       = embarques alocados à parada A
passageiros_acum[A→B] = Σ embarques[stops 0..A]
```

O campo `passageiros_acum` representa a **carga estimada no ônibus** no segmento, assumindo que nenhum passageiro desce antes do fim da linha. É o indicador mais fiel de qual trecho sofre maior demanda.

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

> Camada de memória: **desaparece ao fechar o QGIS**. Use **Filtrar dados** novamente após reconectar.

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

> Camada de memória: **desaparece ao fechar o QGIS**. Use **Alocar Demanda** novamente após reconectar.

#### Simbologia recomendada

- **Embarques por parada:** simbologia graduada no campo `embarques` (identifica pontos com maior demanda de embarque).
- **Carga no tramo:** simbologia graduada no campo `passageiros_acum` (identifica os trechos mais carregados — mais útil para dimensionamento de frota).
- **Divisão por sentido:** filtrar por `sentido = 'ida'` ou `sentido = 'volta'` antes de aplicar a simbologia.

---

## 8. Arquitetura dos Dados

### Dois GeoPackages

| Arquivo | Conteúdo | Gerado por |
|---------|----------|------------|
| `<nome_do_gtfs>.gpkg` | `stops`, `shapes`, `shapes_point`, `routes`, `trips`, `stop_times`, `calendar`, etc. | **Executar GTFS** |
| `sigt.gpkg` | `dados_demanda` | **Inserir** (seção demanda) |

O `sigt.gpkg` é gravado na mesma pasta do CSV de demanda. O GeoPackage do GTFS é gravado na mesma pasta do `.zip`.

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

> Algumas linhas têm PC=2 na demanda mas apenas `direction_id=0` no GTFS (ex.: linha 1170). O plugin registra aviso sem interromper a alocação.

### Persistência entre sessões

O caminho do GeoPackage do GTFS é salvo nas propriedades do projeto (`SIG-Bus/gpkg_path`). Ao reabrir o QGIS e carregar o projeto `.qgs`/`.qgz`, o **Reconectar GeoPackage** recupera o caminho automaticamente sem diálogo de arquivo.

---

## 9. Limitações Conhecidas

| Limitação | Impacto | Contexto |
|-----------|---------|---------|
| Sem dados de desembarque | `passageiros_acum` cresce monotonicamente — é o **limite superior** da carga real | O CSV de demanda registra apenas embarques |
| Join espacial simplificado | Distância euclidiana em WGS84 (não distância ao longo da rede) | Adequado para escala intra-urbana; pode falhar em paradas muito próximas de linhas adjacentes |
| Uma viagem representativa por shape | A sequência de paradas vem de uma única viagem do shape dominante | Variações de itinerário dentro do mesmo shape são ignoradas |
| Camadas de saída em memória | `horarios_paradas` e `tramos_demanda` não persistem no `.qgz` | Reprocessar após reabrir o QGIS |
| `departure_time` > 23h no GTFS | Viagens de madrugada podem ter `departure_time = "24:15:00"` | A extração da hora por `SUBSTR(...,1,2)` retorna `"24"`, que não casa com hora `0`; essas viagens não são contadas em `n_viagens` para `00h` |
