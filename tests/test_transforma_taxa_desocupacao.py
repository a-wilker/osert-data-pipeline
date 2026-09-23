import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.transforma_taxa_desocupacao import COLUNAS, transformar_taxa_desocupacao


OBSERVACAO = {
    "NC": "6", "NN": "Município", "MC": "2", "MN": "%",
    "D1C": "2211001", "D1N": "Teresina (PI)",
    "D2C": "4099", "D2N": "Taxa de desocupação",
    "D3C": "202601", "D3N": "1º trimestre 2026", "V": "7.40",
}
OUTRA = {**OBSERVACAO, "D3C": "202602", "D3N": "2º trimestre 2026", "V": "7.1"}


class TransformacaoTaxaDesocupacaoTest(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.raiz = Path(self.temporario.name)
        self.saida = self.raiz / "processed"

    def _bruto(self, dados=None, conteudo=None):
        if conteudo is None:
            conteudo = (json.dumps(dados, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        sha256 = hashlib.sha256(conteudo).hexdigest()
        arquivo = self.raiz / (
            "tabela-6468_variavel-4099_territorio-2211001"
            f"_periodo-all_sha256-{sha256}.json"
        )
        arquivo.write_bytes(conteudo)
        return arquivo

    def _ler_csv(self, caminho):
        with caminho.open(encoding="utf-8", newline="") as arquivo:
            leitor = csv.DictReader(arquivo)
            self.assertEqual(leitor.fieldnames, list(COLUNAS))
            return list(leitor)

    def test_gera_serie_ordenada_com_metadados_e_rastreabilidade(self):
        bruto = self._bruto([OUTRA, OBSERVACAO])
        antes = bruto.read_bytes()
        destino = transformar_taxa_desocupacao(bruto, self.saida)
        linhas = self._ler_csv(destino)
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0], {
            "fonte": "SIDRA/IBGE", "tabela": "6468", "variavel": "4099",
            "territorio_codigo": "2211001", "territorio_nome": "Teresina (PI)",
            "periodo_codigo": "202601", "periodo_nome": "1º trimestre 2026",
            "ano": "2026", "trimestre": "1", "unidade": "%",
            "classificacoes": "sem_classificacoes", "valor_original": "7.40",
            "valor_numerico": "7.40", "status_valor": "numerico",
            "arquivo_bruto": bruto.name,
            "sha256_bruto": hashlib.sha256(antes).hexdigest(),
            "url_fonte": "https://apisidra.ibge.gov.br/values/t/6468/n6/2211001/v/4099/p/all/h/n/f/a/d/s",
        })
        self.assertEqual(linhas[1]["periodo_codigo"], "202602")
        self.assertEqual(bruto.read_bytes(), antes)
        self.assertNotIn(b"\r\n", destino.read_bytes())

    def test_preserva_simbolos_sem_transformar_em_zero(self):
        for simbolo in ("-", "..", "...", "X"):
            with self.subTest(simbolo=simbolo):
                bruto = self._bruto([{**OBSERVACAO, "V": simbolo}])
                linha = self._ler_csv(transformar_taxa_desocupacao(bruto, self.saida))[0]
                self.assertEqual(linha["valor_original"], simbolo)
                self.assertEqual(linha["valor_numerico"], "")
                self.assertEqual(linha["status_valor"], "simbolo_sidra")

    def test_zero_numerico_e_limites_sao_preservados(self):
        for valor in ("0", "0.0", "100", "100.00"):
            with self.subTest(valor=valor):
                bruto = self._bruto([{**OBSERVACAO, "V": valor}])
                linha = self._ler_csv(transformar_taxa_desocupacao(bruto, self.saida))[0]
                self.assertEqual(linha["valor_numerico"], valor)
                self.assertEqual(linha["status_valor"], "numerico")

    @patch("requests.get", side_effect=AssertionError("A transformação deve ser offline."))
    def test_reprocessamento_sem_rede_nao_regrava_nem_duplica(self, acesso_rede):
        bruto = self._bruto([OBSERVACAO])
        destino = transformar_taxa_desocupacao(bruto, self.saida)
        antes = destino.read_bytes()
        alteracao = destino.stat().st_mtime_ns
        self.assertEqual(transformar_taxa_desocupacao(bruto, self.saida), destino)
        self.assertEqual(destino.read_bytes(), antes)
        self.assertEqual(destino.stat().st_mtime_ns, alteracao)
        self.assertEqual(len(list(self.saida.iterdir())), 1)
        acesso_rede.assert_not_called()

    def test_coletas_distintas_geram_csvs_separados(self):
        primeiro = self._bruto([OBSERVACAO])
        segundo = self._bruto([{**OBSERVACAO, "V": "8.0"}])
        destinos = [transformar_taxa_desocupacao(p, self.saida) for p in (primeiro, segundo)]
        self.assertNotEqual(*destinos)
        self.assertEqual([self._ler_csv(p)[0]["valor_original"] for p in destinos], ["7.40", "8.0"])

    def test_rejeita_registro_invalido_sem_gravar_saida_parcial(self):
        ausente = object()
        casos = [
            ("D1C", "2207702"), ("D2C", "9999"), ("NC", "3"),
            ("MC", "1"), ("MN", "Pessoas"), ("D4C", "1"),
            ("D1N", ""), ("D3N", None),
            ("V", ausente), ("V", None), ("V", ""), ("V", 7.1),
            ("V", "abc"), ("V", "NaN"), ("V", "Infinity"),
            ("V", "7,4"), ("V", "-0.1"), ("V", "100.1"),
            ("D3C", "202605"), ("D3C", "20261"), ("D3C", "000001"),
            ("D3C", 202602), ("D3C", []), ("D3C", ausente),
        ]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor):
                invalida = {**OUTRA}
                if valor is ausente:
                    del invalida[campo]
                else:
                    invalida[campo] = valor
                bruto = self._bruto([OBSERVACAO, invalida])
                antes = bruto.read_bytes()
                with self.assertRaises(ValueError):
                    transformar_taxa_desocupacao(bruto, self.saida)
                self.assertFalse(self.saida.exists())
                self.assertEqual(bruto.read_bytes(), antes)

    def test_rejeita_periodo_duplicado(self):
        bruto = self._bruto([OBSERVACAO, {**OBSERVACAO, "V": "8.0"}])
        with self.assertRaisesRegex(ValueError, "duplicado"):
            transformar_taxa_desocupacao(bruto, self.saida)
        self.assertFalse(self.saida.exists())

    def test_rejeita_json_ou_estrutura_invalidos(self):
        for conteudo in (b"{", b"[]", b"null", b"{}", b"[1]"):
            with self.subTest(conteudo=conteudo):
                bruto = self._bruto(conteudo=conteudo)
                with self.assertRaises(ValueError):
                    transformar_taxa_desocupacao(bruto, self.saida)
                self.assertFalse(self.saida.exists())

    def test_rejeita_conteudo_alterado_depois_da_coleta(self):
        bruto = self._bruto([OBSERVACAO])
        bruto.write_bytes(bruto.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "hash"):
            transformar_taxa_desocupacao(bruto, self.saida)
        self.assertFalse(self.saida.exists())

    def test_rejeita_nome_que_indica_outra_tabela(self):
        bruto = self._bruto([OBSERVACAO])
        outro = bruto.with_name(bruto.name.replace("tabela-6468", "tabela-9999"))
        outro.write_bytes(bruto.read_bytes())
        with self.assertRaisesRegex(ValueError, "Nome"):
            transformar_taxa_desocupacao(outro, self.saida)
        self.assertFalse(self.saida.exists())

    def test_nao_sobrescreve_csv_divergente(self):
        bruto = self._bruto([OBSERVACAO])
        destino = transformar_taxa_desocupacao(bruto, self.saida)
        destino.write_bytes(b"conteudo diferente")
        with self.assertRaisesRegex(ValueError, "Arquivo existente difere"):
            transformar_taxa_desocupacao(bruto, self.saida)
        self.assertEqual(destino.read_bytes(), b"conteudo diferente")


if __name__ == "__main__":
    unittest.main()
