"""
Paridade entre o núcleo Python (computador) e o núcleo JavaScript (celular).

Gera milhares de vetores — respostas para todas as questões do conteúdo inicial, históricos
aleatórios de tentativas e sequências de revisão — calcula o resultado no Python, roda os
mesmos vetores no Node e exige resultados idênticos.
"""
import itertools
import json
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from content.models import Exercise
from learning import grading, mastery, review
from learning.models import ReviewItem
from portability.mobile import content_bundle
from learning.grading import strip_accents

NODE = shutil.which("node")
RUNNER = Path(settings.BASE_DIR) / "mobile" / "tests" / "parity_runner.mjs"


def text_variants(text):
    out = {text, text.upper(), text.lower(), strip_accents(text), f"  {text}  ", text + " !", text + ".",
           text.replace("'", "’"), text.replace("œ", "oe"), text.replace(" ", "  "), text[:-1] if len(text) > 1 else text}
    return [v for v in out]


def answers_for(ex, choices, accepted, rnd):
    """Pares (resposta no formato do celular, resposta no formato do computador)."""
    pk = [c.pk for c in choices]
    n = len(choices)
    it = ex.interaction
    out = []
    if it == "single":
        for i in range(n):
            out.append(({"choice": i}, {"choice": pk[i]}))
        out.append(({"choice": None}, {"choice": None}))
    elif it == "multiple":
        for r in range(n + 1):
            for combo in itertools.combinations(range(n), r):
                out.append(({"choices": list(combo)}, {"choices": [pk[i] for i in combo]}))
    elif it == "order":
        perms = [sorted(range(n), key=lambda i: choices[i].correct_position)]
        perms.append(list(reversed(perms[0])))
        for _ in range(6):
            p = list(range(n))
            rnd.shuffle(p)
            perms.append(p)
        perms.append(perms[0][:-1])
        for p in perms:
            out.append(({"order": p}, {"order": [pk[i] for i in p]}))
    elif it == "match":
        maps = [list(range(n)), list(range(1, n)) + [0]]
        for _ in range(4):
            p = list(range(n))
            rnd.shuffle(p)
            maps.append(p)
        for p in maps:
            out.append(({"pairs": {str(i): p[i] for i in range(n)}}, {"pairs": {str(pk[i]): pk[p[i]] for i in range(n)}}))
        out.append(({"pairs": {"0": None}}, {"pairs": {str(pk[0]): None}}))
    elif it == "writing":
        out.append(({"text": "Bonjour"}, {"text": "Bonjour"}))
    else:
        blanks = max(1, ex.blank_count)
        per_blank = []
        for b in range(blanks):
            texts = [a.text for a in accepted if a.blank_index == b]
            if ex.comparison_mode == "regex":
                texts = [ex.model_answer] if blanks == 1 else []
            cands = ["", "zzz"]
            for t in texts:
                cands += text_variants(t)
            per_blank.append(cands)
        if blanks == 1:
            combos = [[c] for c in per_blank[0]]
        else:
            combos = [[rnd.choice(c) for c in per_blank] for _ in range(25)]
            combos.append([c[2] if len(c) > 2 else c[0] for c in per_blank])
        for combo in combos:
            out.append(({"blanks": combo}, {"blanks": combo}))
    return out


