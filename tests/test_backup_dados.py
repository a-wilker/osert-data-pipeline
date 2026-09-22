import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

from tests.apoio import PublicacaoTestCase, POPULACAO
from src.backup_dados import criar_backup, restaurar_backup
from src.sistema_dados import consultar_dados, verificar_dados


class BackupDadosTest(PublicacaoTestCase):
    def setUp(self):
        super().setUp()
        self.publicar_ambos()
        self.pacote = self.raiz / "backups" / "dados.zip"
        self.destino = self.raiz.parent / "restaurado"
        self.rede.reset_mock()
        self.rede.side_effect = AssertionError("Backup e restauração devem ser offline.")

    def _reescrever_pacote(self, alterar):
        with zipfile.ZipFile(self.pacote) as pacote:
            arquivos = {nome: pacote.read(nome) for nome in pacote.namelist()}
        alterar(arquivos)
        modificado = self.raiz.parent / "modificado.zip"
        with zipfile.ZipFile(modificado, "w") as pacote:
            for nome, conteudo in arquivos.items():
                pacote.writestr(nome, conteudo)
        return modificado

    def test_backup_e_restauracao_preservam_dados_historico_e_consultas(self):
        criar_backup(self.pacote, self.raiz)
        restaurar_backup(self.pacote, self.destino)
        for pasta in ("raw", "processed", "execucoes"):
            for origem in (self.raiz / pasta).iterdir():
                copia = self.destino / pasta / origem.name
                self.assertEqual(copia.read_bytes(), origem.read_bytes())
        self.assertEqual((self.destino / "catalogo.json").read_bytes(), (self.raiz / "catalogo.json").read_bytes())
        self.assertEqual(consultar_dados(self.destino), consultar_dados(self.raiz))
        self.assertEqual(consultar_dados(self.destino, indicador=POPULACAO), consultar_dados(self.raiz, indicador=POPULACAO))
        self.assertTrue(verificar_dados(self.destino)["saudavel"])
        self.rede.assert_not_called()

    def test_mesmo_estado_gera_backup_identico_e_nao_inclui_exportacoes(self):
        (self.raiz / "exports").mkdir()
        (self.raiz / "exports" / "recorte.csv").write_text("recorte")
        criar_backup(self.pacote, self.raiz)
        antes = self.pacote.read_bytes()
        instante = self.pacote.stat().st_mtime_ns
        criar_backup(self.pacote, self.raiz)
        self.assertEqual(self.pacote.read_bytes(), antes)
        self.assertEqual(self.pacote.stat().st_mtime_ns, instante)
        with zipfile.ZipFile(self.pacote) as pacote:
            self.assertNotIn(".atualizacao.lock", pacote.namelist())
            self.assertFalse(any(nome.startswith("exports/") for nome in pacote.namelist()))

    def test_restauracao_nao_altera_diretorio_existente(self):
        criar_backup(self.pacote, self.raiz)
        self.destino.mkdir()
        importante = self.destino / "existente.txt"
        importante.write_text("preservar")
        with self.assertRaisesRegex(ValueError, "ainda não exista"):
            restaurar_backup(self.pacote, self.destino)
        self.assertEqual(importante.read_text(), "preservar")

    def test_conteudo_corrompido_e_rejeitado_antes_de_criar_destino(self):
        criar_backup(self.pacote, self.raiz)
        modificado = self._reescrever_pacote(lambda arquivos: arquivos.update({"catalogo.json": b"{}"}))
        with self.assertRaisesRegex(ValueError, "diverge"):
            restaurar_backup(modificado, self.destino)
        self.assertFalse(self.destino.exists())

    def test_caminho_fora_da_estrutura_e_rejeitado(self):
        criar_backup(self.pacote, self.raiz)
        for nome in ("../fora.json", "raw/../../fora.json", "/tmp/fora.json", "raw\\fora.json"):
            with self.subTest(nome=nome):
                modificado = self._reescrever_pacote(lambda arquivos: arquivos.update({nome: b"fora"}))
                with self.assertRaisesRegex(ValueError, "caminho não permitido"):
                    restaurar_backup(modificado, self.destino)
                self.assertFalse(self.destino.exists())

    def test_manifesto_consistente_nao_oculta_csv_incompativel_com_bruto(self):
        criar_backup(self.pacote, self.raiz)

        def alterar(arquivos):
            catalogo = json.loads(arquivos["catalogo.json"])
            entrada = catalogo["indicadores"]["taxa_desocupacao_teresina"]
            nome_csv = entrada["csv"]["caminho"]
            arquivos[nome_csv] = arquivos[nome_csv].replace(b"7.9", b"9.9")
            entrada["csv"]["sha256"] = hashlib.sha256(arquivos[nome_csv]).hexdigest()
            arquivos["catalogo.json"] = json.dumps(catalogo).encode()
            manifesto = json.loads(arquivos["manifesto.json"])
            for item in manifesto["arquivos"]:
                conteudo = arquivos[item["caminho"]]
                item["tamanho"] = len(conteudo)
                item["sha256"] = hashlib.sha256(conteudo).hexdigest()
            arquivos["manifesto.json"] = json.dumps(manifesto).encode()

        modificado = self._reescrever_pacote(alterar)
        with self.assertRaisesRegex(ValueError, "não corresponde"):
            restaurar_backup(modificado, self.destino)
        self.assertFalse(self.destino.exists())
        self.assertFalse(list(self.destino.parent.glob(".restauracao-*")))

    def test_falha_na_publicacao_da_restauracao_preserva_origem(self):
        criar_backup(self.pacote, self.raiz)
        anterior = (self.raiz / "catalogo.json").read_bytes()
        with patch("src.backup_dados.os.replace", side_effect=OSError("Falha de restauração")):
            with self.assertRaises(OSError):
                restaurar_backup(self.pacote, self.destino)
        self.assertFalse(self.destino.exists())
        self.assertEqual((self.raiz / "catalogo.json").read_bytes(), anterior)
        self.assertFalse(list(self.destino.parent.glob(".restauracao-*")))

    def test_backup_recusa_base_com_integridade_comprometida(self):
        catalogo = json.loads((self.raiz / "catalogo.json").read_bytes())
        bruto = self.raiz / catalogo["indicadores"][POPULACAO]["bruto"]["caminho"]
        bruto.write_bytes(bruto.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "hash"):
            criar_backup(self.pacote, self.raiz)
        self.assertFalse(self.pacote.exists())

    def test_backup_respeita_bloqueio_e_protege_arquivos_internos(self):
        with self.assertRaisesRegex(ValueError, "arquivos internos"):
            criar_backup(self.raiz / "raw" / "backup.zip", self.raiz)
        (self.raiz / ".atualizacao.lock").write_text("outro processo")
        with self.assertRaisesRegex(ValueError, "bloqueio"):
            criar_backup(self.pacote, self.raiz)
        self.assertFalse(self.pacote.exists())
