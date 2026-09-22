"""Pacotes verificáveis dos dados locais, com restauração em diretório novo."""

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from .arquivos import gravar_imutavel
from .registro_execucoes import ler_execucoes

MAXIMO_BYTES = 100 * 1024 * 1024
MAXIMO_ARQUIVOS = 10000


def _nome_permitido(nome):
    if not isinstance(nome, str) or "\\" in nome or ":" in nome:
        return False
    caminho = PurePosixPath(nome)
    if caminho.is_absolute() or caminho.as_posix() != nome or ".." in caminho.parts:
        return False
    if nome == "catalogo.json":
        return True
    if len(caminho.parts) != 2:
        return False
    pasta, arquivo = caminho.parts
    extensao = {"raw": ".json", "processed": ".csv", "execucoes": ".json"}.get(pasta)
    return extensao is not None and not arquivo.startswith(".") and arquivo.endswith(extensao)


def _validar_base(raiz):
    # Importação local evita dependência circular com o ponto de entrada dos comandos.
    from .sistema_dados import CONFIGURACOES, _ler_catalogo, _linhas_catalogadas, verificar_publicacoes_registradas
    catalogo = _ler_catalogo(raiz)
    if not catalogo["indicadores"]:
        raise ValueError("Não há indicadores publicados para preservar.")
    for indicador, entrada in catalogo["indicadores"].items():
        if indicador not in CONFIGURACOES:
            raise ValueError(f"Indicador desconhecido no backup: {indicador}.")
        for tipo, pasta in (("bruto", "raw"), ("csv", "processed")):
            referencia = entrada.get(tipo) if isinstance(entrada, dict) else None
            nome = referencia.get("caminho") if isinstance(referencia, dict) else None
            if not _nome_permitido(nome) or PurePosixPath(nome).parent.as_posix() != pasta:
                raise ValueError("Referência do catálogo fora da estrutura suportada pelo backup.")
        _linhas_catalogadas(raiz, entrada, indicador)
    quantidade = len(list((raiz / "execucoes").glob("*.json")))
    registros = ler_execucoes(raiz, limite=max(quantidade, 1))
    historico = verificar_publicacoes_registradas(raiz, registros)
    if historico["erros"]:
        raise ValueError("Publicação histórica inválida no backup: " + historico["erros"][0]["mensagem"])


def criar_backup(caminho_saida, diretorio_dados=Path("data")):
    from .sistema_dados import _execucao_exclusiva
    raiz = Path(diretorio_dados).resolve()
    destino = Path(caminho_saida)
    resolvido = destino.resolve()
    if resolvido in (raiz / "catalogo.json", raiz / ".atualizacao.lock") or any(
        resolvido.is_relative_to(raiz / pasta) for pasta in ("raw", "processed", "execucoes")
    ):
        raise ValueError("O backup não pode escrever nos arquivos internos do sistema.")
    with _execucao_exclusiva(raiz):
        _validar_base(raiz)
        caminhos = [raiz / "catalogo.json"]
        for pasta, padrao in (("raw", "*.json"), ("processed", "*.csv"), ("execucoes", "*.json")):
            caminhos.extend(sorted((raiz / pasta).glob(padrao)))
        if len(caminhos) > MAXIMO_ARQUIVOS:
            raise ValueError("Quantidade de arquivos excede o limite do backup.")
        total = 0
        arquivos = {}
        for caminho in caminhos:
            if caminho.is_symlink() or not caminho.is_file():
                raise ValueError(f"Arquivo de backup inválido: {caminho.name}.")
            nome = caminho.relative_to(raiz).as_posix()
            if not _nome_permitido(nome):
                raise ValueError(f"Nome de arquivo não suportado: {nome}.")
            total += caminho.stat().st_size
            if total > MAXIMO_BYTES:
                raise ValueError("Conteúdo excede o limite de 100 MiB do backup.")
            arquivos[nome] = caminho.read_bytes()
        manifesto = {
            "versao": 1,
            "arquivos": [
                {"caminho": nome, "tamanho": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}
                for nome, conteudo in sorted(arquivos.items())
            ],
        }
        arquivos["manifesto.json"] = (json.dumps(manifesto, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
            for nome, conteudo in sorted(arquivos.items()):
                info = zipfile.ZipInfo(nome, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                pacote.writestr(info, conteudo)
        return gravar_imutavel(destino, buffer.getvalue())


def _ler_backup(caminho):
    try:
        with zipfile.ZipFile(caminho, "r") as pacote:
            itens = pacote.infolist()
            nomes = [item.filename for item in itens]
            if len(itens) > MAXIMO_ARQUIVOS + 1 or len(set(nomes)) != len(nomes):
                raise ValueError("Backup contém arquivos duplicados ou quantidade excessiva.")
            if sum(item.file_size for item in itens) > MAXIMO_BYTES:
                raise ValueError("Conteúdo excede o limite de 100 MiB da restauração.")
            if "manifesto.json" not in nomes:
                raise ValueError("Backup sem manifesto.")
            if any(nome != "manifesto.json" and not _nome_permitido(nome) for nome in nomes):
                raise ValueError("Backup contém caminho não permitido.")
            manifesto = json.loads(pacote.read("manifesto.json"))
            if (
                not isinstance(manifesto, dict) or manifesto.get("versao") != 1
                or not isinstance(manifesto.get("arquivos"), list)
            ):
                raise ValueError("Manifesto de backup inválido.")
            arquivos = {}
            for item in manifesto["arquivos"]:
                if not isinstance(item, dict) or not _nome_permitido(item.get("caminho")):
                    raise ValueError("Entrada inválida no manifesto.")
                nome = item["caminho"]
                if nome in arquivos or nome not in nomes:
                    raise ValueError("Manifesto contém referência duplicada ou inexistente.")
                conteudo = pacote.read(nome)
                if (
                    type(item.get("tamanho")) is not int or len(conteudo) != item["tamanho"]
                    or hashlib.sha256(conteudo).hexdigest() != item.get("sha256")
                ):
                    raise ValueError(f"Conteúdo do backup diverge do manifesto: {nome}.")
                arquivos[nome] = conteudo
            if set(arquivos) | {"manifesto.json"} != set(nomes) or "catalogo.json" not in arquivos:
                raise ValueError("Manifesto não corresponde aos arquivos do backup.")
            return arquivos
    except (zipfile.BadZipFile, RuntimeError) as erro:
        raise ValueError(f"Pacote de backup inválido: {erro}") from erro


def restaurar_backup(arquivo_backup, destino):
    destino = Path(destino)
    if destino.exists() or destino.is_symlink():
        raise ValueError("A restauração exige um diretório de destino que ainda não exista.")
    arquivos = _ler_backup(arquivo_backup)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destino.parent, prefix=".restauracao-") as pasta:
        temporario = Path(pasta)
        for nome, conteudo in arquivos.items():
            gravar_imutavel(temporario / nome, conteudo)
        _validar_base(temporario)
        # Reserva exclusivamente o destino antes de substituir nossa pasta vazia.
        destino.mkdir()
        try:
            os.replace(temporario, destino)
        except OSError:
            destino.rmdir()
            raise
    return destino
