# Estado do desenvolvimento

Atualizado em 22/09/2026. Este documento registra o ponto de continuidade
do sistema de dados de Teresina.

## Entrega implementada

| Etapa | Situação |
| --- | --- |
| Coleta SIDRA/IBGE | Desocupação e população estimada de Teresina |
| Preservação da fonte | Resposta bruta intacta, identificada por SHA-256 |
| Transformação | CSV validado, preciso e rastreável, símbolos preservados |
| Publicação | Catálogo atualizado após validação, arquivos imutáveis |
| Operação | Atualização por indicador ou em lote, bloqueio e histórico de tentativas |
| Consulta | Terminal e HTTP local, filtros por ano ou intervalo |
| Rastreabilidade das revisões | Novas observações, campos alterados e referências anterior/atual |
| Reprodutibilidade | Consulta e exportação por execução concluída com metadados |
| Histórico HTTP | Descoberta de execuções e resumo das diferenças |
| Integridade | Verificação atual e opção para conferir publicações históricas |
| Recuperação | Backup com manifesto e restauração validada em pasta nova |

## Validações executadas nesta entrega

- Suíte completa: **128 testes passaram**.
- Atualização real dos dois indicadores: sucesso, sem alteração das observações.
- Desocupação: 58 observações, 8 símbolos, sem lacunas entre os extremos.
- População: 22 observações; os anos ausentes foram preservados sem preenchimento.
- Verificação com histórico: duas publicações verificadas, dois registros antigos
  sem metadados completos, nenhum erro.
- Histórico e dados consultados por HTTP real em porta local temporária.
- Respostas históricas HTTP iguais às consultas Python da mesma execução.
- Exportação JSON histórica gerada e backup criado.
- Backup restaurado em diretório temporário; ambas as consultas históricas
  reproduzidas e integridade aprovada.
- Catálogo, dados brutos, CSVs e registros existentes preservados durante
  a consulta e o teste de recuperação. O servidor de teste foi encerrado.
- `git diff --check` sem erros nos arquivos acompanhados pelo Git.

Execuções reais registradas nesta validação:

- Desocupação: `06284994d5c248428ad690240678bae3`.
- População: `df4aaa0e535e414686a47df66a1aa5ed`.

Arquivos locais de saída (ignorados pelo Git):

- `data/exports/populacao-execucao-df4aaa0e535e414686a47df66a1aa5ed.json`.
- `data/backups/osert-historico-20260922T215632Z.zip`.

## Limites atuais

A API é local, em 127.0.0.1, e somente de leitura.
A consulta histórica exige os metadados registrados por esta implementação;
registros anteriores permanecem legíveis, mas não recebem metadados inventados.
A integridade confirma a coerência local com os contratos e arquivos da fonte,
não substitui avaliação metodológica do indicador.
Não há painel, autenticação, implantação externa ou rotina agendada.

## Entrega versionada

O usuário autorizou explicitamente o commit e o push desta entrega.
O código, os testes e a documentação foram reunidos na branch
`codex/sistema-dados-historico`. Dados locais, backups e ambientes não fazem
parte da entrega versionada.

Para continuar em outra sessão do Codex, selecione essa branch.
A revisão para integração está registrada no [PR #3](https://github.com/a-wilker/osert-data-pipeline/pull/3).

## Referências para continuidade

- [Operação do sistema](operacao_sistema.md).
- [Contrato e execução da API](api_consulta.md).
- [Revisões e consultas históricas](revisoes_historico.md).
- [Contrato da desocupação](contratos/taxa_desocupacao_teresina.md).
- [Contrato da população](contratos/populacao_estimada_teresina.md).

## Revisão para integração

- Corrigida a contagem do limite do backup: dados e manifesto entram no
  mesmo limite de 100 MiB usado na restauração.
- O teste de regressão reproduziu a falha antes da correção.
- Testado o excesso causado pelo manifesto e o sucesso de criação e
  restauração no limite exato.
- A leitura dos arquivos do backup respeita o limite restante de bytes.
- Suíte completa após a correção: 128 testes passaram.
- `python -m pip check`: nenhuma dependência incompatível detectada.

## Testes automáticos

Configuração implementada no [PR #4](https://github.com/a-wilker/osert-data-pipeline/pull/4),
com autorização do usuário. A [primeira execução no GitHub](https://github.com/a-wilker/osert-data-pipeline/actions/runs/35913754395)
validou instalação, dependências e os 128 testes em Ubuntu 24.04 com Python 3.14.4.
O fluxo atende PRs para main, pushes na main e execução manual.
Veja [configuração e limites](proposta_testes_automaticos.md).

## Estado operacional das atualizações — 24/09/2026

Implementado relatório separado para integridade dos dados e atenção operacional.
Cada indicador informa a última tentativa, a última concluída e execuções
sem conclusão. Horários do histórico são validados e ordenados por instante.

Validação desta etapa: 138 testes passaram. A verificação da base real com
histórico retornou integridade aprovada e atenção operacional falsa.
Os dois indicadores mantêm os dados publicados anteriormente.

A situação operacional não comprova atualização em relação ao calendário do IBGE.

### Continuidade da revisão

A verificação também passou a rejeitar nome, critério, versão e horário de
publicação inconsistentes. Os testes reproduziram a falha antes da correção.
A suíte local está em 140 testes passando; a base real permanece íntegra,
sem atenção operacional, com conteúdo e horários de modificação preservados.

A entrega está organizada na branch `codex/estado-operacional`.
Após o bloqueio inicial da revisão automática, o usuário autorizou
explicitamente commit, push e abertura do PR desta etapa.
A integração à main desta etapa ainda não está autorizada.

## Exportação CSV pela API — 24/09/2026

Implementada localmente na branch `codex/exportacao-csv-api` a rota
`/indicadores/{id}/dados.csv`, com filtros e seleção de execução histórica.
Os bytes correspondem à exportação local. A resposta inclui nome de download,
hash do conteúdo filtrado, hash do bruto e hash do CSV completo publicado.

Validações executadas:
- 146 testes passaram.
- Erros retornam JSON e não iniciam download.
- Símbolos SIDRA e cabeçalho de consultas vazias preservados.
- Publicação atualizada durante a consulta não mistura dados e hashes.
- Download HTTP real de 2026: duas observações de desocupação e uma de população.
- Conteúdo e hashes conferidos; arquivos da base preservados e servidor encerrado.
- `git diff --check` sem erros.

O usuário autorizou a continuidade do desenvolvimento e da publicação
sem novas aprovações por etapa. A entrega segue por PR e integração após
validação automática.

## Contratos consultáveis — 24/09/2026

Adicionadas consulta de contrato no terminal e rota HTTP por indicador.
As respostas descrevem identificação, território, unidade, grão, períodos,
valores, colunas e filtros sem consultar arquivos publicados ou rede.

153 testes passaram, incluindo equivalência das regras com as observações
normalizadas, resposta independente do catálogo e rejeição de parâmetros extras.
As regras de formato de período são compartilhadas com a validação dos filtros.
A etapa de CSV anterior foi integrada pelo PR #6 e validada na main.
