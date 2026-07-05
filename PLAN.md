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
