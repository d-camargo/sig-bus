# PLAN — SIG-Bus (Edição de GTFS)

## Objetivo
**Fase 1 (concluída):** permitir editar campos e geometria de um GTFS já
carregado no SIG-Bus (routes, trips, stops, shapes, stop_times, calendar) numa
cópia de trabalho isolada (`feed_edit.gpkg`), com chaves protegidas e
integridade validada, e exportar uma versão normalizada em `.zip` — fechando o
ciclo **editar → validar → exportar** sem nunca arriscar o `feed.gpkg` da
análise já carregada.

**Fase 2 (atual):** a implementação está pronta, mas só documentada do ponto
de vista técnico (`ARQUITETURA_EDICAO_GTFS.md`). Falta um **guia de
orientação ao usuário final** da aba "Edição GTFS": que ferramentas existem
na tela, o passo a passo do fluxo completo, e os erros/avisos que aparecem na
prática e como resolvê-los — para quem vai usar o plugin (ex.: analista da
BHTrans) e não precisa (nem deve precisar) ler a arquitetura interna.

**Fase 3 (concluída):** o commit mais recente do HEAD (`96122e8`,
"conflitos resolvidos") na verdade **não** resolveu o conflito de merge:
marcadores `<<<<<<< HEAD` / `=======` / `>>>>>>> temp-resolve-conflict`
ficaram commitados em `sig_bus/SigBus_dialog.py` (linha 959) e
`sig_bus/gtfs_export.py` (linha 26), o que gera `SyntaxError` e impede o
QGIS de carregar o plugin `sig_bus`. Já existe uma resolução iniciada,
porém não commitada, na working tree (visível em `git status`/`git diff`)
que remove os marcadores optando pelo lado que já cobre as mesmas
necessidades da fatia 4 por outro caminho (edição genérica de vértices no
`editOpenClicked` do passo 7, e exportação de `stops` via `osgeo.ogr` em
`_export_stops_ogr`), descartando o botão dedicado
`editStopsClicked`/`button_edit_stops`. O objetivo desta fase é **validar**
essa resolução (nada ficou órfão, nada foi perdido sem substituto
equivalente) e commitá-la para o plugin voltar a carregar.

**Fase 4 (atual):** o guia de usuário `sig_bus/GUIA_EDICAO_GTFS.md` (Fase 2)
já está completo e commitado. Agora é preciso **extrair e reformatar** esse
conteúdo para revisão num canal de comunicação (ex.: Slack/Discord/e-mail —
canal a confirmar com o usuário), já que Markdown de arquivo `.md` de repo
(blockquotes `> [!NOTE]`, links relativos a outro arquivo) nem sempre
renderiza igual num canal de chat. Esta fase é só de comunicação/documentação:
não muda nenhum arquivo do plugin, só produz um texto derivado do guia para
o usuário revisar e publicar manualmente.

**Fase 5 (atual):** criar um GTFS **do zero** dentro do SIG-Bus, para equipes
que não partem de nenhum feed GTFS existente — só uma lista de endereços dos
pontos de ônibus e um descritivo (itinerário) de cada linha, tipicamente já
existente em papel/planilha/documento próprio da operadora (ex.: BHTrans).
Uma aba nova, "Construir GTFS", guia o usuário **linha por linha** (uma linha
de ônibus de cada vez) por um assistente — identidade da linha → endereços
das paradas → geocodificação e confirmação no mapa → sequência das paradas →
horários → revisão e salvar — que grava direto num `feed_edit.gpkg` vazio,
reaproveitando a validação e a exportação já existentes da aba "Edição GTFS"
(Fase 1) em vez de duplicá-las. Uma barra de progresso mostra o quanto falta
para um GTFS mínimo (arquivos/campos obrigatórios) e, além dele, o quanto
falta para um GTFS mais completo (campos opcionais, shapes, segundo sentido
etc.), avisando explicitamente o que falta a cada etapa e atualizando a cada
etapa concluída. Público-alvo leigo em GTFS: janelas de assistente passo a
passo, sem exigir edição de tabela crua para criar os dados. O traçado
(`shapes`) de cada linha é calculado seguindo a rede viária real do
OpenStreetMap entre as paradas — não mais uma linha reta —, com a linha reta
mantida apenas como fallback para os trechos em que a malha viária buscada
não cobrir ou não conectar as paradas.

**Fase 6 (atual):** a revisão automatizada da Fase 5 (`.planexec/job.log`,
2026-07-10) reprovou o trabalho por dois motivos: o commit `c9d610c`
("Implementação do GTFS do zero com roteamento OSM") na verdade só alterou
`PLAN.md` — nenhum dos módulos dos passos 31-52 (`gtfs_builder_core.py`,
`osm_routing.py`, `geocoding.py`) chegou a ser criado, apesar da mensagem de
commit afirmar o contrário; e o commit `0817dd6` ("package: sig_bus 0.4")
commitou o artefato binário de build `dist/sig_bus-0.4.zip` (785 KB) sem
nenhum passo do plano pedir isso — já corrigido em `eb06bc2` (removido do
tracking + `dist/` no `.gitignore`). Esta fase formaliza o processo para não
repetir o erro, em três frentes concretas (com passos verificáveis próprios,
não só esta narrativa): **(a)** o commit que grava esta atualização do
`PLAN.md` reflete só isso — mensagem e diff não podem alegar código
implementado que não existe; **(b)** o pacote `.zip` de distribuição
(`dist/*.zip`) nunca é gerado nem commitado por nenhum passo do plano —
empacotamento já é responsabilidade do alvo `zip`/`package` do `Makefile`,
disparado manualmente pelo usuário fora do fluxo de implementação; e
**(c)** um passo das Fases 5 só pode ser marcado `[x]` quando o arquivo
correspondente existir de fato no repositório e passar no critério descrito
nele — retomando, sem trabalho perdido, a criação pendente de
`gtfs_builder_core.py` e `osm_routing.py` (passos 31-42, ainda `[ ]`).

## Decisões de arquitetura
Referência completa da Fase 1: `sig_bus/ARQUITETURA_EDICAO_GTFS.md` (decisões
tomadas em 2026-06-19). Resumo:

1. **Motor híbrido:** a UI guia (combobox), protege campos de chave e valida;
   a edição em si acontece na tabela de atributos nativa do QGIS e na edição
   de vértices do canvas — não em widgets customizados.
2. **Cópia de trabalho isolada:** toda edição ocorre em `feed_edit.gpkg`
   (cópia de `feed.gpkg`, mesmo diretório); a origem nunca é tocada, e dá pra
   descartar tudo a qualquer momento.
3. **Chaves protegidas + validação na exportação:** campos `*_id` são
   read-only (`editFormConfig.setReadOnly`); integridade referencial e de
   formato só é checada ao gerar o `.zip`.
4. **Exportação normalizada:** ordem canônica de colunas, `calendar.txt`/
   `calendar_dates.txt` corretos, e a geometria como fonte da verdade
   (`stop_lat`/`stop_lon` vêm do ponto, `shapes.txt` vem dos vértices da
   camada de linha `shapes`).
5. **`stop_times` só filtrado:** nunca carregar a tabela inteira na GUI —
   sempre filtrar por viagem/linha (`setSubsetString`) antes de abrir.
