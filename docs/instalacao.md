# Instalação

O SIG-Bus é um plugin do QGIS: ele não tem instalador próprio nem exige
nenhuma biblioteca de fora. Instalar é copiar uma pasta para dentro do perfil
do QGIS e marcar uma caixinha — os passos abaixo cobrem isso do começo ao fim,
mais a única configuração opcional que o plugin tem, a da geocodificação de
endereços.

## O que é preciso ter

- **QGIS 3.34 LTR até a série 4.x.** O plugin roda tanto em Qt 5 (QGIS 3.x)
  quanto em Qt 6 (QGIS 4.x) — a faixa declarada é `3.34` a `4.99`, sondada no
  3.34.4 e testada no 3.44 e no 4.2.
- **Nada além do QGIS.** Todo o código usa o Python que já vem embutido no
  QGIS, inclusive o leitor de GTFS, que é do próprio SIG-Bus. Não é preciso
  instalar outro plugin, nem rodar `pip`, nem criar ambiente virtual.

## Instalar o plugin

1. Copie a pasta `sig_bus/` para o diretório de plugins do QGIS:
   - **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows:** `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
2. Abra o QGIS e ative o plugin **SIG-Bus** em *Complementos → Gerenciar e
   Instalar Complementos → Instalados*.
3. Use o plugin por *Complementos → SIG-Bus*.

Se o QGIS já estava aberto quando você copiou a pasta, feche e abra de novo:
ele lê a lista de plugins na inicialização.

## Configurar a geocodificação

Essa configuração só interessa a quem vai **construir um GTFS do zero** ou
importar paradas por endereço — quem já tem um feed com coordenadas pode pular
esta seção inteira.

Configurar uma **chave da API do Google Maps é opcional**. Sem chave nenhuma, a
cascata do OpenStreetMap (Nominatim → Photon → corretor de nomes de rua via
Overpass) funciona igual, e não há nada a preparar. A chave, quando existe, é
sua e é cobrada pelo Google.

Para mexer nisso, use o botão **Configurar geocodificação…**, ao lado de
"Geocodificar" na etapa de paradas do assistente *Construir GTFS*. A janela tem
três coisas:

- **Modo de provedor.** *Automático* tenta o Google primeiro quando há chave
  configurada e cai para a cascata OSM quando não há (ou quando o Google falha);
  *Somente OSM* ignora qualquer chave e usa só Nominatim e Photon.
- **Chave da API do Google Maps.** Campo mascarado, opcional. A chave é criada
  no [console.cloud.google.com](https://console.cloud.google.com/), com a
  *Geocoding API* habilitada.
- **Testar chave.** Geocodifica um endereço conhecido com o que você digitou e
  mostra o resultado — ou o erro que o Google devolveu — **antes** de salvar.

A chave e o modo ficam no `QSettings` do QGIS (`SIG-Bus/geocoding/google_api_key`
e `SIG-Bus/geocoding/provider`), que é da sua instalação: **nunca** vão para o
arquivo do projeto nem para o feed, que costumam ser compartilhados. No Log de
Mensagens do QGIS, toda URL registrada sai com a chave redigida como `key=***`.

## Geocodificar é lento — e tem que ser

O Nominatim e o Photon são serviços públicos e gratuitos, e a política de uso
deles impõe **no máximo uma requisição por segundo por host**. O SIG-Bus
respeita esse limite esperando entre as chamadas, de propósito.

Na prática: uma parada cujo endereço não casa de primeira pode consumir várias
tentativas de um segundo cada, e uma linha tem dezenas de paradas — então
geocodificar uma linha inteira leva **minutos**. Isso não é lentidão do plugin
nem do seu computador, é a regra do serviço. Para amenizar, o SIG-Bus guarda em
cache o que já consultou na sessão e o botão "Geocodificar" pula as paradas que
já têm coordenada.
