## Visão Geral

A funcionalidade de **Edição GTFS** do SIG-Bus permite editar campos e a geometria de um feed GTFS previamente carregado, realizando validações de integridade e exportando o resultado em um arquivo compactado `.zip` normalizado.

### Cópia de Trabalho Isolada (`feed_edit.gpkg`)
Para garantir a segurança dos dados e evitar a corrupção do banco de dados de análise original (`feed.gpkg`), todas as edições são realizadas em uma cópia de trabalho isolada chamada `feed_edit.gpkg`. Esta cópia é criada no mesmo diretório do arquivo original.

Com essa abordagem:
1. O feed original carregado para análise **nunca** é modificado diretamente.
2. Você pode descartar todas as edições e retornar ao estado original a qualquer momento.
3. As edições permanecem salvas localmente até que você decida exportá-las ou descartá-las.

### Motor de Edição Híbrido
O SIG-Bus utiliza um modelo híbrido para edição:
* **Interface do Plugin (SIG-Bus):** Serve para gerenciar o ciclo de vida da edição (entrar, validar, exportar, descartar), selecionar qual tabela será editada, aplicar filtros para as tabelas volumosas e proteger campos-chave contra alterações acidentais.
* **Ferramentas Nativas do QGIS:** A edição real dos atributos e das geometrias ocorre diretamente nas tabelas de atributos nativas do QGIS e nas ferramentas de edição de vértices do canvas de mapas. Isso permite usufruir de recursos avançados do QGIS, como desfazer/refazer (Undo/Redo), calculadora de campos e snapping de vértices.

---

## Ferramentas Disponíveis

A aba **Edição GTFS** disponibiliza as seguintes ferramentas e controles:

### 1. Botão "Entrar no modo edição"
* **Função:** Inicia ou retoma o modo de edição do GTFS.
* **Funcionamento:** Cria a cópia de trabalho `feed_edit.gpkg` clonando o arquivo original `feed.gpkg`. Se já houver uma cópia de trabalho activa (uma edição em andamento), o plugin perguntará se você deseja:
  * **Retomar:** Continuar editando de onde parou.
  * **Recomeçar:** Descartar a edição atual e criar uma nova cópia limpa a partir do feed de análise original (sobrescrevendo o arquivo temporário).

### 2. Seletor "Tabela" (Combobox)
* **Função:** Permite escolher qual tabela do GTFS você deseja editar.
* **Funcionamento:** Lista apenas as tabelas editáveis especificadas no esquema do GTFS. As opções incluem:
  * `agency` (Agências)
  * `routes` (Linhas/Rotas)
  * `trips` (Viagens)
  * `stops` (Pontos de Parada)
  * `stop_times` (Horários de Parada)
  * `calendar` (Calendário/Operação regular)
  * `calendar_dates` (Exceções de Calendário)
  * `shapes` (Traçados/Geometria das viagens)
* **Nota:** Quando a tabela selecionada for `stop_times`, a interface habilitará automaticamente os seletores de **Linha** e **Viagem** para aplicação de filtro obrigatório.

### 3. Seletores de Filtro ("Linha" e "Viagem")
* **Função:** Filtram os dados da tabela `stop_times` antes de carregá-la para edição.
* **Funcionamento:** Devido ao grande volume de dados contido na tabela `stop_times` (que pode conter milhões de registros e travar o QGIS se carregada inteira), estes campos tornam-se ativos apenas quando `stop_times` é a tabela selecionada.
  * Você deve selecionar primeiro uma linha (`route_short_name`) e, em seguida, uma viagem específica (`trip_id`).
  * Apenas os horários associados a essa viagem selecionada serão carregados para visualização e edição.

### 4. Botão "Abrir para edição"
* **Função:** Carrega a tabela selecionada no QGIS para que você possa editá-la.
* **Funcionamento:**
  * Adiciona a tabela correspondente do arquivo `feed_edit.gpkg` ao painel de camadas do QGIS como uma camada vetorial (`QgsVectorLayer`).
  * Coloca a camada automaticamente em modo de edição (`startEditing()`).
  * Abre a tabela de atributos nativa do QGIS para edição manual dos dados.
  * Se la tabela contiver dados espaciais (`stops` ou `shapes`), centraliza a visualização nela e ativa automaticamente a ferramenta de edição de vértices no canvas do mapa para que você possa mover pontos ou ajustar os traçados das linhas.
  * Define os campos de ID e chaves estrangeiras como de leitura exclusiva (*read-only*) no formulário do QGIS para evitar que a integridade do banco de dados seja quebrada acidentalmente.
  * Fecha temporariamente a janela do plugin para liberar espaço de tela para o trabalho no QGIS.

