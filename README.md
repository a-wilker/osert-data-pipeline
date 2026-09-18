# osert-data-pipeline
Pipeline de Engenharia de Dados para coleta, validação e publicação de indicadores socioeconômicos de Teresina a partir do SIDRA/IBGE.

## Primeira extração: taxa de desocupação de Teresina

O programa consulta a API oficial do SIDRA/IBGE e exibe a série histórica da taxa de desocupação de Teresina (PI).

### Preparação do ambiente

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
observações são validadas antes da gravação.

O nome do arquivo contém tabela, variável, território, o escopo
`periodo-all` e o hash SHA-256 do conteúdo. Como a mesma resposta produz o
mesmo nome, reexecutar a coleta não cria uma cópia duplicada.
