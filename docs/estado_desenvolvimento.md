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

- Suíte completa: **126 testes passaram**.
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
A integração à branch principal é uma etapa posterior de revisão.

## Referências para continuidade

- [Operação do sistema](operacao_sistema.md).
- [Contrato e execução da API](api_consulta.md).
- [Revisões e consultas históricas](revisoes_historico.md).
- [Contrato da desocupação](contratos/taxa_desocupacao_teresina.md).
- [Contrato da população](contratos/populacao_estimada_teresina.md).
