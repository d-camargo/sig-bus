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

## 0.8 — Editor único de horários (diagrama + matriz), retorno automático da janela e guardas na edição

Esta versão entrega, de fato, o `ScheduleEditorWidget`: o ciclo da 0.7 deu a peça como pronta sem que ela existisse no repositório — nenhum arquivo, nenhuma menção (decisão 133). Aqui ela é escrita, e vira o editor de horários único das duas telas: a página "Horários" do assistente **Construir GTFS** e a janela "Ajustar horários" da aba **Edição GTFS** passam a compartilhar o mesmo componente, em vez de duas implementações paralelas. Além disso, o fluxo de edição no QGIS fica mais seguro contra descarte acidental de trabalho, e a matriz de horários fica mais legível para quem não decorou o `trip_id`.

### O editor único: diagrama e matriz sobre o mesmo rascunho (decisões 139 e 141)

- **Um widget, duas telas.** `sig_bus/schedule_editor_widget.py` monta num `QSplitter` horizontal o diagrama de blocos (`BlockView`/`BlockScene`, com o `QSpinBox` de passo, o botão "Enquadrar tudo" e um rótulo de status) à esquerda e a matriz paradas × viagens (`ScheduleGridWidget`) à direita. Os dois lados são vistas do mesmo rascunho de `stop_times` em memória, e há um caminho de escrita só: os atalhos do diagrama (`>`/`<` movem a saída ou a chegada da viagem selecionada; `+`/`-` movem a viagem inteira) e a célula editada na matriz desembocam nas mesmas `shift_trip`/`shift_trip_endpoint` de `schedule_edit_core.py`. Depois de cada mudança o diagrama é redesenhado preservando o enquadramento (`viewport_state`/`restore_viewport`, decisões 109-111 da 0.7) e a matriz é remontada a partir do rascunho.
- **As faixas de frequência não migraram (decisão 141).** A tabela de faixas horárias, "Adicionar faixa"/"Remover faixa" e "Restaurar frequência regular" continuam só na página "Horários" do assistente — são do assistente, que gera oferta do zero, e não do editor, que ajusta uma oferta que já existe.

### O que grava é o diff, nunca a grade inteira (decisões 140 e 118)

- `changed_rows()` usa a função pura `diff_stop_times(original, atual)` de `schedule_edit_core.py`, que casa as linhas por `(trip_id, stop_sequence)` e devolve só aquelas em que `arrival_time` ou `departure_time` mudaram frente ao `stop_times` como veio do `feed_edit.gpkg`. Linha nova ou ausente é ignorada — esta tela não cria nem apaga viagem. Grade sem edição nenhuma não gera nenhum `UPDATE`.
- **Mudança de comportamento na matriz (decisão 112):** editar uma célula agora desloca a viagem inteira — o usuário digita o horário que quer naquela parada e o resto da viagem acompanha, preservando os tempos de percurso entre paradas — em vez de gravar aquela célula isolada, como fazia a versão anterior.

### Cabeçalho legível da matriz (decisões 135 e 136)

- Cada coluna de viagem passa a se chamar `V<n>` na primeira linha do cabeçalho e traz a primeira saída da viagem em `HH:MM` na segunda (ex.: `"V1\n06:10"`), com o `trip_id` completo só no tooltip — ninguém precisa mais decorar um `trip_id` para achar a viagem certa.
- A primeira coluna, "Parada", passa a trazer o nome da parada (`stop_name`, caindo no `stop_id` quando o feed não tem nome) em vez do `stop_id` cru, com o `stop_id` no tooltip. O nome vem de um `LEFT JOIN stops` acrescentado na própria consulta que monta a matriz.

### Guardas contra perda de trabalho no fluxo de edição (decisões 137, 138 e 142)

- **A cópia de trabalho do assistente nasce sob demanda (decisão 137).** Antes, só entrar na aba "Construir GTFS" já criava `feed_edit.gpkg`. Agora a criação foi movida para `_ensure_build_working_copy()`, em `SigBus_dialog.py`, chamado só no primeiro ponto que de fato grava algo (salvar a agência) e no guarda da página "Paradas" — espiar a aba não cria mais cópia nenhuma.
- **"Entrar no modo edição" nunca fica desabilitado (decisão 138).** Com uma edição ativa, o rótulo de status passa a dizer de qual arquivo a cópia veio (por exemplo, "Edição em andamento: feed_edit.gpkg (cópia de bhtrans.gpkg)") ou avisa que é a cópia vazia criada pelo assistente, e a pergunta ao reentrar explicita o que cada resposta faz: "Sim" recria a partir do GTFS carregado (o que não tiver sido exportado se perde), "Não" retoma a edição atual.
- **"Abrir para edição" devolve o plugin sozinho (decisão 142).** A janela do SIG-Bus passa a se esconder (`hide()`, não `close()`) em vez de fechar, e volta (`show()`/`raise_()`/`activateWindow()`) quando a tabela de atributos do QGIS fecha (e, se a API do QGIS não devolver esse diálogo, quando a edição da camada termina). Na volta, se a camada ainda tiver alterações não gravadas no buffer de edição, o plugin pergunta se grava (`commitChanges()`) ou mantém a camada em edição.

