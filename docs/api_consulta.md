# API local de consulta

Implementada com a biblioteca padrão do Python, sem dependências adicionais.
API é uma interface para outros programas consultarem o sistema; HTTP é o
protocolo usado para enviar as solicitações e receber as respostas.

## Iniciar e encerrar

Na raiz do projeto, com o ambiente virtual ativado:

```bash
python -m src.api_consulta --diretorio-dados data --porta 8000
```

O serviço atende exclusivamente em `127.0.0.1`. Encerre com Ctrl+C.
A porta pode ser de 1 a 65535; se estiver ocupada, o comando termina com erro.
No WSL, execute o cliente no mesmo ambiente; acesso pelo navegador do Windows
depende da configuração de encaminhamento local do WSL.

O serviço consulta publicações existentes. Se necessário, antes de iniciá-lo:

```bash
python -m src.sistema_dados atualizar --todos
python -m src.sistema_dados verificar
```

A atualização acessa o SIDRA. As rotas HTTP funcionam somente sobre a base local.

## Rotas

| Método e caminho | Resposta |
| --- | --- |
| GET /indicadores | Objeto com `indicadores`: identificador, nome, unidade, periodicidade e `publicado` |
| GET /indicadores/{id}/dados | Observações filtradas e metadados da publicação |
| GET /indicadores/{id}/metadados | Identificador, fonte, contrato, cobertura, arquivos e versão publicada |
| GET /indicadores/{id}/execucoes | Execuções recentes e resumo das alterações |
| GET /saude | Integridade da base, lacunas entre extremos e avisos operacionais |

Identificadores: `taxa_desocupacao_teresina` e `populacao_estimada_teresina`.
A disponibilidade em `/indicadores` informa a presença no catálogo.
A conferência completa dos arquivos acontece nas consultas de dados,
metadados e saúde.

Exemplos no mesmo ambiente do servidor:

```bash
curl 'http://127.0.0.1:8000/indicadores'
curl 'http://127.0.0.1:8000/indicadores/populacao_estimada_teresina/dados?ano=2026'
curl 'http://127.0.0.1:8000/indicadores/taxa_desocupacao_teresina/dados?inicio=202401&fim=202602'
curl 'http://127.0.0.1:8000/indicadores/populacao_estimada_teresina/metadados'
curl 'http://127.0.0.1:8000/saude'
```

## Filtros e contrato da resposta

A rota de dados aceita os filtros abaixo:

- `ano`: inteiro de 1 a 9999, com até quatro algarismos.
- `inicio` e `fim`: limites inclusivos; cada um pode ser usado sozinho.
  População usa AAAA; desocupação usa AAAA0T, sendo T de 1 a 4.
- Ano e intervalo não podem ser combinados.
- Parâmetros desconhecidos, vazios ou repetidos são rejeitados.

As rotas de dados e metadados também aceitam `execucao`, identificador de
32 caracteres hexadecimais minúsculos de uma execução concluída. Veja
[consultas históricas](revisoes_historico.md). Esse seletor pode acompanhar
os filtros de dados; na resposta histórica, `execucao_id` identifica a execução.

Uma consulta sem filtros devolve toda a série publicada. Não há paginação;
o escopo atual são duas séries municipais pequenas.
Intervalo válido sem observações devolve HTTP 200 e `dados: []`.

O objeto de dados contém `indicador`, `unidade`, `periodicidade`,
`filtros`, `quantidade_observacoes`, `dados` e `metadados`.
A quantidade principal corresponde ao resultado filtrado; a quantidade
dentro de `metadados` corresponde à publicação completa.

As observações mantêm as 17 colunas do CSV, com valores textuais.
Isso preserva a precisão decimal e a mesma representação da consulta local.
Símbolos SIDRA ficam em `valor_original`, com `valor_numerico: ""` e
`status_valor: "simbolo_sidra"`; nunca viram zero.

Os metadados incluem tabela, variável, território, unidade, classificações,
grão, periodicidade, URL da fonte, cobertura, `versao_contrato`,
`publicado_em_utc` e referências `bruto`/`csv` com caminho relativo e SHA-256.
SHA-256 é o resumo usado para identificar o conteúdo de cada arquivo.

Entrada → validação de rota e filtros → leitura única do catálogo →
verificação dos arquivos e correspondência bruto/CSV → filtro →
JSON com dados e metadados da mesma publicação.