6. **`gtfs_schema.py`** é fonte única da verdade (whitelist editável,
   validação, ordem de exportação) — mudar a spec num lugar só propaga.
7. Padrões herdados do projeto: I/O pesado em `QgsTask`, SQL agregado (nunca
   iterar `stop_times` feição-a-feição), nunca `UPDATE` sqlite cru em tabela
   com geometria, feedback via `messageBar`/`QgsMessageLog` (`LOG_TAG='SIG-Bus'`).

Decisões para a Fase 2 (guia do usuário):

8. **Novo arquivo `sig_bus/GUIA_EDICAO_GTFS.md`**, seguindo o padrão de
   nomenclatura já usado por `ARQUITETURA_EDICAO_GTFS.md`. Não expandir o
   `DOCUMENTACAO.md` bilíngue existente: essa feature ainda não tem cobertura
   lá, e misturar o fluxo de uso final com a documentação técnica bilíngue
   das demais seções deixaria os dois documentos inconsistentes em tom.
9. **Só documentação nesta fase — nenhuma mudança de código.** A feature já
   está implementada e com todos os passos da Fase 1 concluídos.
10. **PT-BR**, mesmo idioma do público-alvo real (equipes como BHTrans) e do
   documento de arquitetura irmão.
11. **Fonte de verdade para "erros comuns": o código, não suposição.** Cada
   mensagem documentada deve corresponder a uma mensagem real emitida por
   `iface.messageBar()`/`QgsMessageLog` em `SigBus_dialog.py` ou pelo
   `GtfsValidator` (`gtfs_validator.py`) — nunca uma mensagem genérica
   inventada.

Decisões para a Fase 3 (hotfix do conflito não resolvido):

12. **Terminar a resolução já iniciada, não refazer o merge.** A working
   tree já tem uma resolução em andamento (não commitada) que remove os
   marcadores de conflito; a fase 3 valida e completa essa resolução em vez
   de reabrir o merge do zero.
13. **Preferir o lado que já superou a funcionalidade equivalente, sem
   recriar código descartado.** Onde as duas metades do conflito
   implementam a mesma necessidade de formas diferentes, manter a versão
   que corresponde a uma decisão já registrada nesta PLAN: a ativação
   genérica da ferramenta de vértices em `editOpenClicked` (passo 7) cobre
   o caso de uso do antigo botão dedicado `editStopsClicked`/
   `button_edit_stops`, e `_export_stops_ogr` (leitura via `osgeo.ogr`)
   cobre o mesmo requisito de `_read_stop_coordinates` (stop_lat/stop_lon a
   partir da geometria, passo 4).

Decisões para a Fase 4 (extrair guia para revisão no canal):

14. **Só extração/reformatação de texto já existente — nenhuma mudança de
   código nem de `GUIA_EDICAO_GTFS.md`.** O conteúdo técnico já foi validado
   na Fase 2 (decisão 11: toda mensagem documentada rastreável ao código);
   esta fase não reabre essa validação, só adapta a apresentação.
15. **Nenhum envio automático a canal nenhum.** Sem integração de
   Slack/Discord/e-mail configurada neste repositório (confirmado por busca
   no projeto), o resultado desta fase é um texto pronto para o usuário
   colar e revisar manualmente, nunca uma publicação automatizada.
16. **Confirmar canal/formato de destino antes de reformatar.** Elementos
   como blockquotes `> [!NOTE]` e links relativos a `ARQUITETURA_EDICAO_GTFS.md`
   só podem ser adaptados corretamente se soubermos as limitações de
   Markdown do canal escolhido (ex.: Slack mrkdwn não tem `> [!NOTE]` nem
   headings `#`).

Decisões para a Fase 5 (construir GTFS do zero):

17. **Reaproveitar o mesmo `feed_edit.gpkg` e o mesmo pipeline de
   Validar/Exportar da aba "Edição GTFS"** (decisões 1–6 da Fase 1), em vez
   de criar um pipeline de exportação paralelo. "Construir GTFS" só
   *popula* dados num `feed_edit.gpkg`; `gtfs_validator.py`, `gtfs_export.py`
   e o botão "Exportar .zip" continuam sendo o único caminho de saída.
   `gtfs_schema.py` continua a fonte única de verdade — inclusive para o que
   conta como "GTFS mínimo" (decisão 20).
18. **`WorkingCopy` de origem vazia**: `gtfs_edit_core.py` ganha uma forma
   de criar um `feed_edit.gpkg` vazio (tabelas do `gtfs_schema.py`, sem
   copiar de um `feed.gpkg` existente), já que "Construir GTFS" não tem
   feed de origem — `WorkingCopy.enter()` atual exige `source_gpkg`.
19. **Geocodificação via Nominatim (OpenStreetMap), sem dependência nova de
   pacote.** Usa `QgsNetworkAccessManager`/`QNetworkRequest` (já disponíveis
   no ambiente do QGIS) para chamar a API pública do Nominatim, com
   `User-Agent` identificando o plugin (exigência da política de uso do
   Nominatim) e no mínimo 1 requisição/segundo — sem chave de API, coerente
   com o resto do projeto (GDAL/OGR, nada de lib paga). Endereço não
   encontrado ou ambíguo nunca bloqueia o fluxo: o usuário sempre pode
   digitar lat/lon manualmente ou ajustar o ponto no mapa.
20. **"GTFS mínimo" = `REQUIRED_LAYERS` já definido em `gtfs_reader.py`**
   (`agency, routes, trips, stop_times, stops, calendar`) com os campos
   `required=True` de `gtfs_schema.py` preenchidos em pelo menos uma linha
   de cada tabela — reaproveita metadados já existentes em vez de redefinir
   "mínimo" num terceiro lugar. "Máximo" (segundo trecho da barra, sem
   correspondência formal na spec do GTFS) é a cobertura dos campos
   opcionais (`editable=True, required=False`) + `shapes` preenchido em
   cada trip + segundo sentido (ida/volta) por linha.
21. **Confirmação de coordenadas no canvas nativo do QGIS, não num mapa
   customizado dentro do diálogo** — mesmo princípio da decisão 1 da Fase 1.
   Pontos geocodificados entram como camada temporária no projeto; o
   usuário confirma/arrasta com a ferramenta nativa de edição de vértices
   (já usada na Fase 1, passo 7), em vez de o SIG-Bus construir um
   `QgsMapCanvas` embutido do zero.
22. **Deduplicação de paradas por texto exato do endereço** (normalizado:
   minúsculas + espaços colapsados), não por proximidade geográfica. Casar
   por coordenada teria mais recall (mesma esquina digitada de duas formas),
   mas exige limiar de distância configurável e UI de "possível duplicata"
   — complexidade desproporcional pra v1. Reaproveitar ou duplicar uma
   parada é decisão explícita do usuário na tela de revisão da linha, nunca
   automática por proximidade.
23. **Sequência de paradas e horários resolvidos no assistente, não na
   grade de atributos**: a ordem das paradas por linha é uma lista simples
   (mover para cima/baixo), e os horários são gerados por frequência (ex.:
   "a cada 20 min das 6h às 22h") expandida em `stop_times`, com a opção de
   ajustar viagem a viagem depois na aba "Edição GTFS" já existente para
   casos que fogem da frequência regular. Evita pedir ao usuário leigo uma
   tabela de horários digitada linha a linha.
