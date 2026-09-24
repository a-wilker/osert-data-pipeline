import http.client
import json
import threading
from unittest.mock import patch

from tests.apoio import DESOCUPACAO, POPULACAO, PublicacaoTestCase
from src.api_consulta import ServidorConsulta
from src.sistema_dados import atualizar_dados, consultar_dados
import src.sistema_dados as sistema


class ApiConsultaTests(PublicacaoTestCase):
    def setUp(self):
        super().setUp()
        self.publicar_ambos()
        self.servidor = ServidorConsulta(self.raiz, 0)
        self.thread = threading.Thread(
            target=lambda: self.servidor.serve_forever(poll_interval=0.01), daemon=True,
        )
        self.thread.start()
        self.addCleanup(self.encerrar)

    def encerrar(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def requisitar(self, caminho, metodo="GET"):
        conexao = http.client.HTTPConnection("127.0.0.1", self.servidor.server_port, timeout=5)
        try:
            conexao.request(metodo, caminho)
            resposta = conexao.getresponse()
            conteudo = resposta.read()
            return resposta.status, dict(resposta.getheaders()), json.loads(conteudo) if conteudo else None
        finally:
            conexao.close()

    def test_indicadores_e_saude(self):
        status, headers, corpo = self.requisitar("/indicadores")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual({i["indicador"] for i in corpo["indicadores"]}, {DESOCUPACAO, POPULACAO})
        self.assertTrue(all(i["publicado"] for i in corpo["indicadores"]))
        status, _, corpo = self.requisitar("/saude")
        self.assertEqual(status, 200)
        self.assertTrue(corpo["saudavel"])
        self.assertEqual(self.servidor.server_address[0], "127.0.0.1")

    def test_dados_equivalentes_consulta_local_e_rastreaveis(self):
        for indicador in (DESOCUPACAO, POPULACAO):
            with self.subTest(indicador=indicador):
                status, _, corpo = self.requisitar(f"/indicadores/{indicador}/dados?ano=2026")
                self.assertEqual(status, 200)
                self.assertEqual(corpo["dados"], consultar_dados(self.raiz, 2026, indicador))
                self.assertEqual(corpo["filtros"], {"ano": 2026, "inicio": None, "fim": None})
                meta = corpo["metadados"]
                self.assertEqual(meta["versao_contrato"], 1)
                self.assertIn("publicado_em_utc", meta)
                self.assertEqual(meta["bruto"]["sha256"], corpo["dados"][0]["sha256_bruto"])
                self.assertEqual(meta["url_fonte"], corpo["dados"][0]["url_fonte"])
                status, _, metadados = self.requisitar(f"/indicadores/{indicador}/metadados")
                self.assertEqual(status, 200)
                self.assertEqual(metadados, {"indicador": indicador, **meta})

    def test_intervalos_inclusivos_e_resultado_vazio(self):
        status, _, corpo = self.requisitar(f"/indicadores/{DESOCUPACAO}/dados?inicio=202504&fim=202601")
        self.assertEqual(status, 200)
        self.assertEqual([i["periodo_codigo"] for i in corpo["dados"]], ["202504", "202601"])
        status, _, corpo = self.requisitar(f"/indicadores/{POPULACAO}/dados?inicio=2024&fim=2026")
        self.assertEqual(status, 200)
        self.assertEqual([i["periodo_codigo"] for i in corpo["dados"]], ["2024", "2026"])
        status, _, corpo = self.requisitar(f"/indicadores/{POPULACAO}/dados?ano=2000")
        self.assertEqual(status, 200)
        self.assertEqual(corpo["dados"], [])
        self.assertEqual(corpo["quantidade_observacoes"], 0)

    def test_parametros_invalidos(self):
        queries = [
            "ano=0", "ano=10000", "ano=-1", "ano=abc", "ano=",
            "ano=2026&ano=2025", "ano=2026&inicio=202601", "inicio=202605",
            "inicio=202602&fim=202601", "fim=2026", "formato=csv",
            "ano", "ano=%FF", "a=1&b=2&c=3&d=4",
        ]
        for query in queries:
            with self.subTest(query=query):
                status, _, corpo = self.requisitar(f"/indicadores/{DESOCUPACAO}/dados?{query}")
                self.assertEqual(status, 400)
                self.assertEqual(corpo["erro"]["codigo"], "parametros_invalidos")
        for rota in ("/indicadores", "/saude", f"/indicadores/{POPULACAO}/metadados"):
            self.assertEqual(self.requisitar(rota + "?ano=2026")[0], 400)

    def test_rotas_e_indicadores_desconhecidos(self):
        status, _, corpo = self.requisitar("/indicadores/desconhecido/dados")
        self.assertEqual(status, 404)
        self.assertEqual(corpo["erro"]["codigo"], "indicador_desconhecido")
        for rota in ("/", "/catalogo.json", "/../catalogo.json", "/raw/arquivo.json", "/indicadores/atualizar"):
            self.assertEqual(self.requisitar(rota)[0], 404)

    def test_publicacao_ausente(self):
        catalogo = self.raiz / "catalogo.json"
        conteudo = json.loads(catalogo.read_text())
        del conteudo["indicadores"][POPULACAO]
        catalogo.write_text(json.dumps(conteudo))
        for recurso in ("dados", "metadados"):
            status, _, corpo = self.requisitar(f"/indicadores/{POPULACAO}/{recurso}")
            self.assertEqual(status, 409)
            self.assertEqual(corpo["erro"]["codigo"], "publicacao_ausente")
        self.assertEqual(self.requisitar("/saude")[0], 503)

    def test_corrupcao_nao_expoe_caminhos(self):
        catalogo = json.loads((self.raiz / "catalogo.json").read_text())
        csv = self.raiz / catalogo["indicadores"][POPULACAO]["csv"]["caminho"]
        csv.write_text("corrompido")
        for recurso in ("dados", "metadados"):
            status, _, corpo = self.requisitar(f"/indicadores/{POPULACAO}/{recurso}")
            self.assertEqual(status, 503)
            self.assertEqual(corpo["erro"]["codigo"], "base_inconsistente")
            self.assertNotIn(str(self.raiz), json.dumps(corpo))
        status, _, corpo = self.requisitar("/saude")
        self.assertEqual(status, 503)
        self.assertNotIn(str(self.raiz), json.dumps(corpo))

    def test_catalogo_invalido(self):
        (self.raiz / "catalogo.json").write_text("{")
        for rota in ("/indicadores", "/saude", f"/indicadores/{POPULACAO}/dados"):
            self.assertEqual(self.requisitar(rota)[0], 503)

    def test_consultas_nao_escrevem_nem_acessam_sidra(self):
        def snapshot():
            return {str(p.relative_to(self.raiz)): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.raiz.rglob("*") if p.is_file()}
        antes = snapshot()
        self.rede.reset_mock()
        self.rede.side_effect = AssertionError("Consulta não deve acessar SIDRA")
        for rota in ("/indicadores", "/saude", f"/indicadores/{POPULACAO}/execucoes",
                     f"/indicadores/{POPULACAO}/dados", f"/indicadores/{DESOCUPACAO}/metadados"):
            self.assertEqual(self.requisitar(rota)[0], 200)
        for metodo in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE", "CONNECT"):
            status, headers, _ = self.requisitar("/indicadores", metodo)
            self.assertEqual(status, 405)
            self.assertEqual(headers["Allow"], "GET")
        self.rede.assert_not_called()
        self.assertEqual(antes, snapshot())

    def test_metadados_e_dados_usam_mesma_leitura_do_catalogo(self):
        with patch("src.sistema_dados._ler_catalogo", wraps=sistema._ler_catalogo) as ler:
            status, _, corpo = self.requisitar(f"/indicadores/{POPULACAO}/dados")
        self.assertEqual(status, 200)
        ler.assert_called_once()
        self.assertEqual(corpo["metadados"]["bruto"]["sha256"], corpo["dados"][0]["sha256_bruto"])

    def test_nova_publicacao_fica_visivel_sem_reiniciar(self):
        rota = f"/indicadores/{POPULACAO}/dados?ano=2026"
        antes = self.requisitar(rota)[2]
        self.series["6579"][-1]["V"] = "910000"
        atualizar_dados(self.raiz, POPULACAO)
        status, _, depois = self.requisitar(rota)
        self.assertEqual(status, 200)
        self.assertEqual(depois["dados"][0]["valor_numerico"], "910000")
        self.assertNotEqual(antes["metadados"]["bruto"], depois["metadados"]["bruto"])

    def test_simbolos_preservados(self):
        self.series["6468"][-1]["V"] = "..."
        atualizar_dados(self.raiz, DESOCUPACAO)
        status, _, corpo = self.requisitar(f"/indicadores/{DESOCUPACAO}/dados?inicio=202602")
        self.assertEqual(status, 200)
        linha = corpo["dados"][0]
        self.assertEqual(linha["valor_original"], "...")
        self.assertEqual(linha["valor_numerico"], "")
        self.assertEqual(linha["status_valor"], "simbolo_sidra")

    def test_consulta_historica_http(self):
        primeira = atualizar_dados(self.raiz, POPULACAO)
        identificador = primeira["execucao_id"]
        self.series["6579"][-1]["V"] = "910000"
        atualizar_dados(self.raiz, POPULACAO)
        self.rede.reset_mock()
        self.rede.side_effect = AssertionError("A API não deve acessar SIDRA")
        rota = f"/indicadores/{POPULACAO}"
        status, _, corpo = self.requisitar(f"{rota}/dados?execucao={identificador}&inicio=2026&fim=2026")
        self.assertEqual(status, 200)
        self.assertEqual(corpo["execucao_id"], identificador)
        self.assertEqual(corpo["dados"][0]["valor_numerico"], "900000")
        self.assertEqual(corpo["metadados"], primeira["dados"])
        status, _, meta = self.requisitar(f"{rota}/metadados?execucao={identificador}")
        self.assertEqual(status, 200)
        self.assertEqual(meta["bruto"], primeira["dados"]["bruto"])
        self.assertEqual(meta["execucao_id"], identificador)
        self.rede.assert_not_called()

    def test_erros_de_selecao_historica_http(self):
        rota = f"/indicadores/{POPULACAO}/dados"
        self.assertEqual(self.requisitar(rota + "?execucao=../catalogo")[0], 400)
        status, _, corpo = self.requisitar(rota + "?execucao=" + "0" * 32)
        self.assertEqual(status, 404)
        self.assertEqual(corpo["erro"]["codigo"], "execucao_desconhecida")
        primeira = atualizar_dados(self.raiz, DESOCUPACAO)
        status, _, corpo = self.requisitar(rota + "?execucao=" + primeira["execucao_id"])
        self.assertEqual(status, 409)
        self.assertEqual(corpo["erro"]["codigo"], "publicacao_historica_ausente")

    def test_historico_http_permita_descobrir_e_reproduzir_publicacao(self):
        primeira = atualizar_dados(self.raiz, POPULACAO)
        self.series["6579"][-1]["V"] = "910000"
        segunda = atualizar_dados(self.raiz, POPULACAO)
        status, _, corpo = self.requisitar(f"/indicadores/{POPULACAO}/execucoes?limite=2")
        self.assertEqual(status, 200)
        self.assertEqual(corpo["limite"], 2)
        execucoes = corpo["execucoes"]
        self.assertEqual([item["id"] for item in execucoes], [segunda["execucao_id"], primeira["execucao_id"]])
        self.assertTrue(all(item["publicacao_registrada"] for item in execucoes))
        self.assertEqual(execucoes[0]["comparacao"]["quantidades"]["alteradas"], 1)
        identificador = execucoes[1]["id"]
        status, _, dados = self.requisitar(f"/indicadores/{POPULACAO}/dados?execucao={identificador}&ano=2026")
        self.assertEqual(status, 200)
        self.assertEqual(dados["dados"][0]["valor_numerico"], "900000")

    def test_historico_http_rejeita_parametros_e_nao_expoe_falha_interna(self):
        import requests
        for query in ("limite=0", "limite=101", "limite=-1", "limite=abc", "limite=", "limite=1&limite=2", "ano=2026"):
            with self.subTest(query=query):
                self.assertEqual(self.requisitar(f"/indicadores/{POPULACAO}/execucoes?{query}")[0], 400)
        self.series["6579"] = requests.Timeout(f"Falha interna em {self.raiz}")
        with self.assertRaises(requests.Timeout):
            atualizar_dados(self.raiz, POPULACAO)
        status, _, corpo = self.requisitar(f"/indicadores/{POPULACAO}/execucoes?limite=1")
        self.assertEqual(status, 200)
        item = corpo["execucoes"][0]
        self.assertEqual(item["status"], "falha")
        self.assertFalse(item["publicacao_registrada"])
        self.assertNotIn("erro", item)
        self.assertNotIn(str(self.raiz), json.dumps(corpo))

    def test_historico_http_legado_nao_promete_publicacao_reproduzivel(self):
        ultima = atualizar_dados(self.raiz, POPULACAO)
        caminho = self.raiz / "execucoes" / f"{ultima['execucao_id']}.json"
        registro = json.loads(caminho.read_bytes())
        del registro["resultado"]["publicacao"]
        del registro["resultado"]["comparacao"]
        caminho.write_text(json.dumps(registro))
        status, _, corpo = self.requisitar(f"/indicadores/{POPULACAO}/execucoes?limite=1")
        self.assertEqual(status, 200)
        self.assertFalse(corpo["execucoes"][0]["publicacao_registrada"])
        self.assertNotIn("comparacao", corpo["execucoes"][0])

    def test_saude_expoe_falha_operacional_sem_expor_mensagem_interna(self):
        import requests
        self.series["6579"] = requests.Timeout(f"Erro interno em {self.raiz}")
        with self.assertRaises(requests.Timeout):
            atualizar_dados(self.raiz, POPULACAO)
        status, _, corpo = self.requisitar("/saude")
        self.assertEqual(status, 200)
        self.assertTrue(corpo["saudavel"])
        self.assertTrue(corpo["atencao_operacional"])
        item = next(i for i in corpo["indicadores"] if i["indicador"] == POPULACAO)
        self.assertEqual(item["atualizacao"]["estado"], "ultima_tentativa_falhou")
        self.assertNotIn(str(self.raiz), json.dumps(corpo))
