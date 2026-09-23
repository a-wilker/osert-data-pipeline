import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from src.sistema_dados import INDICADOR, atualizar_dados, consultar_dados


OBSERVACAO = {
    "NC": "6", "MC": "2", "MN": "%",
    "D1C": "2211001", "D1N": "Teresina (PI)", "D2C": "4099",
    "D3C": "202601", "D3N": "1º trimestre 2026", "V": "7.4",
}
OUTRA = {**OBSERVACAO, "D3C": "202602", "D3N": "2º trimestre 2026", "V": "7.1"}


class SistemaDadosTest(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.raiz = Path(self.temporario.name) / "data"
        self.catalogo = self.raiz / "catalogo.json"
        self.patch_rede = patch("src.consulta_taxa_desocupacao.requests.get")
        self.rede = self.patch_rede.start()
        self.addCleanup(self.patch_rede.stop)
        self._resposta([OBSERVACAO, OUTRA])

    def _resposta(self, dados):
        resposta = requests.Response()
        resposta.status_code = 200
        resposta.encoding = "utf-8"
        resposta._content = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.rede.side_effect = None
        self.rede.return_value = resposta

    def test_atualiza_com_uma_consulta_e_publica_referencias_exatas(self):
        resultado = atualizar_dados(self.raiz)
        self.rede.assert_called_once()
        self.assertTrue(resultado["alterado"])
        entrada = json.loads(self.catalogo.read_bytes())["indicadores"][INDICADOR]
        self.assertEqual(entrada["quantidade_observacoes"], 2)
        self.assertEqual(entrada["periodo_inicial"], "202601")
        self.assertEqual(entrada["periodo_final"], "202602")
        self.assertTrue(entrada["publicado_em_utc"].endswith("+00:00"))
        for tipo in ("bruto", "csv"):
            self.assertTrue((self.raiz / entrada[tipo]["caminho"]).is_file())
        self.assertEqual(len(consultar_dados(self.raiz)), 2)
        self.assertFalse((self.raiz / ".atualizacao.lock").exists())

    def test_mesma_resposta_nao_duplica_nem_regrava_catalogo(self):
        atualizar_dados(self.raiz)
        antes = self.catalogo.read_bytes()
        arquivos = [p for p in self.raiz.rglob("*") if p.is_file()]
        datas = {p: p.stat().st_mtime_ns for p in arquivos}
        resultado = atualizar_dados(self.raiz)
        self.assertFalse(resultado["alterado"])
        self.assertEqual(self.catalogo.read_bytes(), antes)
        self.assertEqual({p: p.stat().st_mtime_ns for p in arquivos}, datas)
        self.assertEqual(len(list((self.raiz / "raw").iterdir())), 1)
        self.assertEqual(len(list((self.raiz / "processed").iterdir())), 1)

    def test_revisao_atualiza_consulta_e_preserva_historico(self):
        atualizar_dados(self.raiz)
        antigos = {p: p.read_bytes() for p in self.raiz.rglob("*") if p.suffix in (".csv", ".json") and p != self.catalogo}
        self._resposta([{**OBSERVACAO, "V": "8.0"}, OUTRA])
        resultado = atualizar_dados(self.raiz)
        self.assertTrue(resultado["alterado"])
        self.assertEqual(consultar_dados(self.raiz)[0]["valor_original"], "8.0")
        self.assertEqual(len(list((self.raiz / "raw").iterdir())), 2)
        self.assertEqual(len(list((self.raiz / "processed").iterdir())), 2)
        for caminho, conteudo in antigos.items():
            self.assertEqual(caminho.read_bytes(), conteudo)

    def test_falha_de_rede_mantem_publicacao_anterior(self):
        atualizar_dados(self.raiz)
        antes = self.catalogo.read_bytes()
        self.rede.side_effect = requests.Timeout("SIDRA indisponível")
        with self.assertRaises(requests.Timeout):
            atualizar_dados(self.raiz)
        self.assertEqual(self.catalogo.read_bytes(), antes)
        self.assertEqual(len(consultar_dados(self.raiz)), 2)
        self.assertFalse((self.raiz / ".atualizacao.lock").exists())

    def test_dados_invalidos_nao_substituem_publicacao(self):
        atualizar_dados(self.raiz)
        antes = self.catalogo.read_bytes()
        self._resposta([OBSERVACAO, {**OUTRA, "MN": "Pessoas"}])
        with self.assertRaises(ValueError):
            atualizar_dados(self.raiz)
        self.assertEqual(self.catalogo.read_bytes(), antes)
        self.assertEqual(len(consultar_dados(self.raiz)), 2)

    def test_perda_de_periodo_interrompe_publicacao(self):
        atualizar_dados(self.raiz)
        antes = self.catalogo.read_bytes()
        self._resposta([OUTRA])
        with self.assertRaisesRegex(ValueError, "perdeu períodos"):
            atualizar_dados(self.raiz)
        self.assertEqual(self.catalogo.read_bytes(), antes)
        self.assertEqual(len(consultar_dados(self.raiz)), 2)

    def test_falha_na_troca_do_catalogo_preserva_anterior_e_permite_tentar_novamente(self):
        atualizar_dados(self.raiz)
        antes = self.catalogo.read_bytes()
        self._resposta([{**OBSERVACAO, "V": "8.0"}, OUTRA])
        with patch("src.sistema_dados.os.replace", side_effect=OSError("Falha de escrita")):
            with self.assertRaises(OSError):
                atualizar_dados(self.raiz)
        self.assertEqual(self.catalogo.read_bytes(), antes)
        self.assertEqual(consultar_dados(self.raiz)[0]["valor_original"], "7.4")
        self.assertFalse(list(self.raiz.glob(".catalogo-*.tmp")))
        self.assertFalse((self.raiz / ".atualizacao.lock").exists())
        self.assertTrue(atualizar_dados(self.raiz)["alterado"])

    def test_consulta_por_ano_sem_rede_e_preserva_simbolos(self):
        self._resposta([{**OBSERVACAO, "V": "..."}, OUTRA])
        atualizar_dados(self.raiz)
        self.rede.reset_mock()
        self.rede.side_effect = AssertionError("Consulta deve funcionar sem rede")
        self.assertEqual(len(consultar_dados(self.raiz, 2026)), 2)
        self.assertEqual(consultar_dados(self.raiz, 2025), [])
        linha = consultar_dados(self.raiz)[0]
        self.assertEqual(linha["valor_original"], "...")
        self.assertEqual(linha["valor_numerico"], "")
        self.rede.assert_not_called()

    def test_consulta_sem_publicacao_falha_claramente(self):
        with self.assertRaisesRegex(ValueError, "ainda não publicado"):
            consultar_dados(self.raiz)
        self.rede.assert_not_called()

    def test_consulta_rejeita_ano_invalido(self):
        for ano in (0, 10000, "2026", True):
            with self.subTest(ano=ano), self.assertRaises(ValueError):
                consultar_dados(self.raiz, ano)
        self.rede.assert_not_called()

    def test_adulteracao_do_csv_e_detectada_na_consulta(self):
        resultado = atualizar_dados(self.raiz)
        caminho = self.raiz / resultado["dados"]["csv"]["caminho"]
        caminho.write_bytes(caminho.read_bytes() + b"alteracao")
        with self.assertRaisesRegex(ValueError, "hash divergente"):
            consultar_dados(self.raiz)

    def test_bloqueio_impede_segunda_atualizacao(self):
        self.raiz.mkdir()
        bloqueio = self.raiz / ".atualizacao.lock"
        bloqueio.write_text("outro processo")
        with self.assertRaisesRegex(ValueError, "bloqueio"):
            atualizar_dados(self.raiz)
        self.rede.assert_not_called()
        self.assertEqual(bloqueio.read_text(), "outro processo")

    def test_catalogo_invalido_interrompe_antes_da_coleta(self):
        self.raiz.mkdir()
        self.catalogo.write_text('{"versao": 99, "indicadores": {}}')
        with self.assertRaisesRegex(ValueError, "Catálogo inválido"):
            atualizar_dados(self.raiz)
        self.rede.assert_not_called()

    def test_referencia_fora_do_diretorio_de_dados_e_rejeitada(self):
        atualizar_dados(self.raiz)
        catalogo = json.loads(self.catalogo.read_bytes())
        catalogo["indicadores"][INDICADOR]["csv"]["caminho"] = "../fora.csv"
        self.catalogo.write_text(json.dumps(catalogo))
        with self.assertRaisesRegex(ValueError, "fora do diretório"):
            consultar_dados(self.raiz)


if __name__ == "__main__":
    unittest.main()
