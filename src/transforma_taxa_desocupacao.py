"""Transforma uma coleta de desocupação em CSV, sem consultar a rede."""

import argparse
import csv
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path
import re

from .formato_csv import COLUNAS, SIMBOLOS_SIDRA
from .arquivos import gravar_imutavel

from .consulta_taxa_desocupacao import PERIODO, TABELA, TERRITORIO, URL, VARIAVEL

DIRETORIO_PROCESSADOS = Path("data/processed")


def _texto(observacao, campo):
    valor = observacao.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"Campo {campo} ausente, vazio ou não textual.")
    return valor


def _normalizar(observacao, arquivo, sha256):
    if not isinstance(observacao, dict):
        raise ValueError("Cada observação deve ser um objeto JSON.")
    esperados = {
        "NC": "6", "MC": "2", "MN": "%",
        "D1C": TERRITORIO, "D2C": VARIAVEL,
    }
    for campo, esperado in esperados.items():
        if observacao.get(campo) != esperado:
            raise ValueError(f"Campo {campo} diferente do esperado: {esperado}.")
    if any(
        re.fullmatch(r"D[0-9]+[CN]", chave) and int(chave[1:-1]) > 3
        for chave in observacao
    ):
        raise ValueError("Classificação ou dimensão adicional não prevista no contrato.")

    territorio = _texto(observacao, "D1N")
    periodo_nome = _texto(observacao, "D3N")
    periodo = _texto(observacao, "D3C")
    if not re.fullmatch(r"[0-9]{4}0[1-4]", periodo) or int(periodo[:4]) == 0:
        raise ValueError(f"Período trimestral inválido: {periodo}.")

    original = _texto(observacao, "V")
    valor = original.strip()
    if valor in SIMBOLOS_SIDRA:
        numerico = ""
        status = "simbolo_sidra"
    elif re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", valor):
        decimal = Decimal(valor)
        if not Decimal("0") <= decimal <= Decimal("100"):
            raise ValueError(f"Taxa fora do intervalo de 0 a 100: {original}.")
        numerico = format(decimal, "f")
        status = "numerico"
    else:
        raise ValueError(f"Valor ou símbolo não reconhecido: {original}.")

    return {
        "fonte": "SIDRA/IBGE", "tabela": TABELA, "variavel": VARIAVEL,
        "territorio_codigo": TERRITORIO, "territorio_nome": territorio,
        "periodo_codigo": periodo, "periodo_nome": periodo_nome,
        "ano": int(periodo[:4]), "trimestre": int(periodo[-2:]),
        "unidade": "%", "classificacoes": "sem_classificacoes",
        "valor_original": original, "valor_numerico": numerico,
        "status_valor": status, "arquivo_bruto": arquivo.name,
        "sha256_bruto": sha256, "url_fonte": URL,
    }


def normalizar_serie(dados, arquivo, sha256):
    if not isinstance(dados, list) or not dados:
        raise ValueError("O arquivo bruto deve conter uma série não vazia.")

    linhas = []
    periodos = set()
    for observacao in dados:
        linha = _normalizar(observacao, arquivo, sha256)
        periodo = linha["periodo_codigo"]
        if periodo in periodos:
            raise ValueError(f"Período duplicado: {periodo}.")
        periodos.add(periodo)
        linhas.append(linha)
    linhas.sort(key=lambda linha: linha["periodo_codigo"])

    return linhas


def transformar_taxa_desocupacao(arquivo_bruto, diretorio_saida=DIRETORIO_PROCESSADOS):
    """Valida toda a coleta e gera um CSV determinístico por arquivo bruto."""
    arquivo = Path(arquivo_bruto)
    conteudo = arquivo.read_bytes()
    sha256 = hashlib.sha256(conteudo).hexdigest()
    nome_esperado = (
        f"tabela-{TABELA}_variavel-{VARIAVEL}_territorio-{TERRITORIO}"
        f"_periodo-{PERIODO}_sha256-{sha256}.json"
    )
    if arquivo.name != nome_esperado:
        raise ValueError("Nome ou hash do arquivo bruto não corresponde ao conteúdo e à consulta.")
    dados = json.loads(conteudo)
    linhas = normalizar_serie(dados, arquivo, sha256)

    buffer = io.StringIO(newline="")
    escritor = csv.DictWriter(buffer, fieldnames=COLUNAS, lineterminator="\n")
    escritor.writeheader()
    escritor.writerows(linhas)
    csv_bytes = buffer.getvalue().encode("utf-8")

    diretorio = Path(diretorio_saida)
    destino = diretorio / f"{arquivo.stem}.csv"
    return gravar_imutavel(destino, csv_bytes)


def main():
    parser = argparse.ArgumentParser(
        description="Transforma um arquivo bruto de desocupação em CSV sem acessar a rede."
    )
    parser.add_argument("arquivo_bruto", type=Path)
    parser.add_argument("--diretorio-saida", type=Path, default=DIRETORIO_PROCESSADOS)
    argumentos = parser.parse_args()
    try:
        destino = transformar_taxa_desocupacao(
            argumentos.arquivo_bruto, argumentos.diretorio_saida
        )
    except (OSError, ValueError) as erro:
        parser.exit(1, f"Erro: {erro}\n")
    print(f"CSV disponível em: {destino}")


if __name__ == "__main__":
    main()
