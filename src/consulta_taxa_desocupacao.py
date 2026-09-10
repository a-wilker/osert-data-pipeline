import requests
import pandas as pd
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

def extrair_taxa_desocupacao():
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