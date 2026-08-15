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
32. **Decisão 42 (Estilização de Legibilidade e Suporte a Temas)**: Padronização das folhas de estilo em constantes centralizadas em `SigBus_dialog.py` (`QSS_INPUT`, `QSS_CARD`, `QSS_HINT`, `QSS_STATUS_OK`, `QSS_STATUS_ERR`), garantindo contraste legível em temas claros e escuros (Night Mapping).
33. **Decisão 43 (Padrão de Endereço e Formato CSV em Lote)**: Isolamento do formato de endereço (`Logradouro, Número - Bairro`) no módulo puro `address_format.py` e suporte ao formato de lote em `;` (UTF-8 com BOM) no módulo `stops_csv.py`, além do modelo versionado `sig_bus/modelo_paradas.csv`.
34. **Decisão 44 (Geocodificação Estruturada com Cascata de Busca)**: Extensão do `NominatimGeocoder` em `geocoding.py` para busca estruturada por contexto (com número -> sem número -> busca livre), com preservação de retrocompatibilidade.
35. **Decisão 45 (Contexto Geográfico da Agência - Município e UF)**: Inclusão dos campos obrigatórios de Município e UF no cadastro da Agência para direcionar a geocodificação e delimitar o escopo urbano do feed.
36. **Decisão 46 (Tabela de Configuração Interna `sig_bus_config`)**: Tabela chave-valor no GeoPackage de trabalho para persistir parâmetros internos (município, UF, bbox do município), ignorada durante a exportação GTFS.
37. **Decisão 47 (Bounding Box do Município para Geocodificação)**: Cálculo e armazenamento da caixa envolvente do município (`city_bbox` / `build_city_viewbox`) para aplicar restrição espacial (`viewbox` + `bounded=1`) na busca Nominatim.
38. **Decisão 48 (Supressão Visual de Lat/Lon e Indicadores de Status)**: Remoção dos campos de texto visíveis de lat/lon na tabela de paradas, substituídos por rótulos visuais de status (`✓ localizado`, `✗ não encontrado`, `📍 marcado no mapa`).
39. **Decisão 49 (Ferramenta Interativa `PickStopPointTool` de Captura no Canvas)**: Módulo `map_tools.py` provendo ferramenta de mapa para seleção direta de pontos no canvas do QGIS para linhas rurais ou sem endereço.
40. **Decisão 50 (Mapa de Fundo OSM Automático `ensure_osm_basemap`)**: Adição dinâmica de camada raster OpenStreetMap WMS/XYZ ao projeto para suporte visual durante a marcação de paradas no mapa.
41. **Decisão 51 (Enum qualificado, não shim de versão)**: A correção de compatibilidade com o Qt6/QGIS 4 é sempre a forma qualificada do enum (`QNetworkReply.NetworkError.NoError`, `QgsVectorFileWriter.WriterError.NoError`, `QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwrite*`, `QgsBlockingNetworkRequest.ErrorCode.NoError`, `QgsVectorLayerDirector.Direction.DirectionBoth`, `QgsLayoutExporter.ExportResult.Success`) — todas existem tanto no PyQt5/QGIS 3 quanto no PyQt6/QGIS 4. Nada de `hasattr` nem de `if QT_VERSION`: um caminho de código só (decisão 35).
42. **Decisão 52 (Falha de rede nunca é silenciosa)**: O `except Exception: return []` do `NominatimGeocoder._buscar` continua (a decisão 19 exige que a geocodificação nunca bloqueie o fluxo), mas cada tentativa agora registra no `QgsMessageLog`, sob a tag `SIG-Bus`, a URL consultada, o código de erro do reply e o número de candidatos — e, no ramo de exceção, o `traceback` completo. Sem isso, um erro de programação fica indistinguível de "endereço inexistente", que foi exatamente o que escondeu o bug do enum não qualificado no QGIS 4.
43. **Decisão 53 (`bounded=1` é filtro de qualidade, não regra dura)**: Revisão da decisão 47. Se a cascata inteira com `viewbox`+`bounded=1` voltar vazia, o `geocode` repete a cascata sem esses dois parâmetros antes de declarar "não encontrado" — uma bbox errada, desatualizada ou de município homônimo deixa de zerar permanentemente o resultado. Na busca livre, o bairro é omitido quando é o próprio município (comparação normalizada), para não gerar `"…, Caxias do Sul, Caxias do Sul - RS, Brasil"`.
44. **Decisão 54 (A bbox pertence ao par município/UF)**: `build_city_viewbox` é calculada e gravada junto de `build_city`/`build_state` ao salvar a agência, e invalidada assim que qualquer um dos dois mudar — nunca fica cacheada apontando para outra cidade. Falha de rede nesse ponto não bloqueia o salvamento da agência: no máximo o feed fica sem bbox.
45. **Decisão 55 (A guarda de Qt6 cobre também rede e I/O)**: O teste-guarda `test_qt6_compat.py` (decisão 41) só varria `Qt.*` e alguns widgets, e por isso `QNetworkReply.NoError`, `QgsVectorFileWriter.NoError`, `QgsBlockingNetworkRequest.NoError` e `QgsVectorLayerDirector.DirectionBoth` sobreviveram à Fase 7. A guarda passa a listar essas classes e a varrer também os arquivos de teste (os mocks eram parte do problema) — uma linha de regex por classe, e é a única coisa que impede a regressão de voltar.
46. **Decisão 56 (A causa deixou de ser técnica e passou a ser de dado: o Nominatim não perdoa typo)**: Medido em 2026-08-05 reproduzindo as URLs do log do usuário contra a API pública, uma variável por vez:

    | Variável alterada | Candidatos |
    |---|---|
    | `viewbox` presente/ausente | 2 (indiferente) |
    | `bounded=1` presente/ausente | 2 (indiferente) |
    | número da casa (`210`) presente/ausente | 2 (indiferente) |
    | acentuação `Fórmolo` × `Fôrmolo` | 2 (indiferente) |
    | **`Giusepe` (um `p`) × `Giuseppe` do OSM** | **0** |

    A única variável que zera o resultado é a grafia do logradouro — tanto na busca estruturada quanto na livre. Nenhuma das correções da Fase 9 estava errada; elas simplesmente não atacam este problema, e as seis tentativas da cascata falham juntas porque são o mesmo motor consultado seis vezes.
