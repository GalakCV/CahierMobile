from django.http import QueryDict
from django.test import TestCase

from learning import grading
from tests import factories as f


class NormalizationTests(TestCase):
    def test_normalize_case_spaces_punctuation(self):
        self.assertEqual(grading.normalize("  Je  SUIS de Rio ! "), "je suis de rio")

    def test_normalize_keeps_accents(self):
        self.assertEqual(grading.normalize("Vous êtes"), "vous êtes")

    def test_apostrophes_and_spacing(self):
        self.assertEqual(grading.normalize("J’ai"), "j'ai")
        self.assertEqual(grading.normalize("j ' ai"), "j'ai")
        self.assertEqual(grading.normalize("Est - ce que"), "est-ce que")

    def test_french_typographic_spaces(self):
        self.assertEqual(grading.normalize("Ça va ?"), "ça va")

    def test_strip_accents(self):
        self.assertEqual(grading.strip_accents("êtes ça"), "etes ca")


class TextGradingTests(TestCase):
    def setUp(self):
        self.b = f.basics()

    def g(self, ex, *blanks):
        return grading.grade(ex, {"blanks": list(blanks)})

    def test_exact_mode(self):
        ex = f.exercise(self.b, interaction="text", comparison="exact", answers=["Je suis"])
        self.assertTrue(self.g(ex, "Je suis").is_correct)
        self.assertFalse(self.g(ex, "je suis").is_correct)
        self.assertTrue(self.g(ex, "  Je suis ").is_correct)

    def test_exact_mode_unifies_apostrophes(self):
        ex = f.exercise(self.b, interaction="text", comparison="exact", answers=["j'ai"])
        self.assertTrue(self.g(ex, "j’ai").is_correct)

    def test_normalized_mode_uses_primary_only(self):
        ex = f.exercise(self.b, interaction="text", comparison="normalized",
                        answers=[("des livres", 0, True), ("les livres", 0, False)])
        self.assertTrue(self.g(ex, "Des livres.").is_correct)
        self.assertFalse(self.g(ex, "les livres").is_correct)

    def test_accepted_list_mode_accepts_variants(self):
        ex = f.exercise(self.b, interaction="text", answers=[("premier", 0, True), ("1er", 0, False)])
        self.assertTrue(self.g(ex, "1er").is_correct)
        self.assertTrue(self.g(ex, "Premier").is_correct)

    def test_accents_are_required_by_default(self):
        ex = f.exercise(self.b, interaction="text", answers=["êtes"])
        r = self.g(ex, "etes")
        self.assertEqual(r.result, "incorrect")
        self.assertIn("acentos", r.feedback)

    def test_accent_insensitive_when_configured(self):
        ex = f.exercise(self.b, interaction="text", answers=["Há livros na mesa"], accent_insensitive=True)
        r = self.g(ex, "ha livros na mesa")
        self.assertEqual(r.result, "correct")
        self.assertIn("acentos", r.feedback)

    def test_ligature_oe_accepted(self):
        ex = f.exercise(self.b, interaction="text", answers=["ma sœur"])
        self.assertTrue(self.g(ex, "ma soeur").is_correct)

    def test_regex_mode(self):
        ex = f.exercise(self.b, interaction="text", comparison="regex",
                        answers=[r"nous sommes (des )?étudiante?s"])
        self.assertTrue(self.g(ex, "Nous sommes étudiants.").is_correct)
        self.assertTrue(self.g(ex, "nous sommes des étudiantes").is_correct)
        self.assertFalse(self.g(ex, "nous sont étudiants").is_correct)
        self.assertEqual(self.g(ex, "nous sommes etudiants").result, "incorrect")

    def test_multi_blank_partial(self):
        ex = f.exercise(self.b, interaction="text", prompt="Je ___ et tu ___.", answers=["suis", ("es", 1)])
        r = self.g(ex, "suis", "est")
        self.assertEqual(r.result, "partial")
        self.assertAlmostEqual(r.score, 0.5)
        self.assertTrue(self.g(ex, "suis", "es").is_correct)

    def test_empty_is_wrong(self):
        ex = f.exercise(self.b, interaction="text", answers=["suis"])
        self.assertEqual(self.g(ex, "").result, "incorrect")

    def test_manual_and_self_modes_are_pending(self):
        ex = f.exercise(self.b, interaction="text", comparison="self", model_answer="Modelo")
        self.assertEqual(self.g(ex, "algo").result, "pending")
        ex2 = f.exercise(self.b, interaction="text", comparison="manual", model_answer="Modelo")
        self.assertEqual(self.g(ex2, "algo").result, "pending")