#### Arquivos tocados

`schedule_editor_widget.py` (novo), `test_schedule_editor_widget.py` (novo), `test_edit_tab_guards.py` (novo), `SigBus_dialog.py`, `gtfs_edit_core.py`, `schedule_edit_core.py`, `schedule_grid_widget.py`, `schedule_table_core.py`, `test_gtfs_edit_stop_times.py`, `test_schedule_edit_core.py`, `test_schedule_table_core.py`, `metadata.txt`, `CHANGELOG.md`, `GUIA_EDICAO_GTFS.md`, `ARQUITETURA_CONSTRUIR_GTFS.md`, `DIAGRAMA_BLOCOS.md`.

---

## 0.7 — Ajuste de horários: zoom preservado, faixas horárias e edição no feed

Versão focada no **ajuste de oferta**: o que a 0.5 abriu (deslocar viagem no
Diagrama de Blocos com `>`/`<`/`+`/`-`) vira uma tela de trabalho de verdade —
com o enquadramento que não se perde a cada tecla, faixas horárias por período
do dia e o ajuste de horários disponível também para um feed **já carregado**,
não só para o que o assistente acabou de criar.

Do ponto de vista de **transporte público**, é a diferença entre desenhar uma
oferta uniforme e desenhar a oferta real: intervalo e **duração de viagem**
passam a variar por faixa (pico manhã / entrepico / pico tarde), que é o que o
Diagrama de Blocos usa para estimar frota — manter a duração fixa no pico
produz um `stop_times` que subestima o tempo de ciclo. E o ajuste fino deixa de
ser exclusivo de feed novo: dá para abrir uma linha do feed em edição, mexer
nos horários e gravar de volta.

### O zoom não se perde a cada ajuste (decisões 109-111)

- **A culpa era do redesenho, não do zoom.** `_render_schedule_diagram()`
  terminava chamando `fit_all()` (`resetTransform()` + `fitInView()`), então
  cada tecla de nudge reenquadrava o diagrama inteiro e jogava fora o zoom que
  o usuário tinha acabado de dar na viagem que estava olhando. O redesenho
  passa a **preservar** o enquadramento corrente; enquadrar tudo virou ação
  explícita, no botão **"Enquadrar tudo"** ao lado do "Passo".
- **Preserva transformação e posição, não só a escala (decisão 110)**:
  `BlockView` ganhou `viewport_state()` / `restore_viewport()`, que guardam a
  `QTransform` e o **centro em coordenadas de cena**. Guardar só o fator de
  escala devolveria o zoom certo no lugar errado, já que a view usa
  `AnchorUnderMouse` e uma viagem deslocada pode esticar o `sceneRect`.
- **Primeiro desenho enquadra, os seguintes preservam (decisão 111)**: a regra
  mora no chamador — sem estado anterior (cena vazia, primeira entrada na
  página, "Restaurar frequência regular"), `fit_all()`; com estado anterior,
  `restore_viewport()`. A `BlockView` continua sem conhecer o modelo.

### Faixas horárias no "Construir GTFS" (decisões 119-125)

- **Faixas substituem o par único de hora início/fim (decisão 119)**: a página
  de horários agora tem uma tabela de faixas (`Início`, `Fim`, `Intervalo`,
  `Duração`), que começa com **uma** linha preenchida com os valores de sempre
  (06:00→23:00, 30 min de intervalo, 30 min de duração). Quem não quer
  desagregar não muda nada no que faz, e uma faixa reproduz exatamente a grade
  que a 0.6 gerava.
- **A duração da viagem também é por faixa (decisão 120)**: no pico o mesmo
  percurso demora mais, e é essa duração que vira tempo de ciclo no Diagrama de
  Blocos.
- **A UI oferece até 3 faixas; a função pura não impõe limite (decisão 121)**:
  "Adicionar faixa" para no terceiro item — pico manhã / entrepico / pico tarde
  —, mas `schedule_edit_core.expand_bands_to_stop_times()` aceita N faixas, em
  `dict` ou tupla.
