# Arquitetura — Construção de GTFS (PyQGIS)

**Projeto:** SIG-Bus (plugin QGIS) · **Data:** 2026-07-14
**Branch:** `feature/construir-gtfs`
**Documento irmão (referência de estilo):** [ARQUITETURA_EDICAO_GTFS.md](ARQUITETURA_EDICAO_GTFS.md)

Funcionalidade nova: **construir um feed GTFS do zero por meio de um assistente passo a passo integrado**, permitindo cadastrar agência, linhas, paradas geocodificadas, sequência de paradas, frequências de horários, calcular o traçado real baseado nas ruas (OpenStreetMap) e salvar tudo em uma cópia de trabalho local para posterior edição e exportação em formato `.zip` compatível com a especificação GTFS.

---

## 1. Decisões de projeto (Fase 5)

Estas escolhas guiam toda a arquitetura abaixo:

17. **Reaproveitar o mesmo `feed_edit.gpkg` e o mesmo pipeline de Validar/Exportar da aba "Edição GTFS"** (decisões 1–6 da Fase 1), em vez de criar um pipeline de exportação paralelo. "Construir GTFS" apenas *popula* os dados no GeoPackage temporário (`feed_edit.gpkg`); as ferramentas de exportação (`gtfs_export.py`), validação (`gtfs_validator.py`) e o fluxo de exportação nativo do painel continuam centralizados. O `gtfs_schema.py` segue como fonte única da verdade para a validação das tabelas e a ordem das colunas.
18. **`WorkingCopy` de origem vazia**: A classe `WorkingCopy` (em `gtfs_edit_core.py`) foi estendida com o método `enter_empty()`. Como a aba "Construir GTFS" cria dados a partir do nada, ela gera um `feed_edit.gpkg` em branco com todas as tabelas requeridas e campos definidos no esquema (diferente de `WorkingCopy.enter()` que exige uma cópia de um banco de dados de origem).
19. **Geocodificação via Nominatim (OpenStreetMap), sem dependência nova de pacotes**: O plugin usa `QgsNetworkAccessManager` e `QNetworkRequest` nativos do PyQGIS para realizar buscas de endereços na API pública do Nominatim. As requisições definem um cabeçalho `User-Agent` descritivo exigido pela política de uso do OSM e garantem um espaçamento mínimo de 1.0 segundo entre chamadas. Se a busca falhar ou o endereço não for encontrado, o erro é tratado silenciosamente, permitindo que o usuário digite as coordenadas manualmente ou use o mapa.
20. **"GTFS mínimo" baseado em `REQUIRED_LAYERS` de `gtfs_reader.py`**: O plugin considera como o feed básico a presença de pelo menos um registro válido nas tabelas principais: `agency`, `routes`, `trips`, `stop_times`, `stops` e `calendar`. O progresso máximo, por sua vez, monitora o preenchimento de campos opcionais do esquema, a associação de shapes às viagens e a existência do segundo sentido da linha (ida/volta).
21. **Confirmação de coordenadas no canvas nativo do QGIS**: Em vez de construir um canvas de mapa embutido e complexo (`QgsMapCanvas`) na caixa de diálogo, os pontos geocodificados são gerados em uma camada de memória temporária carregada no projeto atual do QGIS. O usuário visualiza e refina as posições usando a ferramenta nativa de edição de feições/vértices do próprio QGIS, preservando a simplicidade e a coesão com a plataforma.
22. **Deduplicação de paradas por texto exato do endereço normalizado**: Para evitar duplicar registros da mesma parada física na tabela `stops`, o sistema realiza o colapso e normalização de espaços e caracteres do endereço digitado (minúsculas). A verificação por proximidade geográfica não foi adotada para evitar complexidade com distâncias de tolerância configuráveis. A decisão de reutilizar paradas semelhantes fica visível ao usuário na tela do assistente.
23. **Sequência de paradas e horários resolvidos no assistente**: A ordenação das paradas da linha é resolvida em uma lista visual simples (permitindo mover itens para cima ou para baixo). A tabela de `stop_times` é populada automaticamente de forma expandida baseada em uma frequência configurada pelo usuário (ex.: "a cada 15 min das 06:00 às 22:00"). Detalhes viagem a viagem podem ser ajustados individualmente na aba "Edição GTFS" caso necessário.
24. **Traçado (`shapes`) calculado seguindo a rede viária real do OpenStreetMap (OSM)**: O caminho percorrido entre as paradas não é apenas uma linha reta (salvo no fallback). O plugin faz o download das vias reais no entorno, constrói um grafo de roteamento e calcula a menor rota (Dijkstra) na malha viária real. Ajustes refinados do traçado continuam sendo feitos usando a edição de vértices padrão do QGIS.
25. **Fonte da malha viária: Overpass API (OSM) consultada uma vez por linha**: A busca da malha viária é realizada com base em uma única bounding box contendo todas as paradas da linha, adicionando uma margem de ~300 metros. Isso é feito via chamada HTTP síncrona/bloqueante ao endpoint público do Overpass. O resultado é armazenado em cache de memória durante a execução do assistente para evitar consultas redundantes e tráfego desnecessário.
26. **Motor de roteamento: `qgis.analysis` nativo**: A malha viária obtida da API do Overpass é inserida em uma camada temporária de linhas em memória do QGIS. A partir dela, as classes `QgsVectorLayerDirector` e `QgsGraphBuilder` estruturam um grafo, e o caminho entre as paradas é resolvido por Dijkstra com `QgsGraphAnalyzer.shortestPath()`. Desta forma, não há dependência de pacotes externos como NetworkX ou OSMnx.
27. **Fallback silencioso para linha reta por trecho**: Em caso de falha de conexão com a API do Overpass, ou se o grafo resultante possuir componentes desconexas impedindo a rota viária de ligar duas paradas consecutivas, o sistema calcula a rota por linha reta apenas para aquele trecho específico, mantendo os demais trechos roteados viariamente intactos.
28. **`agency` configurada globalmente; `calendar` por linha**: As informações da agência de transportes são fornecidas uma única vez ao iniciar a criação do feed. Já as vigências do calendário são associadas a cada linha individualmente, mas o assistente apresenta e reutiliza os `service_id` já criados para evitar cadastros redundantes.
29. **Geração de shapes reutilizando `GtfsReader.build_shapes_line`**: Ao invés de duplicar a lógica de escrever strings de caminhos e geometrias em arquivo, o assistente popula a tabela de apoio intermediária `shapes_point`. O leitor de GTFS existente (`gtfs_reader.py`) é então utilizado para ler os pontos, ordená-los e convertê-los na polilinha final da tabela `shapes`.
30. **Assistente baseado em `QStackedWidget` na própria aba "Construir GTFS"**: O assistente foi concebido sem arquivos de interface `.ui` gerados no Qt Designer. Ele é inteiramente construído dinamicamente via código no arquivo `SigBus_dialog.py` através de um `QStackedWidget`. Duas barras de progresso (Mínimo e Máximo) permanecem visíveis no topo do widget exibindo o progresso e o checklist de itens ausentes.
31. **Núcleo de construção puro (sem QGIS) sempre que aplicável**: Funções de progresso, normalização de texto, expansão de horários por frequência e interação direta com SQLite foram isoladas em `gtfs_builder_core.py` utilizando apenas as bibliotecas padrão Python (`sqlite3`, `json`, `math`) e `osgeo.ogr`. Isso possibilita a validação de testes unitários offline e de forma standalone.

