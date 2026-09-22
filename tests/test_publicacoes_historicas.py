import json
import subprocess
import sys

from tests.apoio import PublicacaoTestCase, POPULACAO, DESOCUPACAO
from src.backup_dados import criar_backup, restaurar_backup
from src.sistema_dados import (
    atualizar_dados, consultar_dados, consultar_publicacao, exportar_dados,
    ExecucaoNaoEncontrada, PublicacaoHistoricaAusente,
)


class PublicacoesHistoricasTest(PublicacaoTestCase):
    def setUp(self):
        super().setUp()
        self.primeira = atualizar_dados(self.raiz, POPULACAO)
        self.id = self.primeira["execucao_id"]
        self.series["6579"][-1]["V"] = "910000"
        self.segunda = atualizar_dados(self.raiz, POPULACAO)

    def test_reproduz_publicacao_anterior_com_filtro_e_sem_rede(self):
        self.rede.reset_mock()
        self.rede.side_effect = AssertionError("Histórico deve ser offline")
        antes = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.raiz.rglob("*") if p.is_file()}
        antiga = consultar_publicacao(self.raiz, 2026, POPULACAO, execucao_id=self.id)
        atual = consultar_dados(self.raiz, 2026, POPULACAO)
        self.assertEqual(antiga["dados"][0]["valor_numerico"], "900000")
        self.assertEqual(atual[0]["valor_numerico"], "910000")
        self.assertEqual(antiga["metadados"], self.primeira["dados"])
        depois = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.raiz.rglob("*") if p.is_file()}
        self.assertEqual(antes, depois)
        self.rede.assert_not_called()

    def test_json_exportado_tem_versao_mesmo_com_resultado_vazio(self):
        destino = self.raiz / "exports" / "historico.json"
        exportar_dados(destino, self.raiz, 2000, POPULACAO, formato="json", execucao_id=self.id)
        resultado = json.loads(destino.read_bytes())
        self.assertEqual(resultado["dados"], [])
        self.assertEqual(resultado["metadados"], self.primeira["dados"])
        self.assertEqual(resultado["execucao_id"], self.id)

    def test_execucao_ausente_e_id_invalido(self):
        with self.assertRaises(ExecucaoNaoEncontrada):
            consultar_dados(self.raiz, indicador=POPULACAO, execucao_id="0" * 32)
        for valor in ("../catalogo", "", "a" * 33, "x" * 32, 123):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                consultar_dados(self.raiz, indicador=POPULACAO, execucao_id=valor)

    def test_nao_troca_indicador_nem_faz_fallback_para_atual(self):
        with self.assertRaises(PublicacaoHistoricaAusente):
            consultar_dados(self.raiz, indicador=DESOCUPACAO, execucao_id=self.id)
        arquivo = self.raiz / "execucoes" / f"{self.id}.json"
        registro = json.loads(arquivo.read_bytes())
        del registro["resultado"]["publicacao"]
        arquivo.write_text(json.dumps(registro))
        with self.assertRaisesRegex(PublicacaoHistoricaAusente, "Registro antigo"):
            consultar_dados(self.raiz, indicador=POPULACAO, execucao_id=self.id)
        self.assertEqual(consultar_dados(self.raiz, 2026, POPULACAO)[0]["valor_numerico"], "910000")

    def test_execucao_sem_sucesso_nao_serve_publicacao(self):
        arquivo = self.raiz / "execucoes" / f"{self.id}.json"
        registro = json.loads(arquivo.read_bytes())
        for status in ("em_execucao", "falha"):
            registro["status"] = status
            arquivo.write_text(json.dumps(registro))
            with self.subTest(status=status), self.assertRaises(PublicacaoHistoricaAusente):
                consultar_dados(self.raiz, indicador=POPULACAO, execucao_id=self.id)

    def test_corrupcao_em_versao_antiga_e_detectada(self):
        arquivo = self.raiz / self.primeira["dados"]["csv"]["caminho"]
        arquivo.write_text("corrompido")
        with self.assertRaisesRegex(ValueError, "hash divergente"):
            consultar_dados(self.raiz, indicador=POPULACAO, execucao_id=self.id)
        self.assertEqual(consultar_dados(self.raiz, 2026, POPULACAO)[0]["valor_numerico"], "910000")

    def test_catalogo_atual_nao_e_usado_na_consulta_historica(self):
        (self.raiz / "catalogo.json").write_text("{")
        antiga = consultar_dados(self.raiz, 2026, POPULACAO, execucao_id=self.id)
        self.assertEqual(antiga[0]["valor_numerico"], "900000")

    def test_backup_restaurado_preserva_consulta_historica(self):
        backup = criar_backup(self.raiz.parent / "copia.zip", self.raiz)
        destino = restaurar_backup(backup, self.raiz.parent / "restaurada")
        linhas = consultar_dados(destino, 2026, POPULACAO, execucao_id=self.id)
        self.assertEqual(linhas[0]["valor_numerico"], "900000")

    def test_comando_consultar_historico(self):
        resultado = subprocess.run([
            sys.executable, "-m", "src.sistema_dados", "--diretorio-dados", str(self.raiz),
            "consultar", "--indicador", POPULACAO, "--execucao", self.id,
            "--ano", "2026", "--formato", "json",
        ], capture_output=True, text=True, timeout=10)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        corpo = json.loads(resultado.stdout)
        self.assertEqual(corpo["dados"][0]["valor_numerico"], "900000")
        self.assertEqual(corpo["execucao_id"], self.id)
        self.assertEqual(corpo["metadados"], self.primeira["dados"])

    def test_verificacao_historica_detecta_corrupcao_que_nao_afeta_atual(self):
        from src.sistema_dados import verificar_dados
        arquivo = self.raiz / self.primeira["dados"]["csv"]["caminho"]
        arquivo.write_text("corrompido")
        self.assertTrue(verificar_dados(self.raiz, POPULACAO)["saudavel"])
        relatorio = verificar_dados(self.raiz, POPULACAO, incluir_historico=True)
        self.assertFalse(relatorio["saudavel"])
        self.assertEqual(relatorio["historico"]["erros"][0]["execucao_id"], self.id)
        destino = self.raiz.parent / "nao_criar.zip"
        with self.assertRaisesRegex(ValueError, "histórica inválida"):
            criar_backup(destino, self.raiz)
        self.assertFalse(destino.exists())

    def test_verificacao_historica_conta_publicacoes_distintas_e_legado(self):
        from src.sistema_dados import verificar_dados
        atualizar_dados(self.raiz, POPULACAO)
        relatorio = verificar_dados(self.raiz, POPULACAO, incluir_historico=True)
        self.assertTrue(relatorio["saudavel"])
        self.assertEqual(relatorio["historico"]["publicacoes_verificadas"], 2)
        arquivo = self.raiz / "execucoes" / f"{self.id}.json"
        registro = json.loads(arquivo.read_bytes())
        del registro["resultado"]["publicacao"]
        arquivo.write_text(json.dumps(registro))
        relatorio = verificar_dados(self.raiz, POPULACAO, incluir_historico=True)
        self.assertTrue(relatorio["saudavel"])
        self.assertEqual(relatorio["historico"]["execucoes_sem_metadados"], 1)
        self.assertEqual(relatorio["historico"]["publicacoes_verificadas"], 1)

    def test_historico_rejeita_referencia_absoluta_mesmo_dentro_da_base(self):
        arquivo = self.raiz / "execucoes" / f"{self.id}.json"
        registro = json.loads(arquivo.read_bytes())
        referencia = registro["resultado"]["publicacao"]["bruto"]
        referencia["caminho"] = str(self.raiz / referencia["caminho"])
        arquivo.write_text(json.dumps(registro))
        with self.assertRaises(ValueError):
            consultar_dados(self.raiz, indicador=POPULACAO, execucao_id=self.id)

    def test_restauracao_confere_historico_apesar_de_manifesto_consistente(self):
        import hashlib
        import zipfile
        pacote = criar_backup(self.raiz.parent / "bom.zip", self.raiz)
        with zipfile.ZipFile(pacote) as entrada:
            arquivos = {nome: entrada.read(nome) for nome in entrada.namelist()}
        nome_csv = self.primeira["dados"]["csv"]["caminho"]
        arquivos[nome_csv] = b"historico corrompido"
        manifesto = json.loads(arquivos["manifesto.json"])
        for item in manifesto["arquivos"]:
            conteudo = arquivos[item["caminho"]]
            item["sha256"] = hashlib.sha256(conteudo).hexdigest()
            item["tamanho"] = len(conteudo)
        arquivos["manifesto.json"] = json.dumps(manifesto).encode()
        modificado = self.raiz.parent / "modificado.zip"
        with zipfile.ZipFile(modificado, "w") as saida:
            for nome, conteudo in arquivos.items():
                saida.writestr(nome, conteudo)
        destino = self.raiz.parent / "nao_restaurar"
        with self.assertRaisesRegex(ValueError, "histórica inválida"):
            restaurar_backup(modificado, destino)
        self.assertFalse(destino.exists())
