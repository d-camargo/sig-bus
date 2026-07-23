# Guia de Construção de GTFS (SIG-Bus)

Este guia orienta o usuário final sobre como utilizar a aba **Construir GTFS** no plugin SIG-Bus para QGIS. Ele descreve o funcionamento do assistente passo a passo e detalha os conceitos, ferramentas e mensagens de aviso que aparecem durante a criação de um feed GTFS do zero.

---

## Visão Geral

A funcionalidade de **Construir GTFS** permite que equipes que não possuem um feed GTFS preexistente criem um do zero, partindo apenas de informações básicas da agência (operadora), rotas/linhas, endereços das paradas e janelas de horários/frequência de operação.

### Cópia de Trabalho Isolada (`feed_edit.gpkg`)
Assim como na Edição de GTFS, para garantir a segurança e a integridade dos dados, todo o processo de construção gera e manipula uma cópia de trabalho local chamada `feed_edit.gpkg`. Ao entrar na aba pela primeira vez, caso não haja nenhuma edição em andamento, o sistema cria automaticamente esse banco de dados de rascunho vazio com a estrutura de tabelas do esquema GTFS.

### Barra de Progresso Dupla (Mínimo e Máximo)
No topo da aba **Construir GTFS**, duas barras de progresso informam o status da construção do feed em tempo real:
1. **Progresso Mínimo (6 Tabelas Obrigatórias):** Acompanha o preenchimento de pelo menos uma linha com campos obrigatórios (`required=True`) nas tabelas básicas: `agency`, `routes`, `trips`, `stops`, `stop_times` e `calendar`. Quando todas as 6 tabelas tiverem seus requisitos básicos preenchidos, o progresso mínimo atinge **100%**.
2. **Progresso Máximo (Feed Completo):** Monitora o preenchimento de campos opcionais do esquema, a associação de shapes (geometria de traçado) a todas as viagens (`trips`), e o cadastro de pelo menos dois sentidos (ida e volta) para cada linha cadastrada.

Um checklist ("**falta: ...**") é exibido logo abaixo das barras de progresso, indicando textualmente quais elementos ainda estão pendentes.

---

## Estrutura do Assistente (Páginas)

O assistente guia o usuário página por página (uma linha de cada vez) através de uma interface baseada em abas dinâmicas:

### 1. Configuração Inicial (Agência)
* **Objetivo:** Cadastrar as informações da operadora de transporte.
* **Campos Obrigatórios:** Nome da agência (`agency_name`), URL (`agency_url`) e Fuso Horário (`agency_timezone`).
* **Campos Opcionais:** Idioma (`agency_lang`) e Telefone (`agency_phone`).
* **Nota:** Essas informações são salvas globalmente e configuradas uma única vez ao iniciar a criação do feed.

### 2. Nova Linha: Identidade
* **Objetivo:** Definir os dados básicos de identificação da linha de ônibus/rota.
* **Campos:** Nome Curto (`route_short_name`, ex: "105"), Nome Longo (`route_long_name`, ex: "Bairro Novo/Centro") e Tipo de Rota (`route_type`, selecionado via lista, ex: "3 - Ônibus").

### 3. Paradas (Endereços e Geocodificação)
* **Objetivo:** Informar onde ficam localizados os pontos de embarque/desembarque da linha.
* **Geocodificação Automática (Nominatim):** O usuário digita os endereços textuais e clica em **Geocodificar**. O plugin consulta o serviço público do Nominatim (OpenStreetMap) de forma síncrona e preenche a latitude e longitude de cada ponto.
* **Deduplicação de Paradas:** Se o endereço normalizado (espaços colapsados e minúsculas) coincidir com alguma parada já salva no GeoPackage, o assistente exibe a opção `"parada já existe — reaproveitar"` ativada por padrão, evitando duplicar registros.
* **Ajuste Manual e no Mapa:**
  * Caso um endereço não seja encontrado pela geocodificação, o usuário pode digitar manualmente a latitude e a longitude.
  * Ao clicar em "Confirmar e avançar", os pontos são carregados temporariamente em uma camada do QGIS (`stops_temp`) e o plugin ativa a ferramenta nativa de edição de vértices para permitir que os pontos sejam arrastados e reposicionados no mapa.

### 4. Sequência de Paradas
* **Objetivo:** Definir a ordem exata em que o veículo percorre as paradas cadastradas.
* **Navegação:** Uma lista visual que permite mover os itens para cima ou para baixo para ordenar a rota.

