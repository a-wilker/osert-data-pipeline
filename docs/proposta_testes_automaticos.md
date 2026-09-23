# Testes automáticos nos PRs

Situação: aprovada e implementada no PR #4. A primeira execução remota passou.
Preparada em 23/09/2026 após a integração do PR #3.

## Objetivo e motivo

Executar os testes do sistema em cada solicitação de integração (PR) e após
alterações na main. Isso é integração contínua: verificar automaticamente
se uma alteração mantém o sistema funcionando.

O PR #3 foi validado localmente com 128 testes, mas o GitHub não tinha
verificações automáticas configuradas. Essa lacuna é relevante porque o
projeto também recebe alterações pelo Codex web/celular.

## Escopo da implementação

- Criar `.github/workflows/testes.yml` com a configuração abaixo.
- Instalar as dependências fixadas em `requirements.txt`.
- Conferir as dependências e executar toda a suíte de testes.
- Usar Python 3.14.4, versão já validada localmente, em Ubuntu 24.04.
- Exibir o resultado no PR; executar também após integração na main.
- Manter os testes com respostas SIDRA simuladas e pastas temporárias.
- Documentar o resultado da primeira execução real no GitHub.

As ações usadas para preparar o código e o Python são oficiais e estão
fixadas nos commits correspondentes às versões v7 consultadas em 23/09/2026.
A configuração concede leitura do código ao processo de teste.
Não executa atualização da base real, publicação do sistema ou agendamento
de coleta. A instalação das dependências exige acesso à rede.

## Configuração implementada

Arquivo: `.github/workflows/testes.yml`.

```yaml
name: Testes do sistema de dados

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  testes:
    name: Testes Python
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - name: Obter codigo
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
        with:
          persist-credentials: false

      - name: Preparar Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7
        with:
          python-version: "3.14.4"
          cache: pip
          cache-dependency-path: requirements.txt

      - name: Instalar dependencias
        run: python -m pip install -r requirements.txt

      - name: Verificar dependencias
        run: python -m pip check

      - name: Executar testes
        run: python -m unittest discover -s tests -v
```

## Critérios de conclusão

1. Criar uma branch de trabalho, implementar o arquivo e abrir um PR.
2. Confirmar que o GitHub executou a configuração sobre esse PR.
3. Obter sucesso da instalação, da verificação de dependências e dos testes.
4. Corrigir falhas do ambiente remoto, se houver, antes de integrar.
5. Integrar à main e conferir a execução após a integração.

A execução local na main passou: 128 testes e `pip check` sem incompatibilidades.
A [primeira execução em ambiente limpo do GitHub](https://github.com/a-wilker/osert-data-pipeline/actions/runs/35913754395) passou em 23/09/2026,
incluindo instalação, verificação de dependências e os 128 testes.
A integração é acompanhada no [PR #4](https://github.com/a-wilker/osert-data-pipeline/pull/4).

Exigir esse teste como regra obrigatória de proteção da main é uma configuração
administrativa separada; não está incluída nesta proposta.

## Autorização e escopo

O AGENTS.md exige autorização explícita para adicionar tecnologia importante
e cita GitHub Actions como algo a introduzir quando necessário.
O usuário aprovou implementar o arquivo, criar a branch,
fazer commit e push, abrir o PR, validar a execução e integrar após sucesso.
A automação utilizará os recursos de execução do repositório no GitHub.

## Conhecimento essencial

Agora: teste automático detecta regressões de código; não comprova disponibilidade
do SIDRA, atualização dos indicadores ou qualidade metodológica da fonte.
Para depois: matriz de versões Python, cobertura e regras de proteção.

1. Qual é a diferença entre testar o sistema e atualizar seus dados?
2. Por que os testes simulam as respostas do SIDRA?
3. O que deve acontecer se o teste automático falhar em um PR?

Prática pequena depois da aprovação: alterar uma expectativa em um teste numa
branch de teste, observar a falha e restaurar a expectativa antes de integrar.

## Referências oficiais

- [actions/checkout](https://github.com/actions/checkout).
- [actions/setup-python](https://github.com/actions/setup-python).
