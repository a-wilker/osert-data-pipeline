import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from src.sistema_dados import atualizar_dados

POPULACAO = "populacao_estimada_teresina"
DESOCUPACAO = "taxa_desocupacao_teresina"


class PublicacaoTestCase(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.raiz = Path(self.temporario.name) / "data"
        base = {"NC": "6", "D1C": "2211001", "D1N": "Teresina (PI)"}
        self.series = {
            "6468": [
                {**base, "MC": "2", "MN": "%", "D2C": "4099",
                 "D3C": periodo, "D3N": periodo, "V": valor}
                for periodo, valor in (("202503", "7.9"), ("202504", "7.8"), ("202601", "7.4"), ("202602", "7.1"))
            ],
            "6579": [
                {**base, "MC": "45", "MN": "Pessoas", "D2C": "9324",
                 "D3C": ano, "D3N": ano, "V": "900000"}
                for ano in ("2021", "2024", "2026")
            ],
        }
        patch_rede = patch("requests.get", side_effect=self.responder)
        self.rede = patch_rede.start()
        self.addCleanup(patch_rede.stop)

    def responder(self, url, **kwargs):
        tabela = "6579" if "/t/6579/" in url else "6468"
        dados = self.series[tabela]
        if isinstance(dados, Exception):
            raise dados
        resposta = requests.Response()
        resposta.status_code = 200
        resposta.encoding = "utf-8"
        resposta._content = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        return resposta

    def publicar_ambos(self):
        atualizar_dados(self.raiz, DESOCUPACAO)
        atualizar_dados(self.raiz, POPULACAO)
