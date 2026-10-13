from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase

from content.models import ContentIssue, Exercise, ExerciseRelation, ExerciseVersion
from learning.models import Attempt
from tests import factories as f


class MigrationTests(TestCase):
    def test_no_missing_migrations(self):
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit:  # pragma: no cover
            self.fail("Há alterações de modelo sem migration:\n" + out.getvalue())

    def test_all_migrations_applied(self):
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        self.assertEqual(plan, [])


class ExerciseModelTests(TestCase):
    def setUp(self):
        self.b = f.basics()

    def test_exercise_belongs_to_many_objectives(self):
        from content.models import LearningObjective
        ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        o2 = LearningObjective.objects.create(chapter=self.b["chapter"], code="o2", description="Outro")
        ex.objectives.add(o2)
        self.assertEqual(ex.objectives.count(), 2)

    def test_passage_has_many_questions(self):
        p = f.passage(self.b)
        f.exercise(self.b, passage=p, choices=[("a", True), ("b", False)])
        f.exercise(self.b, passage=p, choices=[("a", True), ("b", False)])
        self.assertEqual(p.exercises.count(), 2)

    def test_choices_keep_stable_order(self):
        ex = f.exercise(self.b, choices=[("z", True), ("a", False), ("m", False)])
        self.assertEqual([c.text for c in ex.choices.all()], ["z", "a", "m"])
        self.assertEqual([c.text for c in ex.choices.all()], ["z", "a", "m"])

    def test_interaction_must_match_type(self):
        ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        ex.exercise_type = "conjugation"
        ex.interaction = "match"
        with self.assertRaises(ValidationError):
            ex.full_clean()

    def test_writing_requires_model_answer_and_self_mode(self):
        ex = Exercise(chapter=self.b["chapter"], code="w1", exercise_type="guided_writing", interaction="writing",
                      instruction="i", prompt="p", explanation="e", difficulty=5, competency=self.b["comp"],
                      source=self.b["source"], comparison_mode="exact")
        with self.assertRaises(ValidationError) as ctx:
            ex.full_clean()
        self.assertIn("comparison_mode", ctx.exception.message_dict)
        self.assertIn("model_answer", ctx.exception.message_dict)

    def test_adapted_content_requires_notes(self):
        ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        ex.origin = "adapted"
        with self.assertRaises(ValidationError):
            ex.full_clean()

    def test_versions_created_only_on_change(self):
        ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        self.assertEqual(ex.versions.count(), 1)
        ex.snapshot_version()
        self.assertEqual(ex.versions.count(), 1)
        ex.explanation = "Explicação corrigida"
        ex.save()
        v = ex.snapshot_version("correção")
        self.assertEqual(v.number, 2)
        ex.refresh_from_db()
        self.assertEqual(ex.version, 2)

    def test_versions_are_immutable(self):
        ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        v = ex.versions.first()
        v.note = "outra"
        with self.assertRaises(ValidationError):
            v.save()

    def test_deactivated_content_is_preserved(self):
        ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        Exercise.objects.filter(pk=ex.pk).update(is_active=False)
        self.assertTrue(Exercise.objects.filter(pk=ex.pk).exists())
        self.assertEqual(ExerciseVersion.objects.filter(exercise=ex).count(), 1)

    def test_relation_cannot_point_to_itself(self):
        ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        with self.assertRaises(ValidationError):
            ExerciseRelation(from_exercise=ex, to_exercise=ex).full_clean()

    def test_source_is_reachable(self):
        ex = f.exercise(self.b, choices=[("a", True), ("b", False)])
        resp = self.client.get(self.b["source"].get_absolute_url(), REMOTE_ADDR="127.0.0.1")
        self.assertContains(resp, ex.code)

    def test_word_count_ignores_speaker_labels(self):
        p = f.passage(self.b)
        self.assertEqual(p.word_count, 2)

    def test_blank_count(self):
        ex = f.exercise(self.b, interaction="text", prompt="Je ___ et tu ___.", answers=["suis", ("es", 1)])
        self.assertEqual(ex.blank_count, 2)


class AttemptImmutabilityTests(TestCase):
    def test_attempt_cannot_be_overwritten(self):
        b = f.basics()
        ex = f.exercise(b, choices=[("a", True), ("b", False)])
        a = Attempt.objects.create(exercise=ex, exercise_version=1, answer={}, answer_display="a",
                                   correct_display="a", result="correct", score=1)
        a.result = "incorrect"
        with self.assertRaises(ValidationError):
            a.save()
        a.refresh_from_db()
        self.assertEqual(a.result, "correct")

    def test_issue_keeps_version(self):
        b = f.basics()
        ex = f.exercise(b, choices=[("a", True), ("b", False)])
        issue = ContentIssue.objects.create(exercise=ex, exercise_version=ex.version, kind="ambiguous")
        self.assertEqual(issue.exercise_version, 1)
