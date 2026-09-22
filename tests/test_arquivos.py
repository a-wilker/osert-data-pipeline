import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.arquivos import gravar_imutavel


class GravacaoImutavelTest(unittest.TestCase):
    def setUp(self):
        temporario = tempfile.TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.raiz = Path(temporario.name)
        self.destino = self.raiz / "dado.json"

    def test_publica_somente_conteudo_completo(self):
        publicar = os.link

        def conferir(origem, destino):
            self.assertFalse(destino.exists())
            self.assertEqual(origem.read_bytes(), b"conteudo completo")
            return publicar(origem, destino)

        with patch("src.arquivos.os.link", side_effect=conferir):
            gravar_imutavel(self.destino, b"conteudo completo")
        self.assertEqual(self.destino.read_bytes(), b"conteudo completo")
        self.assertFalse(list(self.raiz.glob("*.tmp")))

    def test_falha_de_escrita_nao_publica_arquivo_incompleto(self):
        with patch("src.arquivos.os.fsync", side_effect=OSError("Disco cheio")):
            with self.assertRaises(OSError):
                gravar_imutavel(self.destino, b"conteudo")
        self.assertFalse(self.destino.exists())
        self.assertEqual(list(self.raiz.iterdir()), [])

    def test_falha_na_publicacao_nao_deixa_destino_parcial(self):
        with patch("src.arquivos.os.link", side_effect=OSError("Falha de publicação")):
            with self.assertRaises(OSError):
                gravar_imutavel(self.destino, b"conteudo")
        self.assertFalse(self.destino.exists())
        self.assertEqual(list(self.raiz.iterdir()), [])

    def test_concorrencia_nao_sobrescreve_outro_conteudo(self):
        def concorrente(origem, destino):
            destino.write_bytes(b"outro conteudo")
            raise FileExistsError()
        with patch("src.arquivos.os.link", side_effect=concorrente):
            with self.assertRaisesRegex(ValueError, "difere"):
                gravar_imutavel(self.destino, b"conteudo")
        self.assertEqual(self.destino.read_bytes(), b"outro conteudo")

    def test_mesmo_conteudo_nao_regrava(self):
        gravar_imutavel(self.destino, b"conteudo")
        instante = self.destino.stat().st_mtime_ns
        gravar_imutavel(self.destino, b"conteudo")
        self.assertEqual(self.destino.stat().st_mtime_ns, instante)