### 5. Botão "Validar"
* **Função:** Executa verificações de integridade e consistência na cópia de trabalho `feed_edit.gpkg`.
* **Funcionamento:** Aciona o validador interno que executa checagens por meio de consultas otimizadas no banco de dados. As validações incluem:
  * **Integridade Referencial:** Garante que todos os IDs informados (como `route_id`, `service_id` e `shape_id` em viagens, ou `trip_id` e `stop_id` em horários) correspondam a registros existentes nas respectivas tabelas de origem.
  * **Formato de Dados:** Verifica a formatação correta de horários (`HH:MM:SS`), datas (`YYYYMMDD`), coordenadas geográficas (latitudes e longitudes dentro de limites realistas) e códigos de enums (tipos de rotas, direções, tipos de exceção).
  * **Resultado:** Exibe a contagem de avisos e erros encontrados diretamente na barra de mensagens do QGIS e detalha cada falha encontrada no painel de logs do plugin (`SIG-Bus`).

### 6. Botão "Exportar .zip"
* **Função:** Gera o arquivo final compactado `.zip` com os arquivos de texto do GTFS atualizados.
* **Funcionamento:**
  * Roda automaticamente o validador antes de iniciar.
  * Se forem encontrados **erros fatais** (ex.: IDs órfãos nas chaves estrangeiras), a exportação é abortada e o relatório de erros é exibido.
  * Se houver apenas **avisos** (ex.: campos opcionais mal formatados), o plugin pergunta se você deseja ignorá-los e prosseguir.
  * Caso a validação seja aceita, abre uma janela para escolha do local e nome do arquivo `.zip` de destino.
  * Cria uma tarefa em segundo plano (`GtfsExporter`) que exporta os dados de forma otimizada (*streaming*), garantindo que as coordenadas geográficas de `stops.txt` e `shapes.txt` sejam reconstruídas diretamente com base na geometria atualizada desenhada no mapa do QGIS, e ordena as colunas conforme o padrão oficial do GTFS.

### 7. Botão "Descartar edição"
* **Função:** Cancela todas as modificações não exportadas e encerra a edição.
* **Funcionamento:** Exibe um aviso de confirmação. Se confirmado pelo usuário, o plugin remove a camada do painel de controle do QGIS, exclui fisicamente o arquivo temporário `feed_edit.gpkg` do disco e retorna a aba ao seu estado desativado inicial.

---

## Passo a Passo: Fluxo Feliz Completo

Esta seção apresenta um passo a passo do fluxo feliz completo de edição, validação e exportação de dados do GTFS usando o plugin.

### 1. Entrar no modo edição
Clique no botão **Entrar no modo edição**.
* O plugin criará uma cópia de trabalho isolada `feed_edit.gpkg` a partir do feed de análise original `feed.gpkg`.
* Se já existir uma edição em andamento, você pode escolher entre **Retomar** (continuar de onde parou) ou **Recomeçar** (descartar e iniciar um novo rascunho limpo).

### 2. Escolher a tabela
No seletor **Tabela**, escolha qual tabela deseja editar (por exemplo: `routes`, `stops` ou `shapes`).

### 3. [Se a tabela for `stop_times`] Filtrar por Linha e Viagem
Caso tenha escolhido a tabela `stop_times`, selecione obrigatoriamente a linha no campo **Linha** e a viagem no campo **Viagem** para aplicar o filtro.
**Nota:** Esta etapa é necessária para limitar a quantidade de dados carregados, garantindo a performance do QGIS.

### 4. Abrir para edição
Clique em **Abrir para edição**. A camada correspondente será carregada no painel do QGIS em modo de edição e a tabela de atributos nativa será aberta.

### 5. Editar na grade de atributos ou nos vértices do canvas
Realize as alterações necessárias no QGIS:
* **Edição de Atributos:** Modifique as colunas de dados diretamente na tabela de atributos (com exceção das colunas de chaves que estarão bloqueadas para leitura).
* **Edição Geométrica:** Caso esteja editando `stops` ou `shapes`, use a ferramenta nativa de edição de vértices do QGIS para reposicionar paradas ou alterar o traçado das rotas diretamente no mapa (canvas).
* **Salvar:** Salve as modificações na própria camada do QGIS ao concluir.

