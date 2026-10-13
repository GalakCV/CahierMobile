import copy
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, TransactionTestCase, override_settings

from content.models import Chapter, Choice, Exercise, Passage, Source
from learning import sessions
from learning.models import Attempt
from portability import backup, exporter, importer
from tests import factories as f

LOCAL = {"REMOTE_ADDR": "127.0.0.1"}


def minimal_package(**overrides):
    data = {
        "format": "cahier-content", "version": 1,
        "sources": [{"key": "orig", "title": "Original", "author": "Eu", "license": "CC BY 4.0"}],
        "competencies": [{"code": "grammaire", "name": "Gramática"}],
        "course": {"code": "fle", "title": "Curso"},
        "chapters": [{
            "code": "ch09", "number": 9, "title": "Teste", "theme": "Tema", "description": "Desc",
            "objectives": [{"code": "ch09.o1", "description": "Objetivo", "competencies": ["grammaire"]}],
            "grammar_topics": [{"code": "ch09.g1", "title": "être", "summary": "Resumo",
                                "examples": [{"fr": "Je suis", "pt": "Eu sou"}]}],
            "vocabulary_topics": [{"code": "ch09.v1", "title": "Sala", "items": [{"fr": "la table", "pt": "a mesa"}]}],
            "passages": [{"code": "ch09.p1", "title": "Texto", "text_type": "dialogue", "body": "A : Salut.",
                          "difficulty": 1, "author": "Eu", "source": "orig", "origin": "original"}],
            "exercises": [
                {"code": "ch09-e1", "type": "mc_single", "instruction": "Escolha", "prompt": "Je ___ ici.",
                 "explanation": "je suis", "difficulty": 1, "competency": "grammaire", "origin": "original",
                 "source": "orig", "objectives": ["ch09.o1"], "grammar_topics": ["ch09.g1"],
                 "choices": [{"text": "suis", "correct": True}, {"text": "es"}]},
                {"code": "ch09-e2", "type": "conjugation", "instruction": "Conjugue", "prompt": "Vous ___ ici.",
                 "explanation": "vous êtes", "difficulty": 2, "competency": "grammaire", "origin": "original",
                 "source": "orig", "answers": ["êtes"], "related": [{"code": "ch09-e1", "kind": "similar"}]},
                {"code": "ch09-e3", "type": "order_words", "instruction": "Ordene", "prompt": "Monte",
                 "explanation": "ordem", "difficulty": 3, "competency": "grammaire", "origin": "original",
                 "source": "orig", "choices": [{"text": "Je"}, {"text": "suis"}, {"text": "ici."}]},
                {"code": "ch09-e4", "type": "true_false", "instruction": "V ou F", "prompt": "A dit salut.",
                 "explanation": "Sim.", "difficulty": 1, "competency": "grammaire", "origin": "exam_inspired",
                 "adaptation_notes": "Inspirada no formato DELF.", "source": "orig", "passage": "ch09.p1",
                 "evidence": "A : Salut.", "answer": True},
            ],
        }],
    }
    data.update(overrides)
    return data


