import contextlib
import io
import json
import re
from unittest.mock import patch

from tests.apoio import PublicacaoTestCase, DESOCUPACAO, POPULACAO
from src.formato_csv import COLUNAS, SIMBOLOS_SIDRA
from src.sistema_dados import consultar_contrato, consultar_dados, main


class ContratosConsultaTest(PublicacaoTestCase):
    def test_contrato_sem_coleta_catalogo_ou_criacao_de_diretorio(self):
        self.rede.side_effect = AssertionError("Contrato não deve coletar dados")
        with patch("src.sistema_dados._ler_catalogo", side_effect=AssertionError("Sem catálogo")):
            for indicador in (DESOCUPACAO, POPULACAO):
                contrato = consultar_contrato(indicador)
                self.assertEqual(contrato["indicador"], indicador)
                self.assertEqual(contrato["territorio"]["codigo"], "2211001")
                self.assertEqual(contrato["valores"]["simbolos_sidra"], sorted(SIMBOLOS_SIDRA))
                self.assertFalse(contrato["preenche_periodos_ausentes"])
        self.assertFalse(self.raiz.exists())
        self.rede.assert_not_called()

    def test_colunas_e_regras_descrevem_as_observacoes_publicadas(self):
        self.publicar_ambos()
        for indicador in (DESOCUPACAO, POPULACAO):
            with self.subTest(indicador=indicador):
                contrato = consultar_contrato(indicador)
                self.assertEqual([c["nome"] for c in contrato["colunas"]], list(COLUNAS))
                for linha in consultar_dados(self.raiz, indicador=indicador):
                    self.assertTrue(re.fullmatch(contrato["periodo"]["padrao"], linha["periodo_codigo"]))
                    self.assertEqual(linha["unidade"], contrato["unidade"])
                    for coluna in contrato["colunas"]:
                        self.assertIsInstance(linha[coluna["nome"]], str)
                        if not coluna["vazio_permitido"]:
                            self.assertNotEqual(linha[coluna["nome"]], "")

    def test_regras_diferenciam_anual_e_trimestral(self):
        anual = consultar_contrato(POPULACAO)
        trimestral = consultar_contrato(DESOCUPACAO)
        self.assertEqual(anual["periodo"]["formato"], "AAAA")
        self.assertEqual(anual["valores"]["dominio_numerico"], "inteiro")
        self.assertIsNone(anual["valores"]["maximo"])
        self.assertEqual(trimestral["periodo"]["formato"], "AAAA0T")
        self.assertEqual(trimestral["valores"]["maximo"], "100")
        self.assertFalse(anual["filtros"]["combina_ano_com_intervalo"])

    def test_resposta_nao_permite_mutar_configuracao_global(self):
        contrato = consultar_contrato(POPULACAO)
        contrato["valores"]["simbolos_sidra"].append("invalido")
        contrato["colunas"][0]["nome"] = "alterado"
        contrato["periodo"]["exemplo"] = "invalido"
        outro = consultar_contrato(POPULACAO)
        self.assertNotIn("invalido", outro["valores"]["simbolos_sidra"])
        self.assertEqual(outro["colunas"][0]["nome"], "fonte")
        self.assertEqual(outro["periodo"]["exemplo"], "2024")

    def test_cli_retorna_contrato_sem_base_publicada(self):
        saida = io.StringIO()
        with patch("sys.argv", ["sistema_dados", "--diretorio-dados", str(self.raiz),
                                "contrato", "--indicador", POPULACAO]), contextlib.redirect_stdout(saida):
            main()
        self.assertEqual(json.loads(saida.getvalue()), consultar_contrato(POPULACAO))
        self.assertFalse(self.raiz.exists())

    def test_indicador_desconhecido_e_rejeitado(self):
        with self.assertRaisesRegex(ValueError, "Indicador desconhecido"):
            consultar_contrato("desconhecido")
