# Proposta de próxima etapa: API local de consulta

Situação: aprovada pelo usuário e implementada. Veja o [contrato da API](api_consulta.md).
A proposta abaixo registra o escopo aprovado; a implementação usa apenas a biblioteca padrão do Python.

## Objetivo

Permitir que outros programas e uma futura interface consultem os indicadores
sem ler os arquivos internos nem executar comandos Python diretamente.
A API HTTP seria um serviço local, inicialmente disponível apenas em
127.0.0.1, com operações de leitura.

## Escopo proposto

| Operação | Resultado |
| --- | --- |
| GET /indicadores | Indicadores, unidades, periodicidades e disponibilidade |
| GET /indicadores/{id}/dados | Observações com ano ou intervalo de períodos |
| GET /indicadores/{id}/metadados | Fonte, contrato, cobertura e versão publicada |
| GET /saude | Estado de integridade da base local |

A resposta de dados incluiria filtros, unidade, versão e rastreabilidade.
Parâmetros inválidos, indicador desconhecido, publicação ausente e base
inconsistente teriam respostas distintas e documentadas.

A implementação reaproveitaria as funções de consulta e verificação que já
estão testadas. Atualizações e operações de restauração permaneceriam nos
comandos operacionais, enquanto a API forneceria acesso aos dados publicados.

## Arquivos previstos

- Novo módulo do serviço HTTP.
- Testes de integração das rotas, filtros e respostas de erro.
- Documentação de execução e contrato da API.
- Dependências de execução, caso seja aprovado usar um framework HTTP.

## Critérios de conclusão

- Consultar os dois indicadores por HTTP, com os mesmos resultados da consulta local.
- Manter consulta sem acesso ao SIDRA.
- Rejeitar parâmetros e dados inconsistentes com respostas previsíveis.
- Confirmar que as rotas não alteram o catálogo, os dados ou o histórico.
- Executar os testes e uma consulta real na interface local.

## Decisão necessária

A criação do serviço HTTP é uma mudança de arquitetura e pode acrescentar
uma dependência importante. O AGENTS.md exige autorização explícita.
Aprovar esta etapa não implica publicar na internet nem implantar o sistema
em um servidor externo.