class ImportTests(TestCase):
    def test_valid_import(self):
        rep = importer.run_import(minimal_package())
        self.assertTrue(rep.ok, rep.errors)
        self.assertTrue(rep.applied)
        self.assertEqual(rep.created["questões"], 4)
        e3 = Exercise.objects.get(code="ch09-e3")
        self.assertEqual(sorted(c.correct_position for c in e3.choices.all()), [1, 2, 3])
        self.assertNotEqual([c.correct_position for c in e3.choices.order_by("position")], [1, 2, 3])
        tf = Exercise.objects.get(code="ch09-e4")
        self.assertEqual([c.text for c in tf.choices.filter(is_correct=True)], ["Vrai"])
        self.assertEqual(tf.passage.code, "ch09.p1")
        self.assertEqual(Exercise.objects.get(code="ch09-e1").versions.count(), 1)

    def test_dry_run_writes_nothing(self):
        rep = importer.run_import(minimal_package(), dry_run=True)
        self.assertTrue(rep.ok)
        self.assertFalse(rep.applied)
        self.assertFalse(Exercise.objects.exists())
        self.assertFalse(Source.objects.exists())

    def test_missing_fields_detected(self):
        data = minimal_package()
        del data["chapters"][0]["exercises"][0]["explanation"]
        del data["chapters"][0]["title"]
        rep = importer.run_import(data)
        self.assertFalse(rep.ok)
        self.assertTrue(any("explanation" in e for e in rep.errors))
        self.assertTrue(any("'title'" in e for e in rep.errors))
        self.assertFalse(Chapter.objects.exists())

    def test_invalid_types_rejected(self):
        data = minimal_package()
        data["chapters"][0]["exercises"][0]["difficulty"] = "fácil"
        data["chapters"][0]["number"] = True
        data["chapters"][0]["exercises"][1]["type"] = "dictee_audio"
        rep = importer.run_import(data)
        self.assertFalse(rep.ok)
        self.assertGreaterEqual(len(rep.errors), 3)

    def test_semantic_checks(self):
        data = minimal_package()
        data["chapters"][0]["exercises"][0]["choices"] = [{"text": "a", "correct": True}, {"text": "b", "correct": True}]
        data["chapters"][0]["exercises"][1]["prompt"] = "Vous ___ et ___."
        rep = importer.run_import(data)
        self.assertFalse(rep.ok)
        self.assertTrue(any("exatamente 1" in e for e in rep.errors))
        self.assertTrue(any("lacuna 2" in e for e in rep.errors))

    def test_wrong_format_rejected(self):
        rep = importer.run_import({"format": "outro", "version": 3})
        self.assertFalse(rep.ok)

    def test_duplicates_in_file_rejected(self):
        data = minimal_package()
        data["chapters"][0]["exercises"].append(copy.deepcopy(data["chapters"][0]["exercises"][0]))
        rep = importer.run_import(data)
        self.assertFalse(rep.ok)
        self.assertTrue(any("duplicado" in e for e in rep.errors))

    def test_duplicates_in_db_rejected_unless_update(self):
        self.assertTrue(importer.run_import(minimal_package()).ok)
        rep = importer.run_import(minimal_package())
        self.assertFalse(rep.ok)
        self.assertTrue(any("já existe" in e for e in rep.errors))
        self.assertEqual(Exercise.objects.count(), 4)
        data = minimal_package()
        data["chapters"][0]["exercises"][0]["explanation"] = "nova explicação"
        rep = importer.run_import(data, update_existing=True)
        self.assertTrue(rep.ok, rep.errors)
        ex = Exercise.objects.get(code="ch09-e1")
        self.assertEqual(ex.explanation, "nova explicação")
        self.assertEqual(ex.versions.count(), 2)
        self.assertEqual(Exercise.objects.count(), 4)

    def test_rollback_on_critical_error(self):
        data = minimal_package()
        data["chapters"][0]["exercises"][3]["passage"] = "texto-inexistente"
        rep = importer.run_import(data)
        self.assertFalse(rep.ok)
        self.assertFalse(Exercise.objects.exists())
        self.assertFalse(Chapter.objects.exists())
        self.assertFalse(Passage.objects.exists())

    def test_regex_validated(self):
        data = minimal_package()
        data["chapters"][0]["exercises"][1]["comparison"] = "regex"
        data["chapters"][0]["exercises"][1]["answers"] = ["(êtes"]
        rep = importer.run_import(data)
        self.assertFalse(rep.ok)

    def test_load_json_errors(self):
        with self.assertRaises(ValueError):
            importer.load_json_bytes(b"{nope")
        with self.assertRaises(ValueError):
            importer.load_json_bytes("{}".encode("utf-16"))