---

## 2. Visão geral (MVC em três camadas)

O assistente foi acoplado à arquitetura geral do plugin do SIG-Bus, complementando a funcionalidade de edição:

```
┌────────────────────────────────────────────────────────────────────────┐
│  INTERFACE (Controller / View)  SigBus_dialog.py (Aba "Construir GTFS") │
│  - Assistente dinâmico baseado em QStackedWidget                       │
│  - Duas barras de progresso: Mínimo e Máximo ( checklist no topo )      │
│  - Telas: Agência ➔ Linha ➔ Paradas ➔ Sequência ➔ Horários ➔ Revisão     │
│  - Ferramentas nativas do canvas (camadas de memória/edição de vértices)│
└───────────────────┬─────────────────────────────────┬──────────────────┘
                    │                                 │ usa
                    ▼                                 ▼
┌──────────────────────────────────────┐      ┌──────────────────────────┐
│  MÓDULOS DE CORE (Model)             │      │  MÓDULO DE REDE          │
│  gtfs_builder_core.py                │      │  geocoding.py            │
│  - compute_progress()                │ ───► │  - NominatimGeocoder     │
│  - save_route() / build_line_shape() │      │    (Busca de endereços   │
│  - expand_frequency_to_stop_times()   │      │     QgsNetworkAccessMgr) │
│  └──────────────────────────┘
└───────────────────┬──────────────────┘
                    │
                    │ usa para rotear
                    ▼
┌──────────────────────────────────────┐      ┌──────────────────────────┐
│  ROTEAMENTO OSM                      │      │  COMPATIBILIDADE / SCHEMA│
│  osm_routing.py                      │ ───► │  gtfs_edit_core.py       │
│  - fetch_ways_for_stops() (Overpass) │      │  - WorkingCopy.enter_emp │
│  - build_road_graph() (qgis.analysis)│      │  gtfs_schema.py          │
│  - route_stops() (Dijkstra/Fallback) │      │  - Esquema de tabelas    │
└───────────────────┬──────────────────┘      └──────────────────────────┘
                    │
                    ▼
            ┌───────────────┐
            │ feed_edit.gpkg│
            └───────────────┘
```