- **Fronteira de faixa não duplica saída (decisão 122)**: com faixas
  `06:00–09:00` e `09:00–16:00`, a saída das 09:00 seria gerada duas vezes —
  fim inclusivo de uma, início da outra —, criando duas viagens no mesmo
  horário. A expansão percorre as faixas em ordem cronológica e descarta a
  saída já gerada; a faixa mais cedo é quem vence.
- **Faixas sobrepostas são erro, não aviso (decisão 123)**:
  `schedule_edit_core.validate_bands()` reprova sobreposição, `fim < início`,
  intervalo ≤ 0 e duração ≤ 0 **antes** de expandir, com a mensagem nomeando a
  faixa ("faixa 2 (09:00–16:00) sobrepõe a faixa 1"). Buraco entre faixas é
  legítimo — linha que não opera no entrepico — e passa sem reclamar.
- **`save_route` aceita as três formas de `frequencia` (decisão 124)**: lista
  de faixas (nova), `dict` e tupla (as duas já suportadas) continuam
  funcionando; o caminho normal do assistente nem passa por lá, porque manda
  `stop_times` já ajustado.
- **`_draft_signature` passa a enxergar as faixas (decisão 125)**: é essa
  assinatura que decide se a grade em memória é regerada ou preservada — sem
  as faixas, mexer numa faixa não regeraria nada e a tela mostraria a oferta
  antiga. O resumo da página soma as viagens de todas as faixas e mostra a
  amplitude do intervalo (ex.: "34 viagens · intervalo de 10 a 30 min").

### Ajustar horários de um feed já carregado (decisões 117-118)

- **Botão "Ajustar horários" na aba "Edição GTFS"** (habilitado só com edição
  ativa e uma linha escolhida), que abre a **matriz de horários** daquela
  linha: uma aba por sentido, paradas nas linhas, viagens nas colunas, os
  horários digitados direto na célula. A matriz é montada pelo núcleo puro
  `schedule_table_core.py` (`build_schedule_table`), sem Qt.
- **Leitura sempre filtrada por linha (decisão 117)**:
  `gtfs_edit_core.load_route_stop_times(gpkg, route_short_name, service_id=None)`
  vai de `route_short_name` (+ `service_id` opcional) → `trips` → `stop_times`
  daquelas viagens, e nada mais. A decisão 5 (nunca carregar `stop_times`
  inteiro) vale igual aqui: num feed real como o da BHTrans essa tabela tem
  milhões de linhas.
- **Gravação é `UPDATE` por (`trip_id`, `stop_sequence`), em transação
  (decisão 118)**: `gtfs_edit_core.apply_stop_times()` altera só
  `arrival_time`/`departure_time`, **e só das células realmente editadas** — o
  tempo parado de cada parada (`departure - arrival`) anda junto com a saída,
  em vez de ser achatado. Nenhuma linha é apagada e nenhum id é reescrito — o
  feed é de terceiros e as viagens carregam `shape_id`, `block_id` e o que mais
  o feed trouxer —, e erro no meio faz `rollback`. Antes de gravar, a grade
  ajustada passa pelo mesmo `validate_draft_times` do assistente: erro bloqueia,
  aviso pergunta; "Cancelar" não toca no arquivo.
- **O validador aprendeu horário fora de ordem**: `GtfsValidator` passa a
  apontar, por SQL agregado, a viagem cuja chegada numa parada é anterior à
  partida da parada anterior — a falha que um ajuste de horário pode introduzir
  e que nenhuma das checagens de formato pegava (decisão 6: um validador só).

### Ainda não entregue nesta versão

O painel lateral de horários **por sentido** ao lado do diagrama (decisões
112-115) e o widget único de edição compartilhado entre o assistente e a aba
"Edição GTFS" (decisão 116) **não** entraram na 0.7: o ajuste no assistente
continua sendo pelo diagrama e pelos atalhos, e na aba de edição é pela matriz
descrita acima. Ficam para a versão seguinte.

### Versão e documentação (decisões 103, 126)

A versão sobe para **0.7** — a fase acrescenta funcionalidade nas duas abas, não
é correção (mesmo critério das decisões 85 e 92). O `.zip` continua fora do
plano (decisão 94): empacotar segue sendo ritual manual. `README.md` (nas duas
metades, EN e PT-BR, no mesmo passo — decisão 103), `DIAGRAMA_BLOCOS.md`,
`GUIA_CONSTRUIR_GTFS.md` e `GUIA_EDICAO_GTFS.md` foram atualizados junto.

#### Arquivos tocados

