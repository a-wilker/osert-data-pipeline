import unittest
from unittest.mock import Mock, patch

from src.consulta_taxa_desocupacao import extrair_taxa_desocupacao


OBSERVACAO_VALIDA = {
    "D1C": "2211001",
    "D1N": "Teresina (PI)",
    "D2C": "4099",
    "D3N": "2º trimestre 2026",
    "MN": "%",
    "V": "7.1",
}


class ExtracaoTaxaDesocupacaoTest(unittest.TestCase):
    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_extrai_resposta_valida(self, mock_get):
        resposta_falsa = Mock()
        resposta_falsa.json.return_value = [OBSERVACAO_VALIDA]
        mock_get.return_value = resposta_falsa

        resultado = extrair_taxa_desocupacao()

        self.assertEqual(resultado.loc[0, "Território"], "Teresina (PI)")
        self.assertEqual(resultado.loc[0, "Período"], "2º trimestre 2026")
        self.assertEqual(resultado.loc[0, "Unidade"], "%")
        self.assertEqual(resultado.loc[0, "Taxa de desocupação"], "7.1")
        resposta_falsa.raise_for_status.assert_called_once()

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_resposta_vazia_falha_claramente(self, mock_get):
        resposta_falsa = Mock()
        resposta_falsa.json.return_value = []
        mock_get.return_value = resposta_falsa

        with self.assertRaisesRegex(ValueError, "exatamente uma"):
            extrair_taxa_desocupacao()

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_territorio_incorreto_falha_claramente(self, mock_get):
        observacao_errada = {
            **OBSERVACAO_VALIDA,
            "D1C": "2207702",
        }

        resposta_falsa = Mock()
        resposta_falsa.json.return_value = [observacao_errada]
        mock_get.return_value = resposta_falsa

        with self.assertRaisesRegex(ValueError, "território diferente"):
            extrair_taxa_desocupacao()


if __name__ == "__main__":
    unittest.main()