24. **Traçado (`shapes`) calculado seguindo a rede viária real do
   OpenStreetMap entre as paradas na ordem escolhida**, não mais como linha
   reta (substitui a decisão original desta fase). Para a linha inteira,
   busca-se a malha de vias do OSM ao redor de todas as paradas e computa-se
   o caminho mais plausível (menor custo) entre cada par consecutivo sobre
   essa malha; os trechos concatenados formam o traçado completo. Ajuste
   fino por vértice (para corrigir o traçado calculado) continua na aba
   "Edição GTFS" (Fase 1, passo 7), sem duplicar essa ferramenta aqui.
25. **Fonte da malha viária: Overpass API (OSM), consultada uma vez por
   linha** (não por par de paradas) — uma bounding box envolvendo todas as
   paradas da linha com uma margem (ex.: ~300 m) ao redor. Usa
   `QgsNetworkAccessManager`/`QNetworkRequest` (mesmo padrão de rede da
   decisão 19) contra o endpoint público do Overpass (`overpass-api.de`),
   sem chave de API, pedindo só as vias (`highway=*`) dentro dessa bbox.
   Uma única consulta por linha evita N consultas/N grafos para N-1
   trechos, e o resultado é cacheado em memória durante a sessão do
   assistente para não repetir a mesma consulta se o usuário reordenar
   paradas ou tentar de novo.
26. **Motor de roteamento: `qgis.analysis` (já embutido no QGIS), não uma
   lib nova.** As vias baixadas do Overpass (decisão 25) viram uma camada
   de linhas em memória; `QgsVectorLayerDirector` + `QgsGraphBuilder`
   constroem um único grafo por linha, reaproveitado para calcular o
   caminho entre cada par consecutivo de paradas via
   `QgsGraphAnalyzer.shortestPath` (Dijkstra). Mesma filosofia da decisão
   19: nenhuma dependência nova de pacote (nada de `networkx`/`osmnx`),
   reaproveitando o que o QGIS já traz.
27. **Fallback silencioso para linha reta por trecho, nunca bloqueando o
   assistente** — quando a malha buscada não cobre um trecho, um par de
   paradas fica em componentes desconexas do grafo, ou a consulta ao
   Overpass falha/expira, só aquele trecho específico (não a linha
   inteira) usa a linha reta equivalente. O comportamento da decisão
   original desta fase (linha reta entre todas as paradas) vira esse
   fallback por trecho, em vez de ser removido.
28. **`agency` é configurado uma vez só** (tela "Configuração inicial",
   antes da primeira linha) — evita redigitar os mesmos dados a cada linha.
   **Calendário (dias de operação/validade) é definido por linha**, mas o
   assistente lista os calendários já criados por linhas anteriores para
   reaproveitar (`service_id` existente) quando o horário de operação é o
   mesmo, em vez de forçar um único calendário-padrão para o feed inteiro.
29. **Gerar `shapes` reaproveitando `shapes_point` (tabela de apoio) +
   `GtfsReader.build_shapes_line`**, a mesma rotina já usada ao carregar um
   GTFS existente (`gtfs_reader.py`), em vez de escrever a camada de linha
   diretamente. O assistente insere em `shapes_point` os vértices do
   traçado calculado pelo roteamento OSM (decisões 24-27) — ou, no
   fallback por trecho, os pontos da linha reta equivalente; quem agrupa
   por `shape_id`/`shape_pt_sequence` e grava a polilinha continua sendo o
   código já validado do leitor — sem duplicar essa lógica.
30. **Assistente = `QStackedWidget` de páginas dentro da própria aba
   "Construir GTFS"**, construída em código no mesmo padrão da aba "Edição
   GTFS" (`SigBus_dialog.py:951`, sem entrada no `.ui` do Designer) — não um
   `QWizard`/diálogo modal separado. Botões "Voltar"/"Avançar" navegam entre
   páginas; duas `QProgressBar` (mínimo e máximo, decisão 20) mais um texto
   "falta: ..." ficam sempre visíveis no topo da aba, atualizados a cada
   gravação no `feed_edit.gpkg`. Mantém a aba nova visualmente e
   estruturalmente consistente com a aba de edição já existente.
31. **Núcleo (`gtfs_edit_core.py`/novo `gtfs_builder_core.py`) sem
   dependência do ambiente gráfico do QGIS sempre que possível** — mesmo
   princípio já documentado no docstring de `gtfs_edit_core.py`. Funções
   puras (progresso, deduplicação, expansão de frequência, criação do
   `feed_edit.gpkg` vazio) usam só `sqlite3`/`osgeo.ogr` (como
   `gtfs_export.py` já faz), para poderem ser verificadas com
   `python3 -c ...` fora do QGIS. Só o que exige mesmo a API do QGIS
   (`build_shapes_line`, geocodificação via `QgsNetworkAccessManager`, a UI
   em si) fica isolado nas camadas que precisam rodar dentro do QGIS.

Decisões para a Fase 6 (processo pós-revisão: commit e gate de implementação):

32. **Commit desta atualização isolado, só com `PLAN.md`, mensagem sem
   alegação de código.** O commit que grava as correções desta fase
   (respostas aos itens 1-3 da revisão) toca apenas `PLAN.md` e a mensagem
   descreve exatamente isso ("atualiza PLAN.md: ..."), nunca "implementa"/
   "adiciona" um módulo que não foi escrito nesse commit — repete o erro do
   `c9d610c` senão.
33. **Empacotamento (`dist/*.zip`) nunca faz parte do fluxo padrão de
   passos do plano.** O `Makefile` já tem o alvo de build/pacote
   (`0817dd6` gerou `dist/sig_bus-0.4.zip` manualmente); nenhum passo desta
   ou de fases futuras deve gerar ou commitar esse artefato — permanece uma
   ação manual do usuário, fora do controle de versão (`dist/` no
   `.gitignore`, já feito em `eb06bc2`).
34. **`[x]` exige o arquivo existir de fato, não só o passo estar descrito.**
   Antes de marcar qualquer passo dos módulos ainda pendentes da Fase 5
   (`gtfs_builder_core.py`, `osm_routing.py`, `geocoding.py`, passos 31-42)
   como concluído ou de commitar alegando isso, o arquivo correspondente
   precisa existir no working tree e passar no critério descrito no próprio
   passo — verificável por `ls`/`git show --stat` no commit, não só pela
   leitura do `PLAN.md`.

## Passos (executor marca [x] ao concluir)

### Fase 1 — Implementação (concluída)
- [x] 1. Esqueleto: aba "Edição GTFS" + `WorkingCopy` (entrar/descartar) +
      `gtfs_schema.py` inicial (routes/trips) — arquivos: `gtfs_schema.py`,
      `gtfs_edit_core.py`, `SigBus_dialog.py`. (commit `7f11604`)
- [x] 2. Abrir tabela editável na grade de atributos nativa do QGIS com IDs
      travados — arquivos: `SigBus_dialog.py` (`editOpenClicked`).
      (commit `baae4b5`)
- [x] 3. Exportador normalizado `.zip`: `gtfs_schema` estendido para
      agency/stops/stop_times/calendar/calendar_dates/shapes;
      `GtfsExporter(QgsTask)` com streaming e ordem canônica; botão
      "Exportar .zip" — arquivos: `gtfs_schema.py`, `gtfs_export.py`,
      `SigBus_dialog.py`. (commit `6d90539`)
