"""Construtores mínimos de dados para os testes."""
from content.models import (AcceptedAnswer, Chapter, Choice, Competency, Course, Exercise, GrammarTopic,
                            LearningObjective, Passage, Source, VocabularyTopic)


def basics(number=1, code=None):
    src, _ = Source.objects.get_or_create(key="test-src", defaults=dict(title="Fonte de teste", author="Autor", license_name="CC BY 4.0"))
    comp, _ = Competency.objects.get_or_create(code="grammaire", defaults=dict(name="Gramática"))
    comp2, _ = Competency.objects.get_or_create(code="lecture", defaults=dict(name="Leitura"))
    course, _ = Course.objects.get_or_create(code="fle", defaults=dict(title="Curso"))
    code = code or f"ch{number:02d}"
    ch = Chapter.objects.create(course=course, code=code, number=number, title=f"Capítulo {number}", theme="Tema",
                                description="Descrição")
    obj = LearningObjective.objects.create(chapter=ch, code=f"{code}.obj", description="Objetivo")
    g = GrammarTopic.objects.create(chapter=ch, code=f"{code}.g", title="être", summary="Resumo")
    v = VocabularyTopic.objects.create(chapter=ch, code=f"{code}.v", title="Sala")
    return {"source": src, "comp": comp, "comp2": comp2, "course": course, "chapter": ch, "objective": obj,
            "grammar": g, "vocab": v}


_counter = [0]


def exercise(b, *, interaction="single", exercise_type=None, choices=None, answers=None, difficulty=2,
             comparison="accepted_list", accent_insensitive=False, prompt="Prompt", passage=None, code=None,
             is_assessment=False, competency=None, criteria=None, model_answer="", estimated_seconds=45, **extra):
    _counter[0] += 1
    default_type = {"single": "mc_single", "multiple": "mc_multiple", "text": "fill_blank", "order": "order_words",
                    "match": "match_pairs", "writing": "guided_writing"}[interaction]
    ex = Exercise.objects.create(
        chapter=b["chapter"], code=code or f"ex-{_counter[0]}", exercise_type=exercise_type or default_type,
        interaction=interaction, instruction="Instrução", prompt=prompt, explanation="Explicação",
        difficulty=difficulty, competency=competency or b["comp"], source=b["source"], comparison_mode=comparison,
        accent_insensitive=accent_insensitive, passage=passage, is_assessment=is_assessment,
        criteria=criteria or [], model_answer=model_answer, estimated_seconds=estimated_seconds, **extra)
    for i, c in enumerate(choices or []):
        if isinstance(c, tuple):
            text, val = c
        else:
            text, val = c, False
        kwargs = {}
        if interaction == "order":
            kwargs["correct_position"] = val
        elif interaction == "match":
            kwargs["match_text"] = val
        else:
            kwargs["is_correct"] = bool(val)
        Choice.objects.create(exercise=ex, text=text, position=i, **kwargs)
    for a in answers or []:
        if isinstance(a, tuple):
            AcceptedAnswer.objects.create(exercise=ex, text=a[0], blank_index=a[1], is_primary=a[2] if len(a) > 2 else True)
        else:
            AcceptedAnswer.objects.create(exercise=ex, text=a)
    ex.objectives.add(b["objective"])
    ex.grammar_topics.add(b["grammar"])
    ex.snapshot_version("teste")
    return ex


def passage(b, code="p1"):
    return Passage.objects.create(chapter=b["chapter"], code=code, title="Texto", text_type="dialogue",
                                  body="A : Bonjour.\nB : Salut.", difficulty=2, author="Autor", source=b["source"])
