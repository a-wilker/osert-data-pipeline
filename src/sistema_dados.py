"""Atualização e consulta local do sistema de dados de Teresina."""

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
from pathlib import Path, PurePosixPath
import sys
import tempfile

import requests

from .consulta_taxa_desocupacao import coletar_taxa_desocupacao, TABELA, VARIAVEL, TERRITORIO, URL
from .transforma_taxa_desocupacao import transformar_taxa_desocupacao, normalizar_serie
from .arquivos import gravar_imutavel
from .formato_csv import COLUNAS, SIMBOLOS_SIDRA
from .revisoes import comparar_observacoes
from .registro_execucoes import agora_utc, gravar_execucao, iniciar_execucao, ler_execucoes, ler_execucao
from . import populacao_estimada as populacao

INDICADOR = "taxa_desocupacao_teresina"


CONFIGURACOES = {
    INDICADOR: {
        "nome": "Taxa de desocupação de Teresina",
        "tabela": TABELA, "variavel": VARIAVEL, "url": URL,
        "unidade": "%", "periodicidade": "trimestral",
        "coletar": coletar_taxa_desocupacao, "transformar": transformar_taxa_desocupacao,
        "normalizar": normalizar_serie,
    },
    "populacao_estimada_teresina": {
        "nome": "População residente estimada de Teresina",
        "tabela": populacao.TABELA, "variavel": populacao.VARIAVEL, "url": populacao.URL,
        "unidade": "Pessoas", "periodicidade": "anual",
        "coletar": populacao.coletar_populacao_estimada,
        "transformar": populacao.transformar_populacao_estimada,
        "normalizar": populacao.normalizar_serie,
    },
}


def _configuracao(indicador):
    if not isinstance(indicador, str) or indicador not in CONFIGURACOES:
        raise ValueError(f"Indicador desconhecido: {indicador}. Use o comando indicadores.")
    return CONFIGURACOES[indicador]


def _regra_periodo(config):
    trimestral = config["periodicidade"] == "trimestral"
    return {
        "formato": "AAAA0T" if trimestral else "AAAA",
        "padrao": r"[0-9]{4}0[1-4]" if trimestral else r"[0-9]{4}",
        "exemplo": "202401" if trimestral else "2024",
        "ano_minimo": 1, "ano_maximo": 9999,
    }


def consultar_contrato(indicador=INDICADOR):
    """Descreve o contrato suportado sem acessar catálogo, arquivos ou rede."""
    config = _configuracao(indicador)
    trimestral = config["periodicidade"] == "trimestral"
    return {
        "versao_contrato": 1, "indicador": indicador, "nome": config["nome"],
        "fonte": "SIDRA/IBGE", "url_fonte": config["url"],
        "tabela": config["tabela"], "variavel": config["variavel"],
        "territorio": {"nivel": "municipio", "codigo": TERRITORIO, "nome": "Teresina (PI)"},
        "unidade": config["unidade"], "periodicidade": config["periodicidade"],
        "classificacoes": "sem_classificacoes",
        "grao": ["tabela", "variavel", "territorio_codigo", "periodo_codigo"],
        "periodo": _regra_periodo(config),
        "valores": {
            "dominio_numerico": "decimal" if trimestral else "inteiro",
            "minimo": "0", "maximo": "100" if trimestral else None,
            "representacao_saida": "string", "separador_decimal": ".",
            "simbolos_sidra": sorted(SIMBOLOS_SIDRA),
            "valor_numerico_para_simbolos": "",
            "status_permitidos": ["numerico", "simbolo_sidra"],
        },
        "colunas": [
            {
                "nome": coluna, "tipo_json": "string",
                "vazio_permitido": coluna == "valor_numerico" or (coluna == "trimestre" and not trimestral),
            }
            for coluna in COLUNAS
        ],
        "csv": {"codificacao": "utf-8", "separador": ",", "quebra_linha": "LF"},
        "ordenacao": ["periodo_codigo"],
        "periodos_duplicados_permitidos": False,
        "preenche_periodos_ausentes": False,
        "filtros": {
            "ano": {"tipo": "integer", "minimo": 1, "maximo": 9999},
            "inicio_fim": {"inclusivos": True, "aceita_limite_unico": True},
            "combina_ano_com_intervalo": False,
        },
    }


