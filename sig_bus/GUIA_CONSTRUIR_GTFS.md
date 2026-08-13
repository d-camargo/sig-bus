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
* **Objetivo:** Cadastrar as informações da operadora de transporte e a localização geográfica da agência.
* **Campos Obrigatórios:** Nome da agência (`agency_name`), URL (`agency_url`), Fuso Horário (`agency_timezone`), Município (`build_city`) e UF (`build_state`).
* **Campos Opcionais:** Idioma (`agency_lang`), Telefone (`agency_phone`) e País (`build_country`, fixo em "Brasil").
* **Nota:** O Município e a UF são salvos na tabela interna `sig_bus_config` e definem o contexto e o bounding box (`viewbox`) para restringir a geocodificação de paradas.

### 2. Nova Linha: Identidade
* **Objetivo:** Definir os dados básicos de identificação da linha de ônibus/rota.
* **Campos:** Nome Curto (`route_short_name`, ex: "105"), Nome Longo (`route_long_name`, ex: "Bairro Novo/Centro") e Tipo de Rota (`route_type`, selecionado via lista, ex: "3 - Ônibus").

### 3. Paradas (Endereços e Geocodificação)
* **Objetivo:** Informar onde ficam localizados os pontos de embarque/desembarque da linha.
* **Padrão de Endereço:** Os endereços devem ser inseridos no padrão `Logradouro, Número - Bairro` (ex.: `Rua Giuseppe Fórmolo, 210 - Centro`). O bairro é opcional. O município e a UF vêm automaticamente da configuração da agência.
* **Geocodificação Automática Estruturada (Nominatim e Fallback Photon):** O usuário digita os endereços textuais e clica em **Geocodificar**. O plugin executa uma busca síncrona estruturada por contexto no Nominatim em cascata (com número, sem número e busca livre), delimitada pela caixa envolvente do município. Caso o Nominatim não encontre o endereço, o assistente aciona automaticamente o geocodificador **Photon (Komoot)** como último degrau de fallback, tolerante a erros de digitação. As consultas em lote utilizam cache de sessão para evitar requisições de rede repetidas.
* **Status Visual das Paradas:** Os campos visuais de latitude e longitude foram suprimidos da tabela para simplificar a interface, sendo substituídos por rótulos visuais de status (`✓ localizado`, `✗ não encontrado`, `📍 marcado no mapa`).
* **Botão "Marcar no mapa":** Para cada parada (especialmente em linhas rurais sem endereço textual), o usuário pode clicar em **Marcar no mapa**. O plugin oculta temporariamente o assistente, ativa a ferramenta interativa `PickStopPointTool` e permite selecionar o ponto com um clique no canvas do QGIS. Se o projeto não possuir uma camada base, uma camada raster OpenStreetMap é adicionada automaticamente via `ensure_osm_basemap`.
* **Importação e Exportação por CSV em Lote:**
  * **Baixar modelo CSV:** Gera o modelo `modelo_paradas.csv` (formato `;`, UTF-8 com BOM) para preenchimento no Excel/LibreOffice.
  * **Importar CSV:** Permite carregar um lote de paradas de um arquivo CSV, suportando tanto endereços no padrão quanto coordenadas lat/lon diretas (linhas rurais).
* **Erro de digitação no nome da rua (a causa mais comum):** o Nominatim **não corrige typo** — `Rua Giusepe Fórmolo` (um `p` a menos que o `Giuseppe` real do OpenStreetMap) devolve **zero** candidatos em todas as tentativas, mesmo com município, UF e número corretos. É por isso que o Photon entra como último degrau: ele tolera a grafia errada e encontra a rua assim mesmo.
  * **Como identificar:** quando a busca aceita um logradouro com grafia diferente da digitada, o status da parada não vira `✓ localizado` e sim **`✓ localizado (via: <nome real>)`** — o nome entre parênteses é a rua que o buscador realmente casou. A troca nunca é silenciosa: o par digitado/aceito também vai para o log `SIG-Bus`.
  * **Quando a via casada não é a desejada:** confira o nome entre parênteses antes de avançar. Ruas de nome parecido existem no mesmo município (ex.: `Giusepe Bressan` × `Giuseppe Fôrmolo`), então o acerto não é garantido. Se estiver errado, corrija a grafia no campo do endereço e clique em **Geocodificar** de novo, ou use **Marcar no mapa** para posicionar o ponto à mão.