- [x] 4. Corrigir exportação de `stops`: gerar `stop_lat`/`stop_lon` a partir
      da geometria do ponto (`ST_X`/`ST_Y` ou leitura via OGR), não das
      colunas de texto — a edição de vértices no canvas não as atualiza
      sozinha. Critério: mover um stop no canvas e exportar; `stops.txt`
      reflete a nova coordenada. — arquivos: `gtfs_export.py`.
- [x] 5. Decidir e registrar o modelo de edição de `shapes`: a camada de
      linha `shapes` (gerada por `build_shapes_line`) passa a ser a fonte
      editável por vértice; `shapes_point` deixa de ser editada diretamente.
      Ajustar `gtfs_schema.py` (a entrada atual tem colunas de ponto que não
      existem na camada de linha) e o mapeamento tabela→layername usado em
      `editOpenClicked`. — arquivos: `gtfs_schema.py`, `SigBus_dialog.py`.
- [x] 6. Corrigir exportação de `shapes`: `gtfs_export.py` regenera
      `shape_pt_lat`/`shape_pt_lon`/`shape_pt_sequence` a partir dos vértices
      da camada de linha `shapes` do `feed_edit.gpkg`, não da tabela crua
      `shapes_point`. Critério: mover um vértice da linha no canvas e
      exportar; `shapes.txt` reflete o novo ponto. — arquivos: `gtfs_export.py`.
- [x] 7. Adicionar caminho "editar no mapa" para `stops`/`shapes`: ao abrir
      para edição uma tabela espacial, além de `startEditing()` + tabela de
      atributos, ativar a ferramenta de edição de vértices do canvas e dar
      zoom na camada. Critério: selecionar `stops` ou `shapes` e clicar
      "Abrir para edição" deixa a ferramenta de vértices pronta pra uso no
      canvas. — arquivos: `SigBus_dialog.py`.
- [x] 8. `stop_times`: adicionar seleção de linha (`route_short_name`) e
      viagem (`trip_id`) na aba "Edição GTFS", habilitada só quando a tabela
      escolhida é `stop_times`. — arquivos: `SigBus_dialog.py`.
- [x] 9. `stop_times`: aplicar `setSubsetString("trip_id = '...'")` com base
      na viagem escolhida antes de abrir a camada; bloquear "Abrir para
      edição" com aviso se `stop_times` for escolhido sem viagem selecionada.
      Critério: sem viagem escolhida, mostra aviso e não abre; com viagem
      escolhida, abre só as linhas daquele `trip_id`. — arquivos:
      `SigBus_dialog.py`.
- [x] 10. Criar `gtfs_validator.py` com `GtfsValidator`: integridade
      referencial via SQL agregado (`LEFT JOIN ... WHERE x IS NULL`) para as
      `foreign_keys` do `gtfs_schema` (`trips.route_id/service_id/shape_id`,
      `stop_times.trip_id/stop_id`) — sem iterar feição-a-feição. —
      arquivos: `gtfs_validator.py` (novo).
- [x] 11. Estender `GtfsValidator` com checagem de formato: horários
      (`HH:MM:SS`, podendo passar de 24h), datas (`YYYYMMDD`), lat/lon em
      faixas válidas, enums (`route_type`, `direction_id`, `exception_type`).
      — arquivos: `gtfs_validator.py`.
- [x] 12. Adicionar botão "Validar" na aba "Edição GTFS" chamando
      `GtfsValidator` sobre o `feed_edit.gpkg` e reportando erros/avisos via
      `iface.messageBar()` + `QgsMessageLog` (`LOG_TAG='SIG-Bus'`). —
      arquivos: `SigBus_dialog.py`.
- [x] 13. Rodar a validação automaticamente antes de "Exportar .zip":
      erro fatal bloqueia a exportação e mostra o relatório; avisos só
      alertam e deixam prosseguir. Critério: um `feed_edit.gpkg` com
      `stop_times.trip_id` órfão não exporta e mostra o erro; um feed sem
      erros exporta normalmente. — arquivos: `SigBus_dialog.py`,
      `gtfs_validator.py`.
- [x] 14. Atualizar `ARQUITETURA_EDICAO_GTFS.md`: marcar fatias 4-6
      concluídas e registrar a decisão do modelo de edição de `shapes`
      (passo 5) e o tratamento de `agency_id` em feed de agência única
      (ponto em aberto da seção 8, se resolvido). — arquivos:
      `ARQUITETURA_EDICAO_GTFS.md`.

### Fase 2 — Guia do usuário (atual)
- [x] 15. Levantar o inventário de ferramentas da aba "Edição GTFS": para
      cada botão/combobox (`Entrar no modo edição`, combobox Tabela,
      combobox Linha/Viagem, `Abrir para edição`, `Validar`,
      `Exportar .zip`, `Descartar edição`), anotar o que ele faz lendo os
      métodos correspondentes em `SigBus_dialog.py`
      (`editEnterClicked`, `editOpenClicked`, `validateClicked`,
      `exportClicked`, `editDiscardClicked`, `_on_edit_table_changed`,
      `_on_edit_route_changed`) e a lista de tabelas editáveis
      (`gtfs_schema.editable_tables()`). Critério: rascunho com uma
      linha por ferramenta, pronto para virar a seção "Ferramentas
      disponíveis". — arquivos (leitura): `SigBus_dialog.py`,
      `gtfs_schema.py`.
- [x] 16. Criar `sig_bus/GUIA_EDICAO_GTFS.md` com as seções "Visão geral" e
      "Ferramentas disponíveis" (consolidando o passo 15). Critério: cada
      botão/campo citado no passo 15 aparece documentado com o que faz. —
      arquivo: `sig_bus/GUIA_EDICAO_GTFS.md` (novo).
- [x] 17. Escrever a seção "Passo a passo": fluxo feliz completo (Entrar no
      modo edição → escolher tabela → [se `stop_times`: escolher linha e
      viagem] → Abrir para edição → editar na grade de atributos ou nos
      vértices do canvas → Validar → Exportar .zip → Descartar edição
      quando quiser recomeçar do `feed.gpkg` original). Critério: alguém
      que nunca usou a feature consegue seguir do início ao fim só com o
      texto, sem precisar olhar o código. — arquivo:
      `sig_bus/GUIA_EDICAO_GTFS.md`.
- [x] 18. Escrever a seção "Erros comuns e soluções": listar cada mensagem
      real de aviso/erro (via `grep` por `messageBar\|QgsMessageLog` em
      `SigBus_dialog.py`, ex. "Entre no modo edição primeiro.",
      "Selecione uma viagem para editar a tabela stop_times.",
      "A exportação foi cancelada devido a erros de validação", e as
      mensagens produzidas por `GtfsValidator`), explicando causa provável
      e como resolver. Critério: nenhuma mensagem documentada é inventada —
      todas rastreáveis a uma linha do código. — arquivos (leitura):
      `SigBus_dialog.py`, `gtfs_validator.py`; (escrita):
      `sig_bus/GUIA_EDICAO_GTFS.md`.
