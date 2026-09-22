# Operação do sistema de dados de Teresina

O sistema coleta indicadores SIDRA/IBGE, preserva a origem, transforma os
dados e mantém versões locais consultáveis. O acesso atual é por comandos
Python, a partir da raiz do projeto e com o ambiente virtual ativado.

## Indicadores e atualização

```bash
python -m src.sistema_dados indicadores
python -m src.sistema_dados atualizar
python -m src.sistema_dados atualizar --indicador populacao_estimada_teresina
python -m src.sistema_dados atualizar --todos
```

| Identificador | Periodicidade | Unidade | Contrato |
| --- | --- | --- | --- |
| taxa_desocupacao_teresina | Trimestral | % | [Desocupação](contratos/taxa_desocupacao_teresina.md) |
| populacao_estimada_teresina | Anual | Pessoas | [População](contratos/populacao_estimada_teresina.md) |

Sem seleção, a atualização e a consulta usam desocupação. `--todos` e
`--indicador` são mutuamente exclusivos na atualização. O lote tenta cada
indicador separadamente e continua se algum falhar. A saída JSON informa os
resultados individuais; o código de saída será 1 se qualquer um falhar.

Cada atualização faz uma consulta à API, preserva a resposta bruta, aplica
o contrato e publica a referência ao CSV. Os indicadores têm publicações
independentes: o lote não é uma transação conjunta dos dois.

## Consulta, intervalos e exportação

```bash
python -m src.sistema_dados consultar --ano 2026
python -m src.sistema_dados consultar --inicio 202401 --fim 202602
python -m src.sistema_dados consultar --indicador populacao_estimada_teresina --inicio 2024 --fim 2026 --formato json
python -m src.sistema_dados consultar --inicio 202401 --fim 202602 --saida data/exports/desocupacao-2024-2026.csv
```

A consulta funciona sem rede. Os limites são inclusivos e podem ser usados
separadamente. Trimestres usam AAAA0T, com T entre 1 e 4; anos usam AAAA.
`--ano` não pode ser combinado com `--inicio` ou `--fim`.
Intervalos invertidos e formatos incompatíveis são rejeitados.

CSV é o formato padrão. JSON inclui indicador, unidade, periodicidade,
filtros, quantidade e observações. Os valores numéricos permanecem
representados como texto decimal, para preservar precisão e o formato
original. Símbolos especiais continuam na coluna original, com valor
numérico vazio e status explícito.

Um recorte vazio resulta em cabeçalho CSV ou lista JSON vazia. A consulta
não preenche lacunas nem mistura unidades dos indicadores.

`--saida` grava o resultado em arquivo. Conteúdo idêntico é reutilizado sem
regravação; conteúdo diferente em um destino existente causa erro.
A exportação não pode escrever no catálogo, bloqueio, bruto, processado
ou histórico interno do sistema. Recomenda-se `data/exports/`.

## Catálogo e integridade

```bash
python -m src.sistema_dados verificar
python -m src.sistema_dados verificar --indicador populacao_estimada_teresina
```

A verificação é local e confere:

- Existência e hashes dos arquivos brutos e processados.
- Tabela, variável, território, unidade, periodicidade, grão e versão do contrato.
- Nome e conteúdo do bruto, validados pelo contrato.
- Correspondência entre cada linha do CSV e a transformação da origem.
- Quantidade de observações e limites de período registrados no catálogo.
- Estrutura do histórico de execuções.

O relatório inclui quantidade de símbolos e períodos ausentes entre o
primeiro e o último disponível. Lacunas são informativas: podem existir
na fonte, especialmente na série anual. `saudavel=true` indica integridade
da publicação, não comprova completude, atualidade ou correção estatística
dos dados do IBGE.

Indicadores selecionados ainda não publicados, corrupção ou metadados
incompatíveis produzem código de saída 1. Bloqueio de atualização e
execuções sem finalização geram avisos para investigação.

## Histórico de execuções

```bash
python -m src.sistema_dados execucoes --limite 10
python -m src.sistema_dados execucoes --indicador taxa_desocupacao_teresina --limite 5
```

Uma tentativa iniciada sob o bloqueio recebe identificador próprio, horários
UTC, indicador, etapa e status: `em_execucao`, `atualizado`,
`sem_alteracao` ou `falha`. Resultados concluídos incluem referências aos
arquivos. Falhas registram tipo e mensagem do erro.

As etapas são preparação, validação anterior, coleta, transformação,
validação da série, publicação e conclusão. Uma tentativa impedida pelo
bloqueio não inicia execução nem gera registro.