def listar_indicadores(diretorio_dados=Path("data")):
    catalogo = _ler_catalogo(Path(diretorio_dados))
    return [
        {
            "indicador": identificador, "nome": config["nome"],
            "periodicidade": config["periodicidade"], "unidade": config["unidade"],
            "publicado": identificador in catalogo["indicadores"],
        }
        for identificador, config in CONFIGURACOES.items()
    ]


def _ler_catalogo(raiz):
    caminho = raiz / "catalogo.json"
    if not caminho.exists():
        return {"versao": 1, "indicadores": {}}
    catalogo = json.loads(caminho.read_bytes())
    if (
        not isinstance(catalogo, dict)
        or type(catalogo.get("versao")) is not int or catalogo.get("versao") != 1
        or not isinstance(catalogo.get("indicadores"), dict)
    ):
        raise ValueError("Catálogo inválido ou de versão não suportada.")
    return catalogo


def _arquivo_catalogado(raiz, referencia):
    if not isinstance(referencia, dict):
        raise ValueError("Referência de arquivo inválida no catálogo.")
    relativo = referencia.get("caminho")
    if not isinstance(relativo, str) or not relativo:
        raise ValueError("Caminho inválido no catálogo.")
    posix = PurePosixPath(relativo)
    if posix.is_absolute() or posix.as_posix() != relativo or ".." in posix.parts or "\\" in relativo or ":" in relativo:
        raise ValueError("A referência deve usar um caminho relativo normalizado.")
    caminho = (raiz / relativo).resolve()
    if not caminho.is_relative_to(raiz.resolve()):
        raise ValueError("O catálogo aponta para um arquivo fora do diretório de dados.")
    conteudo = caminho.read_bytes()
    if hashlib.sha256(conteudo).hexdigest() != referencia.get("sha256"):
        raise ValueError(f"Arquivo catalogado com hash divergente: {relativo}.")
    return conteudo


def _linhas_catalogadas(raiz, entrada, indicador=INDICADOR):
    config = _configuracao(indicador)
    if not isinstance(entrada, dict):
        raise ValueError("Registro do indicador inválido no catálogo.")
    esperados = {
        "nome": config["nome"], "criterio_versao_atual": "ultima_coleta_validada",
        "fonte": "SIDRA/IBGE", "tabela": config["tabela"], "variavel": config["variavel"],
        "territorio_codigo": TERRITORIO, "territorio_nome": "Teresina (PI)",
        "unidade": config["unidade"], "periodicidade": config["periodicidade"],
        "url_fonte": config["url"], "versao_contrato": 1,
        "classificacoes": "sem_classificacoes",
        "grao": ["tabela", "variavel", "territorio_codigo", "periodo_codigo"],
    }
    for campo, esperado in esperados.items():
        if entrada.get(campo) != esperado:
            raise ValueError(f"Metadado {campo} incompatível com o indicador {indicador}.")

    if type(entrada.get("versao_contrato")) is not int:
        raise ValueError("Versão do contrato deve ser um inteiro.")
    try:
        publicado = entrada.get("publicado_em_utc")
        if not isinstance(publicado, str) or datetime.fromisoformat(publicado).utcoffset() is None:
            raise ValueError
    except ValueError:
        raise ValueError("Horário de publicação inválido; informe uma data ISO com fuso horário.") from None

    for tipo, pasta in (("bruto", "raw"), ("csv", "processed")):
        referencia = entrada.get(tipo)
        if not isinstance(referencia, dict) or not isinstance(referencia.get("caminho"), str):
            raise ValueError("Referência de arquivo inválida no catálogo.")
        if PurePosixPath(referencia["caminho"]).parent.as_posix() != pasta:
            raise ValueError("Referência de arquivo fora do diretório previsto pelo contrato.")
    bruto = _arquivo_catalogado(raiz, entrada.get("bruto"))
    hash_bruto = hashlib.sha256(bruto).hexdigest()
    nome_bruto = Path(entrada["bruto"]["caminho"]).name
    nome_esperado = (
        f"tabela-{config['tabela']}_variavel-{config['variavel']}_territorio-{TERRITORIO}"
        f"_periodo-all_sha256-{hash_bruto}.json"
    )
    if nome_bruto != nome_esperado:
        raise ValueError("Nome do arquivo bruto incompatível com o contrato.")
    normalizadas = config["normalizar"](json.loads(bruto), Path(nome_bruto), hash_bruto)

    conteudo = _arquivo_catalogado(raiz, entrada.get("csv"))
    leitor = csv.DictReader(io.StringIO(conteudo.decode("utf-8"), newline=""), strict=True)
    try:
        if leitor.fieldnames != list(COLUNAS):
            raise ValueError("Colunas do CSV catalogado incompatíveis com o contrato.")
        linhas = list(leitor)
    except csv.Error as erro:
        raise ValueError(f"CSV catalogado inválido: {erro}") from erro

    esperadas = [{coluna: str(linha[coluna]) for coluna in COLUNAS} for linha in normalizadas]
    if linhas != esperadas:
        raise ValueError("O CSV catalogado não corresponde à transformação do arquivo bruto.")
    if type(entrada.get("quantidade_observacoes")) is not int or len(linhas) != entrada["quantidade_observacoes"]:
        raise ValueError("Quantidade de observações incompatível com o catálogo.")
    if entrada.get("periodo_inicial") != linhas[0]["periodo_codigo"] or entrada.get("periodo_final") != linhas[-1]["periodo_codigo"]:
        raise ValueError("Cobertura temporal incompatível com o catálogo.")
    return linhas