- [x] 19. Fechar `GUIA_EDICAO_GTFS.md` com uma seção curta "Limitações
      conhecidas" (ex.: `shapes` só é editado pela camada de linha,
      `stop_times` nunca carrega inteiro, `feed_edit.gpkg` é local ao
      diretório do feed) linkando para `ARQUITETURA_EDICAO_GTFS.md` para
      quem quiser o detalhe técnico. — arquivo: `sig_bus/GUIA_EDICAO_GTFS.md`.
- [x] 20. Adicionar link para `GUIA_EDICAO_GTFS.md` no `README.md` (seção
      Features ou Repository Structure), para que o guia seja descobrível
      por quem abre o repositório. — arquivo: `README.md`.

### Fase 3 — Hotfix: SyntaxError por conflito de merge não resolvido (atual)
- [x] 21. Confirmar que não sobraram marcadores de conflito em nenhum
      arquivo do repositório. Critério:
      `grep -rn "<<<<<<<\|=======\|>>>>>>>" --include=*.py --include=*.ui .`
      (fora de `.git/`) não retorna nenhum resultado. — arquivos: todo o
      repositório (verificação).
- [x] 22. Confirmar que `sig_bus/SigBus_dialog.py` e `sig_bus/gtfs_export.py`
      compilam sem erro. Critério:
      `python3 -m py_compile sig_bus/SigBus_dialog.py sig_bus/gtfs_export.py`
      sai com código 0 e sem mensagens. — arquivos: `sig_bus/SigBus_dialog.py`,
      `sig_bus/gtfs_export.py` (verificação).
- [x] 23. Conferir que não há referência órfã ao código removido pela
      resolução do conflito (`editStopsClicked`, `button_edit_stops`,
      `_read_stop_coordinates`, `_edit_stops_layer`) em nenhum lugar do
      projeto. Critério: `grep -rn` por cada um desses quatro nomes em
      `sig_bus/*.py`, `sig_bus/*.md` e `README.md` não retorna nenhuma
      ocorrência. — arquivos (leitura): `sig_bus/*.py`, `sig_bus/*.md`,
      `README.md`.
- [x] 24. Revisar o diff da working tree
      (`git diff sig_bus/SigBus_dialog.py sig_bus/gtfs_export.py`) linha a
      linha, confirmando que cada remoção corresponde à decisão 13 (fatia 4
      substituída por implementação equivalente) e que nenhuma outra
      funcionalidade foi perdida sem substituto. — arquivos:
      `sig_bus/SigBus_dialog.py`, `sig_bus/gtfs_export.py` (revisão, sem
      alterar código).
- [x] 25. Commitar a resolução do conflito
      (`git add sig_bus/SigBus_dialog.py sig_bus/gtfs_export.py && git commit`),
      com mensagem que deixe explícito que o commit anterior tinha
      marcadores de merge não resolvidos causando o `SyntaxError`. —
      arquivos: `sig_bus/SigBus_dialog.py`, `sig_bus/gtfs_export.py`.
- [x] 26. Recarregar o plugin `sig_bus` no QGIS (ou reiniciar o QGIS) e
      confirmar visualmente que ele carrega sem erro no "Log Messages
      Panel", e que a aba "Edição GTFS" abre normalmente. — verificação
      manual no QGIS.

### Fase 4 — Extrair e formatar o guia para revisão no canal (atual)
- [x] 27. Confirmar com o usuário qual é o canal de destino e o formato de
      texto que ele aceita (ex.: Slack, Discord, e-mail, Markdown puro) —
      isso define quais elementos do guia (headings `#`, blockquotes
      `> [!NOTE]`, links relativos) precisam ser adaptados ou removidos.
      Critério: canal e formato confirmados antes do passo 28. — nenhum
      arquivo alterado (esclarecimento com o usuário).
- [ ] 28. Extrair o conteúdo de `sig_bus/GUIA_EDICAO_GTFS.md` (as 4 seções:
      Visão Geral/Ferramentas Disponíveis, Passo a Passo, Erros Comuns e
      Soluções, Limitações) num rascunho único, sem reescrever nem resumir
      o conteúdo técnico já validado na Fase 2. Critério: rascunho cobre as
      4 seções, e cada mensagem de erro/aviso do rascunho ainda corresponde
      literalmente ao texto do guia original. — arquivo (leitura):
      `sig_bus/GUIA_EDICAO_GTFS.md`.
- [ ] 29. Reformatar a sintaxe do rascunho do passo 28 para o formato do
      canal confirmado no passo 27 (ex.: trocar `> [!NOTE]` por texto
      simples em negrito, resolver o link relativo a
      `ARQUITETURA_EDICAO_GTFS.md` para um caminho ou referência que faça
      sentido fora do repositório), preservando todo o conteúdo. Critério:
      nenhum elemento de sintaxe do Markdown original aparece sem renderizar
      (quebrado) no formato de destino escolhido.
- [ ] 30. Apresentar o texto formatado ao usuário para revisão, sem publicar
      ou enviar automaticamente a nenhum canal. Critério: usuário recebe o
      texto pronto para copiar/colar e aprova ou pede ajustes antes de
      qualquer publicação manual.

### Fase 5 — Construir GTFS do zero (atual)

**Núcleo (sem QGIS — verificável com `python3 -c`/`py_compile`, decisão 31)**
- [ ] 31. `WorkingCopy.enter_empty()` em `gtfs_edit_core.py`: cria um
      `feed_edit.gpkg` vazio com todas as tabelas de `gtfs_schema.GTFS_FILES`
      (via `osgeo.ogr`, mesmo pacote já usado em `gtfs_export.py` —
      `ogr.wkbPoint` para `stops`, `ogr.wkbLineString` para `shapes`,
      `ogr.wkbNone` para as demais) mais a tabela de apoio `shapes_point`
      (decisão 29). Critério: script standalone chama `enter_empty()` sobre
      um diretório temporário e confirma, via `sqlite3`, que todas as
      tabelas de `gtfs_schema.editable_tables()` + `shapes_point` existem
      com as colunas de `gtfs_schema.column_order(tabela)`. — arquivos:
      `gtfs_edit_core.py`.
- [ ] 32. `gtfs_builder_core.py` (novo): `compute_progress(gpkg_path)` —
      usando `sqlite3` (padrão de `gtfs_validator.py`), calcula, por tabela
      de `gtfs_reader.REQUIRED_LAYERS`, se há ao menos 1 linha com todos os
      campos `required=True` de `gtfs_schema.py` preenchidos (mínimo,
      decisão 20) e a cobertura dos campos opcionais + `shapes` preenchido +
      segundo sentido por linha (máximo). Retorna `(pct_minimo,
      pct_maximo, faltando_minimo, faltando_maximo)`. Critério: rodar contra
      o gpkg vazio do passo 31 retorna 0% em ambos com todas as tabelas
      obrigatórias listadas em `faltando_minimo`; popular manualmente 1 linha
      de cada tabela obrigatória via `sqlite3` faz `pct_minimo` chegar a
      100%. — arquivos: `gtfs_builder_core.py` (novo).
- [ ] 33. `gtfs_builder_core.py`: `normalize_address(texto)` (minúsculas +
      espaços colapsados) e `find_existing_stop(gpkg_path, endereco)`
      (decisão 22), consultando a coluna `stop_desc`/`stop_name` onde o
      endereço original fica gravado. Critério: duas grafias do mesmo
      endereço com espaços/maiúsculas diferentes normalizam igual; buscar um
      endereço já gravado retorna o `stop_id` existente, e um endereço novo
      retorna `None`. — arquivos: `gtfs_builder_core.py`.
