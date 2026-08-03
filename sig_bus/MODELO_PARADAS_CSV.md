# Modelo de CSV em Lote de Paradas (SIG-Bus)

Este arquivo descreve o formato do CSV usado pelos botões **"Baixar modelo
CSV"** e **"Importar CSV"** da página "Paradas" do assistente **Construir
GTFS**. O modelo pronto para preencher está em
[`modelo_paradas.csv`](modelo_paradas.csv) — é a mesma saída gerada pelo
botão "Baixar modelo CSV" (`stops_csv.write_template`), disponível aqui para
quem prefere baixar direto do repositório.

## Formato do arquivo

* **Delimitador:** ponto e vírgula (`;`) — não vírgula.
* **Codificação:** UTF-8 com BOM, para abrir corretamente acentos no Excel e
  no LibreOffice em português.
* **Separador decimal:** ponto (`.`) em latitude/longitude — vírgula
  decimal (`-29,1634`) também é aceita na importação.

## Colunas

| Coluna | Obrigatória | Descrição |
|---|---|---|
| `sequencia` | Não | Número inteiro que define a ordem de importação das paradas. Linhas sem `sequencia` entram por último, na ordem em que aparecem no arquivo. |
| `nome_parada` | Não | Nome de referência da parada (ex.: "Escola Municipal"). |
| `logradouro` | Uma das duas formas* | Rua/avenida, no padrão `Logradouro, Número - Bairro` (decisão 43): só a parte "Logradouro". |
| `numero` | Uma das duas formas* | Número do endereço. |
| `bairro` | Não | Bairro — opcional mesmo quando o endereço é usado. |
| `latitude` | Uma das duas formas* | Latitude decimal (ex.: `-29.1634`). |
| `longitude` | Uma das duas formas* | Longitude decimal (ex.: `-51.1794`). |
| `observacao` | Não | Texto livre, sem uso na geocodificação. |

\* **Toda linha precisa vir preenchida por pelo menos uma das duas formas a
seguir:**

1. **Por endereço:** preencha `logradouro` (e opcionalmente `numero` e
   `bairro`), deixando `latitude`/`longitude` em branco. O endereço é
   geocodificado pelo Nominatim usando o **município e a UF configurados na
   agência** (página "Configuração inicial" do assistente) como contexto —
   essas duas colunas não existem no CSV porque já vêm da agência, e são
   obrigatórias para a geocodificação funcionar.
2. **Por coordenada direta:** preencha `latitude` e `longitude` juntas,
   deixando `logradouro` em branco. Use esta forma para paradas rurais ou
   sem endereço cadastrado, sem depender de geocodificação.

Linhas sem endereço e sem coordenada, ou com só uma das duas coordenadas
preenchida, são rejeitadas na importação e relatadas como erro.

## Exemplo (mesmo conteúdo de `modelo_paradas.csv`)

```csv
sequencia;nome_parada;logradouro;numero;bairro;latitude;longitude;observacao
1;Escola Municipal;Rua Giuseppe Fórmolo;210;Centro;;;Parada em frente à escola
2;Entroncamento da BR-101;;;;-29.1634;-51.1794;Parada rural, sem endereço cadastrado
```

* Linha 1 usa endereço (forma 1): será geocodificada dentro do
  município/UF da agência.
* Linha 2 usa coordenada direta (forma 2): entra já como parada localizada,
  sem chamar o geocodificador.

Ver o passo a passo completo da importação em
[`GUIA_CONSTRUIR_GTFS.md`](GUIA_CONSTRUIR_GTFS.md).