47. **Decisão 57 (A tolerância entra como último degrau da cascata, com o Photon — o Nominatim não é substituído)**: O Photon (`photon.komoot.io`) é o geocodificador de busca incremental do Komoot sobre os **mesmos dados do OSM**, público, sem chave, e tolerante a erro de digitação por construção (índice Elasticsearch). Verificado: `q=Rua Giusepe Fórmolo` + `bbox` de Caxias do Sul devolve `Rua Giuseppe Fôrmolo` em 1º **e** 2º lugar. O Nominatim continua sendo o caminho principal — é ele que faz busca estruturada e resolve número de casa — e o Photon só é consultado depois de a cascata inteira ter voltado vazia: uma requisição a mais **apenas no caso que hoje falha**, zero custo no caminho feliz. Dois detalhes medidos que viraram código: **(i)** `lang=pt` faz o Photon devolver **HTTP 400** (aceita só `de`/`en`/`fr`/`it`) — não enviar `lang`; **(ii)** o `bbox` do Photon é `minLon,minLat,maxLon,maxLat`, ordem **diferente** do `viewbox` do Nominatim (`lon_min,lat_max,lon_max,lat_min`) já gravado em `build_city_viewbox`, então a conversão é obrigatória. Com a bbox de outro estado a mesma consulta devolve 0 — o filtro geográfico da decisão 47 continua valendo; quando não há bbox, ele é aplicado no pós-filtro por `properties.city`/`county`.
48. **Decisão 58 (Alternativa considerada e recusada: índice de vias por Overpass + `difflib`)**: Também medida em 2026-08-05: uma consulta Overpass traz as **4.342 vias nomeadas** de Caxias do Sul em 3,8 s, e `difflib.get_close_matches` põe `Rua Giuseppe Fôrmolo` em 1º (ratio 0,923) bem separado do 2º (0,718). Funciona, e reaproveitaria o Overpass que `osm_routing.py` já usa. Recusada mesmo assim porque resolve só o **nome** da via — ainda seria preciso voltar ao Nominatim pela coordenada — e exige cache por município mais um limiar de similaridade a calibrar. São várias peças móveis para chegar ao mesmo lugar que uma URL a mais. Fica registrada como plano B se o Photon público sair do ar ou passar a exigir chave. **Não refazer o experimento.**
49. **Decisão 59 (Correção de grafia nunca é silenciosa)**: Com o degrau tolerante, `"Rua Giusepe Fórmolo"` passa a virar `✓ localizado` apontando para um nome que o usuário não digitou — e a mesma resposta trouxe `Rua Giusepe Bressan`, uma rua **diferente e existente** no mesmo município, então o acerto não é garantido. Quando o logradouro do candidato aceito difere do digitado (comparação por `address_format.normalizar_logradouro`: minúsculas, acentos removidos, espaços colapsados), o status da linha vira `✓ localizado (via: <nome real>)` e o par vai para o log. A normalização mora em `address_format.py` porque ele já é a fonte única do padrão de endereço (decisão 43), não solta na UI. Sem isso o assistente estaria corrigindo o cadastro do cliente pelas costas dele.
50. **Decisão 60 (A mensagem de "nada localizado" para de culpar o município)**: A mensagem anterior mandava "Confira o município na página da agência"; no caso relatado o município estava certo, e a orientação levou o usuário a procurar no lugar errado. Passa a listar os endereços que falharam (até 3, para não virar parede de texto) e a apontar a causa que os dados mostram ser a mais comum — grafia do logradouro —, mantendo "Marcar no mapa" como a saída sempre disponível da decisão 19. O município/UF continuam na mensagem, mas como contexto da busca, não como acusação.
51. **Cache de sessão e etiqueta por tentativa (Fase 10)**: Com o degrau do Photon o pior caso passou a ser 7 requisições de 1 s **por parada**, e uma linha real importada por CSV tem dezenas de paradas, muitas na mesma via. Duas contenções, ambas baratas: um cache de sessão em `NominatimGeocoder._session_cache` indexado pela **URL** (que já embute endereço, município, UF e bbox — não é preciso uma chave composta à parte), consultado antes do intervalo de 1 s; e, em `_geocode_stops`, pular as paradas que já têm `lat`/`lon`, o que também impede que um ponto marcado à mão no canvas seja sobrescrito por um clique a mais em "Geocodificar". Cada tentativa carrega uma etiqueta no log (`a-estruturada-num`, `b-estruturada`, `c-livre`, `sem-bbox …`, `photon`, `google`, `city-bbox`) para o próximo diagnóstico não exigir reconstruir a URL à mão.
52. **Decisão 61 (Orquestração desatrelada do `NominatimGeocoder`)**: A orquestração da cascata de geocodificação foi extraída do `NominatimGeocoder` para a função de módulo `geocode(endereco, contexto=None)` em `sig_bus/geocoding.py`. Cada provedor (`GoogleGeocoder`, `NominatimGeocoder`, `PhotonGeocoder` e o corretor Overpass em `street_index.py`) executa apenas sua consulta própria, e `_geocode_stops` em `SigBus_dialog.py` chama a função de módulo.
53. **Decisão 62 (Configuração de geocodificação em `geocoding_config.py` e persistência fora do GeoPackage)**: Criação de `sig_bus/geocoding_config.py` como fonte única de configuração (`get_provider_mode`/`set_provider_mode` e `get_google_api_key`/`set_google_api_key`). A chave da API do Google e a preferência de modo são salvas em `QSettings` (`SIG-Bus/geocoding/...`) e **nunca** no GeoPackage (`sig_bus_config`), evitando vazar credenciais privadas ou atrelar custos de API do usuário ao arquivo `.gpkg` compartilhado.
54. **Decisão 63 (Inclusão do `GoogleGeocoder` como primeiro provedor na cascata `auto`)**: Adição da classe `GoogleGeocoder` em `sig_bus/geocoding.py`. Quando o modo for `"auto"` e houver uma chave de API configurada, o Google Geocoding API é consultado primeiro na ordem `Google → Nominatim → Photon`. Sem chave ou em modo `"osm"`, a busca ignora o Google e consulta apenas os provedores gratuitos OSM.
55. **Decisão 64 (Tratamento de status de erro do Google sem bloquear a cascata)**: Na classe `GoogleGeocoder`, `status == "OK"` devolve os candidatos e `"ZERO_RESULTS"` devolve `[]`. Respostas de erro (`REQUEST_DENIED`, `OVER_QUERY_LIMIT`, `INVALID_REQUEST`) registram `Warning` no `QgsMessageLog`, gravam o erro em `GoogleGeocoder.ultimo_erro` para exibição na UI e devolvem `[]`, permitindo que a cascata continue nos provedores gratuitos.
56. **Decisão 65 (Redação de credenciais em logs - `_redigir_credenciais`)**: Função `_redigir_credenciais(texto)` em `sig_bus/geocoding.py`, aplicada dentro do próprio `_log` — assim nenhuma chamada nova pode esquecer de redigir. Oculta o valor dos parâmetros sensíveis (`key=`, `api_key=`, `token=` e afins) substituindo por `***` em todas as mensagens gravadas no `QgsMessageLog`, prevenindo vazamento acidental de chaves de API nos logs do QGIS. A URL realmente requisitada continua intacta.
57. **Decisão 66 (Descarte de resultados em nível de cidade/localidade no Google)**: Candidatos retornados pelo `GoogleGeocoder` cujos tipos (`types`) pertençam apenas a divisões administrativas genéricas (ex.: `locality`, `administrative_area_level_1`) sem interseção com tipos em nível de rua (`street_address`, `route`, `premise`, `subpremise`, `intersection`, `establishment`, `point_of_interest`) são descartados com log detalhado, evitando posicionar paradas no centro do município.
58. **Decisão 67 (Intervalo de tempo de 1 s por host - `HOSTS_COM_LIMITE`)**: Em `_get_json`, a espera de 1.0 s entre requisições passou a rastrear o tempo por host individualmente. Apenas hosts com limite público de taxa (`nominatim.openstreetmap.org` e `photon.komoot.io`, em `HOSTS_COM_LIMITE`) sofrem o delay de 1.0 s; chamadas ao Google (`maps.googleapis.com`) não aguardam delay desnecessário.
59. **Decisão 68 (Corretor de grafia via Overpass como último degrau - `street_index.py`)**: Módulo `sig_bus/street_index.py` consulta o Overpass (`way["highway"]["name"]`) dentro da bounding box do município para listar todas as vias reais. Caso todos os provedores da cascata retornem vazio, o assistente utiliza `difflib.get_close_matches` para encontrar o nome correto da rua e refazer uma busca com o nome corrigido.
60. **Decisão 69 (Tabela das 4 ordens de Bounding Box do projeto)**: Cada serviço/API de geocodificação ou roteamento utilizado pelo SIG-Bus exige os limites geográficos (bbox) em uma ordem de coordenadas diferente:

    | Serviço / Módulo | Parâmetro | Formato / Ordem das Coordenadas |
    |---|---|---|
    | **Nominatim** (`geocoding.py`) | `viewbox` | `lon_min,lat_max,lon_max,lat_min` |
    | **Photon** (`geocoding.py`) | `bbox` | `minLon,minLat,maxLon,maxLat` |
    | **Google Maps** (`geocoding.py`) | `bounds` | `lat_min,lon_min|lat_max,lon_max` |
    | **Overpass** (`street_index.py` / `osm_routing.py`) | consulta QL | `(lat_min,lon_min,lat_max,lon_max)` |

