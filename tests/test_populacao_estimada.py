import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from src.populacao_estimada import coletar_populacao_estimada, transformar_populacao_estimada, URL
from src.sistema_dados import atualizar_dados, consultar_dados, listar_indicadores

POPULACAO = "populacao_estimada_teresina"
OBS = {
    "NC": "6", "MC": "45", "MN": "Pessoas",
    "D1C": "2211001", "D1N": "Teresina (PI)", "D2C": "9324",
    "D3C": "2024", "D3N": "2024", "V": "902644",
}
OUTRA = {**OBS, "D3C": "2026", "D3N": "2026", "V": "908012"}
DESOCUPACAO = {
    **OBS, "MC": "2", "MN": "%", "D2C": "4099",
    "D3C": "202601", "D3N": "1º trimestre 2026", "V": "7.4",
}


class PopulacaoEstimadaTest(unittest.TestCase):
    def setUp(self):
        temporario = tempfile.TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.raiz = Path(temporario.name) / "data"
        self.populacao = [OUTRA, OBS]
        patch_rede = patch("requests.get", side_effect=self._responder)
        self.rede = patch_rede.start()
        self.addCleanup(patch_rede.stop)

    def _responder(self, url, **kwargs):
        dados = self.populacao if "/t/6579/" in url else [DESOCUPACAO]
        resposta = requests.Response()
        resposta.status_code = 200
        resposta.encoding = "utf-8"
        resposta._content = (json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        return resposta

    def test_coleta_preserva_bytes_e_identifica_fonte(self):
        esperado = self._responder(URL).content
        bruto = coletar_populacao_estimada(self.raiz / "raw")
        self.assertEqual(bruto.read_bytes(), esperado)
        self.assertIn("tabela-6579_variavel-9324", bruto.name)
        self.assertIn(hashlib.sha256(esperado).hexdigest(), bruto.name)
        self.rede.assert_called_once_with(URL, headers={"Accept": "application/json"}, timeout=30)

    def test_publica_populacao_anual_sem_inventar_trimestre_ou_ano_ausente(self):
        resultado = atualizar_dados(self.raiz, POPULACAO)
        self.assertEqual(resultado["dados"]["periodicidade"], "anual")
        self.assertEqual(resultado["dados"]["unidade"], "Pessoas")
        linhas = consultar_dados(self.raiz, indicador=POPULACAO)
        self.assertEqual([l["periodo_codigo"] for l in linhas], ["2024", "2026"])
        self.assertTrue(all(l["trimestre"] == "" for l in linhas))
        self.assertTrue(all(l["tabela"] == "6579" and l["variavel"] == "9324" for l in linhas))
        self.assertEqual(linhas[0]["valor_numerico"], "902644")
        self.assertEqual(consultar_dados(self.raiz, 2025, POPULACAO), [])

    def test_indicadores_coexistem_sem_alterar_publicacao_anterior(self):
        desocupacao = atualizar_dados(self.raiz)["dados"]
        atualizar_dados(self.raiz, POPULACAO)
        catalogo = json.loads((self.raiz / "catalogo.json").read_bytes())
        self.assertEqual(catalogo["indicadores"]["taxa_desocupacao_teresina"], desocupacao)
        self.assertEqual(len(catalogo["indicadores"]), 2)
        self.assertEqual(consultar_dados(self.raiz)[0]["valor_numerico"], "7.4")
        self.assertEqual(consultar_dados(self.raiz, 2026, POPULACAO)[0]["valor_numerico"], "908012")
        self.rede.side_effect = AssertionError("Listagem e consulta devem ser offline")
        self.assertEqual(len(consultar_dados(self.raiz, indicador=POPULACAO)), 2)
        self.assertTrue(all(item["publicado"] for item in listar_indicadores(self.raiz)))

    def test_mesma_coleta_reutiliza_arquivos_e_catalogo(self):
        resultado = atualizar_dados(self.raiz, POPULACAO)
        catalogo = self.raiz / "catalogo.json"
        antes = catalogo.read_bytes()
        self.assertFalse(atualizar_dados(self.raiz, POPULACAO)["alterado"])
        self.assertEqual(catalogo.read_bytes(), antes)
        bruto = self.raiz / resultado["dados"]["bruto"]["caminho"]
        self.rede.side_effect = AssertionError("Transformação deve ser offline")
        csv = transformar_populacao_estimada(bruto, self.raiz / "processed")
        anterior = csv.read_bytes()
        data = csv.stat().st_mtime_ns
        transformar_populacao_estimada(bruto, self.raiz / "processed")
        self.assertEqual(csv.read_bytes(), anterior)
        self.assertEqual(csv.stat().st_mtime_ns, data)

    def test_simbolos_e_zero_conservam_seu_significado(self):
        for valor in ("-", "..", "...", "X", "0"):
            with self.subTest(valor=valor):
                self.populacao = [{**OBS, "V": valor}]
                atualizar_dados(self.raiz, POPULACAO)
                linha = consultar_dados(self.raiz, indicador=POPULACAO)[0]
                self.assertEqual(linha["valor_original"], valor)
                self.assertEqual(linha["valor_numerico"], "0" if valor == "0" else "")
                self.assertEqual(linha["status_valor"], "numerico" if valor == "0" else "simbolo_sidra")

    def test_rejeita_registros_fora_do_contrato_antes_de_salvar(self):
        casos = [
            ("NC", "3"), ("MC", "2"), ("MN", "%"), ("D1C", "9999999"),
            ("D2C", "4099"), ("D3C", "202601"), ("D3C", "0000"),
            ("D3N", "2025"), ("V", "1.5"), ("V", "-1"), ("V", "1e6"),
            ("V", "NaN"), ("V", None), ("V", 900000), ("V", " "),
            ("D4C", "1"), ("D1N", ""),
        ]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                self.populacao = [{**OBS, campo: valor}]
                with self.assertRaises(ValueError):
                    coletar_populacao_estimada(self.raiz / "raw")
                self.assertFalse((self.raiz / "raw").exists())

    def test_rejeita_series_invalidas_e_periodos_duplicados(self):
        for dados in ([], {}, [None], [OBS, OBS]):
            with self.subTest(dados=dados):
                self.populacao = dados
                with self.assertRaises(ValueError):
                    coletar_populacao_estimada(self.raiz / "raw")
                self.assertFalse((self.raiz / "raw").exists())

    def test_falha_na_populacao_preserva_ambos_indicadores(self):
        atualizar_dados(self.raiz)
        atualizar_dados(self.raiz, POPULACAO)
        catalogo = self.raiz / "catalogo.json"
        antes = catalogo.read_bytes()
        self.populacao = [OUTRA]
        with self.assertRaisesRegex(ValueError, "perdeu períodos"):
            atualizar_dados(self.raiz, POPULACAO)
        self.assertEqual(catalogo.read_bytes(), antes)
        self.assertEqual(len(consultar_dados(self.raiz)), 1)
        self.assertEqual(len(consultar_dados(self.raiz, indicador=POPULACAO)), 2)

    def test_indicador_desconhecido_falha_sem_coletar(self):
        with self.assertRaisesRegex(ValueError, "desconhecido"):
            atualizar_dados(self.raiz, "inexistente")
        with self.assertRaisesRegex(ValueError, "desconhecido"):
            consultar_dados(self.raiz, indicador="inexistente")
        self.rede.assert_not_called()
        self.assertFalse(self.raiz.exists())

    def test_transformacao_detecta_bruto_adulterado(self):
        bruto = coletar_populacao_estimada(self.raiz / "raw")
        bruto.write_bytes(bruto.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "hash"):
            transformar_populacao_estimada(bruto, self.raiz / "processed")
        self.assertFalse((self.raiz / "processed").exists())


if __name__ == "__main__":
    unittest.main()