* **Quando a geocodificação não encontra nada:** Se o resumo ao fim da busca disser *"Nenhuma parada localizada: ..."* (com os endereços que falharam), siga nesta ordem:
  1. **Confira a grafia do logradouro** nos endereços citados na mensagem — é a causa mais provável, pelo motivo do item acima.
  2. **Confira o município e a UF na página "Configuração inicial" (agência)** — é o contexto usado em toda a busca. Município errado (ou de outro estado) descarta os candidatos certos.
  3. **Abra o painel "Log Messages" do QGIS, aba `SIG-Bus`** — cada tentativa registra com tag explícita (`[a-estruturada-num]`, `[b-estruturada]`, `[c-livre]`, `[sem-bbox ...]`, `[photon]`, `[city-bbox]`) a URL consultada, o código de erro da resposta e quantos candidatos vieram. É ali que aparece a diferença entre "endereço inexistente" e falha de rede/serviço fora do ar.
  4. **Use "Marcar no mapa"** — é a saída sempre disponível: nenhuma parada depende da geocodificação para ser cadastrada.
* **Deduplicação de Paradas:** Se o endereço normalizado coincidir com alguma parada já salva no GeoPackage, o assistente exibe a opção `"parada já existe — reaproveitar"` ativada por padrão, evitando duplicar registros.
* **Ajuste Manual e no Mapa:**
  * Ao clicar em "Confirmar e avançar", os pontos são carregados temporariamente em uma camada do QGIS (`stops_temp`) e o plugin ativa a ferramenta nativa de edição de vértices para permitir que os pontos sejam arrastados e reposicionados no mapa.

### 4. Sequência de Paradas
* **Objetivo:** Definir a ordem exata em que o veículo percorre as paradas cadastradas.
* **Navegação:** Uma lista visual que permite mover os itens para cima ou para baixo para ordenar a rota.

### 5. Horários (Configuração de Frequência e Faixas Horárias)
* **Objetivo:** Gerar as viagens e os horários em cada parada de forma automática, evitando digitação tabela a tabela.
* **Configuração:**
  * **Calendário:** Reutilizar um calendário existente (ex: dias úteis, sábados, domingos) ou criar um novo definindo o identificador (`service_id`), os dias de operação e o período de vigência (datas de início e término).
  * **Faixas Horárias (Frequência Multi-Faixas):** É possível cadastrar até 3 faixas horárias distintas para a mesma operação. Para cada faixa, informe a **Hora de Início**, **Hora de Fim**, o **Intervalo (em minutos)** e a **Duração da viagem (em minutos)** — a duração é por faixa porque o mesmo percurso demora mais no pico. Utilize os botões **Adicionar faixa** e **Remover faixa** para gerenciar a tabela.

    Exemplo realista de uma linha que opera das 6h às 20h:

    | Início | Fim | Intervalo | Duração |
    |---|---|---|---|
    | 06:00:00 | 09:00:00 | 10 min | 55 min |
    | 09:00:00 | 16:00:00 | 25 min | 40 min |
    | 16:00:00 | 20:00:00 | 12 min | 55 min |

    As faixas **não podem se sobrepor** (duas faixas cobrindo o mesmo horário não dizem qual intervalo vale ali) — encostar o fim de uma no início da outra é permitido, e a saída da fronteira é gerada uma única vez, pela faixa mais cedo. Deixar um vão entre faixas também é permitido: é a linha que não opera naquele período.
* **Expansão Automática:** O plugin expande cada faixa horária configurada e distribui os horários de chegada (`arrival_time`) e partida (`departure_time`) linearmente entre as paradas na tabela `stop_times` com base na duração de cada faixa.