`schedule_table_core.py` (novo), `schedule_grid_widget.py` (novo),
`schedule_edit_core.py`,
`gtfs_edit_core.py`, `gtfs_validator.py`, `gtfs_builder_core.py`,
`block_view.py`, `SigBus_dialog.py`, `metadata.txt`, `README.md`,
`DIAGRAMA_BLOCOS.md`, `GUIA_CONSTRUIR_GTFS.md`, `GUIA_EDICAO_GTFS.md`,
`CHANGELOG.md`, `test_block_view_zoom.py` (novo),
`test_schedule_table_core.py` (novo), `test_gtfs_edit_stop_times.py` (novo),
`test_schedule_edit_core.py`, `test_gtfs_builder_progress.py`,
`test_block_scene_headway.py`.

---

## 0.6 — Leitura do Diagrama de Blocos: cota enxuta e régua de saídas

Duas mudanças de **leitura** no Diagrama de Blocos, pedidas depois de usar o
ajuste fino de horários da 0.5. Nenhuma delas muda dado: as duas só mudam o que
o diagrama conta a quem olha.

Do ponto de vista de **transporte público**, a régua de saídas é a leitura que o
quadro de horários não dá de graça: **quantas partidas por faixa horária,
separadas por sentido** — exatamente o que se olha para decidir se o pico está
coberto e se o intervalo entre-pico está frouxo.

- **A cota mostra só a medida (decisão 96)**: o rótulo do indicador de headway
  era `headway 12 min`; agora é `12 min`. Numa cota de desenho técnico o que se
  lê é a medida — o que ela mede já está dito pela geometria (duas chamadas
  verticais partindo de dois inícios da mesma linha e sentido). De quebra, o
  rótulo curto cabe entre duas viagens próximas sem invadir a barra vizinha.
- **Régua de saídas na base do diagrama (decisões 97-101)**: um traço vertical
  curto e discreto por partida, **ida na banda de cima e volta na de baixo**, no
  pé do eixo de tempo. A mancha de traços mostra pico e vale por sentido sem
  precisar varrer o diagrama faixa por faixa. É derivada dos mesmos
  `start_time_s` que desenham as barras (`departure_ticks`), então nasce correta
  e acompanha qualquer deslocamento feito por `>`/`<`/`+`/`-`. Não é histograma,
  não é clicável e não distingue linha; por ser item de cena, sai no PNG/SVG
  exportado.

---

## 0.5.1 — Faixa de versões do QGIS: o plugin recusado no 4.2 e no 3.34

Correção de **empacotamento**, não de lógica: nas duas pontas da faixa
declarada, o gerenciador de complementos recusava um plugin que o código já
suportava.

- **O teto barrava o QGIS 4.2 (decisão 82)**: a 0.5 prometeu
  `qgisMaximumVersion=4.99` e gravou `3.99`. O gerenciador mostrava *"Plugin
  designed for QGIS 3.40 - 3.99"* e marcava o plugin como incompatível em todo
  QGIS 4.x — apesar de a compatibilidade Qt6 já estar feita e testada.
  Vale lembrar por que a chave não pode simplesmente sumir: **ausente**, o QGIS
  assume `<major do mínimo>.99`, ou seja o mesmo 3.99 que causou o problema.
- **O piso excluía o QGIS 3.34 (decisões 87-89)**: `qgisMinimumVersion=3.40` não
  descrevia requisito nenhum do plugin — existia por causa de **uma linha**,
  `FIELD_STRING = QMetaType.Type.QString`, já que `QgsField(nome,
  QMetaType.Type)` só existe a partir do 3.38. A sondagem contra o 3.34.4 real
  mostrou que **todo** o resto (enums qualificados, `writeAsVectorFormatV3`,
  roteamento, import dos módulos) já roda lá. O tipo de campo agora é resolvido
  **por capacidade** (`_resolve_field_types`, com fallback para `QVariant`), e o
  piso desce para o LTR 3.34 que o Ubuntu 24.04 empacota.
- **Faixa final: 3.34 – 4.99**, com guarda em `test_metadata.py` (comparando por
  tupla de inteiros — em ordem lexicográfica `'3.99' > '4.99'`) e sondagem
  manual contra o QGIS instalado via `sig_bus/scripts/check_qgis_compat.py`.
- **O CHANGELOG não fica mais aberto (decisão 93)**: um teste falha se sobrar
  seção "Não lançado" ou se a primeira seção de versão não casar com o
  `version=` do `metadata.txt` — foi assim que as Fases 7 a 12 ficaram
  publicadas sob "Não lançado" com a 0.5 já no ar.

---

## 0.5 — Construir GTFS, geocodificação e ajuste fino de horários

*(Seções abaixo: entraram todas na 0.5, publicada sem que o CHANGELOG fosse
fechado — daí a guarda da 0.5.1.)*

### Ajuste fino dos horários no Diagrama de Blocos (Fase 12)