61. **Decisão 70 (Rastreamento e exibição da procedência do ponto)**: Cada candidato normalizado retorna com o atributo `provider` (`"google"`, `"nominatim"`, `"photon"` ou `"osm-overpass"`). A interface em `SigBus_dialog.py` exibe a origem no status visual da parada (ex.: `✓ localizado (Google)`, `✓ localizado (via: Rua Giuseppe Fôrmolo — OSM)`), informando a origem de cada ponto.

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
    *   Toda tentativa é registrada no `QgsMessageLog` com a tag `SIG-Bus` (decisão 52): URL, código de erro e número de candidatos em nível `Info`; falha de rede, resposta vazia/inesperada e exceção (com `traceback`) em nível `Warning`. `[]` deixou de significar silêncio.
    *   Cascata com `viewbox`+`bounded=1` primeiro; se ela inteira voltar vazia, a mesma cascata é repetida sem esses parâmetros (decisão 53) antes de devolver `[]`.

---

## 6. EXTENSÕES DO CORE E MÓDULOS AUXILIARES

### 6.1 `WorkingCopy.enter_empty()`
Implementado em `gtfs_edit_core.py`:
*   Inicializa um GeoPackage (`.gpkg`) vazio a partir do zero.
*   Adiciona a definição espacial `EPSG:4326` (WGS84) para as tabelas `stops` e `shapes_point` (tipo ponto) e para `shapes` (tipo linha).
*   Popula as colunas da tabela de acordo com as especificações do `gtfs_schema.py`.