Repetir uma coleta idêntica gera um novo registro de tentativa, sem duplicar
dados nem modificar o catálogo. O horário do registro é da operação local;
não é a data de divulgação do IBGE.

Se o dado for publicado mas a gravação do registro final falhar, a atualização
retorna aviso explícito. O registro pode permanecer em execução; isso não
significa, por si só, que os dados deixaram de ser publicados.

## Organização e preservação

| Caminho | Conteúdo |
| --- | --- |
| data/raw/ | Respostas originais identificadas pelo conteúdo |
| data/processed/ | Um CSV por resposta bruta |
| data/catalogo.json | Referências das versões publicadas |
| data/execucoes/ | Um JSON por tentativa de atualização |
| data/exports/ | Recortes para consumo |
| data/backups/ | Pacotes de preservação |
| data/.atualizacao.lock | Bloqueio temporário de atualização ou backup |

Esses arquivos ficam fora do Git pelo `.gitignore`. O catálogo armazena
caminhos relativos à pasta de dados. Use a opção global antes do comando
para operar outra base:

```bash
python -m src.sistema_dados --diretorio-dados data/copia consultar --ano 2026
```

Os módulos de coleta e transformação continuam disponíveis para uso
individual e reprocessamento. `src/formato_csv.py` define o formato tabular
comum; cada indicador mantém suas regras específicas.

A versão atual é a última coleta validada e publicada pelo comando
`atualizar`. Uma revisão pode alterar valores e acrescentar períodos,
preservando os arquivos anteriores. A publicação é recusada se perder
períodos que já constavam da versão anterior.

Erros de rede, validação ou publicação mantêm a referência anterior.
Artefatos produzidos antes da falha podem permanecer salvos para investigação,
mas não passam a ser consultados automaticamente.

O catálogo e os registros são substituídos em uma operação única. Brutos,
CSVs, exportações e backups só recebem o nome definitivo depois da escrita
completa. Arquivos imutáveis existentes são conferidos, nunca sobrescritos.
A implementação exige suporte a links de arquivos no sistema de arquivos;
foi verificada no Ubuntu/WSL do projeto.

O bloqueio evita duas atualizações simultâneas. Uma interrupção abrupta pode
deixar bloqueio ou temporários residuais. Antes de intervir, confira o
processo indicado no bloqueio; não há remoção automática por idade.
O sistema não faz repetição automática de requisições.

## Backup e restauração

```bash
python -m src.sistema_dados backup --saida data/backups/estado-20260922.zip
python -m src.sistema_dados restaurar data/backups/estado-20260922.zip --destino data/restauracoes/copia-20260922
python -m src.sistema_dados --diretorio-dados data/restauracoes/copia-20260922 verificar
```

O ZIP inclui catálogo, arquivos reconhecidos de `raw/`, `processed/` e
`execucoes/`, além de um manifesto com tamanho e SHA-256 de cada arquivo.
Exportações, outros backups e bloqueios não entram no pacote.

A criação usa o bloqueio e exige integridade das publicações atuais e
das publicações históricas com metadados registrados. Para o mesmo
estado completo, incluindo o histórico, gera o mesmo pacote. Novas tentativas
de atualização mudam o histórico e, portanto, podem mudar o backup mesmo
quando os dados permanecem iguais. Escolha outro nome para preservar um
novo estado.

A restauração valida caminhos, manifesto, hashes, catálogo e correspondência
bruto/CSV. Ela prepara os dados em uma pasta temporária e só publica o
destino após a validação. O destino precisa ser uma pasta que ainda não
exista. A origem e pastas existentes permanecem preservadas.

Esta implementação atende bases locais de até 100 MiB descompactados e
10 mil arquivos. O pacote é uma cópia local: proteção contra perda do
computador exige guardar uma cópia em outro local, decisão ainda não
automatizada pelo sistema.

## Testes e limites atuais

```bash
python -m unittest discover -s tests -v
```

Os testes cobrem contratos, símbolos, precisão, reprocessamento sem rede,
intervalos, exportação, revisão de dados, preservação do histórico, falhas,
concorrência na gravação, integridade, atualização em lote e restauração.

A consulta está disponível pela linha de comando e pela
[API HTTP local](api_consulta.md), com rotas de leitura e validação dos dados.
Os testes também cobrem solicitações HTTP locais reais, filtros, erros e
coerência entre dados e metadados durante as consultas.
O sistema ainda não oferece painel, autenticação, agendamento ou banco de dados.

## Revisões e publicações anteriores

Atualizações registram períodos novos e observações alteradas. As consultas
aceitam uma execução anterior e verificam os arquivos daquela publicação.
Veja [comparação, consulta histórica e compatibilidade](revisoes_historico.md).
