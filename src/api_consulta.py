"""API HTTP local e somente de leitura dos indicadores publicados."""

import argparse
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from .sistema_dados import (
    CONFIGURACOES, PublicacaoAusente, _validar_filtros,
    consultar_publicacao, consultar_contrato, listar_indicadores, listar_execucoes, serializar_publicacao, verificar_dados,
    ExecucaoNaoEncontrada, PublicacaoHistoricaAusente,
)

from .registro_execucoes import validar_id_execucao


class ErroConsulta(ValueError):
    def __init__(self, status, codigo, mensagem):
        self.status = status
        self.codigo = codigo
        super().__init__(mensagem)



@dataclass(frozen=True)
class RespostaCSV:
    conteudo: bytes
    indicador: str
    sha256_bruto: str
    sha256_csv_publicado: str
    execucao_id: str | None = None


def _parametros(query, permitidos):
    try:
        valores = parse_qs(
            query, keep_blank_values=True, strict_parsing=True, max_num_fields=4,
            encoding="utf-8", errors="strict",
        )
    except (ValueError, UnicodeError):
        raise ErroConsulta(400, "parametros_invalidos", "Parâmetros de consulta inválidos.") from None
    if any(chave not in permitidos or len(valor) != 1 or not valor[0] for chave, valor in valores.items()):
        raise ErroConsulta(400, "parametros_invalidos", "Use somente os parâmetros permitidos, sem repetições ou valores vazios.")
    return {chave: valor[0] for chave, valor in valores.items()}


def _saude_publica(relatorio):
    # Diagnósticos internos podem conter caminhos absolutos do servidor.
    for campo in ("erro_catalogo", "erro_historico"):
        if campo in relatorio:
            relatorio[campo] = "Falha de integridade; execute verificar na linha de comando."
    for item in relatorio["indicadores"]:
        if "mensagem" in item:
            item["mensagem"] = "Publicação inconsistente; execute verificar na linha de comando."
    return relatorio



def _resumo_execucao(registro):
    campos = ("id", "iniciado_em_utc", "finalizado_em_utc", "status", "etapa")
    resumo = {campo: registro.get(campo) for campo in campos}
    resultado = registro.get("resultado")
    resumo["publicacao_registrada"] = (
        registro["status"] in ("atualizado", "sem_alteracao")
        and isinstance(resultado, dict) and isinstance(resultado.get("publicacao"), dict)
    )
    if isinstance(resultado, dict):
        comparacao = resultado.get("comparacao")
        if isinstance(comparacao, dict):
            resumo["comparacao"] = {
                chave: comparacao.get(chave)
                for chave in ("quantidades", "periodos_novos", "periodos_removidos", "observacoes_alteradas")
            }
    # Mensagens internas de falha e caminhos de arquivos ficam restritos ao terminal.
    return resumo


def consultar_rota(alvo, raiz):
    try:
        url = urlsplit(alvo)
    except ValueError:
        raise ErroConsulta(400, "requisicao_invalida", "Endereço de consulta inválido.") from None
    if url.scheme or url.netloc or url.fragment:
        raise ErroConsulta(400, "requisicao_invalida", "Use um caminho local sem fragmento.")
    if url.path == "/indicadores":
        _parametros(url.query, set())
        return 200, {"indicadores": listar_indicadores(raiz)}
    if url.path == "/saude":
        _parametros(url.query, set())
        relatorio = _saude_publica(verificar_dados(raiz))
        return (200 if relatorio["saudavel"] else 503), relatorio
    rota = re.fullmatch(r"/indicadores/([a-z0-9_]+)/(dados|dados\.csv|metadados|execucoes|contrato)", url.path)
    if not rota:
        raise ErroConsulta(404, "rota_desconhecida", "Rota não encontrada.")
    indicador, recurso = rota.groups()
    if indicador not in CONFIGURACOES:
        raise ErroConsulta(404, "indicador_desconhecido", "Indicador não encontrado.")
    if recurso == "contrato":
        _parametros(url.query, set())
        return 200, consultar_contrato(indicador)
    if recurso == "execucoes":
        parametros = _parametros(url.query, {"limite"})
        valor = parametros.get("limite", "20")
        if not re.fullmatch(r"[0-9]{1,3}", valor) or not 1 <= int(valor) <= 100:
            raise ErroConsulta(400, "parametros_invalidos", "O limite deve ser um inteiro entre 1 e 100.")
        registros = listar_execucoes(raiz, indicador, int(valor))
        return 200, {
            "indicador": indicador, "limite": int(valor),
            "execucoes": [_resumo_execucao(registro) for registro in registros],
        }
    filtros = _parametros(url.query, {"ano", "inicio", "fim", "execucao"} if recurso in ("dados", "dados.csv") else {"execucao"})
    execucao_id = filtros.pop("execucao", None)
    if execucao_id is not None:
        try:
            validar_id_execucao(execucao_id)
        except ValueError as erro:
            raise ErroConsulta(400, "parametros_invalidos", str(erro)) from None
    if "ano" in filtros:
        if not re.fullmatch(r"[0-9]{1,4}", filtros["ano"]):
            raise ErroConsulta(400, "parametros_invalidos", "O ano deve ser um inteiro entre 1 e 9999.")
        filtros["ano"] = int(filtros["ano"])
    try:
        _validar_filtros(CONFIGURACOES[indicador], filtros.get("ano"), filtros.get("inicio"), filtros.get("fim"))
    except ValueError as erro:
        raise ErroConsulta(400, "parametros_invalidos", str(erro)) from None
    publicacao = consultar_publicacao(raiz, indicador=indicador, execucao_id=execucao_id, **filtros)
    if recurso == "metadados":
        resultado = {"indicador": indicador, **publicacao["metadados"]}
        if execucao_id is not None:
            resultado["execucao_id"] = execucao_id
        return 200, resultado
    if recurso == "dados.csv":
        return 200, RespostaCSV(
            conteudo=serializar_publicacao(publicacao, indicador, formato="csv", **filtros),
            indicador=indicador,
            sha256_bruto=publicacao["metadados"]["bruto"]["sha256"],
            sha256_csv_publicado=publicacao["metadados"]["csv"]["sha256"],
            execucao_id=execucao_id,
        )
    resultado = json.loads(serializar_publicacao(
        publicacao, indicador, formato="json", execucao_id=execucao_id, **filtros,
    ))
    return 200, resultado