class ChoiceGradingTests(TestCase):
    def setUp(self):
        self.b = f.basics()

    def test_single_choice(self):
        ex = f.exercise(self.b, choices=[("est", True), ("et", False)])
        right, wrong = ex.choices.all()
        self.assertTrue(grading.grade(ex, {"choice": right.pk}).is_correct)
        r = grading.grade(ex, {"choice": wrong.pk})
        self.assertEqual(r.result, "incorrect")
        self.assertEqual(r.correct_display, "est")

    def test_single_choice_feedback(self):
        ex = f.exercise(self.b, choices=[("est", True), ("et", False)])
        wrong = ex.choices.get(text="et")
        wrong.feedback = "et = e"
        wrong.save()
        self.assertEqual(grading.grade(ex, {"choice": wrong.pk}).feedback, "et = e")

    def test_multiple_selection(self):
        ex = f.exercise(self.b, interaction="multiple", choices=[("a", True), ("b", True), ("c", False), ("d", False)])
        a, b, c, d = ex.choices.all()
        self.assertTrue(grading.grade(ex, {"choices": [a.pk, b.pk]}).is_correct)
        partial = grading.grade(ex, {"choices": [a.pk]})
        self.assertEqual(partial.result, "partial")
        self.assertAlmostEqual(partial.score, 0.5)
        self.assertEqual(grading.grade(ex, {"choices": [a.pk, c.pk]}).result, "incorrect")  # (1-1)/2 = 0

    def test_ordering(self):
        ex = f.exercise(self.b, interaction="order", choices=[("suis", 2), ("Je", 1), ("de Rio.", 3)])
        by = {c.text: c.pk for c in ex.choices.all()}
        ok = grading.grade(ex, {"order": [by["Je"], by["suis"], by["de Rio."]]})
        self.assertTrue(ok.is_correct)
        self.assertEqual(ok.answer_display, "Je suis de Rio.")
        bad = grading.grade(ex, {"order": [by["suis"], by["Je"], by["de Rio."]]})
        self.assertEqual(bad.result, "incorrect")

    def test_ordering_alternative_accepted(self):
        ex = f.exercise(self.b, interaction="order", choices=[("Demain", 1), ("je pars.", 2)],
                        answers=["je pars. Demain"])
        by = {c.text: c.pk for c in ex.choices.all()}
        self.assertTrue(grading.grade(ex, {"order": [by["je pars."], by["Demain"]]}).is_correct)

    def test_matching(self):
        ex = f.exercise(self.b, interaction="match", choices=[("un", "1"), ("deux", "2"), ("trois", "3")])
        cs = list(ex.choices.all())
        ok = {str(c.pk): c.pk for c in cs}
        self.assertTrue(grading.grade(ex, {"pairs": ok}).is_correct)
        swapped = dict(ok)
        swapped[str(cs[0].pk)], swapped[str(cs[1].pk)] = cs[1].pk, cs[0].pk
        r = grading.grade(ex, {"pairs": swapped})
        self.assertEqual(r.result, "incorrect")
        self.assertAlmostEqual(r.score, 1 / 3, places=2)

    def test_writing_is_pending(self):
        ex = f.exercise(self.b, interaction="writing", comparison="self", model_answer="Modelo", criteria=["a"])
        self.assertEqual(grading.grade(ex, {"text": "Bonjour"}).result, "pending")


class ParseAnswerTests(TestCase):
    def test_parse_from_querydict(self):
        b = f.basics()
        ex = f.exercise(b, interaction="multiple", choices=[("a", True), ("b", True), ("c", False)])
        q = QueryDict(mutable=True)
        q.setlist("choice", ["3", "x", "1"])
        self.assertEqual(grading.parse_answer(ex, q), {"choices": [1, 3]})

    def test_empty_detection(self):
        b = f.basics()
        ex = f.exercise(b, interaction="text", answers=["a"])
        self.assertTrue(grading.answer_is_empty(ex, {"blanks": ["  "]}))
        self.assertFalse(grading.answer_is_empty(ex, {"blanks": ["a"]}))
