# SIG-Bus

O SIG-Bus é um plugin do QGIS que junta duas coisas que normalmente vivem
separadas: o **GTFS** da operação — as linhas, as paradas, os horários — e os
dados de **demanda de embarque por parada**. Com os dois no mesmo mapa, ele
distribui os embarques ao longo do traçado da linha e mostra quanta gente está
dentro do ônibus em cada trecho, hora a hora ou no total do dia. A partir daí
saem o Diagrama de Blocos, que desenha a operação no tempo, e um relatório em
PDF pronto para impressão.

Ele foi feito para quem analisa a operação de uma operadora de transporte
público, não para quem programa. O leitor de GTFS é embutido, então nenhum
outro plugin precisa ser instalado; e quem ainda não tem um feed GTFS pode
construir um do zero por um assistente, que pergunta uma coisa de cada vez e
vai dizendo o que ainda falta para o feed ficar completo. O projeto nasceu do
trabalho de Iniciação Científica PIBIC DPPG 113/2021.

<div class="grid cards" markdown>

-   **Instalação**

    ---

    O que é preciso ter, como copiar o plugin para o QGIS, como ativá-lo e como
    configurar a geocodificação de endereços.

    [Instalar o SIG-Bus](instalacao.md)

-   **Guias**

    ---

    O passo a passo de cada assistente: construir um GTFS do zero, editar um
    feed já carregado e importar paradas em lote por CSV.

    [Ver os guias](guias/construir-gtfs.md)

-   **Referência**

    ---

    O que cada botão faz, os campos das camadas de saída, o método de alocação
    da demanda e como ler o Diagrama de Blocos.

    [Consultar a referência](referencia/funcionalidades.md)

-   **Arquitetura**

    ---

    Como o plugin é organizado por dentro, para quem vai mexer no código.

    [Entender o desenho interno](arquitetura/construir-gtfs.md)

</div>
