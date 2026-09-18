import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from src.consulta_taxa_desocupacao import URL, extrair_taxa_desocupacao


OBSERVACAO_VALIDA = {
    "D1C": "2211001",
    "D1N": "Teresina (PI)",
    "D2C": "4099",
    "D3C": "202601",
    "D3N": "1º trimestre 2026",
    "MN": "%",
    "V": "7.4",
}

OUTRA_OBSERVACAO_VALIDA = {
    **OBSERVACAO_VALIDA,
    "D3C": "202602",
    "D3N": "2º trimestre 2026",
    "V": "7.1",
}


class ExtracaoTaxaDesocupacaoTest(unittest.TestCase):
    def setUp(self):
        self.diretorio_temporario = tempfile.TemporaryDirectory()
        self.diretorio_dados_brutos = Path(self.diretorio_temporario.name) / "raw"

    def tearDown(self):
        self.diretorio_temporario.cleanup()

    def _resposta(self, dados, conteudo=None):
        resposta = Mock()
        resposta.json.return_value = dados
        resposta.content = conteudo or json.dumps(dados).encode("utf-8")
        return resposta

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_extrai_serie_historica_valida(self, mock_get):
        mock_get.return_value = self._resposta(
            [OBSERVACAO_VALIDA, OUTRA_OBSERVACAO_VALIDA]
        )
        resultado = extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        self.assertEqual(len(resultado), 2)
        self.assertEqual(list(resultado["Taxa de desocupação"]), ["7.4", "7.1"])

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_url_solicita_todos_os_periodos(self, mock_get):
        mock_get.return_value = self._resposta([OBSERVACAO_VALIDA])
        extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        mock_get.assert_called_once_with(URL, timeout=30)
        self.assertIn("/p/all/", URL)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_resposta_vazia_falha_claramente(self, mock_get):
        mock_get.return_value = self._resposta([], b"[]")
        with self.assertRaisesRegex(ValueError, "série vazia"):
            extrair_taxa_desocupacao(self.diretorio_dados_brutos)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_territorio_incorreto_em_qualquer_observacao_falha(self, mock_get):
        incorreta = {**OUTRA_OBSERVACAO_VALIDA, "D1C": "2207702"}
        mock_get.return_value = self._resposta([OBSERVACAO_VALIDA, incorreta])
        with self.assertRaisesRegex(ValueError, "território diferente"):
            extrair_taxa_desocupacao(self.diretorio_dados_brutos)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_variavel_incorreta_em_qualquer_observacao_falha(self, mock_get):
        incorreta = {**OUTRA_OBSERVACAO_VALIDA, "D2C": "9999"}
        mock_get.return_value = self._resposta([OBSERVACAO_VALIDA, incorreta])
        with self.assertRaisesRegex(ValueError, "indicador diferente"):
            extrair_taxa_desocupacao(self.diretorio_dados_brutos)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_d3c_invalido_em_qualquer_observacao_falha(self, mock_get):
        for valor in ("ausente", "", "   ", None):
            with self.subTest(valor=valor):
                observacao = {**OUTRA_OBSERVACAO_VALIDA}
                if valor == "ausente":
                    del observacao["D3C"]
                else:
                    observacao["D3C"] = valor
                mock_get.return_value = self._resposta([OBSERVACAO_VALIDA, observacao])
                with self.assertRaisesRegex(ValueError, "D3C ausente ou vazio"):
                    extrair_taxa_desocupacao(self.diretorio_dados_brutos)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_periodo_duplicado_falha(self, mock_get):
        duplicada = {**OUTRA_OBSERVACAO_VALIDA, "D3C": OBSERVACAO_VALIDA["D3C"]}
        mock_get.return_value = self._resposta([OBSERVACAO_VALIDA, duplicada])
        with self.assertRaisesRegex(ValueError, "D3C duplicado"):
            extrair_taxa_desocupacao(self.diretorio_dados_brutos)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_simbolo_especial_permanece_texto(self, mock_get):
        especial = {**OBSERVACAO_VALIDA, "V": "-"}
        mock_get.return_value = self._resposta([especial])
        resultado = extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        self.assertEqual(resultado.loc[0, "Taxa de desocupação"], "-")

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_preserva_exatamente_os_bytes_da_resposta(self, mock_get):
        conteudo = b'[{"espacos":  preservados, "bytes": "\xc3\xa1"}]\n'
        mock_get.return_value = self._resposta([OBSERVACAO_VALIDA], conteudo)
        extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        arquivo = next(self.diretorio_dados_brutos.iterdir())
        self.assertEqual(arquivo.read_bytes(), conteudo)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_mesma_resposta_nao_gera_arquivo_duplicado(self, mock_get):
        mock_get.return_value = self._resposta([OBSERVACAO_VALIDA])
        extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        self.assertEqual(len(list(self.diretorio_dados_brutos.iterdir())), 1)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_nome_bruto_identifica_periodo_all_e_sha256(self, mock_get):
        conteudo = json.dumps([OBSERVACAO_VALIDA]).encode("utf-8")
        mock_get.return_value = self._resposta([OBSERVACAO_VALIDA], conteudo)
        extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        nome = next(self.diretorio_dados_brutos.iterdir()).name
        self.assertIn("periodo-all", nome)
        self.assertIn(f"sha256-{hashlib.sha256(conteudo).hexdigest()}", nome)

    @patch("src.consulta_taxa_desocupacao.requests.get")
    def test_erro_http_interrompe_antes_de_persistir(self, mock_get):
        resposta = self._resposta([OBSERVACAO_VALIDA])
        resposta.raise_for_status.side_effect = requests.HTTPError("erro")
        mock_get.return_value = resposta
        with self.assertRaises(requests.HTTPError):
            extrair_taxa_desocupacao(self.diretorio_dados_brutos)
        self.assertFalse(self.diretorio_dados_brutos.exists())


if __name__ == "__main__":
    unittest.main()
