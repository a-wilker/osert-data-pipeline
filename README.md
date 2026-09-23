# osert-data-pipeline
Pipeline de Engenharia de Dados para coleta, validação e publicação de indicadores socioeconômicos de Teresina a partir do SIDRA/IBGE.


## Operação integrada do sistema

Para atualizar o indicador e disponibilizar sua versão atual para consulta:

```bash
python -m src.sistema_dados atualizar
python -m src.sistema_dados consultar --ano 2026
```

A atualização conecta coleta, transformação e publicação em `data/catalogo.json`.
O catálogo aponta para o CSV validado e registra fonte, período, unidade,
grão e arquivos de origem. A consulta funciona sem internet e confere a
integridade dos arquivos antes de retornar os dados.

Respostas idênticas não duplicam observações nem regravam o catálogo.
Uma revisão do IBGE publica uma nova série e mantém os arquivos anteriores.
Falhas ou perda de períodos preservam a versão já publicada.

Consulte a [operação do sistema](docs/operacao_sistema.md) para comandos,
política de atualização, tratamento de falhas e continuidade do projeto.
Os módulos individuais abaixo continuam disponíveis para coleta e
reprocessamento.



## Comandos operacionais

```bash
python -m src.sistema_dados atualizar --todos
python -m src.sistema_dados verificar
python -m src.sistema_dados execucoes --limite 10
python -m src.sistema_dados consultar --inicio 202401 --fim 202602 --saida data/exports/desocupacao-recorte.csv
python -m src.sistema_dados consultar --indicador populacao_estimada_teresina --inicio 2024 --fim 2026 --formato json
python -m src.sistema_dados backup --saida data/backups/estado-20260922.zip
```

A atualização em lote registra sucessos, respostas sem alteração e falhas.
Consultas por intervalo têm limites inclusivos e exportam CSV ou JSON sem
acessar a rede. A verificação confere os arquivos e sua correspondência com
a origem. O backup permite recuperar dados e histórico em uma pasta nova.

Consulte a [operação do sistema](docs/operacao_sistema.md) para formatos de
período, restauração, integridade, limites e códigos de saída. A
[API local de consulta](docs/api_consulta.md) oferece essas consultas por HTTP.

## Indicadores disponíveis

```bash
python -m src.sistema_dados indicadores
python -m src.sistema_dados atualizar --indicador populacao_estimada_teresina
python -m src.sistema_dados consultar --indicador populacao_estimada_teresina --ano 2026
python -m src.sistema_dados consultar --indicador taxa_desocupacao_teresina --ano 2026
```

| Identificador | Periodicidade | Unidade | Contrato |
| --- | --- | --- | --- |
| `taxa_desocupacao_teresina` | Trimestral | % | [Desocupação](docs/contratos/taxa_desocupacao_teresina.md) |
| `populacao_estimada_teresina` | Anual | Pessoas | [População estimada](docs/contratos/populacao_estimada_teresina.md) |

O comando `indicadores` lista a configuração e informa quais indicadores já
têm publicação no catálogo, sem acessar a rede. Sem `--indicador`, os comandos
continuam usando a taxa de desocupação.

Cada atualização publica somente o indicador escolhido e mantém os demais.
A coluna `trimestre` fica vazia nos dados anuais de população. Anos ausentes
na fonte não são preenchidos. Os valores dos dois indicadores têm unidades
distintas e não devem ser somados ou comparados diretamente.

## Primeira extração: taxa de desocupação de Teresina

O programa consulta a API oficial do SIDRA/IBGE e exibe a série histórica da taxa de desocupação de Teresina (PI).

### Preparação do ambiente

As dependências fixadas exigem Python 3.12 ou superior. A entrega foi
validada com Python 3.14.4 em Ubuntu/WSL. Confira a versão com
`python3 --version` antes de criar o ambiente virtual.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Execução

```bash
python src/consulta_taxa_desocupacao.py
```

