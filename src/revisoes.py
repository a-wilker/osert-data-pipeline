"""Comparação determinística entre observações já normalizadas."""

from .formato_csv import COLUNAS

CAMPOS_COMPARADOS = tuple(
    campo for campo in COLUNAS if campo not in ("arquivo_bruto", "sha256_bruto")
)


def comparar_observacoes(anteriores, atuais):
    """Compara conteúdo por período, sem confundir nova coleta com revisão."""
    antes = {linha["periodo_codigo"]: linha for linha in anteriores}
    depois = {linha["periodo_codigo"]: linha for linha in atuais}
    if len(antes) != len(anteriores) or len(depois) != len(atuais):
        raise ValueError("Não é possível comparar séries com períodos duplicados.")
    novos = sorted(depois.keys() - antes.keys())
    removidos = sorted(antes.keys() - depois.keys())
    alteradas = []
    for periodo in sorted(antes.keys() & depois.keys()):
        campos = {
            campo: {"anterior": antes[periodo][campo], "atual": depois[periodo][campo]}
            for campo in CAMPOS_COMPARADOS
            if antes[periodo][campo] != depois[periodo][campo]
        }
        if campos:
            alteradas.append({"periodo_codigo": periodo, "campos": campos})
    return {
        "versao_relatorio": 1,
        "quantidades": {
            "novas": len(novos), "removidas": len(removidos),
            "alteradas": len(alteradas),
            "inalteradas": len(antes.keys() & depois.keys()) - len(alteradas),
        },
        "periodos_novos": novos, "periodos_removidos": removidos,
        "observacoes_alteradas": alteradas,
    }
