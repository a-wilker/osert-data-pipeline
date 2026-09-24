import json
import os
from unittest.mock import patch

import requests

from tests.apoio import PublicacaoTestCase, DESOCUPACAO, POPULACAO
from src.sistema_dados import atualizar_dados, atualizar_todos, consultar_dados, listar_execucoes
from src.registro_execucoes import gravar_execucao


class RegistroExecucoesTest(PublicacaoTestCase):
    def test_sucesso_e_reexecucao_geram_registros_distintos_sem_alterar_dados(self):
        primeiro = atualizar_dados(self.raiz)
        catalogo = (self.raiz / "catalogo.json").read_bytes()
        segundo = atualizar_dados(self.raiz)
        registros = listar_execucoes(self.raiz)
        self.assertEqual([r["status"] for r in registros], ["sem_alteracao", "atualizado"])
        self.assertNotEqual(primeiro["execucao_id"], segundo["execucao_id"])
        self.assertTrue(all(r["finalizado_em_utc"] for r in registros))
        self.assertEqual((self.raiz / "catalogo.json").read_bytes(), catalogo)
        self.assertEqual(registros[0]["resultado"]["csv"], primeiro["dados"]["csv"])

    def test_falha_registra_etapa_e_preserva_consulta(self):
        atualizar_dados(self.raiz)
        self.series["6468"] = requests.Timeout("Tempo de resposta excedido")
        with self.assertRaises(requests.Timeout):
            atualizar_dados(self.raiz)
        registro = listar_execucoes(self.raiz, limite=1)[0]
        self.assertEqual(registro["status"], "falha")
        self.assertEqual(registro["etapa"], "coleta")
        self.assertEqual(registro["erro"]["tipo"], "Timeout")
        self.assertEqual(len(consultar_dados(self.raiz)), 4)

    def test_lote_continua_apos_falha_de_um_indicador(self):
        self.series["6468"] = requests.Timeout("Falha simulada")
        resultado = atualizar_todos(self.raiz)
        self.assertFalse(resultado["sucesso"])
        self.assertEqual([r["sucesso"] for r in resultado["resultados"]], [False, True])
        self.assertEqual(len(consultar_dados(self.raiz, indicador=POPULACAO)), 3)
        self.assertEqual({r["status"] for r in listar_execucoes(self.raiz)}, {"falha", "atualizado"})

    def test_filtro_e_limite_do_historico(self):
        atualizar_todos(self.raiz)
        atualizar_dados(self.raiz, POPULACAO)
        registros = listar_execucoes(self.raiz, POPULACAO, limite=1)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["indicador"], POPULACAO)
        self.assertEqual(registros[0]["status"], "sem_alteracao")
        with self.assertRaises(ValueError):
            listar_execucoes(self.raiz, limite=0)

    def test_falha_na_publicacao_e_registrada_com_etapa_correta(self):
        atualizar_dados(self.raiz)
        anterior = (self.raiz / "catalogo.json").read_bytes()
        self.series["6468"][0]["V"] = "8.0"
        substituir = os.replace

        def falhar_catalogo(origem, destino):
            if destino.name == "catalogo.json":
                raise OSError("Disco indisponível")
            return substituir(origem, destino)

        with patch("src.sistema_dados.os.replace", side_effect=falhar_catalogo):
            with self.assertRaises(OSError):
                atualizar_dados(self.raiz)
        registro = listar_execucoes(self.raiz, limite=1)[0]
        self.assertEqual(registro["status"], "falha")
        self.assertEqual(registro["etapa"], "publicacao")
        self.assertEqual((self.raiz / "catalogo.json").read_bytes(), anterior)

    def test_falha_do_registro_final_nao_informa_falsamente_falha_da_publicacao(self):
        def falhar_final(raiz, registro):
            if registro["status"] == "atualizado":
                raise OSError("Sem espaço para o registro final")
            return gravar_execucao(raiz, registro)

        with patch("src.sistema_dados.gravar_execucao", side_effect=falhar_final):
            resultado = atualizar_dados(self.raiz)
        self.assertTrue(resultado["alterado"])
        self.assertIn("aviso_registro", resultado)
        self.assertEqual(len(consultar_dados(self.raiz)), 4)
        self.assertEqual(listar_execucoes(self.raiz)[0]["status"], "em_execucao")

    def test_historico_invalido_nao_e_ignorado(self):
        atualizar_dados(self.raiz)
        arquivo = next((self.raiz / "execucoes").glob("*.json"))
        arquivo.write_text("{}")
        with self.assertRaisesRegex(ValueError, "Registro de execução inválido"):
            listar_execucoes(self.raiz)

    def test_historico_ordena_instantes_com_fusos_diferentes(self):
        primeira = atualizar_dados(self.raiz)
        segunda = atualizar_dados(self.raiz)
        for resultado, inicio, fim in (
            (primeira, "2026-09-24T01:00:00+03:00", "2026-09-24T01:01:00+03:00"),
            (segunda, "2026-09-23T23:00:00+00:00", "2026-09-23T23:01:00+00:00"),
        ):
            caminho = self.raiz / "execucoes" / f"{resultado['execucao_id']}.json"
            registro = json.loads(caminho.read_bytes())
            registro["iniciado_em_utc"] = inicio
            registro["finalizado_em_utc"] = fim
            caminho.write_text(json.dumps(registro))
        self.assertEqual(listar_execucoes(self.raiz, limite=1)[0]["id"], segunda["execucao_id"])

    def test_historico_rejeita_data_invalida_sem_fuso_ou_fim_anterior(self):
        resultado = atualizar_dados(self.raiz)
        caminho = self.raiz / "execucoes" / f"{resultado['execucao_id']}.json"
        original = json.loads(caminho.read_bytes())
        casos = [
            {"iniciado_em_utc": "ontem"},
            {"iniciado_em_utc": "2026-09-24T00:00:00"},
            {"finalizado_em_utc": "amanha"},
            {"finalizado_em_utc": "2000-01-01T00:00:00+00:00"},
        ]
        for alteracao in casos:
            with self.subTest(alteracao=alteracao):
                caminho.write_text(json.dumps({**original, **alteracao}))
                with self.assertRaisesRegex(ValueError, "Horário"):
                    listar_execucoes(self.raiz)

    def test_execucao_concluida_sem_horario_final_e_invalida(self):
        resultado = atualizar_dados(self.raiz)
        caminho = self.raiz / "execucoes" / f"{resultado['execucao_id']}.json"
        registro = json.loads(caminho.read_bytes())
        registro["finalizado_em_utc"] = None
        caminho.write_text(json.dumps(registro))
        with self.assertRaisesRegex(ValueError, "Horário"):
            listar_execucoes(self.raiz)
