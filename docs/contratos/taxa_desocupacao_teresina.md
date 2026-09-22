# Contrato: taxa de desocupação de Teresina

Versão 1 — transformação de uma coleta bruta em uma tabela para análise.

## Identidade e fonte

| Propriedade | Regra |
| --- | --- |
| Fonte | SIDRA/IBGE, PNAD Contínua trimestral |
| Indicador | Taxa de desocupação, na semana de referência, das pessoas de 14 anos ou mais de idade |
| Tabela | 6468 |
| Variável | 4099 |
| Nível territorial | Município, código 6 |
| Território | Teresina (PI), código 2211001 |
| Período | Trimestre; código AAAA0T, com T de 1 a 4 |
| Unidade | Percentual: MC = 2 e MN = % |
| Classificações | Sem classificações adicionais neste recorte |
| Grão | Uma observação por tabela + variável + território + período |

Referências: [tabela SIDRA](https://sidra.ibge.gov.br/tabela/6468) e
[consulta de origem](https://apisidra.ibge.gov.br/values/t/6468/n6/2211001/v/4099/p/all/h/n/f/a/d/s).

## Entrada e validação

A entrada é um arquivo JSON produzido pelo extrator do projeto, com o nome
`tabela-6468_variavel-4099_territorio-2211001_periodo-all_sha256-HASH.json`.
HASH é o SHA-256 dos bytes completos: a identificação calculada pelo conteúdo.
O nome e o hash são conferidos antes do processamento. Renomear o arquivo ou
alterar seu conteúdo quebra essa verificação.

O JSON deve conter uma lista não vazia de objetos. Cada objeto precisa ter:

- `NC=6`, `MC=2`, `MN=%`, `D1C=2211001` e `D2C=4099`, como texto.
- `D1N` (nome do território), `D3N` (nome do período) e `V` como textos não vazios.
- `D3C` com quatro dígitos de ano, maior que zero, e trimestre de `01` a `04`.

Períodos duplicados e dimensões `D4C/D4N` ou posteriores causam erro:
não fazem parte do grão contratado. Todas as observações são validadas antes
de criar o CSV. A saída é ordenada pelo código do período.

## Valores

`valor_original` conserva exatamente o texto de `V`. Espaços nas bordas
são desconsiderados somente para interpretar o valor, sem alterar essa coluna.

Números usam ponto decimal e precisam estar entre 0 e 100, inclusive.
A conversão usa `Decimal`, representação decimal que evita aproximações
introduzidas por números binários de ponto flutuante. `7.40` continua `7.40`.
Zero numérico continua zero.

Os símbolos reconhecidos por este contrato são `-`, `..`, `...` e `X`.
Eles permanecem na coluna original, recebem `status_valor=simbolo_sidra`
e deixam `valor_numerico` vazio. Nenhum desses símbolos é convertido em zero
nem recebe uma interpretação estatística automática. Outros textos causam
erro para que o contrato seja revisto conscientemente.

## Colunas de saída

| Coluna | Conteúdo |
| --- | --- |
| fonte | SIDRA/IBGE |
| tabela | 6468 |
| variavel | 4099 |
| territorio_codigo | 2211001 |
| territorio_nome | D1N original |
| periodo_codigo | D3C original |
| periodo_nome | D3N original |
| ano | Ano extraído de D3C |
| trimestre | Número de 1 a 4 extraído de D3C |
| unidade | % |
| classificacoes | sem_classificacoes |
| valor_original | V original, inclusive símbolos |
| valor_numerico | Decimal ou campo vazio para símbolo |
| status_valor | numerico ou simbolo_sidra |
| arquivo_bruto | Nome completo do arquivo de origem |
| sha256_bruto | SHA-256 dos bytes do arquivo de origem |
| url_fonte | Consulta SIDRA usada pelo extrator |

Formato: UTF-8, cabeçalho fixo, vírgula como separador, ponto decimal,
aspas escapadas pelo formato CSV e quebra de linha LF.
Ao importar em uma planilha, configure esses separadores e trate os códigos
como identificadores.

## Saída e reprocessamento

Cada arquivo bruto gera um arquivo com o mesmo nome-base e extensão `.csv`
em `data/processed/`, ou no diretório escolhido na execução.

A transformação apenas lê o arquivo bruto e funciona sem rede. A mesma
entrada produz os mesmos bytes de saída: comportamento determinístico.
Se o CSV já existir com esse conteúdo, ele será reutilizado sem regravação
nem duplicação: comportamento idempotente. Um CSV existente com conteúdo
divergente causa erro e é preservado; pode-se escolher outro diretório de
saída para investigar a divergência.

Coletas diferentes geram CSVs separados, mesmo quando incluem os mesmos
trimestres. Essa etapa não combina revisões do IBGE nem escolhe a mais recente.
Também não preenche lacunas temporais nem garante que todos os trimestres
publicados estejam presentes: representa somente a coleta fornecida.

Erros de leitura, JSON, validação e escrita interrompem a execução.
O nome definitivo do CSV só é publicado após a escrita completa em arquivo
temporário. Uma falha antes da publicação mantém o destino ausente ou seu
conteúdo anterior. O arquivo bruto permanece intacto.