A página "Horários" do assistente "Construir GTFS" pedia um único intervalo e o propagava igual para o dia inteiro. Na operação real o intervalo encurta no pico e alarga fora dele — esta fase permite acertar **viagem a viagem** ainda no bloco de construção, antes de a linha virar dado gravado, reaproveitando o Diagrama de Blocos que o plugin já tem.

Do ponto de vista de **transporte público**, é a diferença entre um quadro de horários teórico (frequência constante das 5h às 23h) e o quadro que a operação realmente pratica. E o ajuste é feito onde ele custa menos: antes da gravação, sem precisar abrir a tabela crua de `stop_times` depois.

- **Duração da viagem (decisão 81a)**: `expand_frequency_to_stop_times` ganhou `duracao_min`. Antes, **todas** as paradas de uma viagem recebiam o mesmo horário — viagem de duração zero, sem chegada para deslocar e com `arrival_time == departure_time` na última parada. Agora os horários são distribuídos linearmente entre a primeira e a última parada. Sem o parâmetro, o comportamento antigo é preservado.
- **`trip_id` único por linha e sentido (decisão 81b)**: o id gerado era `trip_<HHMMSS>`, sem linha nem sentido — duas linhas que saem 06:00 produziam o mesmo `trip_id`, e o editor indexa viagem por `trip_id`. O parâmetro `prefix` compõe `trip_<linha>_<sentido>_<HHMMSS>`.
- **Núcleo puro `schedule_edit_core.py` (decisão 74)**: deslocar viagem (`shift_trip`), deslocar extremo com re-interpolação do miolo (`shift_trip_endpoint`), resumir a grade (`trips_from_stop_times`), calcular intervalos (`headways`), validar (`validate_draft_times` → `(erros, avisos)`) e montar o `Schedule` da cena (`schedule_from_draft`) — tudo sobre listas de dicionários, sem Qt, coberto por `test_schedule_edit_core.py`.
- **Atalhos de teclado (decisões 76-78)**: `>`/`<` movem só a saída **ou** só a chegada (o clique na metade esquerda/direita da barra escolhe qual) e redistribuem as paradas intermediárias; `+`/`-` movem a viagem inteira preservando a duração. As teclas são lidas por `event.text()` — `>` e `<` ficam em teclas diferentes em ABNT2 e US-International. O passo é configurável (padrão 15 min).
- **Headway vira cota de desenho técnico (decisão 75)**: era uma diagonal entre os centros de duas barras em sub-linhas diferentes; agora é uma linha horizontal com linhas de chamada verticais até os dois inícios e o valor no meio — e passa a valer também no Modo Viagens, que é o modo da página de ajuste.
- **Gravar não apaga mais o ajuste (decisão 80)**: `save_route` ganhou `stop_times=None`. Com a grade ajustada, grava exatamente aquelas linhas em vez de reexpandir a frequência; sem o parâmetro, nada muda para quem já chamava a função.
- **Um ajuste vale para todos os dias do calendário (decisão 72)**: no GTFS um único conjunto de viagens já atende os cinco dias úteis — quem diz "seg a sex" é o `calendar`. O comportamento já era esse; o que faltava era a tela dizer isso, e agora um rótulo acima do diagrama lista os dias.

---

### Google Maps opcional + Overpass como último degrau grátis (Fase 11)

Esta fase adiciona o suporte opcional à **Google Geocoding API** como primeiro provedor de geocodificação e introduz o corretor de grafia via **Overpass (OSM)** como último recurso para resolver nomes de vias digitados incorretamente.

Do ponto de vista de **transporte público**, a integração com o Google resolve casos de endereços recém-criados, estabelecimentos ou locais comerciais que ainda não figuram nas bases públicas do OpenStreetMap, garantindo que o assistente de construção de GTFS encontre o ponto com alta precisão sem depender exclusivamente de coordenadas manuais.

- **Google Geocoding API opcional (Decisões 62, 63, 66)**: Quando uma chave de API é fornecida e o modo está em `auto`, o `GoogleGeocoder` é acionado primeiro na cascata `Google → Nominatim → Photon`. A chave é armazenada com segurança no `QSettings` do usuário e não é salva no GeoPackage do projeto (Decisão 62). Candidatos em nível genérico de localidade/município são automaticamente filtrados para evitar posicionamento incorreto no centro da cidade (Decisão 66).
- **Corretor de vias Overpass (`street_index.py`, Decisão 68)**: Se todos os provedores retornarem vazio e houver contexto de município, o módulo realiza o levantamento das vias reais da região via Overpass e utiliza busca por similaridade textual (`difflib`, `cutoff=0.80`) para corrigir o logradouro e refazer **uma** consulta ao Nominatim com o nome corrigido — que resolve o número da casa; se ela também falhar, o ponto sai do `center` da via, sempre com o `(via: <nome real>)` da decisão 59 declarando o palpite.
- **Redação de credenciais em logs (`_redigir_credenciais`, Decisão 65)**: Parâmetros sensíveis (`key=`, `api_key=`, `token=` e afins) são ocultados com `***` nas mensagens gravadas no log do QGIS, prevenindo o vazamento de chaves privadas em relatórios de suporte.
- **Identificação da procedência do ponto (Decisão 70)**: Rótulos de status na UI informam a origem exata do resultado (`✓ localizado (Google)`, `✓ localizado (Nominatim)`, `✓ localizado (Photon)` ou `✓ localizado (via: ... — OSM)`).

