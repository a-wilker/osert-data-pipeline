import requests

from tests.apoio import PublicacaoTestCase, DESOCUPACAO, POPULACAO
from src.registro_execucoes import iniciar_execucao
from src.sistema_dados import atualizar_dados, consultar_dados, verificar_dados


class EstadoOperacionalTest(PublicacaoTestCase):
    def setUp(self):
        super().setUp()
        self.publicar_ambos()

    def test_falha_recente_nao_e_confundida_com_corrupcao(self):
        anteriores = consultar_dados(self.raiz)
        self.series["6468"] = requests.Timeout("Falha de rede")
        with self.assertRaises(requests.Timeout):
            atualizar_dados(self.raiz)
        self.rede.reset_mock()
        self.rede.side_effect = AssertionError("Verificação não deve coletar")
        relatorio = verificar_dados(self.raiz)
        self.assertTrue(relatorio["saudavel"])
        self.assertTrue(relatorio["atencao_operacional"])
        item = next(i for i in relatorio["indicadores"] if i["indicador"] == DESOCUPACAO)
        estado = item["atualizacao"]
        self.assertEqual(estado["estado"], "ultima_tentativa_falhou")
        self.assertEqual(estado["ultima_tentativa"]["status"], "falha")
        self.assertEqual(estado["ultima_concluida"]["status"], "atualizado")
        self.assertNotIn("erro", estado["ultima_tentativa"])
        self.assertEqual(consultar_dados(self.raiz), anteriores)
        self.rede.assert_not_called()
        self.assertFalse(verificar_dados(self.raiz, POPULACAO)["atencao_operacional"])

    def test_novo_sucesso_resolve_alerta_de_falha(self):
        serie = self.series["6468"]
        self.series["6468"] = requests.Timeout("Falha simulada")
        with self.assertRaises(requests.Timeout):
            atualizar_dados(self.raiz)
        self.series["6468"] = serie
        resultado = atualizar_dados(self.raiz)
        relatorio = verificar_dados(self.raiz, DESOCUPACAO)
        self.assertFalse(relatorio["atencao_operacional"])
        estado = relatorio["indicadores"][0]["atualizacao"]
        self.assertEqual(estado["ultima_tentativa"]["id"], resultado["execucao_id"])
        self.assertEqual(estado["ultima_concluida"]["id"], resultado["execucao_id"])
        self.assertEqual(estado["estado"], "ultima_tentativa_concluida")

    def test_execucao_antiga_pendente_continua_visivel_apos_sucesso(self):
        pendente = iniciar_execucao(self.raiz, DESOCUPACAO)
        atualizar_dados(self.raiz)
        relatorio = verificar_dados(self.raiz, DESOCUPACAO)
        self.assertTrue(relatorio["saudavel"])
        self.assertTrue(relatorio["atencao_operacional"])
        estado = relatorio["indicadores"][0]["atualizacao"]
        self.assertEqual(estado["estado"], "ultima_tentativa_concluida")
        self.assertEqual(estado["execucoes_sem_conclusao"], [pendente["id"]])

    def test_sem_historico_nao_inventa_tentativa_bem_sucedida(self):
        relatorio = verificar_dados(self.raiz.parent / "base-vazia")
        self.assertFalse(relatorio["saudavel"])
        self.assertTrue(relatorio["atencao_operacional"])
        for item in relatorio["indicadores"]:
            self.assertEqual(item["atualizacao"]["estado"], "sem_registro")
            self.assertIsNone(item["atualizacao"]["ultima_concluida"])

    def test_historico_corrompido_deixa_estado_operacional_desconhecido(self):
        arquivo = next((self.raiz / "execucoes").glob("*.json"))
        arquivo.write_text("{")
        relatorio = verificar_dados(self.raiz)
        self.assertFalse(relatorio["saudavel"])
        self.assertIsNone(relatorio["atencao_operacional"])
        self.assertTrue(all(item["atualizacao"] is None for item in relatorio["indicadores"]))

    def test_bloqueio_indica_atencao_sem_afirmar_que_processo_esta_ativo(self):
        (self.raiz / ".atualizacao.lock").write_text("999999")
        relatorio = verificar_dados(self.raiz)
        self.assertTrue(relatorio["saudavel"])
        self.assertTrue(relatorio["atencao_operacional"])
        self.assertTrue(all(i["atualizacao"]["estado"] == "ultima_tentativa_concluida"
                            for i in relatorio["indicadores"]))
