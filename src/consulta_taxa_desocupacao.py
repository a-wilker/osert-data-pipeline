import hashlib
from pathlib import Path

import pandas as pd
import requests

# Código da tabela do SIDRA que contém a taxa de desocupação.
TABELA = "6468"

# Código do indicador que queremos: taxa de desocupação em porcentagem.
VARIAVEL = "4099"

# Código IBGE de Teresina (PI).
TERRITORIO = "2211001"

# Pede à API o período mais recente disponível.
PERIODO = "last"

# Endereço da API oficial do SIDRA.
# A URL será montada com a tabela, o município, o indicador e o período escolhidos.
URL = (
    f"https://apisidra.ibge.gov.br/values/t/{TABELA}"
    f"/n6/{TERRITORIO}/v/{VARIAVEL}/p/{PERIODO}"
    "/h/n/f/a/d/s"
)

# Diretório local em que a resposta original da API será preservada.
DIRETORIO_DADOS_BRUTOS = Path("data/raw")


def _salvar_resposta_bruta(conteudo, periodo, diretorio):
    """Salva os bytes originais usando seus metadados e SHA-256 no nome."""
    sha256 = hashlib.sha256(conteudo).hexdigest()
    nome = (
        f"tabela-{TABELA}_variavel-{VARIAVEL}_territorio-{TERRITORIO}"
        f"_periodo-{periodo}_sha256-{sha256}.json"
    )
    caminho = diretorio / nome

    diretorio.mkdir(parents=True, exist_ok=True)
    if not caminho.exists():
        caminho.write_bytes(conteudo)

    return caminho


def extrair_taxa_desocupacao(diretorio_dados_brutos=DIRETORIO_DADOS_BRUTOS):
    # Faz o pedido de dados para a API do IBGE.
    resposta = requests.get(URL, timeout=30)

    # Interrompe a extração se a API devolver um erro.
    resposta.raise_for_status()

    # Transforma a resposta recebida em dados que o Python consegue ler.
    dados = resposta.json()

    # Confirma que a API devolveu somente uma observação.
    if len(dados) != 1:
        raise ValueError("A API deveria retornar exatamente uma observação.")

    # Confirma que o dado recebido é de Teresina.
    if dados[0]["D1C"] != TERRITORIO:
        raise ValueError("A API retornou um território diferente do esperado.")

    # Confirma que o indicador recebido é a taxa de desocupação.
    if dados[0]["D2C"] != VARIAVEL:
        raise ValueError("A API retornou um indicador diferente do esperado.")

    periodo = dados[0].get("D3C")
    if periodo is None or not str(periodo).strip():
        raise ValueError("A API retornou D3C ausente ou vazio para o período.")

    # Preserva os mesmos bytes recebidos antes da conversão para DataFrame.
    _salvar_resposta_bruta(
        resposta.content,
        periodo,
        Path(diretorio_dados_brutos),
    )

    # Transforma os dados recebidos em uma tabela do Pandas.
    df = pd.DataFrame(dados)

    # Seleciona apenas as informações que queremos mostrar.
    resultado = df[["D1N", "D3N", "MN", "V"]]

    # Troca os nomes técnicos das colunas por nomes legíveis.
    resultado = resultado.rename(
        columns={
            "D1N": "Território",
            "D3N": "Período",
            "MN": "Unidade",
            "V": "Taxa de desocupação",
        }
    )

    # Devolve a tabela pronta para quem chamou a função.
    return resultado


def main():
    # Executa a extração e mostra a tabela final.
    resultado = extrair_taxa_desocupacao()
    print(resultado.to_string(index=False))


if __name__ == "__main__":
    main()