### 6.2 Formatação de Endereços — `address_format.py`
Módulo Python puro (sem dependência Qt/QGIS):
*   `parse_address(texto)`: Decompõe endereços no padrão `Logradouro, Número - Bairro` em um dicionário estruturado.
*   `format_address(partes)`: Monta o endereço no formato canônico.

### 6.3 Processamento de Lote CSV — `stops_csv.py`
Módulo puro para gerenciar importação/exportação de paradas:
*   `write_template(caminho)`: Gera o modelo CSV com delimitador `;`, codificação UTF-8 com BOM e exemplos.
*   `parse_stops_csv(caminho)`: Realiza a leitura e validação das paradas em lote, suportando endereços ou coordenadas diretas.

### 6.4 Ferramentas de Mapa — `map_tools.py`
Módulo de apoio visual e captura no QGIS canvas:
*   `PickStopPointTool`: Ferramenta interativa (`QgsMapToolEmitPoint`) para captura de coordenadas diretamente por clique no mapa.
*   `ensure_osm_basemap()`: Adiciona uma camada raster OpenStreetMap XYZ no fundo do projeto QGIS caso nenhuma esteja presente.

### 6.5 Configurações Internas — Tabela `sig_bus_config`
Gerenciada por `set_config` e `get_config` em `gtfs_builder_core.py`:
*   Tabela relacional em SQLite de chave-valor (`chave TEXT PRIMARY KEY, valor TEXT`).
*   Armazena `build_city`, `build_state`, `build_country` e a caixa envolvente `build_city_viewbox`.
*   Totalmente isolada do feed GTFS exportado (não consta na whitelist de exportação).

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
    *   Configuração da operação horária da linha baseada em frequências (início, fim, intervalo e **duração da viagem**).
    *   **Ajuste fino no diagrama** (Fase 12): a mesma página traz uma `BlockView`/`BlockScene` em Modo Viagens sobre a grade em memória (`self.build_stop_times`), com passo configurável, legenda dos atalhos, rótulo dos dias do calendário e botão "Restaurar frequência regular".
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