### 6. Validar as alterações
Volte ao painel do plugin e clique em **Validar**.
* O plugin executará as regras de integridade referencial e formato.
* Verifique se existem erros ou avisos na barra de mensagens ou no painel de log do `SIG-Bus`. Corrija eventuais erros antes de exportar.

### 7. Exportar o `.zip`
Clique em **Exportar .zip**.
* O validador rodará novamente. Se houver erros fatais, o plugin impedirá a exportação. Se houver apenas avisos, você decidirá se quer prosseguir.
* Indique a pasta e o nome do arquivo compactado final e salve. O plugin reestrutura de forma automatizada e ordenada os dados exportados (calculando latitude/longitude dos pontos e geometrias dos caminhos a partir do mapa).

### 8. Descartar edição para recomeçar (optional)
Se quiser descartar as alterações locais e voltar ao estado original do `feed.gpkg`, clique no botão **Descartar edição** e confirme a exclusão do banco de rascunho `feed_edit.gpkg`.

---

## Erros Comuns e Soluções

Esta seção lista as principais mensagens de aviso e erro emitidas pela interface do plugin e pelo validador interno (`GtfsValidator`), explicando suas causas prováveis e como solucioná-las.

### 1. Mensagens da Interface do Plugin

* **"GTFS não encontrado — carregue ou reconecte o GeoPackage primeiro."** (Aviso)
  * **Causa:** O usuário tentou iniciar a edição sem ter um feed GTFS carregado ou sem que o arquivo GeoPackage de análise original esteja no local correto.
  * **Solução:** Carregue um arquivo GTFS `.zip` válido na aba principal do plugin ou clique em "Reconectar GeoPackage" para redefinir o caminho para o arquivo original `.gpkg`.

* **"Falha ao criar a cópia de trabalho do GeoPackage (feed_edit.gpkg)."** (Erro)
  * **Causa:** Não foi possível criar o arquivo de trabalho isolado no disco. Geralmente decorre de falta de permissões de escrita na pasta do feed ou espaço em disco esgotado.
  * **Solução:** Certifique-se de que o diretório que contém o feed GTFS original tem permissão de escrita e que há espaço suficiente em disco.

* **"Nenhuma edição para descartar."** (Aviso)
  * **Causa:** O botão "Descartar edição" foi clicado sem que houvesse um processo de edição ativo.
  * **Solução:** Nenhuma ação é necessária.

* **"Falha ao apagar o arquivo de edição temporário."** (Erro)
  * **Causa:** O sistema operacional impediu a exclusão do arquivo `feed_edit.gpkg` porque ele ainda está sendo lido/escrito pelo QGIS ou outro programa.
  * **Solução:** Remova manualmente do QGIS as camadas que começam com `edit_`, feche qualquer tabela de atributos aberta e tente descartar novamente. Se o problema persistir, reinicie o QGIS.

* **"Entre no modo edição primeiro."** (Aviso)
  * **Causa:** O usuário tentou abrir uma tabela para edição sem ter iniciado o modo de edição.
  * **Solução:** Clique no botão **Entrar no modo edição** antes de tentar abrir qualquer tabela.

* **"Selecione uma viagem para editar a tabela stop_times."** (Aviso)
  * **Causa:** O usuário escolheu a tabela `stop_times` no seletor, mas não definiu uma viagem específica para filtrar.
  * **Solução:** Nos seletores de filtro da interface, escolha primeiro a **Linha** e depois a **Viagem** (trip) desejada antes de clicar em "Abrir para edição".

* **"Falha ao carregar a camada edit_{tabela}."** (Erro)
  * **Causa:** A tabela correspondente não pôde ser carregada a partir do `feed_edit.gpkg`, possivelmente por corrupção de dados ou inconsistência na estrutura do GeoPackage de rascunho.
  * **Solução:** Clique em **Entrar no modo edição** novamente e selecione a opção **Recomeçar** para limpar o rascunho e gerar uma nova cópia de trabalho.

* **"Nenhuma edição ativa para validar."** (Aviso)
  * **Causa:** O botão "Validar" foi clicado sem que o modo de edição estivesse ativado.
  * **Solução:** Ative o modo de edição clicando em **Entrar no modo edição**.

