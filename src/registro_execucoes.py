"""Registros locais de execução, separados das versões dos dados."""

from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import tempfile
from uuid import uuid4


def agora_utc():
    return datetime.now(timezone.utc).isoformat()


def gravar_execucao(raiz, registro):
    pasta = Path(raiz) / "execucoes"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{registro['id']}.json"
    conteudo = (json.dumps(registro, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(dir=pasta, prefix=".execucao-", suffix=".tmp", delete=False) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


def iniciar_execucao(raiz, indicador):
    registro = {
        "versao": 1, "id": uuid4().hex, "indicador": indicador,
        "iniciado_em_utc": agora_utc(), "finalizado_em_utc": None,
        "status": "em_execucao", "etapa": "preparacao",
    }
    gravar_execucao(raiz, registro)
    return registro


def ler_execucoes(raiz, indicador=None, limite=20):
    if type(limite) is not int or limite < 1:
        raise ValueError("O limite de execuções deve ser um inteiro positivo.")
    registros = []
    for caminho in (Path(raiz) / "execucoes").glob("*.json"):
        registro = ler_execucao(raiz, caminho.stem)
        if indicador is None or registro.get("indicador") == indicador:
            registros.append(registro)
    registros.sort(key=lambda item: (_instante(item["iniciado_em_utc"]), item["id"]), reverse=True)
    return registros[:limite]



def _instante(valor):
    try:
        if not isinstance(valor, str):
            raise ValueError
        instante = datetime.fromisoformat(valor)
        if instante.utcoffset() is None:
            raise ValueError
        return instante.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("Horário de execução inválido; informe uma data ISO com fuso horário.") from None


def validar_id_execucao(identificador):
    if not isinstance(identificador, str) or not re.fullmatch(r"[0-9a-f]{32}", identificador):
        raise ValueError("Identificador de execução inválido; use os 32 caracteres exibidos no histórico.")


def ler_execucao(raiz, identificador):
    validar_id_execucao(identificador)
    raiz = Path(raiz).resolve()
    caminho = raiz / "execucoes" / f"{identificador}.json"
    if not caminho.resolve().is_relative_to(raiz):
        raise ValueError("Registro de execução fora do diretório de dados.")
    registro = json.loads(caminho.read_bytes())
    if (
        not isinstance(registro, dict) or registro.get("versao") != 1
        or registro.get("id") != identificador
        or not isinstance(registro.get("iniciado_em_utc"), str)
        or registro.get("status") not in ("em_execucao", "atualizado", "sem_alteracao", "falha")
    ):
        raise ValueError("Registro de execução inválido.")
    inicio = _instante(registro["iniciado_em_utc"])
    if registro["status"] != "em_execucao" and registro.get("finalizado_em_utc") is None:
        raise ValueError("Horário final ausente em execução concluída.")
    if registro.get("finalizado_em_utc") is not None:
        if _instante(registro["finalizado_em_utc"]) < inicio:
            raise ValueError("Horário final da execução é anterior ao início.")
    return registro