Na consulta atual, o catálogo é relido a cada solicitação.
Na consulta histórica, os metadados são lidos do registro de execução. Uma atualização válida fica visível
sem reiniciar o serviço. Como os arquivos publicados são imutáveis, uma
consulta iniciada antes da atualização pode terminar com a publicação anterior,
mantendo seus próprios dados e metadados coerentes.
`/saude` é um diagnóstico dos arquivos durante a solicitação, não um bloqueio
de atualizações concorrentes.

## Erros

| HTTP | Código ou corpo | Condição |
| --- | --- | --- |
| 400 | parametros_invalidos | Filtro inválido, desconhecido ou incompatível |
| 400 | requisicao_invalida | Endereço inválido |
| 404 | rota_desconhecida | Caminho não definido |
| 404 | indicador_desconhecido | Identificador desconhecido |
| 404 | execucao_desconhecida | Execução não encontrada |
| 409 | publicacao_historica_ausente | Execução sem publicação consultável para o indicador |
| 405 | metodo_nao_permitido | Método diferente de GET dentre os métodos HTTP tratados |
| 409 | publicacao_ausente | Indicador conhecido ainda sem publicação |
| 503 | base_inconsistente | Falha ao ler ou validar catálogo, bruto ou CSV |
| 503 | Relatório com saudavel=false | Integridade reprovada em /saude |

Formato dos erros de consulta:

```json
{"erro": {"codigo": "publicacao_ausente", "mensagem": "Indicador ainda não publicado; execute atualizar na linha de comando."}}
```

O cabeçalho `Allow: GET` acompanha o erro 405.
HEAD retorna os cabeçalhos de erro sem corpo, conforme a semântica HTTP.
Métodos não reconhecidos e mensagens HTTP malformadas podem ser rejeitados
pelo servidor padrão antes do tratamento das rotas.

As respostas das rotas são JSON UTF-8 e incluem `Cache-Control: no-store`,
para que o cliente consulte a versão publicada em cada solicitação.
Falhas de integridade não expõem caminhos absolutos; use o comando
`verificar` para obter o diagnóstico detalhado no terminal.
Um erro de leitura não dispara coleta, correção ou gravação automática.

## Limites e verificação

Esta entrega serve uso local. Não inclui autenticação, exposição na rede,
implantação externa, painel ou política para clientes de outras origens.
O servidor padrão do Python não é recomendado para produção:
[documentação oficial de http.server](https://docs.python.org/3.14/library/http.server.html).
Uma implantação externa exige uma etapa própria de arquitetura e autorização.

Os testes de integração abrem uma porta local temporária, fazem solicitações
HTTP reais e fecham o servidor. A coleta de preparação é simulada.
São conferidos filtros, erros, equivalência com a consulta local,
rastreabilidade, símbolos, atualização sem reinício e ausência de alterações
em arquivos ou acesso ao SIDRA durante as consultas.

```bash
python -m unittest discover -s tests -v
```

## Conhecimento essencial

Agora: distinguir indicador e publicação; interpretar filtros, símbolos e
códigos HTTP; conferir a versão pelos metadados.
Para depois: autenticação, implantação externa, paginação e interface visual.

Três perguntas de recuperação:

1. O que diferencia um erro 404 de um erro 409 nesta API?
2. Por que o símbolo `...` não pode ser interpretado como zero?
3. Como identificar a publicação que originou uma resposta?

Pequena prática: troque o ano da consulta de população para um ano sem
observações e confira `dados: []`, preservando os metadados da publicação.

## Descobrir publicações pelo histórico

```text
GET /indicadores/populacao_estimada_teresina/execucoes?limite=20
```

Aceita somente `limite`, inteiro de 1 a 100 (padrão 20).
Retorna `indicador`, `limite` e `execucoes`, da mais recente para a mais antiga.
Cada item contém ID, horários, status, etapa, `publicacao_registrada` e,
quando disponível, a comparação entre observações.

`publicacao_registrada` indica que há metadados de uma publicação concluída
no registro. A existência e integridade dos arquivos são verificadas quando
a publicação é consultada; a listagem não promete que arquivos estejam íntegros.
Execuções antigas, interrompidas ou com falha não são anunciadas como consultáveis.

Use o ID do item em `dados?execucao=ID` para reproduzir a consulta.
Mensagens internas de falha e caminhos de arquivos são omitidos nesta rota.
O histórico completo para diagnóstico continua disponível pelo terminal.

## Integridade e resultado das atualizações

A rota `/saude` inclui `atencao_operacional` e o estado de `atualizacao`
por indicador. Uma falha recente de coleta não torna os dados anteriores
corrompidos: a resposta pode ser HTTP 200 com `saudavel: true` e
`atencao_operacional: true`. Consulte os [estados operacionais](operacao_sistema.md#estado-operacional-das-atualizações).