class ExportTests(TestCase):
    def setUp(self):
        importer.run_import(minimal_package())

    def test_round_trip(self):
        data = exporter.export_content()
        json.dumps(data)  # serializável
        snapshot = {e.code: e.content_snapshot() for e in Exercise.objects.all()}
        Exercise.objects.all().update(is_active=True)
        # importa em um banco "limpo" (mesma transação de teste): apaga e reimporta
        from content.models import (AcceptedAnswer, Competency, Course, ExerciseRelation, ExerciseVersion,
                                    GrammarTopic, LearningObjective, VocabularyTopic)
        for model in (ExerciseRelation, ExerciseVersion, Choice, AcceptedAnswer):
            model.objects.all().delete()
        Exercise.objects.all().delete()
        Passage.objects.all().delete()
        for model in (LearningObjective, GrammarTopic, VocabularyTopic):
            model.objects.all().delete()
        Chapter.objects.all().delete()
        rep = importer.run_import(data)
        self.assertTrue(rep.ok, rep.errors)
        for code, snap in snapshot.items():
            new = Exercise.objects.get(code=code).content_snapshot()
            strip = lambda s: {**s, "choices": [{k: v for k, v in c.items() if k not in ("id", "position")} for c in s["choices"]]}  # noqa
            a, b = strip(snap), strip(new)
            a["choices"].sort(key=lambda c: c["text"])
            b["choices"].sort(key=lambda c: c["text"])
            self.assertEqual(a, b, code)

    def test_chapter_export(self):
        b = f.basics(number=2, code="outro")
        f.exercise(b, choices=[("a", True), ("b", False)])
        data = exporter.export_content(Chapter.objects.get(code="ch09"))
        self.assertEqual([c["code"] for c in data["chapters"]], ["ch09"])
        self.assertEqual([s["key"] for s in data["sources"]], ["orig"])

    def test_progress_and_notebook_export(self):
        ex = Exercise.objects.get(code="ch09-e2")
        s = sessions.create_session([ex])
        sessions.answer_item(s.items.first(), {"blank_0": "etes"})
        progress = exporter.export_progress()
        self.assertEqual(len(progress["attempts"]), 1)
        self.assertEqual(progress["attempts"][0]["answer_display"], "etes")
        notebook = exporter.export_error_notebook()
        self.assertEqual(notebook["items"][0]["resposta_do_usuario"], "etes")
        self.assertEqual(notebook["items"][0]["resposta_correta"], "êtes")
        full = exporter.export_full()
        self.assertIn("content", full)

    def test_export_views(self):
        c = Client(**LOCAL)
        for kind in ("conteudo", "progresso", "caderno", "completo"):
            resp = c.get(f"/dados/exportar/{kind}/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("attachment", resp["Content-Disposition"])
            json.loads(resp.content)
        self.assertEqual(c.get("/dados/exportar/conteudo/?capitulo=ch09").status_code, 200)
        self.assertEqual(c.get("/dados/exportar/conteudo/?capitulo=xx").status_code, 404)


@override_settings(MAX_IMPORT_BYTES=50_000)
class ImportViewTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(DATA_DIR=Path(self.tmp))
        self.override.enable()
        self.c = Client(**LOCAL)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def upload(self, data, name="pacote.json", **extra):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        return self.c.post("/dados/importar/", {"file": SimpleUploadedFile(name, raw, "application/json"), **extra})

    def test_validate_then_confirm(self):
        resp = self.upload(minimal_package())
        self.assertContains(resp, "Arquivo válido")
        self.assertFalse(Exercise.objects.exists())
        token = resp.context["token"]
        resp = self.c.post("/dados/importar/", {"token": token, "filename": "pacote.json"})
        self.assertContains(resp, "Importação gravada")
        self.assertEqual(Exercise.objects.count(), 4)

    def test_invalid_upload_shows_report(self):
        data = minimal_package()
        del data["chapters"][0]["exercises"][0]["source"]
        resp = self.upload(data)
        self.assertContains(resp, "foi recusada")
        self.assertNotIn("token", resp.context)

    def test_size_and_extension_limits(self):
        self.assertContains(self.upload(b"{}", name="x.txt"), "extensão .json")
        self.assertContains(self.upload(b" " * 60_000), "limite")
        self.assertContains(self.upload(b"{oops"), "JSON inválido")

    def test_bad_token(self):
        resp = self.c.post("/dados/importar/", {"token": "../../etc", "filename": "x"})
        self.assertEqual(resp.status_code, 404)


class BackupTests(TransactionTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(BACKUP_DIR=Path(self.tmp) / "backups", DATA_DIR=Path(self.tmp))
        self.override.enable()
        self.b = f.basics()
        self.ex = f.exercise(self.b, choices=[("a", True), ("b", False)])

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_and_inspect_backup(self):
        path = backup.create_backup("teste")
        self.assertTrue(path.exists())
        self.assertRegex(path.name, r"^cahier-\d{8}-\d{6}-teste\.sqlite3$")
        info = backup.inspect(path)
        self.assertEqual(info["exercises"], 1)
        self.assertEqual([b.name for b in backup.list_backups()], [path.name])

    def test_restore_requires_confirmation(self):
        path = backup.create_backup()
        with self.assertRaises(backup.BackupError):
            backup.restore_backup(path, "sim")

    def test_restore_rejects_non_sqlite(self):
        bad = Path(self.tmp) / "x.sqlite3"
        bad.write_bytes(b"not a database at all")
        with self.assertRaises(backup.BackupError):
            backup.inspect(bad)
        other = Path(self.tmp) / "y.sqlite3"
        conn = sqlite3.connect(other)
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
        conn.close()
        with self.assertRaises(backup.BackupError):
            backup.inspect(other)

    def test_restore_brings_back_state(self):
        path = backup.create_backup("antes")
        f.exercise(self.b, choices=[("c", True), ("d", False)], code="depois")
        self.assertEqual(Exercise.objects.count(), 2)
        summary = backup.restore_backup(path, "RESTAURAR")
        self.assertEqual(Exercise.objects.count(), 1)
        self.assertTrue((Path(self.tmp) / "backups" / summary["safety_backup"]).exists())

    def test_path_traversal_blocked(self):
        with self.assertRaises(backup.BackupError):
            backup.resolve_backup("../db.sqlite3")
        c = Client(**LOCAL)
        self.assertEqual(c.get("/dados/backup/..%2Fsecret/baixar/").status_code, 404)

    def test_backup_views(self):
        c = Client(**LOCAL)
        resp = c.post("/dados/backup/criar/", {"label": "pela web"})
        self.assertEqual(resp.status_code, 302)
        name = backup.list_backups()[0].name
        self.assertIn("pela-web", name)
        self.assertEqual(c.get(f"/dados/backup/{name}/baixar/").status_code, 200)
        resp = c.post("/dados/backup/restaurar/", {"name": name, "confirmation": "restaurar?"})
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "RESTAURAR", status_code=400)
        resp = c.post("/dados/backup/restaurar/", {"name": name, "confirmation": "RESTAURAR"})
        self.assertEqual(resp.status_code, 302)

    def test_backup_command(self):
        from django.core.management import call_command
        call_command("backup_db", label="cli")
        self.assertTrue(any("cli" in b.name for b in backup.list_backups()))