### 5. Horários (Configuração de Frequência)
* **Objetivo:** Gerar as viagens e os horários em cada parada de forma automática, evitando digitação tabela a tabela.
* **Configuração:**
  * **Calendário:** Reutilizar um calendário existente (ex: dias úteis, sábados, domingos) ou criar um novo definindo o identificador (`service_id`), os dias de operação e o período de vigência (datas de início e término).
  * **Frequência:** Informar a hora de início da operação, a hora de término e o intervalo entre as viagens (em minutos).
* **Expansão Automática:** O plugin expande a frequência e distribui os horários de chegada (`arrival_time`) e partida (`departure_time`) linearmente entre as paradas na tabela `stop_times`.

### 6. Revisão e Salvar
* **Objetivo:** Revisar o resumo das configurações da linha e gravá-las definitivamente.
* **Ações Disponíveis:**
  * **Salvar Linha:** Grava a rota, viagens, calendários, paradas e horários no GeoPackage, além de calcular o traçado geométrico.
  * **Adicionar segundo sentido desta linha:** Inverte a ordem das paradas para facilitar o cadastro do sentido de volta (sentido oposto).
  * **Nova linha:** Reinicia o assistente na etapa da identidade da rota para cadastrar uma nova linha de ônibus.
  * **Ir para Edição GTFS:** Redireciona o usuário para a aba de Edição GTFS, mantendo a mesma cópia de trabalho ativa.

---

## Roteamento e Traçado OSM (OpenStreetMap)

Um dos grandes diferenciais do SIG-Bus na criação do GTFS é a geração do traçado das rotas (`shapes.txt`):
* **Cálculo Real por Vias:** O traçado geométrico não é uma linha reta simples. O plugin faz o download das vias reais no entorno das paradas (consultando a API Overpass do OpenStreetMap com uma margem de 300 metros ao redor dos pontos) e constrói um grafo de roteamento utilizando a biblioteca nativa `qgis.analysis`.
* **Algoritmo de Dijkstra:** A menor rota que passa pelas paradas na sequência correta é calculada sobre a malha de ruas reais.
* **Fallback Silencioso em Linha Reta:** Caso haja falha de conexão com a API do Overpass ou o grafo viário possua trechos desconexos que impeçam o cálculo da rota viária, o sistema desenha silenciosamente uma linha reta **apenas** para o trecho sem rota viária, preservando as partes que foram calculadas com sucesso.
* **Ajuste Fino:** Caso o traçado calculado precise de correções, o usuário pode ajustá-lo na aba **Edição GTFS**, selecionando a tabela `shapes` e usando a ferramenta de edição de vértices do QGIS.

---

## Passo a Passo: Fluxo Feliz Completo

1. **Acessar o assistente:** Clique na aba **Construir GTFS**.
2. **Definir Agência:** Preencha os campos obrigatórios da operadora na página "Configuração Inicial" e clique em **Salvar e continuar**.
3. **Identificar a Linha:** Insira o Nome Curto (ex: "105"), Nome Longo e selecione o Tipo de Rota. Clique em **Avançar**.
4. **Adicionar Paradas:** Digite o nome/endereço de cada ponto de parada, clique em **Geocodificar** para encontrar as coordenadas automaticamente. Insira ou ajuste coordenadas manualmente se necessário.
5. **Confirmar no Mapa:** Clique em **Confirmar e avançar**. As paradas temporárias serão carregadas no canvas do QGIS. Use a ferramenta de vértices para arrastar as paradas para a posição correta na via, se necessário.
6. **Ordenar Paradas:** Avance para a página "Sequência" (as coordenadas editadas no canvas serão salvas automaticamente). Ordene os pontos de parada usando os botões de mover para cima/baixo.
7. **Definir Horários:** Configure ou selecione o calendário de operação, defina a hora de início, hora de término e o intervalo (ex: a cada 20 minutos). Clique em **Avançar**.
8. **Revisar e Salvar:** Verifique o resumo gerado e clique em **Salvar linha**. O plugin gravará as feições e calculará o traçado pelas ruas automaticamente.
9. **Finalizar ou Cadastrar Mais:** Escolha entre criar o sentido de volta (segundo sentido), cadastrar outra linha ou clicar em **Ir para Edição GTFS** para validar e exportar o feed compactado `.zip` final.

---

## Erros Comuns e Soluções

Abaixo estão listadas as mensagens de aviso e de erro emitidas pelo assistente:

### 1. Mensagens da Interface do Assistente

* **"Por favor, preencha todos os campos obrigatórios (*)."** (Aviso)
  * **Causa:** O usuário tentou avançar na página de Configuração Inicial da agência sem preencher o nome, URL ou fuso horário.
  * **Solução:** Preencha os campos obrigatórios sinalizados com um asterisco (*).

* **"Por favor, preencha o Nome Curto (route_short_name) da linha."** (Aviso)
  * **Causa:** O usuário tentou avançar na página de Identidade da Linha com o nome curto em branco.
  * **Solução:** Insira um código ou nome curto para a linha (ex.: `105`, `501B`).