- [ ] 34. `gtfs_builder_core.py`: `list_reusable_calendars(gpkg_path)`
      (decisão 28) — `SELECT` de `service_id` + dias + vigência distintos já
      gravados em `calendar`. Critério: gpkg com 2 `service_id` diferentes em
      `calendar` retorna as 2 linhas; gpkg sem `calendar` retorna lista
      vazia. — arquivos: `gtfs_builder_core.py`.
- [ ] 35. `gtfs_builder_core.py`: `expand_frequency_to_stop_times(stop_ids,
      hora_inicio, hora_fim, intervalo_min)` (decisão 23) — função pura
      (sem I/O) que gera as viagens e as linhas de `stop_times`
      (`trip_id`, `arrival_time`, `departure_time`, `stop_id`,
      `stop_sequence`) para uma frequência regular. Critério: com 3 paradas,
      `06:00`–`08:00`, intervalo de 60 min, gera 3 viagens (`06:00`, `07:00`,
      `08:00`), cada uma com 3 linhas de `stop_times` em sequência
      1,2,3. — arquivos: `gtfs_builder_core.py`.
- [ ] 36. `gtfs_builder_core.py`: `save_route(gpkg_path, agency, linha,
      paradas, service, frequencia)` — grava/atualiza `agency` (uma vez),
      insere `routes`/`trips`/`stops` (reaproveitando `find_existing_stop`
      do passo 33 antes de criar `stop_id` novo)/`calendar`/`stop_times`
      (via `expand_frequency_to_stop_times` do passo 35) no
      `feed_edit.gpkg`, respeitando `gtfs_schema.column_order` por tabela.
      Critério: chamar a função sobre o gpkg vazio do passo 31 com uma linha
      de exemplo e conferir via `sqlite3` que todas as tabelas envolvidas
      têm as linhas esperadas e nenhuma coluna fora da ordem de
      `gtfs_schema.py`. — arquivos: `gtfs_builder_core.py`.

**Núcleo dependente do QGIS (verificável no Console Python do QGIS)**
- [ ] 37. `osm_routing.py` (novo): `fetch_ways_for_stops(paradas_em_ordem,
      margem_m=300)` — monta uma bbox única cobrindo todas as paradas da
      linha com margem (decisão 25) e consulta o Overpass API uma vez via
      `QgsNetworkAccessManager`/`QNetworkRequest` (mesmo padrão de rede da
      decisão 19), pedindo só vias (`highway=*`); erro de rede ou resposta
      vazia não levanta exceção, devolve lista vazia (aciona o fallback da
      decisão 27), e o resultado fica em cache de memória por conjunto de
      paradas já consultado na sessão. Critério (Console Python do QGIS):
      paradas numa área urbana conhecida retornam ao menos 1 `way` com tag
      `highway`; paradas isoladas (ex.: meio do oceano) retornam lista
      vazia sem lançar exceção. — arquivos: `osm_routing.py` (novo).
- [ ] 38. `osm_routing.py`: `build_road_graph(elementos_osm)` — usa
      `QgsVectorLayerDirector` + `QgsGraphBuilder` (decisão 26) para montar,
      a partir do resultado do passo 37, uma camada de linhas em memória e
      um único grafo roteável para a linha inteira. Critério (Console
      Python do QGIS): o grafo construído a partir do resultado do passo 37
      tem um número de arestas coerente com o número de `way` retornados
      (uma via pode virar mais de uma aresta entre nós). — arquivos:
      `osm_routing.py`.
- [ ] 39. `osm_routing.py`: `shortest_path(grafo, ponto_a, ponto_b)` — faz
      snap de cada ponto ao vértice mais próximo do grafo e usa
      `QgsGraphAnalyzer.shortestPath` (Dijkstra, decisão 26) para achar o
      caminho entre eles; devolve `None` se os pontos estiverem em
      componentes desconexas do grafo (aciona o fallback da decisão 27).
      Critério (Console Python do QGIS): duas paradas na mesma rua (ou
      ligadas por vias conectadas) retornam uma lista de vértices que segue
      a malha; duas paradas sem caminho no grafo retornam `None` sem
      exceção. — arquivos: `osm_routing.py`.
- [ ] 40. `osm_routing.py`: `route_stops(paradas_em_ordem)` — orquestra
      `fetch_ways_for_stops` (passo 37) e `build_road_graph` (passo 38) uma
      vez para a linha inteira, depois chama `shortest_path` (passo 39)
      para cada par consecutivo de paradas sobre o mesmo grafo,
      concatenando os trechos (removendo o vértice duplicado na junção)
      numa lista única e ordenada de vértices — o traçado completo da
      linha. Um trecho sem caminho encontrado (ou a consulta Overpass do
      passo 37 falhando por completo) substitui só aquele trecho pela linha
      reta equivalente (decisão 27), sem descartar os trechos roteados dos
      demais pares. Critério: 3 paradas em vias conectadas devolvem uma
      lista única de vértices que passa pelas 3 na ordem certa, seguindo a
      malha; forçar a falha de um par específico (ex.: coordenada fora de
      qualquer via) faz só aquele trecho virar reta, mantendo os outros
      trechos roteados. — arquivos: `osm_routing.py`.
- [ ] 41. `gtfs_builder_core.py`: `build_line_shape(gpkg_path, shape_id,
      paradas_em_ordem)` — chama `route_stops` (passo 40) e insere os
      vértices resultantes (roteados e/ou fallback reto) em `shapes_point`,
      depois `GtfsReader.build_shapes_line(gpkg_path)` (decisão 29) gera/
      atualiza a camada de linha `shapes` como antes. Critério (Console
      Python do QGIS): chamar a função com 3 paradas em vias conectadas
      gera uma feição em `shapes` cujos vértices seguem a malha viária —
      verificável comparando a geometria resultante com uma reta simples
      entre os mesmos pontos (a roteada tem mais vértices e maior
      comprimento). — arquivos: `gtfs_builder_core.py`.
- [ ] 42. `geocoding.py` (novo): `NominatimGeocoder.geocode(endereco)` via
      `QgsNetworkAccessManager`/`QNetworkRequest` (decisão 19) — cabeçalho
      `User-Agent` identificando o plugin, no mínimo 1 requisição/segundo, e
      nunca levanta exceção para endereço não encontrado/ambíguo (retorna
      lista vazia ou lista com mais de 1 candidato). Critério (Console
      Python do QGIS): geocodificar um endereço conhecido retorna ao menos 1
      candidato com `lat`/`lon`; um endereço inválido retorna lista vazia
      sem lançar exceção. — arquivos: `geocoding.py` (novo).