* **"Arquivo de edição GeoPackage não encontrado."** (Erro)
  * **Causa:** O arquivo `feed_edit.gpkg` foi excluído ou movido manualmente do diretório original durante a sessão de edição.
  * **Solução:** Inicie uma nova edição clicando em **Entrar no modo edição**.

* **"Erro durante a validação: {detalhes}"** ou **"Erro durante a validação pré-exportação: {detalhes}"** (Erro)
  * **Causa:** Falha de banco de dados SQLite ou erro de execução no código do validador.
  * **Solução:** Consulte os logs no painel inferior do QGIS (aba `SIG-Bus`). Em caso de corrupção, recomece a edição.

* **"A exportação foi cancelada devido a erros de validação..."** (Erro Fatal / Diálogo)
  * **Causa:** Foram identificados erros graves que violam as regras do GTFS ou que quebrariam a integridade dos dados na exportação.
  * **Solução:** Verifique a lista de erros exibida no diálogo ou no painel de log (SIG-Bus) e edite as tabelas correspondentes para fazer as correções necessárias antes de tentar exportar novamente.

* **"A validação encontrou alguns avisos. Deseja prosseguir com a exportação mesmo assim?"** (Aviso / Diálogo)
  * **Causa:** Existem problemas não impeditivos identificados nos dados (ex: campos opcionais preenchidos incorretamente ou tabelas opcionais ausentes).
  * **Solução:** O usuário pode escolher prosseguir clicando em **Sim** (gerando o `.zip` normalmente) ou cancelar clicando em **Não** para corrigir as inconsistências.

### 2. Mensagens do Validador (`GtfsValidator`)

#### A. Erros de Integridade Referencial

* **"Erro de integridade referencial: route_id '{id}' em trips ({N} ocorrências) não existe na tabela routes."**
  * **Causa:** Há registros na tabela `trips` associados a um identificador de linha (`route_id`) que não está cadastrado na tabela `routes`.
  * **Solução:** Edite a tabela `trips` e altere as viagens para usar um `route_id` válido, ou cadastre a rota correspondente na tabela `routes`.

* **"Erro de integridade referencial: a tabela 'routes' está ausente, mas existem {N} viagens referenciando-a em 'trips'."**
  * **Causa:** A tabela `routes` não existe no feed, mas a tabela `trips` tenta referenciá-la.
  * **Solução:** Certifique-se de que a tabela `routes` seja restaurada e carregada no GTFS.

* **"Erro de integridade referencial: service_id '{id}' em trips ({N} ocorrências) não existe nas tabelas calendar ou calendar_dates."**
  * **Causa:** A viagem está programada para um calendário de operação (`service_id`) que não existe nas definições de calendário do feed.
  * **Solução:** Cadastre as regras do serviço na tabela `calendar` ou insira datas de exceção na tabela `calendar_dates`.

* **"Erro de integridade referencial: shape_id '{id}' em trips ({N} ocorrências) não existe na tabela shapes."**
  * **Causa:** A viagem faz referência a um traçado geométrico (`shape_id`) que não tem nenhuma coordenada ou geometria desenhada.
  * **Solução:** Desenhe ou importe o traçado correspondente na camada `shapes` do mapa ou atribua um `shape_id` válido e existente à viagem.

* **"Erro de integridade referencial: trip_id '{id}' em stop_times ({N} ocorrências) não existe na tabela trips."**
  * **Causa:** Existem registros de horários de parada vinculados a um ID de viagem (`trip_id`) que não existe na tabela `trips`.
  * **Solução:** Corrija o `trip_id` na tabela `stop_times` para corresponder a uma viagem válida ou remova esses registros órfãos.

* **"Erro de integridade referencial: stop_id '{id}' em stop_times ({N} ocorrências) não existe na tabela stops."**
  * **Causa:** O horário de parada faz referência a um ponto (`stop_id`) que não está listado ou desenhado.
  * **Solução:** Desenhe o ponto correspondente na camada de mapa `stops` ou ajuste o `stop_id` nos horários da viagem.

* **"Erro de integridade referencial: agency_id '{id}' em routes ({N} ocorrências) não existe na tabela agency."**
  * **Causa:** A rota aponta para uma agência (`agency_id`) que não está descrita na tabela principal `agency`.
  * **Solução:** Ajuste o `agency_id` na tabela `routes` ou cadastre a agência na tabela `agency`.

