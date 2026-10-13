"""Páginas de conteúdo: capítulos, explicações, textos, mapa curricular, créditos e fontes."""
from collections import Counter

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from learning import sessions
from learning.models import Mastery

from .models import Chapter, Course, Exercise, Origin, Passage, Source


def chapter_list(request):
    chapters = (Chapter.objects.filter(is_active=True, is_planned=False)
                .prefetch_related("objectives", "grammar_topics", "vocabulary_topics")
                .annotate(n_exercises=Count("exercises", filter=Q(exercises__is_active=True), distinct=True),
                          n_passages=Count("passages", filter=Q(passages__is_active=True), distinct=True)))
    rows = [{"chapter": ch, "info": sessions.chapter_status(ch)} for ch in chapters]
    planned = Chapter.objects.filter(is_planned=True).order_by("number")
    return render(request, "content/chapter_list.html", {"rows": rows, "planned": planned})


def chapter_detail(request, code):
    ch = get_object_or_404(Chapter.objects.prefetch_related("objectives", "grammar_topics",
                                                            "vocabulary_topics__items"), code=code, is_active=True)
    info = sessions.chapter_status(ch)
    exercises = Exercise.objects.filter(chapter=ch, is_active=True)
    type_counts = Counter(exercises.values_list("exercise_type", flat=True))
    type_labels = dict(Exercise.Type.choices)
    objective_scores = dict(Mastery.objects.filter(scope=Mastery.Scope.OBJECTIVE).values_list("object_id", "score"))
    objectives = [{"obj": o, "score": objective_scores.get(o.pk)} for o in ch.objectives.filter(is_active=True)]
    grammar_scores = dict(Mastery.objects.filter(scope=Mastery.Scope.GRAMMAR).values_list("object_id", "score"))
    grammar = [{"topic": g, "score": grammar_scores.get(g.pk)} for g in ch.grammar_topics.filter(is_active=True)]
    passages = Passage.objects.filter(chapter=ch, is_active=True).annotate(
        n_questions=Count("exercises", filter=Q(exercises__is_active=True)))
    return render(request, "content/chapter_detail.html", {
        "ch": ch, "info": info, "objectives": objectives, "grammar": grammar,
        "vocabulary": ch.vocabulary_topics.filter(is_active=True).prefetch_related("items"),
        "passages": passages,
        "type_counts": sorted(((type_labels[t], n) for t, n in type_counts.items()), key=lambda x: -x[1]),
        "difficulty_counts": sorted(Counter(exercises.values_list("difficulty", flat=True)).items()),
        "n_exercises": exercises.count(),
        "tab": request.GET.get("aba", "visao"),
    })


def passage_detail(request, code):
    p = get_object_or_404(Passage.objects.select_related("chapter", "source"), code=code, is_active=True)
    questions = p.exercises.filter(is_active=True).order_by("position")
    return render(request, "content/passage_detail.html", {"p": p, "questions": questions})


def curriculum_map(request):
    course = Course.objects.select_related("reference_source").first()
    chapters = Chapter.objects.filter(Q(is_active=True) | Q(is_planned=True)).prefetch_related(
        "objectives", "grammar_topics", "vocabulary_topics").order_by("number")
    return render(request, "content/curriculum_map.html", {"course": course, "chapters": chapters})


def credits(request):
    sources = Source.objects.annotate(
        n_ex=Count("exercises", filter=Q(exercises__is_active=True), distinct=True),
        n_pas=Count("passages", filter=Q(passages__is_active=True), distinct=True))
    origin_counts = Counter(Exercise.objects.filter(is_active=True).values_list("origin", flat=True))
    passage_origins = Counter(Passage.objects.filter(is_active=True).values_list("origin", flat=True))
    labels = dict(Origin.choices)
    return render(request, "content/credits.html", {
        "sources": sources, "course": Course.objects.select_related("reference_source").first(),
        "origins": [(labels[k], origin_counts.get(k, 0), passage_origins.get(k, 0)) for k in labels]})


def source_detail(request, key):
    src = get_object_or_404(Source, key=key)
    return render(request, "content/source_detail.html", {
        "src": src, "exercises": src.exercises.select_related("chapter").order_by("chapter__number", "position")[:200],
        "passages": src.passages.select_related("chapter")})


def exercise_preview(request, code):
    """Pré-visualização editorial (mostra resposta, explicação, versões e problemas)."""
    ex = get_object_or_404(Exercise.objects.select_related("chapter", "passage", "source", "competency"), code=code)
    from .quality import exercise_problems
    errors, warnings = exercise_problems(ex)
    from learning.grading import correct_display
    return render(request, "content/exercise_preview.html", {
        "ex": ex, "choices": ex.choices.all(), "answers": ex.accepted_answers.all(), "errors": errors,
        "warnings": warnings, "correct": correct_display(ex), "versions": ex.versions.all()[:10],
        "issues": ex.issues.all()[:10]})