def _referencia(raiz, caminho):
    return {
        "caminho": caminho.relative_to(raiz).as_posix(),
        "sha256": hashlib.sha256(caminho.read_bytes()).hexdigest(),
    }


def _publicar_catalogo(raiz, catalogo):
    conteudo = (json.dumps(catalogo, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(dir=raiz, prefix=".catalogo-", suffix=".tmp", delete=False) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, raiz / "catalogo.json")
    finally:
        if temporario is not None and temporario.exists():
            temporario.unlink()


@contextmanager
def _execucao_exclusiva(raiz):
    raiz.mkdir(parents=True, exist_ok=True)
    bloqueio = raiz / ".atualizacao.lock"
    try:
        arquivo = bloqueio.open("x")
    except FileExistsError:
        raise ValueError("Já existe um bloqueio de atualização; confira se outra execução está ativa.") from None
    try:
        with arquivo:
            arquivo.write(str(os.getpid()))
        yield
    finally:
        bloqueio.unlink()


def _atualizar_indicador(raiz, indicador, config, etapa):
    etapa("validacao_anterior")
    catalogo = _ler_catalogo(raiz)
    anterior = catalogo["indicadores"].get(indicador)
    linhas_anteriores = _linhas_catalogadas(raiz, anterior, indicador) if anterior is not None else []

    etapa("coleta")
    bruto = config["coletar"](raiz / "raw")
    etapa("transformacao")
    processado = config["transformar"](bruto, raiz / "processed")
    with processado.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    etapa("validacao_serie")
    periodos = {linha["periodo_codigo"] for linha in linhas}
    perdidos = {linha["periodo_codigo"] for linha in linhas_anteriores} - periodos
    if perdidos:
        raise ValueError("A coleta perdeu períodos já publicados: " + ", ".join(sorted(perdidos)))

    entrada = {
        "nome": config["nome"],
        "fonte": "SIDRA/IBGE", "tabela": config["tabela"], "variavel": config["variavel"],
        "territorio_codigo": TERRITORIO, "territorio_nome": "Teresina (PI)",
        "unidade": config["unidade"], "periodicidade": config["periodicidade"],
        "classificacoes": "sem_classificacoes",
        "grao": ["tabela", "variavel", "territorio_codigo", "periodo_codigo"],
        "url_fonte": config["url"], "versao_contrato": 1,
        "criterio_versao_atual": "ultima_coleta_validada",
        "quantidade_observacoes": len(linhas),
        "periodo_inicial": min(periodos), "periodo_final": max(periodos),
        "bruto": _referencia(raiz, bruto), "csv": _referencia(raiz, processado),
    }
    comparacao = {
        **comparar_observacoes(linhas_anteriores, linhas),
        "bruto_anterior": anterior["bruto"] if anterior is not None else None,
        "bruto_atual": entrada["bruto"],
    }
    if anterior is not None:
        sem_data = {chave: valor for chave, valor in anterior.items() if chave != "publicado_em_utc"}
        if entrada == sem_data:
            return {"alterado": False, "indicador": indicador, "dados": anterior, "comparacao": comparacao}

    entrada["publicado_em_utc"] = datetime.now(timezone.utc).isoformat()
    catalogo["indicadores"][indicador] = entrada
    etapa("publicacao")
    _publicar_catalogo(raiz, catalogo)
    return {"alterado": True, "indicador": indicador, "dados": entrada, "comparacao": comparacao}


def atualizar_dados(diretorio_dados=Path("data"), indicador=INDICADOR):
    """Executa e registra uma atualização sob bloqueio exclusivo."""
    config = _configuracao(indicador)
    raiz = Path(diretorio_dados)
    with _execucao_exclusiva(raiz):
        registro = iniciar_execucao(raiz, indicador)

        def etapa(nome):
            registro["etapa"] = nome
            gravar_execucao(raiz, registro)

        try:
            resultado = _atualizar_indicador(raiz, indicador, config, etapa)
        except Exception as erro:
            registro.update(
                status="falha", finalizado_em_utc=agora_utc(),
                erro={"tipo": type(erro).__name__, "mensagem": str(erro)},
            )
            try:
                gravar_execucao(raiz, registro)
            except OSError as erro_registro:
                erro.add_note(f"Também houve falha ao registrar a execução: {erro_registro}")
            raise

        registro.update(
            status="atualizado" if resultado["alterado"] else "sem_alteracao",
            etapa="concluida", finalizado_em_utc=agora_utc(),
            resultado={
                "quantidade_observacoes": resultado["dados"]["quantidade_observacoes"],
                "bruto": resultado["dados"]["bruto"], "csv": resultado["dados"]["csv"],
                "comparacao": resultado["comparacao"], "publicacao": resultado["dados"],
            },
        )
        resultado["execucao_id"] = registro["id"]
        try:
            gravar_execucao(raiz, registro)
        except OSError as erro:
            # A publicação já terminou. Não reportar falsamente que ela falhou.
            resultado["aviso_registro"] = f"Dados disponíveis, mas o registro final falhou: {erro}"
        return resultado


def atualizar_todos(diretorio_dados=Path("data")):
    resultados = []
    for indicador in CONFIGURACOES:
        try:
            resultado = atualizar_dados(diretorio_dados, indicador)
            resultados.append({"sucesso": True, **resultado})
        except (OSError, ValueError, requests.RequestException) as erro:
            resultados.append({
                "sucesso": False, "indicador": indicador,
                "erro": {"tipo": type(erro).__name__, "mensagem": str(erro)},
            })
    return {"sucesso": all(item["sucesso"] for item in resultados), "resultados": resultados}


def listar_execucoes(diretorio_dados=Path("data"), indicador=None, limite=20):
    if indicador is not None:
        _configuracao(indicador)
    return ler_execucoes(diretorio_dados, indicador, limite)


class ExecucaoNaoEncontrada(ValueError):
    """Não há registro para o identificador solicitado."""


class PublicacaoHistoricaAusente(ValueError):
    """A execução não registrou uma publicação consultável."""


class PublicacaoAusente(ValueError):
    """Indicador conhecido que ainda não possui uma publicação local."""


def consultar_dados(
    diretorio_dados=Path("data"), ano=None, indicador=INDICADOR, *, inicio=None, fim=None, execucao_id=None,
):
    return consultar_publicacao(
        diretorio_dados, ano, indicador, inicio=inicio, fim=fim, execucao_id=execucao_id
    )["dados"]


def consultar_publicacao(
    diretorio_dados=Path("data"), ano=None, indicador=INDICADOR, *, inicio=None, fim=None, execucao_id=None,
):
    """Lê a versão catalogada e aplica filtros inclusivos, sem acessar a API."""
    config = _configuracao(indicador)
    _validar_filtros(config, ano, inicio, fim)
    raiz = Path(diretorio_dados)
    if execucao_id is None:
        catalogo = _ler_catalogo(raiz)
        entrada = catalogo["indicadores"].get(indicador)
        if entrada is None:
            raise PublicacaoAusente("Indicador ainda não publicado; execute o comando atualizar.")
    else:
        try:
            registro = ler_execucao(raiz, execucao_id)
        except FileNotFoundError:
            raise ExecucaoNaoEncontrada("Execução não encontrada no histórico local.") from None
        if registro.get("indicador") != indicador:
            raise PublicacaoHistoricaAusente("A execução não pertence ao indicador solicitado.")
        if registro["status"] not in ("atualizado", "sem_alteracao"):
            raise PublicacaoHistoricaAusente("A execução não terminou com uma publicação válida.")
        resultado = registro.get("resultado")
        if not isinstance(resultado, dict):
            raise ValueError("Resultado de execução inválido.")
        if "publicacao" not in resultado:
            raise PublicacaoHistoricaAusente(
                "Registro antigo sem metadados da publicação; não é possível reproduzir esta execução."
            )
        entrada = resultado["publicacao"]
    linhas = _linhas_catalogadas(raiz, entrada, indicador)
    filtradas = [
        linha for linha in linhas
        if (ano is None or int(linha["ano"]) == ano)
        and (inicio is None or linha["periodo_codigo"] >= inicio)
        and (fim is None or linha["periodo_codigo"] <= fim)
    ]
    return {"metadados": entrada, "dados": filtradas}


def _validar_filtros(config, ano, inicio, fim):
    if ano is not None and (type(ano) is not int or not 1 <= ano <= 9999):
        raise ValueError("O ano deve ser um inteiro entre 1 e 9999.")
    if ano is not None and (inicio is not None or fim is not None):
        raise ValueError("Use ano ou intervalo de períodos, sem combinar os dois.")
    regra = _regra_periodo(config)
    padrao = regra["padrao"]
    for nome, valor in (("inicio", inicio), ("fim", fim)):
        if valor is not None and (
            not isinstance(valor, str) or not re.fullmatch(padrao, valor) or int(valor[:4]) == 0
        ):
            exemplo = regra["exemplo"]
            raise ValueError(f"Período {nome} inválido. Exemplo para este indicador: {exemplo}.")
    if inicio is not None and fim is not None and inicio > fim:
        raise ValueError("O início do intervalo deve ser menor ou igual ao fim.")


def serializar_consulta(linhas, indicador=INDICADOR, *, formato="csv", ano=None, inicio=None, fim=None):
    config = _configuracao(indicador)
    _validar_filtros(config, ano, inicio, fim)
    if formato == "csv":
        buffer = io.StringIO(newline="")
        escritor = csv.DictWriter(buffer, fieldnames=COLUNAS, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(linhas)
        return buffer.getvalue().encode("utf-8")
    if formato == "json":
        resultado = {
            "indicador": indicador, "unidade": config["unidade"],
            "periodicidade": config["periodicidade"],
            "filtros": {"ano": ano, "inicio": inicio, "fim": fim},
            "quantidade_observacoes": len(linhas), "dados": linhas,
        }
        return (json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    raise ValueError("Formato inválido; use csv ou json.")



def serializar_publicacao(publicacao, indicador=INDICADOR, *, formato="csv", execucao_id=None, **filtros):
    conteudo = serializar_consulta(publicacao["dados"], indicador, formato=formato, **filtros)
    if formato == "json":
        resultado = json.loads(conteudo)
        resultado["metadados"] = publicacao["metadados"]
        if execucao_id is not None:
            resultado["execucao_id"] = execucao_id
        return (json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return conteudo


def exportar_dados(
    caminho_saida, diretorio_dados=Path("data"), ano=None, indicador=INDICADOR,
    *, inicio=None, fim=None, formato="csv", execucao_id=None,
):
    raiz = Path(diretorio_dados).resolve()
    destino = Path(caminho_saida)
    resolvido = destino.resolve()
    protegidos = ("raw", "processed", "execucoes")
    if resolvido in (raiz / "catalogo.json", raiz / ".atualizacao.lock") or any(
        resolvido.is_relative_to(raiz / pasta) for pasta in protegidos
    ):
        raise ValueError("A exportação não pode escrever nos arquivos internos do sistema.")
    publicacao = consultar_publicacao(
        diretorio_dados, ano, indicador, inicio=inicio, fim=fim, execucao_id=execucao_id,
    )
    conteudo = serializar_publicacao(
        publicacao, indicador, formato=formato, ano=ano, inicio=inicio, fim=fim, execucao_id=execucao_id,
    )
    try:
        return gravar_imutavel(destino, conteudo)
    except ValueError:
        raise ValueError(f"Destino já existe com outro conteúdo: {destino}.") from None



def _periodos_ausentes(linhas, periodicidade):
    presentes = {linha["periodo_codigo"] for linha in linhas}
    primeiro, ultimo = min(presentes), max(presentes)
    candidatos = []
    for ano in range(int(primeiro[:4]), int(ultimo[:4]) + 1):
        if periodicidade == "anual":
            candidatos.append(f"{ano:04d}")
        else:
            candidatos.extend(f"{ano:04d}0{trimestre}" for trimestre in range(1, 5))
    return [periodo for periodo in candidatos if primeiro <= periodo <= ultimo and periodo not in presentes]



def verificar_publicacoes_registradas(raiz, registros):
    """Confere as publicações históricas registradas, sem repetir arquivos da mesma publicação."""
    resultado = {"publicacoes_verificadas": 0, "execucoes_sem_metadados": 0, "erros": []}
    conferidas = set()
    for registro in registros:
        if registro["status"] not in ("atualizado", "sem_alteracao"):
            continue
        try:
            dados = registro.get("resultado")
            if not isinstance(dados, dict):
                raise ValueError("Resultado de execução inválido.")
            if "publicacao" not in dados:
                resultado["execucoes_sem_metadados"] += 1
                continue
            indicador = registro.get("indicador")
            _configuracao(indicador)
            entrada = dados["publicacao"]
            chave = (indicador, json.dumps(entrada, sort_keys=True))
            if chave not in conferidas:
                _linhas_catalogadas(Path(raiz), entrada, indicador)
                conferidas.add(chave)
                resultado["publicacoes_verificadas"] += 1
        except (ValueError, OSError) as erro:
            resultado["erros"].append({"execucao_id": registro["id"], "mensagem": str(erro)})
    return resultado



def _estado_atualizacao(registros, indicador):
    tentativas = [r for r in registros if r.get("indicador") == indicador]
    concluidas = [r for r in tentativas if r["status"] in ("atualizado", "sem_alteracao")]
    pendentes = [r["id"] for r in tentativas if r["status"] == "em_execucao"]

    def resumo(registro):
        return {campo: registro.get(campo) for campo in (
            "id", "status", "etapa", "iniciado_em_utc", "finalizado_em_utc",
        )}

    ultima = tentativas[0] if tentativas else None
    if ultima is None:
        estado = "sem_registro"
    elif ultima["status"] == "falha":
        estado = "ultima_tentativa_falhou"
    elif ultima["status"] == "em_execucao":
        estado = "execucao_sem_conclusao"
    else:
        estado = "ultima_tentativa_concluida"
    return {
        "estado": estado,
        "ultima_tentativa": resumo(ultima) if ultima else None,
        "ultima_concluida": resumo(concluidas[0]) if concluidas else None,
        "execucoes_sem_conclusao": pendentes,
        "requer_atencao": estado != "ultima_tentativa_concluida" or bool(pendentes),
    }


def verificar_dados(diretorio_dados=Path("data"), indicador=None, *, incluir_historico=False):
    """Confere dados publicados e relata lacunas sem alterar arquivos nem consultar a rede."""
    if indicador is not None:
        _configuracao(indicador)
    raiz = Path(diretorio_dados)
    relatorio = {"saudavel": True, "atencao_operacional": None, "indicadores": [], "avisos": []}
    try:
        catalogo = _ler_catalogo(raiz)
    except (ValueError, OSError) as erro:
        return {**relatorio, "saudavel": False, "erro_catalogo": str(erro)}
    desconhecidos = sorted(set(catalogo["indicadores"]) - set(CONFIGURACOES))
    if desconhecidos:
        relatorio["saudavel"] = False
        relatorio["avisos"].append("Indicadores desconhecidos no catálogo: " + ", ".join(desconhecidos))

    for identificador in ([indicador] if indicador else CONFIGURACOES):
        entrada = catalogo["indicadores"].get(identificador)
        if entrada is None:
            item = {"indicador": identificador, "status": "nao_publicado"}
        else:
            try:
                linhas = _linhas_catalogadas(raiz, entrada, identificador)
                lacunas = _periodos_ausentes(linhas, CONFIGURACOES[identificador]["periodicidade"])
                item = {
                    "indicador": identificador, "status": "ok",
                    "quantidade_observacoes": len(linhas),
                    "periodo_inicial": linhas[0]["periodo_codigo"],
                    "periodo_final": linhas[-1]["periodo_codigo"],
                    "quantidade_simbolos": sum(linha["status_valor"] == "simbolo_sidra" for linha in linhas),
                    "periodos_ausentes_entre_extremos": lacunas,
                }
            except (ValueError, OSError) as erro:
                item = {"indicador": identificador, "status": "erro", "mensagem": str(erro)}
        item["atualizacao"] = None
        relatorio["indicadores"].append(item)
        if item["status"] != "ok":
            relatorio["saudavel"] = False

    bloqueado = (raiz / ".atualizacao.lock").exists()
    if bloqueado:
        relatorio["avisos"].append("Existe bloqueio de atualização; confira se há uma execução ativa.")
    try:
        quantidade = len(list((raiz / "execucoes").glob("*.json")))
        registros = ler_execucoes(raiz, indicador, max(1, quantidade))
        relatorio["atencao_operacional"] = bloqueado
        for item in relatorio["indicadores"]:
            estado = _estado_atualizacao(registros, item["indicador"])
            item["atualizacao"] = estado
            relatorio["atencao_operacional"] |= estado["requer_atencao"]
            if estado["estado"] == "ultima_tentativa_falhou":
                relatorio["avisos"].append(
                    "Última atualização falhou para " + item["indicador"]
                    + "; confira o histórico de execuções."
                )
        if incluir_historico:
            historico = verificar_publicacoes_registradas(raiz, registros)
            relatorio["historico"] = historico
            if historico["erros"]:
                relatorio["saudavel"] = False
        pendentes = [r["id"] for r in registros if r["status"] == "em_execucao"]
        if pendentes:
            relatorio["avisos"].append(
                "Execuções sem registro final (ativas, interrompidas ou com falha de registro): " + ", ".join(pendentes)
            )
    except (ValueError, OSError) as erro:
        relatorio["saudavel"] = False
        relatorio["erro_historico"] = str(erro)
    return relatorio


def main():
    parser = argparse.ArgumentParser(description="Sistema de dados de Teresina: atualização e consulta local.")
    parser.add_argument("--diretorio-dados", type=Path, default=Path("data"))
    comandos = parser.add_subparsers(dest="comando", required=True)
    comandos.add_parser("indicadores", help="Lista os indicadores disponíveis, sem acessar a rede.")
    contrato = comandos.add_parser("contrato", help="Descreve o contrato do indicador sem precisar de dados publicados.")
    contrato.add_argument("--indicador", choices=CONFIGURACOES, default=INDICADOR)
    atualizacao = comandos.add_parser("atualizar", help="Coleta, transforma e publica o indicador no catálogo.")
    consulta = comandos.add_parser("consultar", help="Consulta a versão publicada sem internet.")
    selecao = atualizacao.add_mutually_exclusive_group()
    selecao.add_argument("--indicador", choices=CONFIGURACOES, default=INDICADOR)
    selecao.add_argument("--todos", action="store_true")
    consulta.add_argument("--indicador", choices=CONFIGURACOES, default=INDICADOR)
    historico = comandos.add_parser("execucoes", help="Consulta o histórico local de atualizações.")
    historico.add_argument("--indicador", choices=CONFIGURACOES)
    historico.add_argument("--limite", type=int, default=20)
    verificacao = comandos.add_parser("verificar", help="Confere integridade e cobertura dos dados locais.")
    verificacao.add_argument("--indicador", choices=CONFIGURACOES)
    verificacao.add_argument("--historico", action="store_true", help="Confere também as publicações registradas no histórico.")
    backup = comandos.add_parser("backup", help="Cria pacote verificável dos dados e do histórico.")
    backup.add_argument("--saida", required=True, type=Path)
    restauracao = comandos.add_parser("restaurar", help="Restaura um backup em diretório novo.")
    restauracao.add_argument("arquivo", type=Path)
    restauracao.add_argument("--destino", required=True, type=Path)
    consulta.add_argument("--execucao", dest="execucao_id", help="Consulta a publicação registrada nesta execução.")
    consulta.add_argument("--ano", type=int)
    consulta.add_argument("--inicio")
    consulta.add_argument("--fim")
    consulta.add_argument("--formato", choices=("csv", "json"), default="csv")
    consulta.add_argument("--saida", type=Path)
    args = parser.parse_args()
    try:
        if args.comando == "indicadores":
            print(json.dumps(listar_indicadores(args.diretorio_dados), ensure_ascii=False, indent=2))
        elif args.comando == "contrato":
            print(json.dumps(consultar_contrato(args.indicador), ensure_ascii=False, indent=2))
        elif args.comando == "backup":
            from .backup_dados import criar_backup
            print(f"Backup disponível em: {criar_backup(args.saida, args.diretorio_dados)}")
        elif args.comando == "restaurar":
            from .backup_dados import restaurar_backup
            print(f"Dados restaurados em: {restaurar_backup(args.arquivo, args.destino)}")
        elif args.comando == "verificar":
            relatorio = verificar_dados(args.diretorio_dados, args.indicador, incluir_historico=args.historico)
            print(json.dumps(relatorio, ensure_ascii=False, indent=2))
            if not relatorio["saudavel"]:
                parser.exit(1)
        elif args.comando == "execucoes":
            print(json.dumps(listar_execucoes(args.diretorio_dados, args.indicador, args.limite), ensure_ascii=False, indent=2))
        elif args.comando == "atualizar" and args.todos:
            resultado = atualizar_todos(args.diretorio_dados)
            print(json.dumps(resultado, ensure_ascii=False, indent=2))
            if not resultado["sucesso"]:
                parser.exit(1)
        elif args.comando == "atualizar":
            resultado = atualizar_dados(args.diretorio_dados, args.indicador)
            estado = "Atualizado" if resultado["alterado"] else "Sem alteração"
            print(f"{estado} — {args.indicador}: {resultado['dados']['quantidade_observacoes']} observações disponíveis.")
            print(f"Catálogo: {args.diretorio_dados / 'catalogo.json'}")
            print(f"Execução: {resultado['execucao_id']}")
            contagens = resultado["comparacao"]["quantidades"]
            print(
                f"Observações: {contagens['novas']} novas, "
                f"{contagens['alteradas']} alteradas, {contagens['inalteradas']} inalteradas."
            )
            if "aviso_registro" in resultado:
                print(resultado["aviso_registro"], file=sys.stderr)
        else:
            filtros = {"ano": args.ano, "inicio": args.inicio, "fim": args.fim, "execucao_id": args.execucao_id}
            if args.saida:
                destino = exportar_dados(
                    args.saida, args.diretorio_dados, indicador=args.indicador,
                    formato=args.formato, **filtros,
                )
                print(f"Exportação disponível em: {destino}")
            else:
                publicacao = consultar_publicacao(args.diretorio_dados, indicador=args.indicador, **filtros)
                conteudo = serializar_publicacao(publicacao, args.indicador, formato=args.formato, **filtros)
                sys.stdout.write(conteudo.decode("utf-8"))
    except (OSError, ValueError, requests.RequestException) as erro:
        parser.exit(1, f"Erro: {erro}\n")


if __name__ == "__main__":
    main()