### 5.1 Ajuste de horários (diagrama, na mesma página)
* **Objetivo:** Visualizar e refinar viagem a viagem o quadro gerado pela frequência — ainda em memória, antes de qualquer gravação. Na operação real o intervalo encurta no pico e alarga fora dele.
* **Diagrama:** o mesmo Diagrama de Blocos do plugin, em Modo Viagens: cada viagem é uma barra cuja largura é a duração informada acima.
* **Seleção:** clique na barra da viagem. A **metade esquerda** seleciona a **saída**; a **metade direita**, a **chegada**.
* **Passo:** o campo **Passo** define quantos minutos cada tecla desloca (padrão: 15 minutos).
* **Atalhos de teclado** (clique no diagrama antes, para ele receber o teclado):

  | Tecla | Efeito |
  |---|---|
  | `>` | adia o extremo selecionado (saída **ou** chegada) em um passo |
  | `<` | antecipa o extremo selecionado em um passo |
  | `+` | adia a viagem inteira (saída e chegada juntas), preservando a duração |
  | `-` | antecipa a viagem inteira, preservando a duração |

  Ao mover um extremo, as paradas intermediárias são redistribuídas linearmente entre a saída e a chegada resultantes. Um deslocamento que inverteria saída e chegada é recusado — a grade fica como estava.
* **Indicador de headway (cota):** com uma viagem selecionada, uma cota de desenho técnico liga a saída da viagem anterior à da selecionada, com o valor `headway N min`.
* **Restaurar frequência regular:** descarta os ajustes manuais e regera a grade a partir das faixas horárias configuradas. Mudar qualquer parâmetro das faixas horárias também regera a grade.
* **Um ajuste vale para todos os dias do calendário.** No GTFS um único conjunto de viagens já atende os cinco dias úteis — quem diz "seg a sex" é o calendário (`service_id`), não uma cópia por dia. O rótulo acima do diagrama mostra para quais dias aquele conjunto vale.
* **Validação ao avançar:** erro (chegada antes da partida, sequência decrescente, saída ≥ chegada) **bloqueia** o avanço; aviso (duas viagens saindo no mesmo horário, ordem trocada, headway muito acima do típico) pede confirmação.
* **E se eu quiser digitar o horário em vez de deslocar a barra?** Nesta página o ajuste é só pelo diagrama e pelos atalhos acima — não há tabela de horários ao lado dele. A edição em **tabela** (matriz paradas × viagens, com o horário digitado direto na célula) existe na aba **Edição GTFS**, no botão **Ajustar horários**, e vale para qualquer feed já carregado — inclusive o que este assistente acabou de criar. Ver [GUIA_EDICAO_GTFS.md](GUIA_EDICAO_GTFS.md).

### 6. Revisão e Salvar
* **Objetivo:** Revisar o resumo das configurações da linha e gravá-las definitivamente.
* **Ações Disponíveis:**
  * **Salvar Linha:** Grava a rota, viagens, calendários, paradas e horários (incluindo os horários ajustados na etapa anterior) no GeoPackage, além de calcular o traçado geométrico.
  * **Adicionar segundo sentido desta linha:** Inverte a ordem das paradas para facilitar o cadastro do sentido de volta (sentido oposto).
  * **Nova linha:** Reinicia o assistente na etapa da identidade da rota para cadastrar uma nova linha de ônibus.
  * **Ir para Edição GTFS:** Redireciona o usuário para a aba de Edição GTFS, mantendo a mesma cópia de trabalho ativa.

---

## Geocodificação: quando o OSM não basta

Embora o geocodificador gratuito baseado em OpenStreetMap (Nominatim + Photon) atenda à maioria dos casos urbanos, certos endereços comerciais ou recém-criados podem não estar indexados na base livre do OSM. Para essas situações, o SIG-Bus permite integrar opcionalmente a **Google Geocoding API**.

### Chave de API do Google (Opcional)
* **Caráter Opcional:** O uso de uma chave do Google é totalmente **opcional** e de responsabilidade/custo do próprio usuário. O plugin funciona perfeitamente sem chave (utilizando a cascata pública e gratuita Nominatim → Photon → corretor de vias Overpass).
* **Como obter e habilitar:**
  1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
  2. Crie um projeto e ative a **Geocoding API**.
  3. Em *Credenciais*, crie uma **API Key** (chave de API) e configure restrições de uso recomendadas.
* **Onde configurar no plugin:** Na página de **Paradas** do assistente, clique no botão **"Configurar geocodificação…"** (ao lado do botão *Geocodificar*). Na janela que se abre:
  * Escolha o modo de operação: `Automático (usa Google se houver chave)` ou `Somente OSM (Nominatim + Photon)`.
  * Cole sua chave de API no campo `Chave da API do Google Maps`.
  * Clique em **Testar chave** para verificar a validade das credenciais.
* **Persistência segura:** A chave é salva localmente nas configurações do seu usuário no QGIS (`QSettings`), e **nunca** é gravada no arquivo `.gpkg` do projeto nem exportada no feed GTFS, garantindo que suas credenciais não vazem ao compartilhar arquivos de projeto.

