"""O conteúdo inicial carrega, é válido e cobre os requisitos pedagógicos."""
from collections import Counter

from django.core.management import call_command
from django.test import TestCase

from content.models import Chapter, Exercise, Passage
from content.quality import report
from learning.grading import grade


class SeedContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_content", verbosity=0)

    def test_quality_report_has_no_errors(self):
        rep = report()
        self.assertEqual(rep["totals"].get("errors", 0), 0, [r for r in rep["rows"] if r["errors"]])
        self.assertEqual(rep["missing_types"], [])

    def test_each_chapter_complete(self):
        chapters = Chapter.objects.filter(is_active=True, is_planned=False)
        self.assertGreaterEqual(chapters.count(), 4)
        for ch in chapters:
            exs = Exercise.objects.filter(chapter=ch, is_active=True)
            self.assertEqual(set(exs.values_list("difficulty", flat=True)), {1, 2, 3, 4, 5}, ch)
            self.assertGreaterEqual(Passage.objects.filter(chapter=ch).count(), 2, ch)
            self.assertTrue(exs.filter(is_assessment=True).exists(), ch)
            self.assertGreaterEqual(len(Counter(exs.values_list("exercise_type", flat=True))), 15, ch)
            self.assertTrue(ch.objectives.exists() and ch.grammar_topics.exists() and ch.vocabulary_topics.exists())
            self.assertTrue(ch.review_points())

    def test_every_exercise_answerable_with_its_own_answer(self):
        for ex in Exercise.objects.prefetch_related("choices", "accepted_answers"):
            it, ch = ex.interaction, list(ex.choices.all())
            if it == "single":
                ans = {"choice": next(c.pk for c in ch if c.is_correct)}
            elif it == "multiple":
                ans = {"choices": [c.pk for c in ch if c.is_correct]}
            elif it == "order":
                ans = {"order": [c.pk for c in sorted(ch, key=lambda c: c.correct_position)]}
            elif it == "match":
                ans = {"pairs": {str(c.pk): c.pk for c in ch}}
            elif it == "writing" or ex.comparison_mode in ("self", "manual"):
                self.assertTrue(ex.model_answer, ex.code)
                continue
            elif ex.comparison_mode == "regex":
                ans = {"blanks": [ex.model_answer]}
            else:
                ans = {"blanks": [ex.accepted_answers.filter(blank_index=i, is_primary=True).first().text
                                  for i in range(max(1, ex.blank_count))]}
            self.assertEqual(grade(ex, ans).result, "correct", ex.code)

    def test_every_exercise_has_source_explanation_and_origin(self):
        for ex in Exercise.objects.select_related("source"):
            self.assertTrue(ex.explanation.strip(), ex.code)
            self.assertTrue(ex.source.license_name, ex.code)
            if ex.origin == "exam_inspired":
                self.assertIn("não é questão oficial", ex.adaptation_notes, ex.code)

    def test_passage_questions_have_evidence(self):
        for ex in Exercise.objects.filter(passage__isnull=False):
            self.assertTrue(ex.evidence, ex.code)

    def test_seed_is_idempotent(self):
        n = Exercise.objects.count()
        call_command("seed_content", verbosity=0)
        self.assertEqual(Exercise.objects.count(), n)
        call_command("seed_content", "--update", verbosity=0)
        self.assertEqual(Exercise.objects.count(), n)

    def test_no_audio_features(self):
        text = " ".join(Exercise.objects.values_list("instruction", flat=True)).lower()
        for word in ("áudio", "ouça", "escute", "ditado", "pronuncie"):
            self.assertNotIn(word, text)