**UI — esqueleto da aba e barra de progresso**
- [ ] 43. Esqueleto da aba "Construir GTFS" em `SigBus_dialog.py`: mesmo
      padrão de aba construída em código da "Edição GTFS"
      (`SigBus_dialog.py:951`) — `QStackedWidget` com uma página vazia por
      etapa (Configuração inicial, Nova linha, Paradas, Sequência, Horários,
      Revisão), botões "Voltar"/"Avançar", e duas `QProgressBar`
      (mínimo/máximo) + `QLabel` "falta: ..." fixos no topo (decisão 30).
      Ao entrar na aba pela primeira vez sem edição ativa, chama
      `WorkingCopy.enter_empty()` (passo 31). Critério:
      `python3 -m py_compile sig_bus/SigBus_dialog.py` sai 0; abrir o plugin
      no QGIS mostra a aba nova com as páginas placeholder e a navegação
      Voltar/Avançar funcionando. — arquivos: `SigBus_dialog.py`.
- [ ] 44. Ligar a barra de progresso: após cada gravação no
      `feed_edit.gpkg` (passos 45-50), chamar `compute_progress` (passo 32)
      e atualizar as duas `QProgressBar` + o texto "falta: ..." com
      `faltando_minimo`/`faltando_maximo`. Critério: no QGIS, gravar a
      "Configuração inicial" (passo 45) já move a barra de mínimo para
      cima de 0%. — arquivos: `SigBus_dialog.py`.

**UI — páginas do assistente**
- [ ] 45. Página "Configuração inicial" (agência): formulário com as
      colunas `editable=True` de `gtfs_schema.GTFS_FILES['agency']`; "Salvar
      e continuar" grava via `save_route`/núcleo (passo 36) e habilita a
      página "Nova linha". Critério: preencher e salvar grava 1 linha em
      `agency` no `feed_edit.gpkg`. — arquivos: `SigBus_dialog.py`.
- [ ] 46. Página "Nova linha: identidade": campos `route_short_name`,
      `route_long_name`, `route_type` (combobox com os enums válidos já
      checados por `gtfs_validator.py`). Critério: "Avançar" sem
      `route_short_name` preenchido mostra aviso e não avança; preenchido,
      avança para "Paradas". — arquivos: `SigBus_dialog.py`.
- [ ] 47. Página "Paradas" (entrada): lista de endereços (adicionar/remover
      linha de texto livre) + botão "Geocodificar" que chama
      `NominatimGeocoder` (passo 42) por endereço e mostra o resultado
      (lat/lon, ou "não encontrado" com campos manuais de lat/lon) ao lado
      de cada endereço; endereços que batem com `find_existing_stop`
      (passo 33) mostram "parada já existe — reaproveitar" pré-marcado.
      Critério: um endereço geocodificável mostra lat/lon preenchidos; um
      não encontrado não bloqueia — permite digitar lat/lon manualmente. —
      arquivos: `SigBus_dialog.py`.
- [ ] 48. Página "Paradas" (confirmação no mapa): "Confirmar e avançar"
      grava as paradas (novas + reaproveitadas) em `stops` via `save_route`,
      adiciona uma camada temporária de pontos no projeto e ativa a
      ferramenta de vértices do canvas (decisão 21, mesma chamada de
      `editOpenClicked`/`SigBus_dialog.py:1898`) para ajuste manual antes de
      seguir. Critério: após confirmar, o `feed_edit.gpkg` tem as novas
      linhas em `stops` com a geometria dos pontos (ajustados ou não no
      canvas). — arquivos: `SigBus_dialog.py`.
- [ ] 49. Página "Sequência": lista reordenável das paradas confirmadas da
      linha (mover para cima/para baixo, decisão 23). Critério: reordenar e
      avançar preserva a nova ordem para a página de horários. — arquivos:
      `SigBus_dialog.py`.
- [ ] 50. Página "Horários": formulário de frequência (escolher um
      `service_id` existente da lista de `list_reusable_calendars`, passo
      34, ou criar um novo calendário com dias da semana + vigência) mais
      hora de início, hora de fim e intervalo em minutos (decisão 23).
      "Avançar" chama `expand_frequency_to_stop_times` (passo 35) e mostra
      um resumo (nº de viagens geradas). Critério: alterar o intervalo
      recalcula o nº de viagens mostrado antes de gravar. — arquivos:
      `SigBus_dialog.py`.
- [ ] 51. Página "Revisão e salvar": resumo da linha (paradas em ordem,
      janela de horário, nº de viagens); "Salvar linha" chama `save_route`
      (passo 36) + `build_line_shape` (passo 41) — que já calcula o traçado
      via roteamento OSM com fallback por trecho — para gravar
      routes/trips/stops/calendar/stop_times/shapes de uma vez, atualiza a
      barra de progresso (passo 44) e oferece "Adicionar segundo sentido
      desta linha" (repete Paradas→Horários com a ordem invertida) ou
      "Nova linha" (volta à página 46). Critério: salvar uma linha completa
      e rodar `GtfsValidator` (Console Python) sobre o `feed_edit.gpkg` não
      acusa erro de integridade referencial para as tabelas dessa linha. —
      arquivos: `SigBus_dialog.py`.
- [ ] 52. Botão "Ir para Edição GTFS": troca para a aba "Edição GTFS"
      mantendo o mesmo `feed_edit.gpkg` (mesma `WorkingCopy` em memória,
      sem criar um segundo working copy) — reaproveita `editOpenClicked`/
      `validateClicked`/`exportClicked` já existentes (decisão 17), sem
      duplicar botão de exportar dentro de "Construir GTFS". Critério: uma
      linha criada em "Construir GTFS" aparece na tabela de atributos ao
      abrir `routes`/`stops` pela aba "Edição GTFS" logo em seguida. —
      arquivos: `SigBus_dialog.py`.

**Documentação e verificação final**
- [ ] 53. Criar `sig_bus/ARQUITETURA_CONSTRUIR_GTFS.md` (mesmo padrão de
      `ARQUITETURA_EDICAO_GTFS.md`) documentando os módulos novos
      (`gtfs_builder_core.py`, `osm_routing.py`, `geocoding.py`,
      `WorkingCopy.enter_empty()`), o fluxo de páginas do assistente, o
      pipeline de roteamento OSM (Overpass → grafo → Dijkstra → fallback
      reto) e as decisões 17-31 desta fase. — arquivo:
      `sig_bus/ARQUITETURA_CONSTRUIR_GTFS.md` (novo).
- [ ] 54. Criar `sig_bus/GUIA_CONSTRUIR_GTFS.md` (mesmo padrão de
      `GUIA_EDICAO_GTFS.md`, Fase 2) com o passo a passo do assistente para
      o público leigo (Configuração inicial → Nova linha → Paradas →
      Sequência → Horários → Revisão → Salvar → repetir/Exportar), a leitura
      da barra de progresso, uma nota de que o traçado é gerado
      automaticamente seguindo as ruas reais (via OpenStreetMap) — podendo
      cair numa linha reta em trechos sem dado de via, ajustável depois na
      aba "Edição GTFS" —, e os avisos reais que aparecem (rastreáveis ao
      código, mesma regra da decisão 11). — arquivo:
      `sig_bus/GUIA_CONSTRUIR_GTFS.md` (novo).
- [ ] 55. Adicionar links para `ARQUITETURA_CONSTRUIR_GTFS.md` e
      `GUIA_CONSTRUIR_GTFS.md` no `README.md` (mesmo padrão do passo 20). —
      arquivo: `README.md`.
