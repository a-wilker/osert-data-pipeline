import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.consulta_taxa_desocupacao import extrair_taxa_desocupacao


OBSERVACAO_VALIDA = {
    "D1C": "2211001",
    "D1N": "Teresina (PI)",
    "D2C": "4099",
    "D3C": "202602",
    "D3N": "2º trimestre 2026",
    "MN": "%",
    "V": "7.1",
}


class ExtracaoTaxaDesocupacaoTest(unittest.TestCase):
    def setUp(self):
        self.diretorio_temporario = tempfile.TemporaryDirectory()
        self.diretorio_dados_brutos = Path(self.diretorio_temporario.name) / "raw"

    def tearDown(self):
        self.diretorio_temporario.cleanup()

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_extrai_resposta_valida(self, mock_get):
        resposta_falsa = Mock()
        resposta_falsa.json.return_value = [OBSERVACAO_VALIDA]
        resposta_falsa.content = json.dumps([OBSERVACAO_VALIDA]).encode("utf-8")
        mock_get.return_value = resposta_falsa

        resultado = extrair_taxa_desocupacao(self.diretorio_dados_brutos)

        self.assertEqual(resultado.loc[0, "Território"], "Teresina (PI)")
        self.assertEqual(resultado.loc[0, "Período"], "2º trimestre 2026")
        self.assertEqual(resultado.loc[0, "Unidade"], "%")
        self.assertEqual(resultado.loc[0, "Taxa de desocupação"], "7.1")
        resposta_falsa.raise_for_status.assert_called_once()

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_resposta_vazia_falha_claramente(self, mock_get):
        resposta_falsa = Mock()
        resposta_falsa.json.return_value = []
        resposta_falsa.content = b"[]"
        mock_get.return_value = resposta_falsa

        with self.assertRaisesRegex(ValueError, "exatamente uma"):
            extrair_taxa_desocupacao(self.diretorio_dados_brutos)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_territorio_incorreto_falha_claramente(self, mock_get):
        observacao_errada = {**OBSERVACAO_VALIDA, "D1C": "2207702"}
        resposta_falsa = Mock()
        resposta_falsa.json.return_value = [observacao_errada]
        resposta_falsa.content = json.dumps([observacao_errada]).encode("utf-8")
        mock_get.return_value = resposta_falsa

        with self.assertRaisesRegex(ValueError, "território diferente"):
            extrair_taxa_desocupacao(self.diretorio_dados_brutos)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_preserva_exatamente_os_bytes_da_resposta(self, mock_get):
        conteudo = b'[{"espacos":  preservados, "bytes": "\xc3\xa1"}]\n'
        resposta_falsa = Mock()
        resposta_falsa.json.return_value = [OBSERVACAO_VALIDA]
        resposta_falsa.content = conteudo
        mock_get.return_value = resposta_falsa

        extrair_taxa_desocupacao(self.diretorio_dados_brutos)

        arquivos = list(self.diretorio_dados_brutos.iterdir())
        self.assertEqual(len(arquivos), 1)
        self.assertEqual(arquivos[0].read_bytes(), conteudo)
        self.assertIn("tabela-6468", arquivos[0].name)
        self.assertIn("variavel-4099", arquivos[0].name)
        self.assertIn("territorio-2211001", arquivos[0].name)
        self.assertIn("periodo-202602", arquivos[0].name)
        self.assertIn(
            f"sha256-{hashlib.sha256(conteudo).hexdigest()}",
            arquivos[0].name,
        )

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_mesma_resposta_nao_gera_arquivo_duplicado(self, mock_get):
        resposta_falsa = Mock()
        resposta_falsa.json.return_value = [OBSERVACAO_VALIDA]
        resposta_falsa.content = json.dumps([OBSERVACAO_VALIDA]).encode("utf-8")
        mock_get.return_value = resposta_falsa

        extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        extrair_taxa_desocupacao(self.diretorio_dados_brutos)

        self.assertEqual(len(list(self.diretorio_dados_brutos.iterdir())), 1)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_d3c_invalido_falha_antes_de_criar_diretorio(self, mock_get):
        casos = ("ausente", "", "   ", None)

        for valor in casos:
            with self.subTest(valor=valor):
                observacao = {**OBSERVACAO_VALIDA}
                if valor == "ausente":
                    del observacao["D3C"]
                else:
                    observacao["D3C"] = valor

                resposta_falsa = Mock()
                resposta_falsa.json.return_value = [observacao]
                resposta_falsa.content = json.dumps([observacao]).encode("utf-8")
                mock_get.return_value = resposta_falsa

                with self.assertRaisesRegex(ValueError, "D3C ausente ou vazio"):
                    extrair_taxa_desocupacao(self.diretorio_dados_brutos)

                self.assertFalse(self.diretorio_dados_brutos.exists())


if __name__ == "__main__":
    unittest.main()