### Leitura dos Novos Status de Procedência
Quando a busca por paradas é realizada, o plugin exibe a procedência do ponto localizado nos rótulos de status:
* **`✓ localizado (Google)`**: A parada foi localizada via Google Geocoding API (primeiro provedor acionado quando a chave está configurada).
* **`✓ localizado (Nominatim)`**: A parada foi localizada pela busca direta no Nominatim.
* **`✓ localizado (Photon)`**: A parada foi localizada através do fallback do Photon.
* **`✓ localizado (via: <nome real> — OSM)`**: A parada foi localizada após correção de grafia feita pelo corretor de vias do Overpass/OSM.

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
2. **Definir Agência:** Preencha os campos obrigatórios da operadora (incluindo Município e UF) na página "Configuração Inicial" e clique em **Salvar e continuar**.
3. **Identificar a Linha:** Insira o Nome Curto (ex: "105"), Nome Longo e selecione o Tipo de Rota. Clique em **Avançar**.
4. **Adicionar Paradas:** Digite os endereços no padrão (ou importe um lote via **Importar CSV** / `modelo_paradas.csv`), clique em **Geocodificar** para encontrar as coordenadas automaticamente. Para paradas rurais ou sem endereço, use o botão **Marcar no mapa** para indicar a posição diretamente no canvas.
5. **Confirmar no Mapa:** Clique em **Confirmar e avançar**. As paradas temporárias serão carregadas no canvas do QGIS. Use a ferramenta de vértices para arrastar as paradas para a posição correta na via, se necessário.
6. **Ordenar Paradas:** Avance para a página "Sequência" (as coordenadas editadas no canvas serão salvas automaticamente). Ordene os pontos de parada usando os botões de mover para cima/baixo.
7. **Definir Horários e Duração:** Configure ou selecione o calendário de operação, defina as faixas horárias (hora de início, término, intervalo e duração estimada da viagem para cada faixa, podendo cadastrar até 3 faixas horárias).
8. **Ajustar Horários no Diagrama (opcional):** Ainda na página "Horários", use o diagrama para acertar viagem a viagem: clique numa barra e use `>`/`<` (só a saída ou a chegada) ou `+`/`-` (a viagem inteira), com o passo definido no campo **Passo**. Clique em **Avançar**.
9. **Revisar e Salvar:** Verifique o resumo gerado e clique em **Salvar linha**. O plugin gravará as feições e calculará o traçado pelas ruas automaticamente.
10. **Finalizar ou Cadastrar Mais:** Escolha entre criar o sentido de volta (segundo sentido), cadastrar outra linha ou clicar em **Ir para Edição GTFS** para validar e exportar o feed compactado `.zip` final.

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

* **"Nenhuma faixa de horário definida."** (Aviso, janela "Faixas horárias inválidas")
  * **Causa:** O usuário tentou avançar na etapa de Horários sem nenhuma faixa cadastrada na tabela de faixas horárias.
  * **Solução:** Clique no botão **Adicionar faixa** e configure ao menos uma faixa horária.

* **"faixa N (HH:MM–HH:MM): a hora de fim é anterior à hora de início."** (Aviso, janela "Faixas horárias inválidas")
  * **Causa:** A faixa indicada termina antes de começar.
  * **Solução:** Corrija a hora de fim daquela linha da tabela de faixas.

* **"faixa N (HH:MM–HH:MM): o intervalo entre viagens deve ser maior que 0."** (Aviso, janela "Faixas horárias inválidas")
  * **Causa:** O intervalo entre viagens da faixa indicada ficou em zero ou negativo.
  * **Solução:** Defina um intervalo maior que zero (ex.: `15` minutos).

* **"faixa N (HH:MM–HH:MM): a duração da viagem deve ser maior que 0."** (Aviso, janela "Faixas horárias inválidas")
  * **Causa:** A duração da viagem da faixa indicada ficou em zero ou negativa.
  * **Solução:** Informe quanto tempo a viagem leva de ponta a ponta naquela faixa.