class ServidorConsulta(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, diretorio_dados=Path("data"), porta=8000):
        self.diretorio_dados = Path(diretorio_dados).resolve()
        super().__init__(("127.0.0.1", porta), ManipuladorConsulta)


class ManipuladorConsulta(BaseHTTPRequestHandler):
    server_version = "OsertConsulta/1"
    sys_version = ""

    def log_message(self, formato, *argumentos):
        # Evita registrar consultas e dados enviados pelo cliente.
        pass

    def _responder(self, status, corpo, *, permitir=False):
        csv = isinstance(corpo, RespostaCSV)
        conteudo = corpo.conteudo if csv else (
            json.dumps(corpo, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/csv; charset=utf-8" if csv else "application/json; charset=utf-8")
        if csv:
            sha256 = hashlib.sha256(conteudo).hexdigest()
            nome = f"{corpo.indicador}-{sha256}.csv"
            self.send_header("Content-Disposition", f'attachment; filename="{nome}"')
            self.send_header("X-SHA256-Conteudo", sha256)
            self.send_header("X-SHA256-Bruto", corpo.sha256_bruto)
            self.send_header("X-SHA256-CSV-Publicado", corpo.sha256_csv_publicado)
            if corpo.execucao_id is not None:
                self.send_header("X-Execucao-Id", corpo.execucao_id)
        self.send_header("Content-Length", str(len(conteudo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if permitir:
            self.send_header("Allow", "GET")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(conteudo)

    def do_GET(self):
        try:
            status, corpo = consultar_rota(self.path, self.server.diretorio_dados)
        except ErroConsulta as erro:
            status, corpo = erro.status, {"erro": {"codigo": erro.codigo, "mensagem": str(erro)}}
        except ExecucaoNaoEncontrada:
            status, corpo = 404, {"erro": {
                "codigo": "execucao_desconhecida", "mensagem": "Execução não encontrada no histórico local.",
            }}
        except PublicacaoHistoricaAusente:
            status, corpo = 409, {"erro": {
                "codigo": "publicacao_historica_ausente", "mensagem": "Esta execução não tem publicação consultável para o indicador.",
            }}
        except PublicacaoAusente:
            status, corpo = 409, {"erro": {
                "codigo": "publicacao_ausente", "mensagem": "Indicador ainda não publicado; execute atualizar na linha de comando.",
            }}
        except (ValueError, OSError):
            status, corpo = 503, {"erro": {
                "codigo": "base_inconsistente", "mensagem": "Base indisponível ou inconsistente; execute verificar na linha de comando.",
            }}
        self._responder(status, corpo)

    def _metodo_nao_permitido(self):
        self.close_connection = True
        self._responder(405, {"erro": {
            "codigo": "metodo_nao_permitido", "mensagem": "Esta API aceita somente GET.",
        }}, permitir=True)

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = do_TRACE = do_CONNECT = _metodo_nao_permitido


def main():
    parser = argparse.ArgumentParser(description="Consulta HTTP local dos indicadores, somente leitura.")
    parser.add_argument("--diretorio-dados", type=Path, default=Path("data"))
    parser.add_argument("--porta", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.porta <= 65535:
        parser.error("A porta deve estar entre 1 e 65535.")
    try:
        with ServidorConsulta(args.diretorio_dados, args.porta) as servidor:
            print(f"API de consulta em http://127.0.0.1:{servidor.server_port} (Ctrl+C para encerrar).", flush=True)
            servidor.serve_forever()
    except KeyboardInterrupt:
        return 0
    except OSError as erro:
        parser.exit(1, f"Não foi possível iniciar o serviço: {erro}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