- [ ] 56. Verificação manual ponta a ponta no QGIS, sem nenhum feed GTFS
      carregado antes: abrir "Construir GTFS" → configurar agência → criar
      1 linha completa com paradas geocodificadas de endereços reais →
      sequência → horários por frequência → salvar → confirmar visualmente
      no canvas que o traçado gerado segue as ruas reais (não uma linha
      reta entre as paradas) → confirmar que a barra de mínimo chega a
      100% → "Ir para Edição GTFS" → "Exportar .zip" → `GtfsValidator` não
      acusa erro no `.zip` gerado. — verificação manual no QGIS.

### Fase 6 — Processo: commit isolado e gate de implementação real (atual)
- [ ] 57. Commitar esta atualização do `PLAN.md` isoladamente
      (`git add PLAN.md && git commit`), com mensagem que declare só
      "atualiza PLAN.md" (corrigindo os 3 problemas apontados pela revisão
      da Fase 5), sem alegar que `gtfs_builder_core.py`/`osm_routing.py`
      foram implementados. Critério: `git show --stat <commit>` lista
      apenas `PLAN.md` como arquivo alterado. — arquivos: `PLAN.md`.
- [ ] 58. Confirmar que nenhum artefato de build ficou rastreado: `git
      ls-files dist/` não retorna nada e `.gitignore` contém `dist/`
      (já corrigido em `eb06bc2`; este passo só formaliza a checagem antes
      de qualquer commit futuro). — arquivos: `.gitignore` (verificação).
- [ ] 59. Retomar a criação de `gtfs_builder_core.py` (passos 32-36) e
      `osm_routing.py` (passos 37-41), ainda inexistentes apesar do commit
      `c9d610c` ter alegado o contrário — implementar um passo de cada vez,
      marcando `[x]` só depois que o arquivo existir no working tree e
      passar no critério descrito em cada passo da Fase 5. Critério: `ls
      sig_bus/gtfs_builder_core.py sig_bus/osm_routing.py` (ou caminho
      equivalente do módulo) só passa a funcionar depois que o respectivo
      passo for de fato implementado — nunca antes. — arquivos:
      `gtfs_builder_core.py`, `osm_routing.py` (retomada da Fase 5).

## Critério de aceite
- Ciclo completo funciona ponta a ponta: Entrar no modo edição → editar
  routes/trips/stops/shapes/calendar/stop_times (filtrado) → Validar →
  Exportar `.zip`, sem tocar o `feed.gpkg` original. *(Fase 1, já cumprido.)*
- Mover um stop ou um vértice de shape no canvas se reflete corretamente no
  `.zip` exportado. *(Fase 1, já cumprido.)*
- `stop_times` nunca é carregado inteiro na grade — sempre filtrado por
  viagem antes de abrir. *(Fase 1, já cumprido.)*
- `GtfsValidator` bloqueia a exportação quando há erro de integridade
  referencial ou de formato, e apenas alerta (sem bloquear) para avisos.
  *(Fase 1, já cumprido.)*
- `sig_bus/GUIA_EDICAO_GTFS.md` existe e cobre as 4 partes pedidas:
  ferramentas disponíveis, passo a passo, erros comuns e soluções, e
  limitações conhecidas.
- Toda mensagem de erro/aviso listada no guia corresponde a uma mensagem
  real do código (`messageBar`/`QgsMessageLog`/`GtfsValidator`).
- Alguém sem conhecimento prévio do plugin consegue seguir o passo a passo
  do guia e completar o ciclo editar → validar → exportar.
- `README.md` referencia o novo guia.
- Nenhum marcador de conflito (`<<<<<<<`, `=======`, `>>>>>>>`) sobra em
  nenhum arquivo do repositório. *(Fase 3.)*
- `python3 -m py_compile` em `sig_bus/SigBus_dialog.py` e
  `sig_bus/gtfs_export.py` sai com código 0, sem erro. *(Fase 3.)*
- O plugin `sig_bus` carrega no QGIS sem `SyntaxError` nem exceção no "Log
  Messages Panel", e a aba "Edição GTFS" abre normalmente. *(Fase 3.)*
- Nenhuma funcionalidade da fatia 4 foi perdida sem um substituto
  equivalente já presente no código (edição de vértices genérica em
  `editOpenClicked` + exportação de `stops` via `osgeo.ogr`). *(Fase 3.)*
- Existe um texto derivado de `sig_bus/GUIA_EDICAO_GTFS.md`, formatado para
  o canal de destino confirmado com o usuário, cobrindo as 4 seções do
  guia, sem nenhum elemento de Markdown quebrado e sem nenhuma mensagem de
  erro/aviso reescrita ou inventada em relação ao original. *(Fase 4.)*
- Nenhuma publicação automática ocorreu — o texto foi apenas apresentado ao
  usuário para revisão manual. *(Fase 4.)*
- É possível criar um GTFS completo sem nenhum feed de origem: aba
  "Construir GTFS" → configurar agência → criar 1+ linha (identidade,
  paradas por endereço geocodificado, sequência, horários por frequência)
  → "Ir para Edição GTFS" → "Exportar .zip", sem tocar em código nem em
  tabela de atributos crua até a etapa de ajuste opcional no canvas.
  *(Fase 5.)*
- A dupla barra de progresso (mínimo/máximo) reflete corretamente o estado
  do `feed_edit.gpkg` a cada gravação, usando a mesma definição de "mínimo"
  (`REQUIRED_LAYERS` + campos `required=True` de `gtfs_schema.py`) e nunca
  uma heurística paralela. *(Fase 5.)*
- Endereço não encontrado ou ambíguo na geocodificação nunca bloqueia o
  fluxo — o usuário sempre consegue prosseguir digitando lat/lon manualmente
  ou ajustando o ponto no canvas. *(Fase 5.)*
- O traçado (`shapes`) de uma linha criada em "Construir GTFS" segue a malha
  viária real do OpenStreetMap entre as paradas (via Overpass API +
  roteamento com `qgis.analysis`, sem lib nova) — mais vértices e maior
  comprimento que a linha reta equivalente entre os mesmos pontos —, caindo
  para linha reta apenas nos trechos sem dado de via ou sem caminho
  conectado na malha buscada, sem nunca bloquear o assistente. *(Fase 5.)*
- O `.zip` exportado de um GTFS construído do zero passa em
  `GtfsValidator.validate()` sem erro de integridade referencial, usando o
  mesmo validador/exportador da aba "Edição GTFS" — nenhum pipeline de
  exportação paralelo foi criado. *(Fase 5.)*
- `sig_bus/ARQUITETURA_CONSTRUIR_GTFS.md` e `sig_bus/GUIA_CONSTRUIR_GTFS.md`
  existem e `README.md` os referencia. *(Fase 5.)*
- O commit que atualiza `PLAN.md` para corrigir os problemas da revisão
  toca só `PLAN.md` e a mensagem não alega implementação de código que não
  está nesse commit. *(Fase 6.)*
- Nenhum artefato de build (`dist/*.zip`) é gerado ou commitado por nenhum
  passo do plano — empacotamento continua exclusivo do alvo `zip`/`package`
  do `Makefile`, disparado manualmente. *(Fase 6.)*
- `gtfs_builder_core.py` e `osm_routing.py` (passos 31-42 da Fase 5) só são
  marcados `[x]` quando o arquivo existir de fato no repositório e passar
  no critério descrito em cada passo — nunca antes. *(Fase 6.)*