---

## 9. AJUSTE FINO DE HORÁRIOS (Fase 12 — decisões 71-81)

Na operação real o intervalo encurta no pico e alarga fora dele, então a
frequência única propagada para o dia inteiro não basta. O ajuste acontece
**antes de gravar**, sobre a grade que o assistente já monta em memória.

### 9.1 Decisões

*   **71 — O ajuste é etapa do assistente, não uma segunda tela de edição do
    `feed_edit.gpkg`.** Opera sobre `self.build_stop_times`/`self.build_trips`,
    antes de qualquer gravação. Ajustar depois, na aba "Edição GTFS", continua
    possível (decisão 23) — só deixa de ser o único caminho.
*   **72 — Um conjunto de viagens por `service_id`; o `calendar` é quem
    multiplica pelos dias.** Não existe cópia de viagem por dia da semana: um
    `>` ali mexe nos cinco dias de uma vez. O que a Fase 12 acrescenta é a tela
    **dizer isso** (rótulo "Estas N viagens valem para: seg, ter, ...").
*   **73 — Reaproveitar `BlockScene`/`BlockView`/`block_core.Trip`.** A geometria,
    o eixo de tempo, as faixas, as cores e a exportação PNG/SVG continuam sendo o
    código do Diagrama de Blocos; a Fase 12 só acrescenta edição.
