import re

from django.test import Client, TestCase

from learning.models import Attempt, ReviewItem, SessionItem, StudySession, UserSetting, WrittenAnswer
from content.models import ContentIssue
from tests import factories as f

LOCAL = {"REMOTE_ADDR": "127.0.0.1"}


class Base(TestCase):
    def setUp(self):
        self.client = Client(**LOCAL)
        self.b = f.basics()
        self.p = f.passage(self.b)
        self.single = f.exercise(self.b, choices=[("est", True), ("et", False)], code="single", difficulty=1)
        self.text = f.exercise(self.b, interaction="text", prompt="Vous ___ ici ?", answers=["êtes"], code="text", difficulty=2)
        self.order = f.exercise(self.b, interaction="order", choices=[("suis", 2), ("Je", 1)], code="order", difficulty=3)
        self.match = f.exercise(self.b, interaction="match", choices=[("un", "1"), ("deux", "2")], code="match", difficulty=3)
        self.multi = f.exercise(self.b, interaction="multiple", choices=[("a", True), ("b", True), ("c", False)], code="multi", difficulty=4)
        self.writing = f.exercise(self.b, interaction="writing", comparison="self", model_answer="Bonjour, je suis Ana.",
                                  criteria=["Cumprimentei", "Disse o nome"], code="writing", difficulty=5)
        self.pq = f.exercise(self.b, passage=self.p, choices=[("A", True), ("B", False)], code="pq", difficulty=2,
                             evidence="A : Bonjour.", exercise_type="text_interpretation")
        self.assess = f.exercise(self.b, choices=[("x", True), ("y", False)], code="assess", is_assessment=True)

    def correct_data(self, ex):
        ch = list(ex.choices.all())
        if ex.interaction == "single":
            return {"choice": [c.pk for c in ch if c.is_correct][0]}
        if ex.interaction == "multiple":
            return {"choice": [c.pk for c in ch if c.is_correct]}
        if ex.interaction == "order":
            return {"order": ",".join(str(c.pk) for c in sorted(ch, key=lambda c: c.correct_position))}
        if ex.interaction == "match":
            return {f"match_{c.pk}": c.pk for c in ch}
        if ex.interaction == "writing":
            return {"text": "Bonjour, je suis Bia."}
        return {f"blank_{i}": ex.accepted_answers.filter(blank_index=i).first().text for i in range(max(1, ex.blank_count))}

    def wrong_data(self, ex):
        ch = list(ex.choices.all())
        if ex.interaction == "single":
            return {"choice": [c.pk for c in ch if not c.is_correct][0]}
        return {"blank_0": "zzz"}

    def answer_current(self, session, data_fn):
        resp = self.client.get(session.get_absolute_url())
        self.assertEqual(resp.status_code, 200)
        item_id = re.search(r'name="item" value="(\d+)"', resp.content.decode()).group(1)
        item = SessionItem.objects.get(pk=item_id)
        data = {"item": item_id, **data_fn(item.exercise)}
        return item, self.client.post(session.get_absolute_url(), data)


class RouteTests(Base):
    def test_main_routes(self):
        urls = ["/", "/capitulos/", f"/capitulos/{self.b['chapter'].code}/", f"/capitulos/{self.b['chapter'].code}/?aba=gramatica",
                f"/capitulos/{self.b['chapter'].code}/?aba=vocabulario", f"/capitulos/{self.b['chapter'].code}/?aba=textos",
                f"/capitulos/{self.b['chapter'].code}/?aba=revisao", "/textos/p1/", "/mapa-curricular/", "/creditos/",
                "/fontes/test-src/", "/sessao/nova/", "/revisoes/", "/caderno-de-erros/", "/producao-escrita/", "/progresso/",
                "/preferencias/", "/sessoes/", "/historico/", "/dados/", "/dados/importar/", "/dados/backup/restaurar/",
                "/editorial/", "/editorial/questao/single/", "/admin/", "/admin/content/exercise/",
                f"/admin/content/exercise/{self.single.pk}/change/"]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_unknown_chapter_404(self):
        self.assertEqual(self.client.get("/capitulos/nao-existe/").status_code, 404)

    def test_static_served(self):
        self.assertEqual(self.client.get("/static/css/app.css").status_code, 200)

    def test_no_external_resources(self):
        html = self.client.get("/").content.decode()
        self.assertNotRegex(html, r'(src|href)="https?://')