* **"faixa 2 (09:00–16:00) sobrepõe a faixa 1."** (Aviso, janela "Faixas horárias inválidas")
  * **Causa:** Duas faixas cobrem o mesmo horário — não há como saber qual intervalo vale ali.
  * **Solução:** Encoste as faixas (o fim de uma igual ao início da outra: a saída da fronteira é gerada uma única vez, pela faixa mais cedo) ou deixe um intervalo sem operação entre elas, que é permitido.

* **"A grade de horários contém inconsistências e não pode avançar: ..."** (Aviso)
  * **Causa:** O ajuste manual no diagrama deixou uma viagem inconsistente (chegada anterior à partida na mesma parada, sequência de paradas decrescente ou saída igual/posterior à chegada).
  * **Solução:** Corrija a viagem citada com `>`/`<`/`+`/`-`, ou clique em **Restaurar frequência regular** para voltar à grade gerada automaticamente.

* **"A grade de horários tem pontos a conferir: ... Avançar assim mesmo?"** (Pergunta)
  * **Causa:** Duas viagens saem no mesmo horário, o ajuste inverteu a ordem de duas viagens ou algum headway ficou acima do triplo do intervalo típico.
  * **Solução:** Nenhuma correção é obrigatória — confirme se o quadro é mesmo esse (pico/entrepico) ou volte e ajuste.

* **"Dados de horários/calendário não foram configurados."** (Aviso)
  * **Causa:** O assistente tentou salvar a linha sem que a página de horários tivesse sido concluída com sucesso.
  * **Solução:** Certifique-se de avançar todas as etapas anteriores preenchendo as configurações corretamente.

* **"Ocorreu um erro ao salvar a agência / paradas / linha: {detalhes}"** (Erro Crítico)
  * **Causa:** Falha de E/S, erro de banco de dados SQLite ao gravar as informações no GeoPackage.
  * **Solução:** Verifique o painel de log do SIG-Bus para detalhes do erro SQLite. Certifique-se de que o GeoPackage temporário não está bloqueado por outra aplicação.

### 2. Mensagens do Geocodificador

* **Status: "não encontrado"**
  * **Causa:** O endereço digitado é muito específico, incorreto ou não possui correspondência nas bases do Nominatim nem do Photon (Komoot). Erro de digitação no nome da rua é o caso mais frequente.
  * **Solução:** Confira a grafia do logradouro, simplifique o endereço (use apenas o nome da rua e município, ex: "Rua Afonso Pena, Caxias do Sul") ou marque o ponto diretamente no mapa com **Marcar no mapa**.
* **Status: "✓ localizado (via: &lt;nome real&gt;)"**
  * **Causa:** A busca só encontrou a parada com um logradouro de grafia diferente da digitada — normalmente um erro de digitação corrigido pelo Photon.
  * **Solução:** Nenhuma, se o nome entre parênteses for a rua desejada. Se não for, corrija a grafia e clique em **Geocodificar** novamente, ou use **Marcar no mapa**. O assistente nunca altera o endereço cadastrado por conta própria.
* **Aviso: "Nenhuma parada localizada: &lt;endereços&gt;"**
  * **Causa:** *Todos* os endereços falharam na busca (tanto no Nominatim quanto no fallback do Photon). A causa mais comum é a grafia do logradouro; depois dela, município/UF incorretos no cadastro da agência ou falha de conexão de rede/serviço fora do ar.
  * **Solução:** Confira a grafia dos endereços citados na própria mensagem, depois o município e a UF na página da agência, e verifique o painel **Log Messages** do QGIS (aba `SIG-Bus`): cada consulta registra com tags (`[a-estruturada-num]`, `[b-estruturada]`, `[c-livre]`, `[sem-bbox ...]`, `[photon]`) a URL consultada, o código de erro de rede e a quantidade de candidatos encontrados. A opção **Marcar no mapa** permanece totalmente funcional para incluir as paradas.

---

## Limitações Conhecidas

* **Dependência da Internet:** A geocodificação de endereços e o roteamento baseado no OpenStreetMap exigem conexão ativa com a internet para acessar as APIs Nominatim e Overpass.
* **Apenas uma agência por feed:** O assistente foi otimizado para o cenário comum de agência única. Informações de agência cadastradas no início são aplicadas globalmente a todas as linhas criadas no mesmo feed.
* **Edição Avançada posterior:** Ajustes de traçado que exijam desvios de vias não presentes no OSM ou alterações em horários específicos viagem a viagem devem ser realizados por meio das ferramentas de edição direta da aba **Edição GTFS**.