*   **74 — Núcleo de edição puro em `schedule_edit_core.py`, sem Qt.** Extensão da
    decisão 31: deslocar viagem, deslocar extremo, resumir a grade, calcular
    headway e validar são funções sobre listas de dicionários de `stop_times`,
    verificáveis por `pytest` fora do QGIS (`test_schedule_edit_core.py`).
*   **75 — O headway vira cota e vale nos dois modos.** `_show_headway` não sai
    mais cedo em Modo Viagens; a diagonal entre centros de barra deu lugar a uma
    cota horizontal com linhas de chamada verticais.
*   **76 — Os atalhos são lidos por `event.text()`, não por keycode**, porque `>`
    e `<` ficam em teclas diferentes em ABNT2 e US-International.
    `Key_Plus`/`Key_Minus` do teclado numérico são aceitos em adição.
*   **77 — O passo do deslocamento é configurável, com 15 min de padrão.**
*   **78 — `>`/`<` movem só o extremo selecionado e re-interpolam o miolo;
    `+`/`-` movem a viagem inteira.** O clique escolhe a viagem **e** o extremo
    mais próximo do X clicado. A sequência de horários nunca decresce, e um
    deslocamento que inverteria saída e chegada é recusado (a função devolve a
    grade original).
*   **79 — Cada tecla redesenha a cena inteira via `set_schedule`.** Uma linha tem
    dezenas de viagens, não milhares: reconstruir o `Schedule` é mais simples e
    menos sujeito a estado inconsistente que mutar item a item. A seleção
    (viagem + extremo) é restaurada logo depois do redesenho.
*   **80 — `save_route` ganha `stop_times=None`: sem o parâmetro, nada muda.**
*   **81 — Viagem precisa ter duração > 0 e `trip_id` único.**

### 9.2 Módulo `schedule_edit_core.py`

Funções puras (sem Qt no nível do módulo; `block_core` só é importado sob demanda
dentro de `schedule_from_draft`):

| Função | Papel |
|---|---|
| `expand_frequency_to_stop_times(stop_ids, hora_inicio, hora_fim, intervalo_min, duracao_min=None, prefix=None)` | Gera a grade regular. `duracao_min` distribui os horários linearmente entre as paradas (antes toda parada recebia o mesmo horário — barra de largura zero); `prefix` compõe `trip_<prefix>_<HHMMSS>`, evitando a colisão de `trip_id` entre linhas que saem no mesmo horário. Sem os dois, o comportamento anterior é preservado. |
| `trips_from_stop_times(stop_times)` | Resume a grade em `{trip_id, start_s, end_s, n_stops}`, em ordem de saída. |
| `headways(stop_times)` | `{trip_id: headway_s}` em relação à viagem anterior **na ordem da grade** — headway negativo denuncia ordem trocada por um ajuste. |
| `shift_trip(stop_times, trip_id, delta_s)` | `+`/`-`: move a viagem inteira, preservando a duração. Recusa o que iria para antes de `00:00:00`; horários acima de 24 h são mantidos (o GTFS permite). |
| `shift_trip_endpoint(stop_times, trip_id, endpoint, delta_s)` | `>`/`<`: move só `'first'` (saída) ou `'last'` (chegada) e redistribui linearmente as paradas intermediárias. Recusa o cruzamento dos extremos. |
| `validate_draft_times(stop_times)` | Devolve `(erros, avisos)`. Erro bloqueia o avanço; aviso só pede confirmação. |
| `schedule_from_draft(stop_times, route_short_name, direction_id, service_id, trip_headsign)` | Converte a grade num `block_core.Schedule` (`mode='trips'`) para a cena desenhar — sem tocar em `sqlite3`. O `ScheduleReader` continua sendo o único caminho para o diagrama que lê do GeoPackage. |