@unittest.skipUnless(NODE, "Node.js não está instalado")
class MobileParityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_content", verbosity=0)

    def run_node(self, vectors, bundle):
        with tempfile.TemporaryDirectory() as tmp:
            vp, bp = Path(tmp) / "v.json", Path(tmp) / "b.json"
            vp.write_text(json.dumps(vectors, ensure_ascii=False), encoding="utf-8")
            bp.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run([NODE, str(RUNNER), str(vp), str(bp)], capture_output=True, text=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)

    def test_grading_parity(self):
        rnd = random.Random(7)
        bundle = content_bundle()
        vectors, expected = [], []
        for ex in Exercise.objects.filter(is_active=True).prefetch_related("choices", "accepted_answers"):
            choices = sorted(ex.choices.all(), key=lambda c: (c.position, c.pk))
            accepted = list(ex.accepted_answers.all())
            for mob, desk in answers_for(ex, choices, accepted, rnd):
                r = grading.grade(ex, desk)
                vectors.append({"code": ex.code, "answer": mob})
                expected.append({"result": r.result, "score": r.score, "answer_display": r.answer_display,
                                 "correct_display": r.correct_display, "feedback": r.feedback})
        self.assertGreater(len(vectors), 3000)
        got = self.run_node({"grading": vectors, "mastery": [], "review": []}, bundle)["grading"]
        mismatches = [(v, e, g) for v, e, g in zip(vectors, expected, got) if e != g]
        self.assertEqual(mismatches[:5], [], f"{len(mismatches)} divergências de {len(vectors)}")
        results = {e["result"] for e in expected}
        self.assertTrue({"correct", "incorrect", "partial", "pending"} <= results)

    def test_mastery_parity(self):
        rnd = random.Random(11)
        bundle = content_bundle()
        exs = list(Exercise.objects.filter(is_active=True))
        base = timezone.now() - timedelta(days=60)
        vectors, expected = [], []
        for case in range(120):
            scope = rnd.sample(exs, rnd.randint(1, 40))
            py_attempts, js_attempts = [], []
            t = base
            for k in range(rnd.randint(0, 60)):
                ex = rnd.choice(scope)
                t = t + timedelta(hours=rnd.choice([0.2, 1, 5, 30, 80]))
                score = rnd.choice([0.0, 0.0, 1.0, 1.0, 1.0, 0.5, 0.333, 0.667])
                pending = rnd.random() < 0.08
                assessed = rnd.choice([None, 0.0, 0.5, 1.0]) if pending else None
                dur = rnd.choice([0, 5, 30, 200, 900])
                eff = assessed if pending else score
                py_attempts.append(SimpleNamespace(created_at=t, pk=k + 1, exercise_id=ex.pk, effective_score=eff,
                                                   duration_seconds=dur))
                js_attempts.append({"exercise": ex.code, "created_at": t.isoformat(), "seq": k + 1,
                                    "result": "pending" if pending else "x", "score": 0 if pending else score,
                                    "duration_seconds": dur,
                                    "written": {"assessed_score": assessed} if pending else None})
            expected.append(mastery.compute(scope, py_attempts))
            vectors.append({"exercises": [e.code for e in scope], "attempts": js_attempts})
        got = self.run_node({"grading": [], "mastery": vectors, "review": []}, bundle)["mastery"]
        for i, (e, g) in enumerate(zip(expected, got)):
            self.assertEqual(e, g, f"caso {i}")

    def test_review_parity(self):
        rnd = random.Random(5)
        bundle = content_bundle()
        exs = list(Exercise.objects.filter(is_active=True)[:80])
        vectors, expected = [], []
        for ex in exs:
            t = (timezone.now() - timedelta(days=200)).replace(microsecond=0)
            attempts, flags, order, states = [], [], [], []
            for k in range(rnd.randint(1, 14)):
                t = t + timedelta(hours=rnd.choice([1, 20, 70, 300]))
                if rnd.random() < 0.15:
                    review.flag(ex, now=t)
                    order.append({"t": "f", "i": len(flags)})
                    flags.append({"exercise": ex.code, "created_at": t.isoformat(), "seq": k})
                else:
                    score = rnd.choice([0.0, 0.5, 1.0, 1.0, 0.75, 0.25])
                    fr = rnd.random() < 0.3
                    review.register(ex, score, "x", now=t, from_review=fr)
                    order.append({"t": "a", "i": len(attempts)})
                    attempts.append({"exercise": ex.code, "created_at": t.isoformat(), "seq": k, "result": "x",
                                     "score": score, "answer_display": "x", "from_review": fr})
                it = ReviewItem.objects.get(exercise=ex)
                states.append({"stage": it.stage, "interval_days": it.interval_days,
                               "due_at": round(it.due_at.timestamp() * 1000), "error_count": it.error_count,
                               "correct_streak": it.correct_streak, "review_count": it.review_count,
                               "flagged": it.flagged, "recovery": it.recovery, "last_result": it.last_result})
            vectors.append({"code": ex.code, "attempts": attempts, "flags": flags, "order": order})
            expected.append(states)
        got = self.run_node({"grading": [], "mastery": [], "review": vectors}, bundle)["review"]
        for i, (e, g) in enumerate(zip(expected, got)):
            for k, (es, gs) in enumerate(zip(e, g)):
                # last_result de um item criado só por marcação é "" nos dois lados
                self.assertEqual(es, gs, f"questão {exs[i].code}, evento {k}")