---

### O Nominatim não perdoa erro de digitação (Fase 10)

Depois das correções da Fase 9 a requisição saía e o log provava isso — e mesmo
assim o botão **Geocodificar** continuava devolvendo "não encontrado". A medição
de 2026-08-05, reproduzindo as URLs do log contra a API pública uma variável por
vez, isolou a causa: `viewbox`, `bounded=1`, número da casa e acentuação são
todos indiferentes; a única variável que zera o resultado é a **grafia do
logradouro**. `Rua Giusepe Fórmolo` (um `p` a menos que o `Giuseppe` real do
OpenStreetMap) devolve **0 candidatos**, na busca estruturada e na livre. A
causa deixou de ser técnica e passou a ser de dado — e as seis tentativas da
cascata falhavam juntas porque eram o mesmo motor consultado seis vezes.

Do ponto de vista de **transporte público**, isso é o caso comum: o itinerário
vem de planilha ou de papel da operadora, digitado por gente, e um nome de rua
de origem italiana (`Giuseppe Fôrmolo`, na serra gaúcha) erra fácil. Sem
tolerância a typo, o cadastro de paradas por endereço simplesmente não sai do
lugar.

- **Photon como último degrau da cascata (Decisão 57)**: o
  `photon.komoot.io` é o geocodificador do Komoot sobre os **mesmos dados do
  OSM**, público, sem chave e tolerante a erro de digitação por construção.
  Verificado: `q=Rua Giusepe Fórmolo` + bbox de Caxias do Sul traz
  `Rua Giuseppe Fôrmolo` em 1º e 2º lugar. O Nominatim **não** foi substituído —
  continua sendo quem faz busca estruturada e resolve número de casa; o Photon
  só é consultado depois de a cascata inteira ter voltado vazia. Uma requisição
  a mais apenas no caso que hoje falha, zero custo no caminho feliz. Dois
  detalhes medidos viraram código: `lang=pt` devolve HTTP 400 (não enviar
  `lang`), e a `bbox` do Photon é `minLon,minLat,maxLon,maxLat` — ordem
  **diferente** do `viewbox` do Nominatim já gravado em `build_city_viewbox`.
- **Transporte separado de interpretação (`geocoding.py`)**: `_get_json(url)`
  faz a requisição, respeita o intervalo de 1 s e devolve o JSON decodificado
  (`list` **ou** `dict`); `_buscar` virou uma casca fina sobre ele para o
  formato do Nominatim, e o `PhotonGeocoder` tem a sua, para o GeoJSON do
  Photon — que é normalizado no mesmo dicionário `lat`/`lon`/`display_name` que
  a UI já consome.
- **Correção de grafia nunca é silenciosa (Decisão 59)**: quando o logradouro do
  candidato aceito difere do digitado, o status da parada vira
  `✓ localizado (via: <nome real>)` em vez de `✓ localizado`, e o par vai para o
  log `SIG-Bus`. A mesma resposta do Photon trouxe `Rua Giusepe Bressan`, uma
  rua diferente e existente no mesmo município — o acerto não é garantido, e o
  assistente não corrige o cadastro do usuário pelas costas dele. A comparação
  normalizada (minúsculas, acentos removidos, espaços colapsados) mora em
  `address_format.normalizar_logradouro`, que já é a fonte única do padrão de
  endereço.
- **A mensagem de "nada localizado" parou de culpar o município (Decisão 60)**:
  antes ela mandava "Confira o município na página da agência"; no caso relatado
  o município estava certo e a orientação levou o usuário a procurar no lugar
  errado. Agora lista até 3 dos endereços que falharam, aponta a grafia do
  logradouro como causa mais provável e lembra de "Marcar no mapa" como saída.
- **Cache de sessão e menos trabalho repetido (Decisão 61)**: com o degrau novo
  o pior caso virou 7 requisições de 1 s **por parada**, e uma linha importada
  por CSV tem dezenas delas. Passou a haver cache de sessão por URL, e
  "Geocodificar" pula as paradas que já têm coordenada — o que também impede que
  um ponto marcado à mão no canvas seja sobrescrito por um clique a mais.