* **"Aviso de integridade referencial: a tabela 'agency' está ausente, mas existem {N} rotas com agency_id preenchido."**
  * **Causa:** Não há tabela `agency` cadastrada, mas existem campos de ID de agência preenchidos em rotas.
  * **Solução:** Em sistemas simplificados de agência única, isso pode ser ignorado (apenas aviso). Caso contrário, recarregue a tabela `agency`.

#### B. Erros de Formato de Dados

* **"Erro de formato: arrival_time '{valor}' em stop_times ({N} ocorrências) não segue o formato HH:MM:SS."**
  * **Causa:** O horário de chegada em um ponto está com padrão inválido (ex.: usando `AM/PM`, letras ou formato de hora incompleto).
  * **Solução:** Ajuste o horário na tabela de atributos para seguir estritamente o formato de 24h `HH:MM:SS` (ex.: `07:15:00` ou `24:30:00` para serviços pós-meia-noite).

* **"Erro de formato: departure_time '{valor}' em stop_times ({N} ocorrências) não segue o formato HH:MM:SS."**
  * **Causa:** O horário de partida não segue o formato `HH:MM:SS`.
  * **Solução:** Ajuste a formatação na tabela de atributos para `HH:MM:SS`.

* **"Erro de formato: start_date/end_date/date '{valor}' em calendar/calendar_dates ({N} ocorrências) não segue o formato YYYYMMDD."**
  * **Causa:** A data cadastrada contém caracteres especiais, barras, traços ou não possui exatamente 8 dígitos.
  * **Solução:** Edite as datas para conterem apenas números na sequência de ano, mês e dia (ex.: `20260705`).

* **"Erro de formato: stop_lat '{valor}' em stops (stop_id '{id}') fora da faixa válida [-90, 90]."**
  * **Causa:** A latitude informada para a parada está com valor fisicamente impossível no planeta.
  * **Solução:** Verifique o posicionamento do ponto no mapa (se foi desenhado fora da projeção correta) ou edite o valor da latitude para a faixa entre -90 e 90.

* **"Erro de formato: stop_lon '{valor}' em stops (stop_id '{id}') fora da faixa válida [-180, 180]."**
  * **Causa:** A longitude informada está com valor fisicamente impossível.
  * **Solução:** Mova o ponto no mapa para a coordenada geográfica correta ou edite o valor para a faixa entre -180 e 180.

* **"Erro de formato: route_type '{valor}' em routes (route_id '{id}') inválido. Valores aceitos: 0, 1, 2, 3, 4, 5, 6, 7, 11, 12."**
  * **Causa:** O tipo de transporte cadastrado não corresponde a um código aceito pela especificação GTFS.
  * **Solução:** Altere a coluna `route_type` para usar um código padrão (ex.: `3` para ônibus, `0` para bonde, `1` para metrô, etc.).

* **"Erro de formato: direction_id '{valor}' em trips (trip_id '{id}') inválido. Valores aceitos: 0 ou 1."**
  * **Causa:** O identificador de direção da viagem foi preenchido com valor diferente de 0 ou 1.
  * **Solução:** Altere a coluna `direction_id` para `0` (ida) ou `1` (volta), ou deixe em branco se não aplicável.

* **"Erro de formato: exception_type '{valor}' em calendar_dates (service_id '{id}', date '{data}') inválido. Valores aceitos: 1 ou 2."**
  * **Causa:** O tipo de exceção de calendário foi preenchido com valor incorreto.
  * **Solução:** Utilize `1` para adicionar o serviço no dia da exceção, ou `2` para remover o serviço no dia.

---

## Limitações

O módulo de edição do GTFS possui algumas limitações técnicas planejadas para garantir a integridade e o desempenho:

* **Edição de `shapes`:** O traçado geométrico deve ser editado apenas pela camada de linha (`shapes`), não pela camada de pontos (`shapes_point`).
* **Filtro em `stop_times`:** A tabela `stop_times` nunca é carregada inteira para evitar lentidão e travamentos no QGIS, exigindo o filtro obrigatório por linha e viagem.
* **Localização do rascunho:** O arquivo de rascunho `feed_edit.gpkg` é local e fica restrito ao mesmo diretório do feed original (`feed.gpkg`).

Para mais detalhes sobre as decisões e estrutura técnica, consulte o documento [ARQUITETURA_EDICAO_GTFS.md](https://github.com/d-camargo/sig-bus/blob/main/sig_bus/ARQUITETURA_EDICAO_GTFS.md).