---

## 3. CORE (Model) — `gtfs_builder_core.py`

Camada contendo a lógica central de manipulação dos dados relacionais do GTFS no banco de dados SQLite/GeoPackage. Funciona de forma pura (sem exigir o ambiente QGIS, exceto na escrita de geometrias no OGR).

### 3.1 Progresso (`compute_progress`)
Calcula e retorna o percentual de preenchimento mínimo e máximo para orientar as barras de progresso.
*   **Mínimo (6 tabelas básicas)**: Verifica se `agency`, `routes`, `trips`, `stop_times`, `stops` e `calendar` possuem pelo menos uma feição com seus campos obrigatórios (`required=True` em `gtfs_schema`) preenchidos.
*   **Máximo**: Incrementa a contagem com base em:
    1. Preenchimento de cada campo opcional das 6 tabelas básicas.
    2. Presença de dados na tabela de geometrias `shapes` vinculados a cada viagem (`trip`).
    3. Cadastro de pelo menos duas rotas de sentidos opostos (`direction_id = 0` e `direction_id = 1`) para cada linha de ônibus.
*   Retorna a lista de pendências em formato amigável para exibição no topo do assistente.

### 3.2 Expansão por Frequência (`expand_frequency_to_stop_times`)
Recebe os horários de início e fim de operação, o intervalo em minutos e a lista de paradas em ordem. Produz as linhas que serão inseridas na tabela `stop_times` para cada viagem simulada daquele intervalo.
*   Realiza a conversão e cálculos internamente usando segundos inteiros do dia para evitar problemas com horários extrapolando as 24 horas (ex: `25:30:00`).
*   Distribui as paradas linearmente ou com base nas distâncias cumulativas para interpolar os horários de chegada (`arrival_time`) e partida (`departure_time`) em cada ponto.

### 3.3 Persistência da Linha (`save_route`)
Lógica transacional em `sqlite3` que insere/atualiza registros nas tabelas relevantes ao final do assistente:
*   Grava/atualiza os dados de `agency`.
*   Cria registros em `routes`.
*   Insere a linha na tabela `trips` e gera as correspondências de `calendar` (ou reaproveita calendário se idêntico).
*   Gera as linhas associadas em `stop_times` chamando o expansor de frequência.
*   Gera os registros em `stops` (caso a parada seja nova) e aciona `build_line_shape()` para processar o traçado.

---

## 4. ROTEAMENTO OSM — `osm_routing.py`

Gerencia a modelagem matemática do traçado viário real sobre o qual a linha de ônibus trafega.

### 4.1 Download de Vias (`fetch_ways_for_stops`)
*   Define a área de busca englobando todas as paradas com uma margem ajustável (padrão `300` metros).
*   Realiza uma única consulta via HTTP POST à Overpass API buscando por feições que correspondam a `way["highway"]`.
*   Armazena os elementos no dicionário global de cache de memória `_WAYS_CACHE` para otimizar reordenamentos de paradas.

### 4.2 Montagem do Grafo (`build_road_graph`)
*   Lê os nós (nodes) e caminhos (ways) retornados.
*   Cria uma camada vetorial de linhas temporária em memória (`LineString?crs=EPSG:4326`) contendo os caminhos viários.
*   Utiliza `QgsVectorLayerDirector` e `QgsGraphBuilder` do QGIS para gerar a estrutura de grafo bidirecional (`QgsVectorLayerDirector.DirectionBoth`).