- **Cada tentativa etiquetada no log**: `a-estruturada-num`, `b-estruturada`,
  `c-livre`, `sem-bbox …`, `photon`, `city-bbox`, junto de `erro=` e
  `candidatos=`, para o próximo diagnóstico não exigir reconstruir a URL à mão.
- **Alternativa recusada, registrada para ninguém refazer (Decisão 58)**: índice
  de vias por Overpass + `difflib` também funciona (4.342 vias de Caxias do Sul
  em 3,8 s; ratio 0,923 no 1º lugar), mas resolve só o nome da via — ainda
  exigiria voltar ao Nominatim pela coordenada — e pede cache por município e um
  limiar a calibrar. Fica como plano B se o Photon público sair do ar.

---

### Geocodificação no QGIS 4 (Fase 9): enum de rede e bbox por município

No QGIS 4 (Qt 6) o botão **Geocodificar** devolvia "não encontrado" para *todo*
endereço, com bairro e sem bairro. A causa era um enum não qualificado —
`QNetworkReply.NoError`, que o PyQt6 removeu — levantando `AttributeError` dentro
do `try` do `NominatimGeocoder._buscar` e sendo engolido pelo `except Exception:
return []`. Toda requisição voltava vazia, sem nenhuma mensagem.

- **Enum de rede corrigido (Decisão 51)**: `QNetworkReply.NetworkError.NoError` e,
  na mesma varredura, `QgsVectorFileWriter.WriterError.NoError` /
  `ActionOnExistingFile.CreateOrOverwrite*` (`SigBus_dialog.py`, `gtfs_reader.py`),
  `QgsBlockingNetworkRequest.ErrorCode.NoError` e
  `QgsVectorLayerDirector.Direction.DirectionBoth` (`osm_routing.py`) e
  `QgsLayoutExporter.ExportResult.Success`. Todas as formas foram verificadas no
  QGIS 3.44/Qt5 **e** no QGIS 4.2/Qt6 — um codebase só, sem shim de versão.
- **Geocodificação deixou de falhar em silêncio (Decisão 52)**: cada tentativa
  registra no painel **Log Messages**, aba `SIG-Bus`, a URL consultada, o código de
  erro e o número de candidatos; exceção vai com `traceback` completo. Erro de
  programação deixou de ser indistinguível de "endereço inexistente".
- **`bounded=1` virou filtro de qualidade, não regra dura (Decisão 53)**: se toda a
  cascata restrita à caixa envolvente do município voltar vazia, ela é repetida sem
  `viewbox`/`bounded` antes de declarar "não encontrado" — bbox errada ou de
  município homônimo não zera mais o resultado. Na busca livre, o bairro não é mais
  repetido quando é o próprio município.
- **Caixa envolvente do município recalculada na UI (Decisão 54)**: salvar a agência
  grava `build_city_viewbox` junto de município/UF e a invalida quando o par muda —
  a bbox nunca fica cacheada apontando para outra cidade. Falha de rede aí não
  bloqueia o salvamento.
- **Guarda de Qt6 ampliada (Decisão 55)**: `test_qt6_compat.py` passou a cobrir
  `QNetworkReply`, `QgsVectorFileWriter`, `QgsBlockingNetworkRequest`,
  `QgsVectorLayerDirector` e `QgsLayoutExporter`, e a varrer também os arquivos de
  teste — os mocks do `conftest.py` expunham a forma curta e escondiam a regressão.
- **Mensagem de resumo com contexto**: quando nenhuma parada é localizada, o aviso
  mostra o município/UF usados na busca e aponta o log `SIG-Bus`.

#### Arquivos tocados

`geocoding.py`, `SigBus_dialog.py`, `gtfs_reader.py`, `osm_routing.py`,
`conftest.py`, `test_geocoding.py`, `test_qt6_compat.py`,
`GUIA_CONSTRUIR_GTFS.md`, `ARQUITETURA_CONSTRUIR_GTFS.md`, `CHANGELOG.md`.

---

### Construção de GTFS (Fase 8): Padrão de Endereço, Geocodificação e Lote

Melhorias de legibilidade, usabilidade e robustez na aba **Construir GTFS**:

