"""Gravação de arquivos imutáveis sem publicar conteúdo parcial."""

import os
from pathlib import Path
import tempfile


def gravar_imutavel(destino, conteudo):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    def conferir_existente():
        if destino.read_bytes() != conteudo:
            raise ValueError(f"Arquivo existente difere do conteúdo esperado: {destino}.")

    if destino.exists():
        conferir_existente()
        return destino

    temporario = None
    try:
        with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".gravacao-", suffix=".tmp", delete=False) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        try:
            # Link no mesmo diretório: publica o arquivo completo e falha se o nome já existe.
            os.link(temporario, destino)
        except FileExistsError:
            conferir_existente()
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()
    return destino
