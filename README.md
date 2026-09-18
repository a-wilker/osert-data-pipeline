# osert-data-pipeline
Pipeline de Engenharia de Dados para coleta, validação e publicação de indicadores socioeconômicos de Teresina a partir do SIDRA/IBGE.

## Primeira extração: taxa de desocupação de Teresina

O programa consulta a API oficial do SIDRA/IBGE e exibe a taxa de desocupação mais recente de Teresina (PI).

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

Além de exibir a observação, o programa preserva exatamente os bytes do corpo
HTTP recebido do SIDRA em `data/raw/`, sem decodificação ou reserialização.
Antes da gravação, o período `D3C` é validado; respostas sem um período
preenchido falham claramente e não criam o diretório de dados brutos.

O nome do arquivo contém tabela `6468`, variável `4099`, território `2211001`,
período e o hash SHA-256 do conteúdo. Como a mesma resposta produz o mesmo
nome, reexecutar a coleta não cria uma cópia duplicada.