- **Legibilidade e Temas (Decisão 42)**: padronização das folhas de estilo em constantes centralizadas em `SigBus_dialog.py` (`QSS_INPUT`, `QSS_CARD`, `QSS_HINT`, `QSS_STATUS_OK`, `QSS_STATUS_ERR`), garantindo contraste legível em temas claros e escuros (Night Mapping).
- **Padrão de Endereço (Decisão 43)**: formato padronizado `Logradouro, Número - Bairro` via `sig_bus/address_format.py`, com Município e UF configurados globalmente na agência.
- **Geocodificação Estruturada por Contexto (Decisões 44, 45 e 47)**: busca síncrona no Nominatim em cascata (com número, sem número, e busca livre), restrita ao contexto e à caixa envolvente (bounding box / `viewbox`) do Município configurado.
- **Tabela Interna `sig_bus_config` (Decisão 46)**: persistência de metadados da agência e caixa envolvente do município no GeoPackage de trabalho, ignorada na exportação GTFS.
- **Indicadores Visuais de Status e Supressão de Lat/Lon (Decisão 48)**: remoção dos campos visuais de latitude e longitude da tabela de paradas, substituídos por status visuais (`✓ localizado`, `✗ não encontrado`, `📍 marcado no mapa`).
- **Marcação no Mapa (Decisões 49 e 50)**: botão **Marcar no mapa** ativa a ferramenta interativa `PickStopPointTool` (`map_tools.py`) para selecionar coordenadas com um clique no canvas (ideal para linhas rurais), com adição automática do raster OpenStreetMap (`ensure_osm_basemap`).
- **Importação de Paradas em Lote via CSV (Decisão 43)**: suporte à importação por arquivo CSV (delimitador `;`, UTF-8 com BOM, `stops_csv.py`), com o modelo de exemplo `modelo_paradas.csv` e guia explicativo `MODELO_PARADAS_CSV.md`.

#### Arquivos tocados

`SigBus_dialog.py`, `geocoding.py`, `gtfs_builder_core.py`, `address_format.py` (novo), `stops_csv.py` (novo), `map_tools.py` (novo), `modelo_paradas.csv` (novo), `MODELO_PARADAS_CSV.md` (novo), `GUIA_CONSTRUIR_GTFS.md`, `ARQUITETURA_CONSTRUIR_GTFS.md`, `README.md`, `CHANGELOG.md`.

---

### Suporte a QGIS 4 / Qt 6

O **QGIS 4 roda sobre Qt 6**, e o PyQt6 removeu os enums "curtos" do Qt 5
(`Qt.AlignTop`, `Qt.Horizontal`, `QMessageBox.Yes`, `.exec_()` etc.), assim
como o QGIS 4 removeu os aliases depreciados dos seus próprios enums
(`Qgis.Critical`, `QgsTask.CanCancel`, `QgsUnitTypes.LayoutMillimeters`). Sem
essa migração o plugin nem abria no QGIS 4 (`AttributeError: type object 'Qt'
has no attribute 'AlignTop'`). A forma qualificada usada aqui vale nos dois
ambientes: **um único caminho de código**, sem shim de versão, rodando tanto
no QGIS 3.40 LTR (Qt 5) quanto no QGIS 4 (Qt 6).

- **Enums qualificados em todo o pacote**: `SigBus.py`, `SigBus_dialog.py`,
  `gtfs_reader.py`, `gtfs_export.py`, `block_core.py`,
  `block_diagram_dialog.py`, `block_scene.py` e `block_view.py` passaram a
  usar a forma qualificada dos enums Qt/QGIS (`Qt.AlignmentFlag.AlignTop`,
  `Qgis.MessageLevel.Critical`, `QgsTask.Flag.CanCancel`,
  `Qgis.LayoutUnit.Millimeters`, `.exec()`).
- **`QVariant.Type` → `QMetaType.Type`**: `QVariant.Type` não existe mais no
  PyQt6, então `QgsField(nome, QVariant.String)` é quebra dura no QGIS 4.
  `gtfs_reader.py` expõe `FIELD_STRING`/`FIELD_INT` (`QMetaType.Type.QString`/
  `.Int`), usados por todas as criações de campo do plugin.
- **`qgisMinimumVersion` atualizado** de `3.0` para `3.40` e
  `supportsQt6=True` acrescentado em `metadata.txt` — o `QgsField` com
  `QMetaType` exige QGIS ≥ 3.38 (3.40 é o LTR), e sem o flag o QGIS 4 não
  considera o plugin instalável.
- **Guarda de regressão**: novo `test_qt6_compat.py` varre todo o pacote por
  padrão de texto em busca de enums na forma antiga (Qt5) e falha se algum
  reaparecer — evita que copy-paste de código antigo reintroduza a
  regressão.

#### Arquivos tocados

`SigBus.py`, `SigBus_dialog.py`, `gtfs_reader.py`, `gtfs_export.py`,
`block_core.py`, `block_diagram_dialog.py`, `block_scene.py`,
`block_view.py`, `metadata.txt`, `conftest.py`, `README.md`,
`test_qt6_compat.py` (novo).

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