Todas devolvem listas novas: a grade de entrada nunca é mutada.

### 9.3 Contrato novo de `save_route`

`save_route(gpkg_path, agency, linha, paradas, service, frequencia, stop_times=None)`.

Sem `stop_times`, nada muda: a função expande `frequencia` como antes (agora
repassando `duracao_min` e o prefixo de `trip_id`). Com `stop_times`, grava
**exatamente** aquelas linhas, derivando a lista de viagens dos `trip_id`
distintos na ordem de saída — é o que impede o `DELETE` + reexpansão de apagar o
ajuste manual no "Salvar Linha". O `DELETE` prévio das viagens da rota continua
igual.

---

## 10. FAIXAS HORÁRIAS E AJUSTE NO FEED (Fase 17 — decisões 109-126)

### 10.1 Novas funções puras de `schedule_edit_core.py`

| Função | Papel |
|---|---|
| `validate_bands(faixas)` | `(erros, avisos)` das faixas horárias **antes** de expandir: `fim < início`, intervalo ≤ 0, duração ≤ 0 e **sobreposição** entre faixas são erro, com a mensagem nomeando a faixa (decisão 123). Vão entre faixas é legítimo e passa. |
| `expand_bands_to_stop_times(stop_ids, faixas, prefix=None)` | Expande N faixas (`dict` ou tupla), cada uma com seu intervalo e sua **duração** (decisão 120), reusando `expand_frequency_to_stop_times` por faixa. Percorre em ordem cronológica e descarta a saída cujo horário já foi gerado, para a fronteira entre faixas não duplicar viagem (decisão 122). Uma faixa reproduz exatamente a grade da expansão simples. |
| `diff_stop_times(original, atual)` | Compara duas grades de `stop_times` casando as linhas por `(trip_id, stop_sequence)` e devolve **só as linhas alteradas** (`arrival_time`/`departure_time` diferentes) — linha nova ou ausente é ignorada, porque a tela não cria nem apaga viagem. Diferença pura, sem I/O, que isola "o que gravar" do widget que exibe a grade. Recebe listas de `dict`. |

`save_route` passa a aceitar `frequencia` como **lista de faixas**, além do
`dict` e da tupla que já aceitava (decisão 124); o caminho com `stop_times`
explícito continua com precedência sobre os três.

### 10.2 Módulo `schedule_table_core.py` (Core, sem Qt)

Monta a matriz de horários de uma linha — paradas nas linhas, viagens nas
colunas — que a janela "Ajustar horários" da aba "Edição GTFS" exibe:

| Função | Papel |
|---|---|
| `build_schedule_table(stop_times, stops=None, ...)` | Devolve um `ScheduleTable` com `stops` (ordenadas pela sequência média observada), `trips` (ordenadas pela saída) e `matrix[(stop_id, trip_id)]`. |
| `ScheduleTable.to_grid(time_format, empty_cell)` | Converte em `(cabeçalhos, linhas)` de strings, prontos para a tabela da tela. |
| `format_time_str(valor, fmt)` | Normaliza `HH:MM`/`HH:MM:SS`, preservando horário GTFS acima de 24 h. |

### 10.3 Acesso ao `feed_edit.gpkg` em `gtfs_edit_core.py`

| Função | Papel |
|---|---|
| `load_route_stop_times(gpkg_path, route_short_name, service_id=None)` | `{direction_id: {"trip_headsign", "stop_times"}}` por `routes` → `trips` → `stop_times`, **sempre filtrado por linha** (decisões 5 e 117). |
| `apply_stop_times(gpkg_path, stop_times)` | `UPDATE stop_times SET arrival_time=?, departure_time=? WHERE trip_id=? AND stop_sequence=?` numa única transação, com `rollback` em erro (decisão 118). Nada é apagado nem inserido, nenhum id é reescrito. |

A tela grava só as células realmente editadas e preserva o tempo parado
(`departure - arrival`) de cada parada; antes de gravar, a grade passa pelo
mesmo `validate_draft_times` do assistente, e o `GtfsValidator` ganhou a
checagem de horário fora de ordem dentro da mesma viagem (decisão 6: um
validador só, nunca um paralelo).

