# Contrato: população residente estimada de Teresina

Versão 1.

| Propriedade | Regra |
| --- | --- |
| Fonte | SIDRA/IBGE |
| Indicador | População residente estimada |
| Tabela | 6579 |
| Variável | 9324 |
| Nível territorial | Município, NC = 6 |
| Território | Teresina (PI), código 2211001 |
| Periodicidade | Anual |
| Período | D3C = AAAA; D3N deve conter o mesmo ano |
| Unidade | Pessoas, MC = 45 e MN = Pessoas |
| Classificações | Sem classificações adicionais neste recorte |
| Grão | Uma observação por tabela + variável + território + ano |

Fonte: [consulta oficial usada na coleta](https://apisidra.ibge.gov.br/values/t/6579/n6/2211001/v/9324/p/all/h/n/f/a/d/s).

## Entrada e valores

A resposta precisa ser uma lista não vazia de objetos. Os códigos são textos
e devem coincidir com os da tabela acima. Nome do território, ano e valor
devem ser textos não vazios. O ano precisa ter quatro dígitos e ser maior
que zero. Períodos duplicados ou dimensões D4C/D4N e posteriores causam erro.

Valores numéricos representam contagens inteiras não negativas.
Frações, números negativos, notação científica e separadores de milhar
são recusados. O texto original é preservado; o valor numérico é escrito
como inteiro decimal, sem aproximações.

Os símbolos `-`, `..`, `...` e `X` permanecem em `valor_original`,
com `valor_numerico` vazio e `status_valor=simbolo_sidra`. Zero numérico
permanece zero. Outros textos causam erro.

## Coleta, transformação e saída

O arquivo bruto é preservado com o nome
`tabela-6579_variavel-9324_territorio-2211001_periodo-all_sha256-HASH.json`.
O hash identifica seus bytes originais e é conferido no reprocessamento.

O CSV usa o formato compartilhado em `src/formato_csv.py`, com as mesmas
colunas documentadas no contrato de desocupação. Neste indicador:

- `tabela=6579`, `variavel=9324`, `unidade=Pessoas`.
- `periodo_codigo` e `periodo_nome` contêm o ano.
- `ano` contém o ano numérico e `trimestre` fica vazio.
- `classificacoes=sem_classificacoes`.
- `arquivo_bruto`, `sha256_bruto` e `url_fonte` identificam a origem.

A saída é ordenada por ano, em UTF-8, com vírgula como separador e LF nas
quebras de linha. Não há interpolação nem preenchimento de anos ausentes.
Esta série é de estimativas: o sistema não combina outras tabelas ou
resultados censitários para completar lacunas.

Cada resposta gera seu próprio CSV. A mesma entrada produz os mesmos bytes,
sem duplicar nem regravar uma saída idêntica. Um arquivo existente divergente
causa erro. Dados inválidos são rejeitados antes da gravação.

## Uso no sistema

Identificador: `populacao_estimada_teresina`.

```bash
python -m src.sistema_dados atualizar --indicador populacao_estimada_teresina
python -m src.sistema_dados consultar --indicador populacao_estimada_teresina --ano 2026
```

Para reprocessar uma coleta sem rede:

```bash
python -m src.populacao_estimada "data/raw/NOME_DA_COLETA.json"
```

As regras de publicação são as mesmas da operação do sistema: última coleta
validada, manutenção das versões anteriores e recusa de perda de períodos
já publicados. A atualização deste indicador preserva as referências dos
demais indicadores no catálogo.
