from unittest.mock import patch

from tests.apoio import PublicacaoTestCase, POPULACAO
from src.sistema_dados import atualizar_dados, consultar_dados, listar_execucoes


class RevisoesTest(PublicacaoTestCase):
    def test_primeira_publicacao_e_repeticao(self):
        primeira = atualizar_dados(self.raiz)
        self.assertEqual(primeira["comparacao"]["quantidades"],
                         {"novas": 4, "alteradas": 0, "removidas": 0, "inalteradas": 0})
        self.assertIsNone(primeira["comparacao"]["bruto_anterior"])
        segunda = atualizar_dados(self.raiz)
        self.assertFalse(segunda["alterado"])
        self.assertEqual(segunda["comparacao"]["quantidades"],
                         {"novas": 0, "alteradas": 0, "removidas": 0, "inalteradas": 4})
        registro = listar_execucoes(self.raiz, limite=1)[0]
        self.assertEqual(registro["resultado"]["comparacao"], segunda["comparacao"])
        self.assertEqual(registro["resultado"]["publicacao"], primeira["dados"])

    def test_novo_periodo_e_revisao_anteriores_rastreaveis(self):
        primeira = atualizar_dados(self.raiz)
        bruto = self.raiz / primeira["dados"]["bruto"]["caminho"]
        bytes_antes = bruto.read_bytes()
        self.series["6468"][0]["V"] = "8.0"
        self.series["6468"].append({
            **self.series["6468"][-1], "D3C": "202603", "D3N": "202603", "V": "6.9",
        })
        segunda = atualizar_dados(self.raiz)
        diff = segunda["comparacao"]
        self.assertEqual(diff["quantidades"], {"novas": 1, "alteradas": 1, "removidas": 0, "inalteradas": 3})
        self.assertEqual(diff["periodos_novos"], ["202603"])
        self.assertEqual(diff["observacoes_alteradas"], [{
            "periodo_codigo": "202503", "campos": {
                "valor_original": {"anterior": "7.9", "atual": "8.0"},
                "valor_numerico": {"anterior": "7.9", "atual": "8.0"},
            },
        }])
        self.assertEqual(diff["bruto_anterior"], primeira["dados"]["bruto"])
        self.assertEqual(diff["bruto_atual"], segunda["dados"]["bruto"])
        self.assertEqual(bruto.read_bytes(), bytes_antes)

    def test_mudanca_somente_na_ordem_nao_e_revisao(self):
        atualizar_dados(self.raiz)
        self.series["6468"].reverse()
        segunda = atualizar_dados(self.raiz)
        self.assertTrue(segunda["alterado"])
        self.assertNotEqual(segunda["comparacao"]["bruto_anterior"], segunda["comparacao"]["bruto_atual"])
        self.assertEqual(segunda["comparacao"]["quantidades"]["inalteradas"], 4)
        self.assertEqual(segunda["comparacao"]["observacoes_alteradas"], [])

    def test_simbolo_para_valor_e_detectado_sem_converter_zero(self):
        self.series["6579"][-1]["V"] = "..."
        atualizar_dados(self.raiz, POPULACAO)
        self.series["6579"][-1]["V"] = "900000"
        diff = atualizar_dados(self.raiz, POPULACAO)["comparacao"]
        campos = diff["observacoes_alteradas"][0]["campos"]
        self.assertEqual(campos["valor_original"]["anterior"], "...")
        self.assertEqual(campos["valor_numerico"]["anterior"], "")
        self.assertEqual(campos["status_valor"], {"anterior": "simbolo_sidra", "atual": "numerico"})

    def test_representacao_decimal_diferente_fica_explicita(self):
        self.series["6468"][0]["V"] = "7.90"
        atualizar_dados(self.raiz)
        self.series["6468"][0]["V"] = "7.9"
        diff = atualizar_dados(self.raiz)["comparacao"]
        self.assertEqual(diff["quantidades"]["alteradas"], 1)
        self.assertEqual(diff["observacoes_alteradas"][0]["campos"]["valor_original"],
                         {"anterior": "7.90", "atual": "7.9"})

    def test_perda_de_periodos_continua_bloqueada(self):
        atualizar_dados(self.raiz)
        catalogo = (self.raiz / "catalogo.json").read_bytes()
        self.series["6468"].pop()
        with self.assertRaisesRegex(ValueError, "perdeu períodos"):
            atualizar_dados(self.raiz)
        self.assertEqual((self.raiz / "catalogo.json").read_bytes(), catalogo)
        registro = listar_execucoes(self.raiz, limite=1)[0]
        self.assertEqual(registro["status"], "falha")
        self.assertNotIn("resultado", registro)
        self.assertEqual(len(consultar_dados(self.raiz)), 4)

    def test_falha_na_publicacao_nao_registra_revisao_publicada(self):
        atualizar_dados(self.raiz)
        self.series["6468"][0]["V"] = "8.0"
        with patch("src.sistema_dados._publicar_catalogo", side_effect=OSError("Falha simulada")):
            with self.assertRaises(OSError):
                atualizar_dados(self.raiz)
        registro = listar_execucoes(self.raiz, limite=1)[0]
        self.assertEqual(registro["status"], "falha")
        self.assertNotIn("resultado", registro)
        self.assertEqual(consultar_dados(self.raiz)[0]["valor_original"], "7.9")