### 10.3.1 A tabela de horários: `schedule_grid_widget.py` (UI)

`ScheduleGridWidget` é um `QTableWidget` que **é** a matriz de horários — a
metade direita do `ScheduleEditorWidget` (§10.3.2), uma instância por sentido.
Monta a grade com `build_schedule_table()` + `to_grid(time_format="HH:MM:SS")`, trava
a coluna 0 (`Parada`) como somente leitura e deixa editáveis as colunas de
viagem, cujo cabeçalho mostra `V<n>` na primeira linha e a primeira saída da
viagem em `HH:MM` na segunda, com o `trip_id` completo no tooltip.

| Método | Papel |
|---|---|
| `collect_changes()` | Compara a grade na tela com a `matrix` original e devolve `(alterados, grade_validacao, ilegiveis)`: as linhas de `stop_times` a gravar, a grade completa para `validate_draft_times` e os horários fora do formato. Preserva o tempo parado da parada (`departure - arrival`), que anda junto com a saída (decisão 118). Célula sem par `(stop_id, trip_id)` na matriz — a que aparece como `-` — é ignorada, então digitar nela não cria parada nova na viagem. |

`collect_changes()` é a comparação célula a célula do próprio
`ScheduleGridWidget`, usada por quem monta a matriz sozinha. Quem hoje agrega
para o "Aplicar ao feed" é o `ScheduleEditorWidget` (§10.3.2), por
`changed_rows()`/`validation_rows()`;
`SigBus_dialog._open_schedule_edit_dialog()` só soma o que cada aba devolve e
faz o `validate_draft_times` → `apply_stop_times`.

### 10.3.2 O editor de horários: `schedule_editor_widget.py` (UI)

`ScheduleEditorWidget` é o **editor único das duas telas**: a página
"Horários" do assistente "Construir GTFS" e a janela "Ajustar horários" da
aba "Edição GTFS" instanciam o **mesmo** widget, em vez de cada tela manter
sua própria implementação. Monta num `QSplitter` horizontal, à esquerda, o
diagrama de blocos (`BlockView`/`BlockScene`) com o `QSpinBox` de passo, o
botão "Enquadrar tudo" e um rótulo de status; à direita, a matriz paradas ×
viagens (`ScheduleGridWidget`). Os dois lados são vistas do **mesmo** rascunho
de `stop_times` em memória, e há um caminho de escrita só: os atalhos do
diagrama (`>`/`<` movem a saída ou a chegada da viagem selecionada; `+`/`-`
movem a viagem inteira) e a célula editada na matriz desembocam nas mesmas
`shift_trip`/`shift_trip_endpoint` de `schedule_edit_core.py`. Depois de cada
mudança o diagrama é redesenhado preservando o enquadramento
(`viewport_state`/`restore_viewport`, §10.4) e a matriz é remontada a partir
do rascunho.

**As faixas de frequência não estão no widget (decisão 141):** a tabela de
faixas, "Adicionar faixa"/"Remover faixa" e "Restaurar frequência regular"
continuam só na página "Horários" do assistente — são do assistente, que gera
oferta do zero, e não do editor, que ajusta uma oferta que já existe.

Quem decide o que gravar é `changed_rows()`, que usa a função pura
`diff_stop_times(original, atual)` (§10.1) — casa as linhas por `(trip_id,
stop_sequence)` e devolve só as que tiveram `arrival_time`/`departure_time`
alterados frente ao `stop_times` como veio do `feed_edit.gpkg`; linha nova ou
ausente é ignorada, porque esta tela não cria nem apaga viagem.

### 10.4 Fronteira UI × lógica pura

`BlockView.viewport_state()` / `restore_viewport()` guardam e reaplicam a
transformação e o centro de cena (decisão 110); quem decide entre preservar e
enquadrar é o chamador em `SigBus_dialog.py` (decisão 111). A view continua sem
conhecer o modelo, e o `fit_all()` do `block_diagram_dialog.py` fica como está
(decisão 109).