* **"Cópia de trabalho não está activa."** (Erro)
  * **Causa:** A sessão ou arquivo temporário `feed_edit.gpkg` tornou-se inacessível ou não foi devidamente inicializado.
  * **Solução:** Mude para a aba de Edição e ative o modo de edição, ou reinicie o plugin.

* **"Por favor, adicione pelo menos uma parada válida."** (Aviso)
  * **Causa:** Nenhuma parada com endereço textual foi informada na etapa de Paradas.
  * **Solução:** Adicione uma ou mais paradas digitando os respectivos endereços.

* **"Não foi possível carregar a camada temporária de paradas."** (Aviso)
  * **Causa:** Falha de banco de dados ou problemas internos ao gerar a camada `stops_temp` no QGIS.
  * **Solução:** Certifique-se de que a cópia de trabalho não está corrompida. Tente reiniciar a criação da rota.

* **"A lista de paradas está vazia. Volte e adicione paradas."** (Aviso)
  * **Causa:** O usuário tentou avançar na etapa de Sequência ou Horários sem ter adicionado pontos na etapa anterior.
  * **Solução:** Clique em **Voltar** e adicione os pontos de parada.

* **"Por favor, preencha o ID do Serviço (service_id)."** (Aviso)
  * **Causa:** Ao criar um novo calendário na etapa de Horários, o identificador do serviço foi deixado em branco.
  * **Solução:** Insira um nome identificador para o serviço (ex: `Uteis`, `Sabado`).

* **"Por favor, selecione pelo menos um dia de operação para o calendário."** (Aviso)
  * **Causa:** O calendário novo foi criado sem que nenhum checkbox de dia de semana estivesse marcado.
  * **Solução:** Marque os dias da semana em que esta programação deve rodar (ex: de segunda a sexta).

* **"A data de início da vigência deve ser anterior ou igual à data de término."** (Aviso)
  * **Causa:** As datas informadas no calendário estão invertidas (término ocorre antes do início).
  * **Solução:** Corrija os campos de data de vigência para que a data de término seja igual ou posterior ao início.

* **"Nenhum calendário selecionado."** (Aviso)
  * **Causa:** A opção de reaproveitar calendário foi selecionada, mas nenhum calendário existente foi escolhido na lista.
  * **Solução:** Selecione um calendário da lista ou mude a opção para cadastrar um novo calendário.

* **"A hora de início deve ser anterior ou igual à hora de fim."** (Aviso)
  * **Causa:** A janela de operação horária configurada possui a hora de início maior que a hora de término.
  * **Solução:** Ajuste os seletores de horário.

* **"O intervalo de frequência deve ser maior que 0."** (Aviso)
  * **Causa:** O intervalo entre viagens foi configurado com valor zero ou negativo.
  * **Solução:** Defina um intervalo de tempo maior que zero (ex: `15` minutos).

* **"Dados de horários/calendário não foram configurados."** (Aviso)
  * **Causa:** O assistente tentou salvar a linha sem que a página de horários tivesse sido concluída com sucesso.
  * **Solução:** Certifique-se de avançar todas as etapas anteriores preenchendo as configurações corretamente.

* **"Ocorreu um erro ao salvar a agência / paradas / linha: {detalhes}"** (Erro Crítico)
  * **Causa:** Falha de E/S, erro de banco de dados SQLite ao gravar as informações no GeoPackage.
  * **Solução:** Verifique o painel de log do SIG-Bus para detalhes do erro SQLite. Certifique-se de que o GeoPackage temporário não está bloqueado por outra aplicação.

### 2. Mensagens do Geocodificador

* **Status: "não encontrado"**
  * **Causa:** O endereço digitado é muito específico, incorreto, ou não possui correspondência na base do OpenStreetMap/Nominatim.
  * **Solução:** Simplifique o endereço (use apenas o nome da rua e cidade, ex: "Av. Afonso Pena, Belo Horizonte") ou preencha a latitude e longitude manualmente.

---

## Limitações Conhecidas

* **Dependência da Internet:** A geocodificação de endereços e o roteamento baseado no OpenStreetMap exigem conexão ativa com a internet para acessar as APIs Nominatim e Overpass.
* **Apenas uma agência por feed:** O assistente foi otimizado para o cenário comum de agência única. Informações de agência cadastradas no início são aplicadas globalmente a todas as linhas criadas no mesmo feed.
* **Edição Avançada posterior:** Ajustes de traçado que exijam desvios de vias não presentes no OSM ou alterações em horários específicos viagem a viagem devem ser realizados por meio das ferramentas de edição direta da aba **Edição GTFS**.
