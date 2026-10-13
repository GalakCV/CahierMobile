"""
Relatório de validação do conteúdo cadastrado (usado no painel editorial,
no comando ``validate_content`` e nos testes).

Erros = impedem o uso correto da questão. Avisos = merecem revisão humana.
"""
from __future__ import annotations

import re
from collections import Counter

from .models import Chapter, Exercise, Origin, Passage

# Instruções (em português) que indicariam atividade oral — fora do escopo desta versão.
FORBIDDEN_AUDIO = re.compile(r"\b(áudio|audio|ouça|escute|ditado|pronuncie|pronúncia|grave sua voz|fale em voz alta)", re.I)


def exercise_problems(ex: Exercise) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    choices = list(ex.choices.all())
    answers = list(ex.accepted_answers.all())
    allowed = Exercise.TYPE_INTERACTIONS.get(ex.exercise_type, ())
    if ex.interaction not in allowed:
        errors.append("interação incompatível com o tipo")
    if not ex.explanation.strip():
        errors.append("sem explicação")
    if ex.interaction == "single":
        n = sum(c.is_correct for c in choices)
        if len(choices) < 2 or n != 1:
            errors.append(f"escolha única com {n} alternativa(s) correta(s) em {len(choices)}")
    elif ex.interaction == "multiple":
        n = sum(c.is_correct for c in choices)
        if n < 1 or n == len(choices):
            errors.append("múltipla seleção sem mistura de corretas e incorretas")
    elif ex.interaction == "order":
        pos = sorted(c.correct_position or 0 for c in choices)
        if pos != list(range(1, len(choices) + 1)):
            errors.append("posições de ordenação inconsistentes")
        elif [c.correct_position for c in sorted(choices, key=lambda c: c.position)] == pos:
            warnings.append("ordem exibida já é a ordem correta")
    elif ex.interaction == "match":
        if len(choices) < 2 or any(not c.match_text for c in choices):
            errors.append("pares incompletos")
    elif ex.interaction == "text" and ex.comparison_mode not in ("manual", "self"):
        for b in range(max(1, ex.blank_count)):
            if not any(a.blank_index == b for a in answers):
                errors.append(f"lacuna {b + 1} sem resposta aceita")
    elif ex.interaction == "writing":
        if not ex.model_answer or not ex.criteria_list():
            errors.append("produção escrita sem resposta-modelo ou critérios")
    if ex.passage_id and not ex.evidence:
        warnings.append("questão de texto sem trecho de fundamentação")
    if ex.exercise_type == "text_interpretation" and not ex.passage_id:
        warnings.append("interpretação sem texto associado")
    if ex.origin == Origin.ADAPTED and not ex.adaptation_notes:
        errors.append("adaptação sem descrição")
    if not ex.objectives.exists():
        warnings.append("sem objetivo de aprendizagem")
    if not ex.passage_id and not ex.grammar_topics.exists() and not ex.vocabulary_topics.exists():
        warnings.append("sem tópico gramatical nem tema de vocabulário")
    if FORBIDDEN_AUDIO.search(ex.instruction):
        errors.append("menciona áudio/pronúncia (fora do escopo)")
    if ex.review_status != "reviewed":
        warnings.append("revisão pedagógica não concluída")
    return errors, warnings


def report() -> dict:
    rows = []
    totals = Counter()
    for ex in (Exercise.objects.filter(is_active=True).select_related("chapter")
               .prefetch_related("choices", "accepted_answers")):
        errs, warns = exercise_problems(ex)
        totals["exercises"] += 1
        if errs or warns:
            rows.append({"exercise": ex, "errors": errs, "warnings": warns})
        totals["errors"] += len(errs)
        totals["warnings"] += len(warns)
    chapter_rows = []
    for ch in Chapter.objects.filter(is_active=True, is_planned=False):
        exs = Exercise.objects.filter(chapter=ch, is_active=True)
        problems = []
        diffs = set(exs.values_list("difficulty", flat=True))
        missing = [d for d in range(1, 6) if d not in diffs]
        if missing:
            problems.append(f"faltam questões de dificuldade {', '.join(map(str, missing))}")
        if Passage.objects.filter(chapter=ch, is_active=True).count() < 2:
            problems.append("menos de dois textos de interpretação")
        if not exs.filter(is_assessment=True).exists():
            problems.append("sem avaliação final")
        if not ch.objectives.exists():
            problems.append("sem objetivos")
        if not ch.grammar_topics.exists():
            problems.append("sem tópicos gramaticais")
        if not ch.vocabulary_topics.exists():
            problems.append("sem vocabulário")
        for p in Passage.objects.filter(chapter=ch, is_active=True):
            if not p.exercises.filter(is_active=True).exists():
                problems.append(f"texto '{p.title}' sem perguntas")
        totals["errors"] += len(problems)
        chapter_rows.append({"chapter": ch, "problems": problems,
                             "types": sorted(set(exs.values_list("exercise_type", flat=True)))})
    all_types = set(Exercise.objects.filter(is_active=True).values_list("exercise_type", flat=True))
    missing_types = [label for value, label in Exercise.Type.choices if value not in all_types]
    return {"rows": rows, "chapters": chapter_rows, "totals": dict(totals), "missing_types": missing_types}
