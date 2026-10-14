import json
import shutil
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from content.models import ContentIssue
from learning import review, sessions, sync
from learning.models import Attempt, ReviewFlag, ReviewItem, StudySession, WrittenAnswer
from tests import factories as f

LOCAL = {"REMOTE_ADDR": "127.0.0.1"}


def mobile_attempt(code, score, when, result=None, written=None, **extra):
    result = result or ("correct" if score >= 0.99 else "partial" if score >= 0.5 else "incorrect")
    return {"uid": str(uuid.uuid4()), "exercise": code, "version": 1, "mode": "practice", "from_review": False,
            "answer": {"choice": 0}, "answer_display": "resposta", "correct_display": "certa", "result": result,
            "score": score, "feedback": "", "duration_seconds": 12, "used_translation": False,
            "created_at": when.isoformat(), "device": "mobile", "written": written, **extra}


class SyncTests(TestCase):
    def setUp(self):
        self.b = f.basics()
        self.a = f.exercise(self.b, choices=[("est", True), ("et", False)], code="sync-a")
        self.bx = f.exercise(self.b, choices=[("x", True), ("y", False)], code="sync-b")
        self.w = f.exercise(self.b, interaction="writing", comparison="self", model_answer="Modelo",
                            criteria=["a", "b"], code="sync-w")
        self.t0 = timezone.now() - timedelta(days=10)

    def payload(self, **kw):
        data = {"format": "cahier-sync", "version": 1, "device": "mobile", "exported_at": timezone.now().isoformat(),
                "attempts": [], "flags": [], "assessments": [], "issues": []}
        data.update(kw)
        return data

    def test_import_mobile_progress(self):
        data = self.payload(
            attempts=[mobile_attempt("sync-a", 0.0, self.t0), mobile_attempt("sync-a", 1.0, self.t0 + timedelta(days=1)),
                      mobile_attempt("sync-b", 1.0, self.t0 + timedelta(hours=2)),
                      mobile_attempt("nao-existe", 1.0, self.t0)],
            flags=[{"uid": str(uuid.uuid4()), "exercise": "sync-b", "created_at": (self.t0 + timedelta(hours=3)).isoformat()}],
            assessments=[{"uid": str(uuid.uuid4()), "chapter": self.b["chapter"].code, "result_score": 0.8,
                          "finished_at": self.t0.isoformat(), "title": "Avaliação final"}],
            issues=[{"uid": str(uuid.uuid4()), "exercise": "sync-a", "version": 1, "kind": "ambiguous",
                     "comment": "dúvida", "created_at": self.t0.isoformat()}])
        rep = sync.import_sync(data)
        self.assertTrue(rep.ok, rep.errors)
        self.assertEqual(rep.added, {"tentativas": 3, "marcações": 1, "avaliações": 1, "problemas": 1})
        self.assertTrue(rep.skipped)
        self.assertEqual(Attempt.objects.filter(device="mobile").count(), 3)
        item = ReviewItem.objects.get(exercise=self.a)
        self.assertEqual((item.error_count, item.correct_streak, item.stage), (1, 1, 1))
        self.assertTrue(ReviewItem.objects.get(exercise=self.bx).flagged)
        self.assertEqual(ContentIssue.objects.get().comment, "dúvida")
        self.assertEqual(sessions.chapter_status(self.b["chapter"])["status"], "completed")
        # segunda importação do mesmo arquivo não duplica nada
        rep2 = sync.import_sync(data)
        self.assertEqual(rep2.total_added(), 0)
        self.assertEqual(Attempt.objects.count(), 3)

    def test_round_trip_desktop_to_desktop_is_idempotent(self):
        s = sessions.create_session([self.a, self.bx])
        for it in s.items.all():
            sessions.answer_item(it, {"choice": it.exercise.choices.first().pk})
        review.flag(self.a)
        data = json.loads(json.dumps(sync.export_sync()))
        self.assertEqual(len(data["attempts"]), 2)
        self.assertEqual(len(data["flags"]), 1)
        rep = sync.import_sync(data)
        self.assertEqual(rep.total_added(), 0)

    def test_rebuild_matches_incremental_state(self):
        s = sessions.create_session([self.a, self.bx, self.a])
        answers = [1, 0, 0]
        for it, k in zip(s.items.order_by("position"), answers):
            pk = list(it.exercise.choices.order_by("position"))[k].pk
            sessions.answer_item(it, {"choice": pk})
        review.flag(self.bx)
        before = {r.exercise_id: (r.stage, r.error_count, r.correct_streak, r.flagged, r.recovery, r.interval_days)
                  for r in ReviewItem.objects.all()}
        sync.rebuild_review()
        after = {r.exercise_id: (r.stage, r.error_count, r.correct_streak, r.flagged, r.recovery, r.interval_days)
                 for r in ReviewItem.objects.all()}
        self.assertEqual(before, after)

    def test_written_assessment_merge(self):
        when = self.t0
        att = mobile_attempt("sync-w", 0.0, when, result="pending",
                             written={"text": "Bonjour", "assessed_score": None, "criteria_checked": []})
        sync.import_sync(self.payload(attempts=[att]))
        w = WrittenAnswer.objects.get()
        self.assertIsNone(w.assessed_score)
        att2 = dict(att, written={"text": "Bonjour", "assessed_score": 0.5, "criteria_checked": [0],
                                  "assessed_by": "self", "assessed_at": (when + timedelta(hours=1)).isoformat()})
        rep = sync.import_sync(self.payload(attempts=[att2]))
        self.assertEqual(rep.updated_written, 1)
        w.refresh_from_db()
        self.assertEqual(w.assessed_score, 0.5)
        self.assertEqual(Attempt.objects.get().result, "pending")  # tentativa original intacta
        self.assertTrue(ReviewItem.objects.filter(exercise=self.w).exists())

    def test_invalid_files_rejected(self):
        self.assertFalse(sync.import_sync({"format": "outro"}).ok)
        bad = self.payload(attempts=[{"uid": "x", "exercise": "sync-a", "result": "?", "score": "1"}])
        rep = sync.import_sync(bad)
        self.assertFalse(rep.ok)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_flag_records_event(self):
        review.flag(self.a)
        self.assertEqual(ReviewFlag.objects.count(), 1)


class SyncViewTests(TransactionTestCase):  # o backup do SQLite não roda dentro da transação de teste
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.override = override_settings(BACKUP_DIR=Path(self.tmp) / "b", DATA_DIR=Path(self.tmp))
        self.override.enable()
        self.c = Client(**LOCAL)
        self.b = f.basics()
        self.ex = f.exercise(self.b, choices=[("a", True), ("b", False)], code="v-a")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_export_and_import_views(self):
        resp = self.c.get("/dados/sincronizar/exportar/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content)["format"], "cahier-sync")
        data = {"format": "cahier-sync", "version": 1, "device": "mobile",
                "attempts": [mobile_attempt("v-a", 1.0, timezone.now() - timedelta(hours=1))]}
        up = SimpleUploadedFile("s.json", json.dumps(data).encode(), "application/json")
        resp = self.c.post("/dados/sincronizar/importar/", {"file": up}, follow=True)
        self.assertContains(resp, "Progresso do celular importado")
        self.assertEqual(Attempt.objects.count(), 1)
        page = self.c.get("/dados/")
        self.assertContains(page, "Sincronizar com o celular")
        up = SimpleUploadedFile("s.json", b"{nope", "application/json")
        resp = self.c.post("/dados/sincronizar/importar/", {"file": up}, follow=True)
        self.assertContains(resp, "JSON inválido")
