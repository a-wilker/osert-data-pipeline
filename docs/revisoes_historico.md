# Revisões e consultas históricas

## O que fica registrado

Cada atualização concluída passa a gravar em `resultado` do registro de execução:

- `comparacao`: períodos novos, contagem de observações alteradas e inalteradas,
  e os campos alterados com seus valores anterior e atual.
- `publicacao`: cópia dos metadados da publicação resultante, incluindo referências
  ao bruto e ao CSV, seus SHA-256 e o instante da publicação.
- As referências `bruto`, `csv` e a quantidade, já existentes, são mantidas.

A comparação usa as observações normalizadas, ordenadas por período.
Uma nova coleta muda o hash e o nome do arquivo bruto; esses dois campos
de procedência não contam como alteração em todas as observações.
Alterações nos demais campos ficam explícitas. Por exemplo, `7.90` → `7.9`
é uma alteração de representação registrada; a contagem não significa
necessariamente mudança no valor econômico ou demográfico.

A primeira publicação classifica todas as observações como novas.
Coleta idêntica registra todas como inalteradas e mantém o catálogo.
Uma coleta sem períodos antes publicados continua sendo rejeitada.
Falha de publicação não é registrada como uma revisão publicada.
Se a gravação final do histórico falhar depois da publicação, a atualização
retorna um aviso; essa execução não se torna consultável pelo histórico.

## Consultar uma publicação anterior

Primeiro obtenha o identificador de uma execução concluída:

```bash
python -m src.sistema_dados execucoes --indicador populacao_estimada_teresina --limite 5
```

Substitua ID_EXECUCAO pelo identificador de 32 caracteres:

```bash
python -m src.sistema_dados consultar --indicador populacao_estimada_teresina --execucao ID_EXECUCAO --ano 2026 --formato json
python -m src.sistema_dados consultar --indicador populacao_estimada_teresina --execucao ID_EXECUCAO --formato json --saida data/exports/populacao-historica.json
```

Sem `--execucao`, a consulta continua usando a publicação atual.
Com o identificador, usa os metadados daquela execução e valida os arquivos
referenciados antes de retornar os dados. A consulta histórica é independente
do catálogo atual, não acessa o SIDRA e não restaura nem altera a base.

O JSON de consulta e exportação agora inclui os mesmos metadados da API,
inclusive para filtros sem observações. A consulta histórica acrescenta
`execucao_id`. O CSV conserva as colunas existentes e a referência ao bruto.

A API aceita `execucao` nas rotas de dados e metadados:

```text
GET /indicadores/populacao_estimada_teresina/dados?execucao=ID_EXECUCAO&ano=2026
GET /indicadores/populacao_estimada_teresina/metadados?execucao=ID_EXECUCAO
```

O identificador é validado; não é um caminho de arquivo.
Uma execução de outro indicador, falha ou em andamento não fornece dados.
Arquivos históricos corrompidos causam erro; não há substituição silenciosa
pela versão atual.

## Compatibilidade

Registros anteriores a esta implementação continuam disponíveis em
`execucoes`, mas não contêm a cópia completa dos metadados.
A consulta histórica desses registros retorna erro explícito.
Não são inventados metadados nem modificados registros antigos.
Uma próxima atualização concluída, mesmo sem mudanças nos dados, registra
a publicação atual no novo formato.

Atualizações distintas sem mudança podem apontar para a mesma publicação.
O identificador da execução identifica uma tentativa de atualização; os
hashes identificam o conteúdo dos arquivos.

## Fluxo e conhecimento essencial

Coleta → validação e normalização → comparação por período → publicação →
registro dos metadados e diferenças → consulta atual ou histórica.

Essencial agora: distinguir execução, publicação e conteúdo; saber que revisão
da fonte pode mudar observações antigas; manter a referência da publicação
junto com um resultado de análise.
Para depois: comparação estatística entre revisões e políticas de retenção.

1. Por que uma mudança no hash não implica alteração em todos os valores?
2. Qual a diferença entre consultar sem execução e indicar uma execução?
3. O que acontece se o CSV da publicação antiga estiver corrompido?

Prática pequena: em uma base de teste, altere um único valor da resposta
simulada, atualize e compare a consulta atual com a execução anterior.
Os testes em `tests/test_revisoes.py` e `tests/test_publicacoes_historicas.py`
exercitam esse fluxo sem alterar a base real.

## Verificação do histórico e backup

```bash
python -m src.sistema_dados verificar --historico
python -m src.sistema_dados verificar --historico --indicador populacao_estimada_teresina
```

O relatório inclui quantidade de publicações distintas verificadas,
quantidade de execuções antigas sem metadados completos e erros por execução.
Uma mesma publicação referenciada por tentativas repetidas é conferida uma vez.
Registros antigos são contabilizados como não verificáveis por esse mecanismo;
isso não significa que a integridade de seus arquivos foi comprovada.

Sem `--historico`, a verificação continua focada nas publicações atuais e
na leitura dos registros. A API `/saude` mantém esse escopo atual.
Backup e restauração sempre conferem também as publicações históricas que
possuem metadados, antes de disponibilizar o pacote ou a pasta restaurada.
Caminhos absolutos e referências fora das pastas previstas são rejeitados.
