# Tópico: gtfs
_Memória deste tópico. O orquestrador lê isto no início de toda conversa._
Atualizado: 2026-07-13 · HEAD: 20a05fd (branch `feature/construir-gtfs`)

## Objetivo
Duas frentes no plugin QGIS `sig_bus` (v0.4): (1) editar um GTFS já carregado
("Edição GTFS") e (2) **construir um GTFS do zero** ("Construir GTFS", núcleo
desta branch) a partir de endereços + itinerário, com traçado roteado pela
malha viária do OSM (Overpass + `qgis.analysis`). Plano completo e decisões
em `PLAN.md` (raiz do repo).

## Estado atual (o que JÁ está feito e verificado)
- **Fase 1 — Edição GTFS**: implementada e verificada (14/14 passos). Editar
  campos/geometria em `feed_edit.gpkg` isolado, validar (`gtfs_validator.py`)
  e exportar `.zip` normalizado.
- **Fase 2 — Guia do usuário**: `sig_bus/GUIA_EDICAO_GTFS.md` existe e é
  linkado no `README.md`.
- **Fase 3 — Hotfix conflito de merge**: verificado agora — sem marcadores
  `<<<<<<<` em `.py`/`.ui`, `py_compile` de `SigBus_dialog.py` e
  `gtfs_export.py` passa sem erro.
- **Fase 5 — Construir GTFS do zero**: **0% feito.** Confirmado agora por
  `ls`/`grep`: `gtfs_builder_core.py`, `osm_routing.py`, `geocoding.py` não
  existem; `gtfs_edit_core.py` não tem `enter_empty()`; `SigBus_dialog.py`
  não tem aba "Construir GTFS" nem `QStackedWidget` novo. Apesar de commits
  anteriores (`c9d610c`, `0817dd6`) sugerirem progresso, nenhum código real
  foi escrito ainda.
- `dist/` não está rastreado e consta no `.gitignore` (verificado agora).
- **PLAN.md tem edição não commitada na working tree** (`git status` mostra
  `modified: PLAN.md`): uma seção "Panorama atual (reavaliação 2026-07-12)" e
  os passos 27/57/58 revisados, ainda não commitados.

## Decisões tomadas
Lista completa numerada em `PLAN.md` (34 decisões). As mais relevantes p/
retomada:
- Fase 5 reaproveita o `feed_edit.gpkg` e o pipeline de validar/exportar já
  existentes (decisão 17) — não cria pipeline paralelo.
- Geocodificação: Nominatim via `QgsNetworkAccessManager` (decisão 19).
  Roteamento: Overpass (malha) + `qgis.analysis`/`QgsGraphAnalyzer` Dijkstra
  (decisões 25-26), com fallback silencioso pra linha reta por trecho
  (decisão 27) — nunca bloqueia o assistente.
- `[x]` num passo só é válido se o arquivo existir de fato e passar no
  critério descrito (decisão 34) — regra criada depois de commits que
  alegaram progresso inexistente (ver Armadilhas).
- Empacotamento (`dist/*.zip`) nunca entra no fluxo do plano — é manual via
  `Makefile` (decisão 33).

## Pendências / próximo passo
1. **Commitar o PLAN.md** (mudança já na working tree, isolado, decisão 32)
   antes de seguir — senão o histórico de decisões da reavaliação se perde.
2. **Fase 4, passo 27 (bloqueado):** canal/formato de destino do guia
   (aparentemente GitHub Markdown, sugerido pelo commit `0c56ffe`) ainda não
   está registrado como decisão explícita no `PLAN.md` — só o checkbox foi
   mexido. Resolver isso é rápido e desbloqueia os passos 28-30.
3. **Fase 5 (prioridade real da branch), começar pelo núcleo sem QGIS:**
   passo 31 `WorkingCopy.enter_empty()` em `gtfs_edit_core.py` é
   pré-requisito de tudo; depois 32-36 (`gtfs_builder_core.py`); só depois
   37-42 (`osm_routing.py`, `geocoding.py`, dependem do QGIS); UI (43+) por
   último.

## Armadilhas (o que já deu errado aqui — pra não repetir)
- **Commit `96122e8`** ("conflitos resolvidos") na verdade deixou marcadores
  `<<<<<<<`/`=======`/`>>>>>>>` commitados em `SigBus_dialog.py` e
  `gtfs_export.py` → `SyntaxError`, plugin não carregava. Corrigido na Fase 3.
- **Commit `c9d610c`** ("Implementação do GTFS do zero com roteamento OSM")
  alegou implementação completa mas só alterou `PLAN.md` — nenhum módulo
  novo foi criado. **Nunca confie na mensagem de commit**: sempre confirmar
  com `ls`/`git show --stat` que o arquivo alegado existe.
- **Commit `0817dd6`** commitou `dist/sig_bus-0.4.zip` (785KB, artefato de
  build binário) sem necessidade — corrigido em `eb06bc2`. Empacotamento
  nunca deve ser commitado (decisão 33).
- **Commit `0c56ffe`** reverteu o checkbox do passo 27 de `[x]`→`[ ]` sem
  escrever a decisão correspondente no texto — checkbox sozinho não é
  registro de decisão.
