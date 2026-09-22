import hashlib
from pathlib import Path

import pandas as pd
import requests

if __package__:
    from .arquivos import gravar_imutavel
else:
    from arquivos import gravar_imutavel

TABELA = "6468"
VARIAVEL = "4099"
TERRITORIO = "2211001"
PERIODO = "all"

URL = (
    f"https://apisidra.ibge.gov.br/values/t/{TABELA}"
    f"/n6/{TERRITORIO}/v/{VARIAVEL}/p/{PERIODO}"
    "/h/n/f/a/d/s"
)

# Evita que a API escolha XML por negociação automática de conteúdo.
CABECALHOS = {"Accept": "application/json"}

DIRETORIO_DADOS_BRUTOS = Path("data/raw")


def _salvar_resposta_bruta(conteudo, periodo, diretorio):
    """Salva os bytes originais usando seus metadados e SHA-256 no nome."""
    sha256 = hashlib.sha256(conteudo).hexdigest()
    nome = (
        f"tabela-{TABELA}_variavel-{VARIAVEL}_territorio-{TERRITORIO}"
        f"_periodo-{periodo}_sha256-{sha256}.json"
    )
    caminho = diretorio / nome

    return gravar_imutavel(caminho, conteudo)


def _consultar_e_salvar(diretorio_dados_brutos):
    resposta = requests.get(URL, headers=CABECALHOS, timeout=30)
    resposta.raise_for_status()
    dados = resposta.json()

    if not isinstance(dados, list) or not dados:
        raise ValueError("A API retornou uma série vazia ou inválida.")

    periodos = set()
    for observacao in dados:
        if not isinstance(observacao, dict):
            raise ValueError("A API retornou uma observação inválida.")
        if observacao.get("D1C") != TERRITORIO:
            raise ValueError("A API retornou um território diferente do esperado.")
        if observacao.get("D2C") != VARIAVEL:
            raise ValueError("A API retornou um indicador diferente do esperado.")

        periodo = observacao.get("D3C")
        if periodo is None or not str(periodo).strip():
            raise ValueError("A API retornou D3C ausente ou vazio para o período.")
        if periodo in periodos:
            raise ValueError(f"A API retornou o período D3C duplicado: {periodo}.")
        periodos.add(periodo)

        for campo in ("D1N", "D3N", "MN", "V"):
            valor = observacao.get(campo)
            if not isinstance(valor, str) or not valor.strip():
                raise ValueError(
                    f"A API retornou {campo} ausente, vazio ou não textual "
                    f"para o período {periodo}."
                )

    df = pd.DataFrame(dados)
    resultado = df[["D1N", "D3N", "MN", "V"]]
    resultado = resultado.rename(
        columns={
            "D1N": "Território",
            "D3N": "Período",
            "MN": "Unidade",
            "V": "Taxa de desocupação",
        }
    )

    caminho = _salvar_resposta_bruta(
        resposta.content,
        PERIODO,
        Path(diretorio_dados_brutos),
    )
    return resultado, caminho


def extrair_taxa_desocupacao(diretorio_dados_brutos=DIRETORIO_DADOS_BRUTOS):
    resultado, _ = _consultar_e_salvar(diretorio_dados_brutos)
    return resultado


def coletar_taxa_desocupacao(diretorio_dados_brutos=DIRETORIO_DADOS_BRUTOS):
    """Devolve o caminho exato da resposta bruta desta coleta."""
    _, caminho = _consultar_e_salvar(diretorio_dados_brutos)
    return caminho


def main():
    resultado = extrair_taxa_desocupacao()
    print(resultado.to_string(index=False))


if __name__ == "__main__":
    main()
