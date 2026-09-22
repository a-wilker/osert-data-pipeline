import csv
import io
import json
from pathlib import Path

from tests.apoio import PublicacaoTestCase, DESOCUPACAO, POPULACAO
from src.sistema_dados import consultar_dados, exportar_dados, serializar_consulta


class ConsultaIntervaloTest(PublicacaoTestCase):
    def setUp(self):
        super().setUp()
        self.publicar_ambos()
        self.rede.reset_mock()
        self.rede.side_effect = AssertionError("Consulta e exportação devem ser offline.")

    def test_intervalo_trimestral_inclui_os_dois_limites(self):
        linhas = consultar_dados(self.raiz, inicio="202504", fim="202601")
        self.assertEqual([linha["periodo_codigo"] for linha in linhas], ["202504", "202601"])
        self.rede.assert_not_called()

    def test_intervalo_anual_conserva_lacunas(self):
        linhas = consultar_dados(self.raiz, indicador=POPULACAO, inicio="2022", fim="2026")
        self.assertEqual([linha["ano"] for linha in linhas], ["2024", "2026"])

    def test_limites_abertos_e_intervalo_vazio(self):
        self.assertEqual(len(consultar_dados(self.raiz, inicio="202601")), 2)
        self.assertEqual(len(consultar_dados(self.raiz, fim="202504")), 2)
        self.assertEqual(consultar_dados(self.raiz, inicio="203001"), [])

    def test_rejeita_intervalos_invertidos_e_formatos_incompativeis(self):
        casos = [
            (DESOCUPACAO, {"inicio": "2026"}), (POPULACAO, {"fim": "202601"}),
            (DESOCUPACAO, {"inicio": "202605"}), (POPULACAO, {"inicio": "0000"}),
            (DESOCUPACAO, {"inicio": "202602", "fim": "202601"}),
            (DESOCUPACAO, {"ano": 2026, "inicio": "202601"}),
            (POPULACAO, {"inicio": 2024}),
        ]
        for indicador, filtros in casos:
            with self.subTest(indicador=indicador, filtros=filtros), self.assertRaises(ValueError):
                consultar_dados(self.raiz, indicador=indicador, **filtros)

    def test_exporta_csv_e_reutiliza_sem_regravar(self):
        caminho = self.raiz / "exports" / "desocupacao.csv"
        exportar_dados(caminho, self.raiz, inicio="202601", fim="202602")
        antes = caminho.read_bytes()
        data = caminho.stat().st_mtime_ns
        linhas = list(csv.DictReader(io.StringIO(antes.decode("utf-8"))))
        self.assertEqual(len(linhas), 2)
        self.assertTrue(all(linha["sha256_bruto"] for linha in linhas))
        exportar_dados(caminho, self.raiz, inicio="202601", fim="202602")
        self.assertEqual(caminho.read_bytes(), antes)
        self.assertEqual(caminho.stat().st_mtime_ns, data)

    def test_json_inclui_filtros_e_metadados_sem_perder_precisao(self):
        caminho = self.raiz / "exports" / "populacao.json"
        exportar_dados(caminho, self.raiz, indicador=POPULACAO, ano=2026, formato="json")
        dados = json.loads(caminho.read_bytes())
        self.assertEqual(dados["indicador"], POPULACAO)
        self.assertEqual(dados["unidade"], "Pessoas")
        self.assertEqual(dados["quantidade_observacoes"], 1)
        self.assertEqual(dados["filtros"]["ano"], 2026)
        self.assertEqual(dados["dados"][0]["valor_numerico"], "900000")

    def test_recorte_vazio_tem_cabecalho_csv_ou_lista_json(self):
        csv_vazio = serializar_consulta([], formato="csv").decode("utf-8")
        self.assertIn("valor_original", csv_vazio)
        self.assertEqual(len(csv_vazio.splitlines()), 1)
        self.assertEqual(json.loads(serializar_consulta([], formato="json"))["dados"], [])

    def test_exportacao_nao_sobrescreve_destino_diferente(self):
        caminho = self.raiz / "exportacao.csv"
        caminho.write_bytes(b"existente")
        with self.assertRaisesRegex(ValueError, "outro conteúdo"):
            exportar_dados(caminho, self.raiz)
        self.assertEqual(caminho.read_bytes(), b"existente")

    def test_exportacao_protege_arquivos_do_sistema(self):
        for nome in ("catalogo.json", ".atualizacao.lock", "raw/novo.json", "processed/novo.csv", "execucoes/novo.json"):
            with self.subTest(nome=nome), self.assertRaisesRegex(ValueError, "arquivos internos"):
                exportar_dados(self.raiz / nome, self.raiz)

    def test_formato_invalido_nao_cria_destino(self):
        caminho = self.raiz / "exports" / "nao_criar.txt"
        with self.assertRaises(ValueError):
            exportar_dados(caminho, self.raiz, formato="xml")
        self.assertFalse(caminho.exists())