O grão de cada linha é tabela `6468` + variável `4099` + território
`2211001` + período trimestral (`D3C`). Cada período deve aparecer uma única
vez. Os valores são mantidos como texto, portanto símbolos especiais do SIDRA
não são convertidos automaticamente em zero.

Além de exibir a série, o programa preserva exatamente os bytes do corpo HTTP
recebido do SIDRA em `data/raw/`, sem decodificação ou reserialização. Todas as
observações são validadas antes da gravação, incluindo os campos de saída
`D1N`, `D3N`, `MN` e `V`: todos devem conter texto não vazio. Campos ausentes,
nulos ou de outro tipo interrompem a extração sem criar um arquivo bruto.
A tabela de saída também é preparada antes da gravação.

O nome do arquivo contém tabela, variável, território, o escopo
`periodo-all` e o hash SHA-256 do conteúdo. Como a mesma resposta produz o
mesmo nome, reexecutar a coleta não cria uma cópia duplicada.

### Verificação

Execute os testes locais a partir da raiz do projeto:

```bash
python -m unittest discover -s tests -v
```

Os testes simulam as respostas HTTP, sem acessar o SIDRA. Eles verificam a
extração da série, a rejeição de registros incompletos antes da gravação,
a preservação de símbolos e bytes e a ausência de arquivos duplicados.

Para verificar também o acesso real à API, execute o programa conforme a
seção Execução. Essa consulta depende da disponibilidade e das permissões
de acesso do SIDRA no ambiente utilizado. Falhas de rede ou HTTP interrompem
a execução; os testes locais não garantem a disponibilidade do serviço.

## Segunda etapa: transformar o arquivo bruto em CSV

A transformação lê uma coleta salva, valida o contrato do indicador e gera
uma linha por trimestre em `data/processed/`. Ela funciona sem internet e
preserva o arquivo bruto.

Após a coleta, consulte os nomes disponíveis com `ls data/raw/`. Execute,
a partir da raiz do projeto, substituindo `NOME_DA_COLETA.json` pelo arquivo
desejado:

```bash
python -m src.transforma_taxa_desocupacao "data/raw/NOME_DA_COLETA.json"
```

Para escolher outro diretório de saída:

```bash
python -m src.transforma_taxa_desocupacao "data/raw/NOME_DA_COLETA.json" --diretorio-saida data/processed/reprocessamento
```

O CSV inclui códigos do indicador e território, ano, trimestre, unidade,
classificações, valor original, valor numérico e referência ao arquivo bruto
com seu SHA-256. Símbolos como `-` e `...` permanecem na coluna original;
a coluna numérica fica vazia e o status identifica um símbolo.

Cada coleta gera seu próprio CSV. Reexecutar sobre o mesmo arquivo reutiliza
o resultado idêntico. Um resultado existente com conteúdo diferente causa
erro, para preservar o arquivo e permitir investigação.

Consulte o [contrato do indicador](docs/contratos/taxa_desocupacao_teresina.md)
para as colunas, validações, símbolos aceitos e limites desta etapa.
O comando de testes da seção Verificação também executa os testes da
transformação. Dados brutos e processados ficam locais, ignorados pelo Git.

## API local de consulta

A API permite consultar a base publicada a partir de outros programas, usando HTTP.
Para iniciar, com o ambiente virtual ativado:

```bash
python -m src.api_consulta --diretorio-dados data --porta 8000
```

Acesse `http://127.0.0.1:8000/indicadores` no mesmo ambiente do serviço.
As rotas permitem consultar dados com filtros, metadados e integridade.
O serviço usa somente a base local, preserva os arquivos e é encerrado com Ctrl+C.
Consulte [rotas, exemplos, erros e limites](docs/api_consulta.md).

## Revisões e publicações anteriores

Atualizações registram períodos novos e observações alteradas. As consultas
aceitam uma execução anterior e verificam os arquivos daquela publicação.
Veja [comparação, consulta histórica e compatibilidade](docs/revisoes_historico.md).

[Estado atual e validações da entrega](docs/estado_desenvolvimento.md).