class SessionFlowTests(Base):
    def test_create_session_via_form(self):
        resp = self.client.post("/sessao/nova/", {"chapter": self.b["chapter"].pk, "count": 5, "mode": "practice"})
        self.assertEqual(resp.status_code, 302)
        s = StudySession.objects.get()
        self.assertEqual(s.items.count(), 5)
        self.assertFalse(s.items.filter(exercise__is_assessment=True).exists())

    def test_form_validation(self):
        resp = self.client.post("/sessao/nova/", {"count": 1, "mode": "practice"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "maior ou igual a 3")
        resp = self.client.post("/sessao/nova/", {"count": 5, "mode": "practice", "difficulties": [1], "competency": self.b["comp2"].pk})
        self.assertContains(resp, "Nenhuma questão encontrada")

    def test_correct_and_wrong_answers_with_explanation(self):
        from learning import sessions
        s = sessions.create_session([self.single, self.text])
        item, resp = self.answer_current(s, self.correct_data)
        self.assertRedirects(resp, f"/sessao/{s.pk}/questao/1/")
        fb = self.client.get(resp["Location"])
        self.assertContains(fb, "Correto!")
        self.assertContains(fb, "Explicação")
        item, resp = self.answer_current(s, lambda ex: {"blank_0": "etes"})
        fb = self.client.get(resp["Location"])
        self.assertContains(fb, "Não foi dessa vez")
        self.assertContains(fb, "êtes")
        self.assertContains(fb, "acentos")
        self.assertEqual(Attempt.objects.count(), 2)
        self.assertTrue(ReviewItem.objects.get(exercise=self.text).in_notebook)

    def test_empty_answer_rejected(self):
        from learning import sessions
        s = sessions.create_session([self.text])
        resp = self.client.get(s.get_absolute_url())
        item_id = re.search(r'name="item" value="(\d+)"', resp.content.decode()).group(1)
        resp = self.client.post(s.get_absolute_url(), {"item": item_id, "blank_0": "  "})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "antes de enviar")
        self.assertEqual(Attempt.objects.count(), 0)

    def test_double_submit_does_not_duplicate(self):
        from learning import sessions
        s = sessions.create_session([self.single, self.text])
        resp = self.client.get(s.get_absolute_url())
        item_id = re.search(r'name="item" value="(\d+)"', resp.content.decode()).group(1)
        data = {"item": item_id, **self.correct_data(self.single)}
        self.client.post(s.get_absolute_url(), data)
        self.client.post(s.get_absolute_url(), data)
        self.assertEqual(Attempt.objects.count(), 1)

    def test_all_interactions_and_finish(self):
        from learning import sessions
        exs = [self.single, self.text, self.order, self.match, self.multi, self.writing, self.pq]
        s = sessions.create_session(exs)
        for _ in exs:
            item, resp = self.answer_current(s, self.correct_data)
            self.assertEqual(resp.status_code, 302)
            self.assertEqual(self.client.get(resp["Location"]).status_code, 200)
        resp = self.client.get(s.get_absolute_url())
        self.assertRedirects(resp, f"/sessao/{s.pk}/resultado/")
        s.refresh_from_db()
        self.assertEqual(s.status, "finished")
        results = set(Attempt.objects.values_list("result", flat=True))
        self.assertEqual(results, {"correct", "pending"})
        page = self.client.get(f"/sessao/{s.pk}/resultado/")
        self.assertContains(page, "A : Bonjour.")  # trecho que fundamenta a resposta

    def test_pause_and_resume(self):
        from learning import sessions
        s = sessions.create_session([self.single, self.text])
        self.answer_current(s, self.correct_data)
        self.client.post(f"/sessao/{s.pk}/interromper/")
        s.refresh_from_db()
        self.assertEqual(s.status, "paused")
        dash = self.client.get("/")
        self.assertContains(dash, "Retomar sessão")
        resp = self.client.get(s.get_absolute_url())
        self.assertContains(resp, "Questão 2 de 2")
        s.refresh_from_db()
        self.assertEqual(s.status, "active")

    def test_assessment_mode_hides_feedback_until_end(self):
        from learning import sessions
        s = sessions.create_session([self.single, self.text], mode="assessment")
        item, resp = self.answer_current(s, self.wrong_data)
        self.assertRedirects(resp, s.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(self.client.get(f"/sessao/{s.pk}/questao/1/").status_code, 404)
        page = self.client.get(s.get_absolute_url())
        self.assertNotContains(page, "Ver tradução")
        self.answer_current(s, self.correct_data)
        result = self.client.get(f"/sessao/{s.pk}/resultado/")
        self.assertContains(result, "Explicação")
        self.assertContains(result, "Refazer só as erradas")

    def test_chapter_assessment_uses_assessment_items_and_completes_chapter(self):
        resp = self.client.post(f"/iniciar/capitulo/{self.b['chapter'].code}/avaliacao/")
        s = StudySession.objects.get()
        self.assertEqual([i.exercise.code for i in s.items.all()], ["assess"])
        self.answer_current(s, self.correct_data)
        self.client.get(f"/sessao/{s.pk}/resultado/")
        from learning.sessions import chapter_status
        self.assertEqual(chapter_status(self.b["chapter"])["status"], "completed")

    def test_retry_only_wrong(self):
        from learning import sessions
        s = sessions.create_session([self.single, self.text])
        self.answer_current(s, self.correct_data)
        self.answer_current(s, self.wrong_data)
        resp = self.client.post(f"/sessao/{s.pk}/refazer-erradas/")
        retry = StudySession.objects.exclude(pk=s.pk).get()
        self.assertEqual([i.exercise for i in retry.items.all()], [self.text])
        self.assertEqual(retry.parent, s)

    def test_passage_session(self):
        resp = self.client.post("/iniciar/texto/p1/")
        s = StudySession.objects.get()
        self.assertEqual(s.kind, "passage")
        page = self.client.get(s.get_absolute_url())
        self.assertContains(page, "Bonjour.")

    def test_spaced_review_session(self):
        from learning import review
        from django.utils import timezone
        from datetime import timedelta
        review.register(self.text, 0.0, "x", timezone.now() - timedelta(days=3))
        resp = self.client.post("/iniciar/revisoes/", {"count": 10})
        s = StudySession.objects.get()
        self.assertEqual(s.kind, "spaced_review")
        self.assertEqual([i.exercise for i in s.items.all()], [self.text])

    def test_mark_for_review_and_flag_issue(self):
        resp = self.client.post("/questao/single/marcar/", {"next": "/revisoes/"})
        self.assertRedirects(resp, "/revisoes/")
        self.assertTrue(ReviewItem.objects.get(exercise=self.single).flagged)
        resp = self.client.post("/questao/single/sinalizar/", {"kind": "ambiguous", "comment": "Duas respostas possíveis"})
        self.assertEqual(resp.status_code, 302)
        issue = ContentIssue.objects.get()
        self.assertEqual(issue.exercise_version, self.single.version)
        self.assertContains(self.client.get("/editorial/"), "Duas respostas possíveis")
        bad = self.client.post("/questao/single/sinalizar/", {"kind": "nao-existe"})
        self.assertEqual(bad.status_code, 200)

    def test_open_redirect_blocked(self):
        resp = self.client.post("/questao/single/marcar/", {"next": "https://evil.example/"})
        self.assertEqual(resp["Location"], "/revisoes/")

    def test_writing_self_assessment(self):
        from learning import sessions
        s = sessions.create_session([self.writing])
        item, resp = self.answer_current(s, self.correct_data)
        fb = self.client.get(resp["Location"])
        self.assertContains(fb, "Bonjour, je suis Ana.")  # resposta-modelo
        w = WrittenAnswer.objects.get()
        self.client.post(f"/producao-escrita/{w.pk}/", {"criteria": ["0"], "marked_for_review": "1"})
        w.refresh_from_db()
        self.assertEqual(w.assessed_score, 0.5)
        self.assertTrue(w.marked_for_review)
        self.assertTrue(ReviewItem.objects.get(exercise=self.writing).flagged)
        a = Attempt.objects.get()
        self.assertEqual(a.result, "pending")       # tentativa original preservada
        self.assertEqual(a.effective_score, 0.5)

    def test_settings_form(self):
        resp = self.client.post("/preferencias/", {"default_session_size": 1, "daily_goal_minutes": 20,
                                                   "font_size": "normal", "theme": "auto"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "maior ou igual a 3")
        resp = self.client.post("/preferencias/", {"display_name": "Gui", "default_session_size": 12, "daily_goal_minutes": 30,
                                                   "font_size": "large", "theme": "dark", "show_keyboard": "on"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(UserSetting.get().default_session_size, 12)
        self.assertContains(self.client.get("/"), 'data-font="large"')

    def test_history_preserved_after_editorial_change(self):
        from learning import sessions
        s = sessions.create_session([self.single])
        self.answer_current(s, self.correct_data)
        a = Attempt.objects.get()
        c = self.single.choices.get(is_correct=True)
        c.text = "est (corrigido)"
        c.save()
        v = self.single.snapshot_version("edição")
        self.assertEqual(v.number, 2)
        a.refresh_from_db()
        self.assertEqual(a.exercise_version, 1)
        self.assertEqual(a.correct_display, "est")
        old = self.single.versions.get(number=1).snapshot
        self.assertIn("est", [ch["text"] for ch in old["choices"]])


class SecurityTests(Base):
    def test_csrf_enforced(self):
        c = Client(enforce_csrf_checks=True, **LOCAL)
        resp = c.post("/sessao/nova/", {"count": 5, "mode": "practice"})
        self.assertEqual(resp.status_code, 403)

    def test_content_is_escaped(self):
        self.single.prompt = "<script>alert(1)</script>"
        self.single.save()
        resp = self.client.get("/editorial/questao/single/")
        self.assertNotContains(resp, "<script>alert(1)</script>")
        self.assertContains(resp, "&lt;script&gt;")

    def test_non_local_requests_not_auto_logged_in(self):
        c = Client(REMOTE_ADDR="192.168.0.20")
        resp = c.get("/admin/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])

    def test_local_user_has_no_usable_password(self):
        self.client.get("/admin/")
        from django.contrib.auth import get_user_model
        u = get_user_model().objects.get(username="estudante")
        self.assertFalse(u.has_usable_password())

    def test_unknown_host_rejected(self):
        resp = Client(HTTP_HOST="evil.example", **LOCAL).get("/")
        self.assertEqual(resp.status_code, 400)
