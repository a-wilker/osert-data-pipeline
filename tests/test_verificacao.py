import hashlib
import json
from unittest.mock import patch

from tests.apoio import PublicacaoTestCase, DESOCUPACAO, POPULACAO
from src.sistema_dados import consultar_dados, verificar_dados


class VerificacaoTest(PublicacaoTestCase):
    def setUp(self):
        super().setUp()
        self.publicar_ambos()
        self.rede.reset_mock()
        self.rede.side_effect = AssertionError("Verificação deve ser offline.")
        self.catalogo = self.raiz / "catalogo.json"

    def test_verifica_integridade_e_informa_lacunas_sem_preencher(self):
        relatorio = verificar_dados(self.raiz)
        self.assertTrue(relatorio["saudavel"])
        por_indicador = {item["indicador"]: item for item in relatorio["indicadores"]}
        self.assertEqual(por_indicador[POPULACAO]["periodos_ausentes_entre_extremos"], ["2022", "2023", "2025"])
        self.assertEqual(por_indicador[DESOCUPACAO]["periodos_ausentes_entre_extremos"], [])
        self.rede.assert_not_called()

    def test_csv_alterado_e_hash_recalculado_nao_enganam_verificacao(self):
        catalogo = json.loads(self.catalogo.read_bytes())
        entrada = catalogo["indicadores"][DESOCUPACAO]
        caminho = self.raiz / entrada["csv"]["caminho"]
        conteudo = caminho.read_bytes().replace(b"7.9", b"9.9")
        caminho.write_bytes(conteudo)
        entrada["csv"]["sha256"] = hashlib.sha256(conteudo).hexdigest()
        self.catalogo.write_text(json.dumps(catalogo))
        relatorio = verificar_dados(self.raiz, DESOCUPACAO)
        self.assertFalse(relatorio["saudavel"])
        self.assertIn("não corresponde", relatorio["indicadores"][0]["mensagem"])
        with self.assertRaisesRegex(ValueError, "não corresponde"):
            consultar_dados(self.raiz)

    def test_referencias_de_outro_indicador_sao_detectadas(self):
        catalogo = json.loads(self.catalogo.read_bytes())
        entrada = catalogo["indicadores"][DESOCUPACAO]
        outra = catalogo["indicadores"][POPULACAO]
        entrada["bruto"] = outra["bruto"]
        entrada["csv"] = outra["csv"]
        self.catalogo.write_text(json.dumps(catalogo))
        self.assertFalse(verificar_dados(self.raiz, DESOCUPACAO)["saudavel"])
        self.assertTrue(verificar_dados(self.raiz, POPULACAO)["saudavel"])

    def test_metadados_e_cobertura_divergentes_sao_detectados(self):
        original = self.catalogo.read_bytes()
        for campo, valor in (("unidade", "Pessoas"), ("quantidade_observacoes", 99), ("periodo_final", "202604")):
            with self.subTest(campo=campo):
                catalogo = json.loads(original)
                catalogo["indicadores"][DESOCUPACAO][campo] = valor
                self.catalogo.write_text(json.dumps(catalogo))
                self.assertFalse(verificar_dados(self.raiz, DESOCUPACAO)["saudavel"])

    def test_catalogo_corrompido_e_reportado(self):
        self.catalogo.write_bytes(b"{")
        relatorio = verificar_dados(self.raiz)
        self.assertFalse(relatorio["saudavel"])
        self.assertIn("erro_catalogo", relatorio)

    def test_catalogo_sem_indicador_relata_nao_publicado(self):
        catalogo = json.loads(self.catalogo.read_bytes())
        del catalogo["indicadores"][POPULACAO]
        self.catalogo.write_text(json.dumps(catalogo))
        relatorio = verificar_dados(self.raiz, POPULACAO)
        self.assertFalse(relatorio["saudavel"])
        self.assertEqual(relatorio["indicadores"][0]["status"], "nao_publicado")

    def test_execucao_pendente_e_bloqueio_sao_avisos(self):
        arquivo = next((self.raiz / "execucoes").glob("*.json"))
        registro = json.loads(arquivo.read_bytes())
        registro["status"] = "em_execucao"
        registro["finalizado_em_utc"] = None
        arquivo.write_text(json.dumps(registro))
        (self.raiz / ".atualizacao.lock").write_text("999999")
        relatorio = verificar_dados(self.raiz)
        self.assertTrue(relatorio["saudavel"])
        self.assertEqual(len(relatorio["avisos"]), 2)

    def test_arquivo_inacessivel_nao_e_reportado_como_saudavel(self):
        with patch("src.sistema_dados._arquivo_catalogado", side_effect=OSError("Arquivo não encontrado")):
            relatorio = verificar_dados(self.raiz)
        self.assertFalse(relatorio["saudavel"])
        self.assertTrue(all(item["status"] == "erro" for item in relatorio["indicadores"]))
