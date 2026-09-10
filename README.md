# osert-data-pipeline
Pipeline de Engenharia de Dados para coleta, validação e publicação de indicadores socioeconômicos de Teresina a partir do SIDRA/IBGE.

## Primeira extração: taxa de desocupação de Teresina

O programa consulta a API oficial do SIDRA/IBGE e exibe a taxa de desocupação mais recente de Teresina (PI).

### Preparação do ambiente

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt