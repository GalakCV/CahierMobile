from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from learning import mastery, review, sessions
from learning.models import Attempt, Mastery, ReviewItem
from tests import factories as f


def attempt(ex, score, when=None, duration=10):
    result = "correct" if score >= 0.99 else ("partial" if score >= 0.5 else "incorrect")
    return Attempt.objects.create(exercise=ex, exercise_version=ex.version, answer={}, answer_display="x",
                                  correct_display="y", result=result, score=score, duration_seconds=duration,
                                  created_at=when or timezone.now())


class MasteryTests(TestCase):
    def setUp(self):
        self.b = f.basics()
        self.exs = [f.exercise(self.b, choices=[("a", True), ("b", False)], difficulty=(i % 5) + 1) for i in range(10)]

    def test_single_correct_answer_is_far_from_100(self):
        attempt(self.exs[0], 1.0)
        data = mastery.compute_scope("chapter", self.b["chapter"].pk)
        self.assertEqual(data["accuracy"], 100.0)
        self.assertLess(data["score"], 40)

    def test_single_answer_in_tiny_scope_is_limited(self):
        ex = self.exs[0]
        attempt(ex, 1.0)
        data = mastery.compute([ex], list(Attempt.objects.filter(exercise=ex)))
        self.assertLess(data["score"], 40)

    def test_no_attempts_is_zero(self):
        self.assertEqual(mastery.compute_scope("chapter", self.b["chapter"].pk)["score"], 0.0)

    def test_full_coverage_without_retention_is_capped(self):
        for ex in self.exs:
            for _ in range(2):
                attempt(ex, 1.0)
        data = mastery.compute_scope("chapter", self.b["chapter"].pk)
        self.assertLessEqual(data["score"], 90.0)
        self.assertFalse(data["retention"])

    def test_retention_lifts_cap(self):
        old = timezone.now() - timedelta(days=5)
        for ex in self.exs:
            attempt(ex, 1.0, when=old)
            attempt(ex, 1.0)
        data = mastery.compute_scope("chapter", self.b["chapter"].pk)
        self.assertTrue(data["retention"])
        self.assertGreater(data["score"], 90.0)

    def test_repeated_errors_penalised(self):
        for ex in self.exs:
            attempt(ex, 1.0)
        base = mastery.compute_scope("chapter", self.b["chapter"].pk)["score"]
        for _ in range(2):
            attempt(self.exs[0], 0.0)
            attempt(self.exs[1], 0.0)
        data = mastery.compute_scope("chapter", self.b["chapter"].pk)
        self.assertEqual(data["repeated_errors"], 2)
        self.assertLess(data["score"], base)

    def test_recent_performance_weighs_more(self):
        ex = self.exs[0]
        t0 = timezone.now() - timedelta(hours=5)
        for i in range(5):
            attempt(ex, 0.0, when=t0 + timedelta(minutes=i))
        for i in range(5):
            attempt(ex, 1.0, when=t0 + timedelta(hours=1, minutes=i))
        data = mastery.compute_scope("chapter", self.b["chapter"].pk)
        self.assertGreater(data["accuracy"], 50)

    def test_harder_questions_weigh_more(self):
        easy = [e for e in self.exs if e.difficulty == 1][0]
        hard = [e for e in self.exs if e.difficulty == 5][0]
        attempt(easy, 0.0, when=timezone.now() - timedelta(minutes=1))
        attempt(hard, 1.0)
        acc = mastery.compute_scope("chapter", self.b["chapter"].pk)["accuracy"]
        self.assertGreater(acc, 50)

    def test_slow_answers_weigh_less(self):
        a = mastery.compute(self.exs[:1], [attempt(self.exs[0], 1.0, duration=10), attempt(self.exs[0], 0.0, duration=500)])
        b = mastery.compute(self.exs[:1], [attempt(self.exs[0], 1.0, duration=500), attempt(self.exs[0], 0.0, duration=10)])
        self.assertNotEqual(a["accuracy"], b["accuracy"])

    def test_variety_counts(self):
        attempt(self.exs[0], 1.0)
        data = mastery.compute_scope("chapter", self.b["chapter"].pk)
        self.assertEqual(data["variety"], 100.0)  # um único tipo disponível

    def test_refresh_for_exercise_creates_rows(self):
        attempt(self.exs[0], 1.0)
        mastery.refresh_for_exercise(self.exs[0])
        scopes = set(Mastery.objects.values_list("scope", flat=True))
        self.assertTrue({"overall", "chapter", "competency", "objective", "grammar"} <= scopes)


class ReviewTests(TestCase):
    def setUp(self):
        self.b = f.basics()
        self.ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        self.now = timezone.now()

    def test_first_wrong_answer_due_tomorrow(self):
        item = review.register(self.ex, 0.0, "b", self.now)
        self.assertEqual(item.stage, 0)
        self.assertEqual(item.interval_days, 1)
        self.assertEqual(item.error_count, 1)
        self.assertEqual(item.recovery, ReviewItem.Recovery.RECENT)

    def test_first_correct_answer_enters_maintenance(self):
        item = review.register(self.ex, 1.0, "a", self.now)
        self.assertEqual(item.interval_days, 7)
        self.assertEqual(item.error_count, 0)
        self.assertFalse(item.in_notebook)

    def test_correct_answers_increase_interval(self):
        review.register(self.ex, 0.0, "b", self.now)
        intervals = [review.register(self.ex, 1.0, "a", self.now).interval_days for _ in range(5)]
        self.assertEqual(intervals, sorted(intervals))
        self.assertEqual(intervals[-1], review.interval_for(4, 1))

    def test_wrong_answer_reduces_interval(self):
        for _ in range(4):
            review.register(self.ex, 1.0, "a", self.now)
        before = ReviewItem.objects.get(exercise=self.ex).interval_days
        after = review.register(self.ex, 0.0, "b", self.now).interval_days
        self.assertLess(after, before)

    def test_repeated_errors_shorten_intervals(self):
        self.assertLess(review.interval_for(3, 4), review.interval_for(3, 1))

    def test_mastered_items_still_reviewed(self):
        for _ in range(10):
            item = review.register(self.ex, 1.0, "a", self.now)
        self.assertEqual(item.interval_days, 30)
        self.assertIsNotNone(item.due_at)

    def test_recovery_states(self):
        review.register(self.ex, 0.0, "b", self.now)
        self.assertEqual(review.register(self.ex, 1.0, "a", self.now).recovery, "reviewing")
        self.assertEqual(review.register(self.ex, 1.0, "a", self.now).recovery, "improving")
        item = review.register(self.ex, 1.0, "a", self.now)
        self.assertEqual(item.recovery, "overcome")
        self.assertEqual(review.register(self.ex, 0.0, "b", self.now).recovery, "recent")

    def test_flag_makes_item_due(self):
        review.register(self.ex, 1.0, "a", self.now)
        review.flag(self.ex)
        self.assertIn(self.ex.pk, review.due_queryset().values_list("exercise_id", flat=True))

    def test_due_queue_and_review_session_only_due(self):
        other = f.exercise(self.b, choices=[("a", True), ("b", False)])
        review.register(self.ex, 0.0, "b", self.now - timedelta(days=2))
        review.register(other, 1.0, "a", self.now)
        selected = sessions.select_review(count=10)
        self.assertEqual([e.pk for e in selected], [self.ex.pk])

    def test_priority_prefers_errors_and_weak_competencies(self):
        weak_ex = f.exercise(self.b, choices=[("a", True), ("b", False)], competency=self.b["comp2"])
        i1 = review.register(self.ex, 0.0, "b", self.now - timedelta(days=1))
        i2 = review.register(weak_ex, 0.0, "b", self.now - timedelta(days=1))
        comp = {self.b["comp"].pk: 90.0, self.b["comp2"].pk: 10.0}
        self.assertGreater(review.priority(i2, comp), review.priority(i1, comp))

    def test_similar_questions_not_together(self):
        from content.models import ExerciseRelation
        twin = f.exercise(self.b, choices=[("a", True), ("b", False)])
        ExerciseRelation.objects.create(from_exercise=self.ex, to_exercise=twin, kind="similar")
        review.register(self.ex, 0.0, "b", self.now - timedelta(days=2))
        review.register(twin, 0.0, "b", self.now - timedelta(days=2))
        selected = sessions.select_review(count=10)
        self.assertEqual(len(selected), 1)


class NotebookTests(TestCase):
    def test_notebook_lists_errors_with_details(self):
        b = f.basics()
        ex = f.exercise(b, interaction="text", answers=["êtes"], prompt="Vous ___ ici ?")
        s = sessions.create_session([ex])
        item = s.items.first()
        sessions.answer_item(item, {"blank_0": "etes"})
        resp = self.client.get("/caderno-de-erros/", REMOTE_ADDR="127.0.0.1")
        self.assertContains(resp, "Vous ___ ici ?")
        self.assertContains(resp, "etes")
        self.assertContains(resp, "êtes")
        self.assertContains(resp, "Erro recente")
        resp = self.client.get("/caderno-de-erros/?estado=overcome", REMOTE_ADDR="127.0.0.1")
        self.assertNotContains(resp, "Vous ___ ici ?")