### 4.3 Dijkstra (`shortest_path` / `route_stops`)
*   Itera sobre a sequência de paradas consecutivas.
*   Para cada par de paradas `A` e `B`, snapa as coordenadas nos vértices do grafo mais próximos e roda `QgsGraphAnalyzer.dijkstra()`.
*   Monta a polilinha resultante concatenando os trechos roteados.
*   Caso o snap falhe ou as paradas estejam em ilhas isoladas (componentes desconexas do grafo), aciona o fallback desenhando uma linha reta entre as duas paradas.

---

## 5. GEOCODIFICAÇÃO — `geocoding.py`

Provê a conversão de endereços em coordenadas geográficas.

*   **Classe `NominatimGeocoder`**:
    *   Método `geocode(endereco)`: encapsula a chamada HTTP GET para `https://nominatim.openstreetmap.org/search`.
    *   Usa a classe `QgsNetworkAccessManager` para executar a requisição de forma bloqueante síncrona dentro da lógica do assistente.
    *   Implementa o *throttle* de requisições de 1.0 segundo com `time.sleep` para cumprimento das políticas públicas do Nominatim.
    *   Tratamento de exceções robusto: qualquer falha na conexão, time out ou parsing retorna uma lista vazia `[]`, não quebrando o fluxo principal do usuário.

---

## 6. EXTENSÕES DO CORE — `WorkingCopy.enter_empty()`

Implementado em `gtfs_edit_core.py`:
*   Inicializa um GeoPackage (`.gpkg`) vazio a partir do zero.
*   Adiciona a definição espacial `EPSG:4326` (WGS84) para as tabelas `stops` e `shapes_point` (tipo ponto) e para `shapes` (tipo linha).
*   Popula as colunas da tabela de acordo com as especificações do `gtfs_schema.py`.

---

## 7. FLUXO DE PÁGINAS DO ASSISTENTE

A navegação pelo assistente de construção de GTFS ocorre da seguinte forma através do `QStackedWidget`:

1.  **Página 0: Configuração Inicial (`page_config`)**
    *   Formulário para definição da agência (Nome, URL, Fuso Horário, Idioma, Telefone).
    *   Salva globalmente os metadados da agência.
2.  **Página 1: Nova Linha (`page_nova_linha`)**
    *   Definição de nome curto, nome longo e tipo de transporte (ônibus, bonde, metrô, etc.).
3.  **Página 2: Paradas (`page_paradas`)**
    *   Busca de endereços (geocodificação via Nominatim) e inserção das paradas.
    *   Adiciona os pontos temporários ao canvas do QGIS para ajuste de vértices pelo usuário.
4.  **Página 3: Sequência (`page_sequencia`)**
    *   Reordenação visual das paradas inseridas (subir/descer na lista) e deduplicação opcional de nomes e endereços.
5.  **Página 4: Horários (`page_horarios`)**
    *   Configuração da operação horária da linha baseada em frequências (início, fim e intervalo).
6.  **Página 5: Revisão (`page_revisao`)**
    *   Resumo de todas as informações inseridas para a linha.
    *   Permite salvar a linha (persiste no banco de dados e calcula o traçado viário via OSM/Dijkstra).
    *   Oferece as opções de: "Adicionar segundo sentido desta linha", "Nova linha" ou "Ir para Edição GTFS" (redireciona para a aba de Edição reaproveitando a mesma cópia de trabalho).

---

## 8. Ordem de implementação (Fase 5)

A implementação seguiu passos incrementais para assegurar a testabilidade das camadas:

1.  **Estrutura de `WorkingCopy.enter_empty()`**: Permitiu gerar um GeoPackage em branco estruturado.
2.  **Mecanismos de Core & Progresso**: Desenvolvimento de `compute_progress` e expansão de frequências com testes síncronos de inserção no SQLite.
3.  **Módulo de Geocodificação**: Chamada à API Nominatim com proteção de requisições por tempo.
4.  **Pipeline de Roteamento viário com OSM**: Integração com a API do Overpass e processamento do grafo pelo `qgis.analysis`.
5.  **Interface gráfica**: Desenvolvimento dinâmico do assistente, `QStackedWidget`, lógica de navegação dos botões e ligação com o canvas nativo.
6.  **Integração e Validação**: Ligação de "Construir GTFS" à aba "Edição GTFS" compartilhando o mesmo GeoPackage de trabalho.
