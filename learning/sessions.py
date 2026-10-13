"""
Montagem de sessões e registro de respostas.

Regras de seleção (prática e revisão):
- prioriza questões ainda não feitas, questões com erros e competências frágeis;
- evita, na mesma sessão, questões marcadas como "muito semelhantes" ou "variantes";
- limita a concentração em um mesmo tópico gramatical;
- apresenta as questões em ordem crescente de dificuldade, mantendo juntas as
  perguntas de um mesmo texto.
"""
from __future__ import annotations

import math
import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from content.models import Chapter, Exercise, ExerciseRelation, Passage

from . import grading, mastery, review
from .models import Attempt, ReviewItem, SessionItem, StudySession, WrittenAnswer

MAX_ANSWER_SECONDS = 600  # evita contar tempo ocioso como estudo
PASS_SCORE = 0.7


# ---------------------------------------------------------------------------
# Seleção de questões
# ---------------------------------------------------------------------------

def base_queryset():
    return (Exercise.objects.filter(is_active=True, chapter__is_active=True)
            .select_related("chapter", "passage", "competency")
            .prefetch_related("grammar_topics"))


def similar_map(ids: list[int]) -> dict[int, set[int]]:
    rel = ExerciseRelation.objects.filter(
        Q(from_exercise_id__in=ids) | Q(to_exercise_id__in=ids),
        kind__in=[ExerciseRelation.Kind.SIMILAR, ExerciseRelation.Kind.VARIANT])
    out: dict[int, set[int]] = {}
    for r in rel:
        out.setdefault(r.from_exercise_id, set()).add(r.to_exercise_id)
        out.setdefault(r.to_exercise_id, set()).add(r.from_exercise_id)
    return out


def pick_diverse(ranked: list[Exercise], count: int, topic_cap: int | None = None) -> list[Exercise]:
    """Escolhe ``count`` questões evitando semelhantes e excesso de um mesmo tópico."""
    sims = similar_map([e.pk for e in ranked])
    topic_cap = topic_cap or max(2, math.ceil(count / 2))
    chosen: list[Exercise] = []
    blocked: set[int] = set()
    per_topic: dict[int, int] = {}
    deferred: list[Exercise] = []
    for ex in ranked:
        if len(chosen) >= count:
            break
        if ex.pk in blocked:
            continue
        topics = [t.pk for t in ex.grammar_topics.all()]
        if topics and any(per_topic.get(t, 0) >= topic_cap for t in topics):
            deferred.append(ex)
            continue
        chosen.append(ex)
        blocked |= sims.get(ex.pk, set())
        for t in topics:
            per_topic[t] = per_topic.get(t, 0) + 1
    for ex in deferred:  # completa se faltar questão, sem violar a regra de semelhança
        if len(chosen) >= count:
            break
        if ex.pk not in blocked:
            chosen.append(ex)
            blocked |= sims.get(ex.pk, set())
    return chosen


def progressive_order(exercises: list[Exercise]) -> list[Exercise]:
    """Ordena por dificuldade e mantém as perguntas do mesmo texto juntas."""
    groups: dict[object, list[Exercise]] = {}
    for ex in exercises:
        key = ("p", ex.passage_id) if ex.passage_id else ("e", ex.pk)
        groups.setdefault(key, []).append(ex)
    ordered_groups = sorted(groups.values(), key=lambda g: (min(e.difficulty for e in g), min(e.chapter.number for e in g)))
    out: list[Exercise] = []
    for g in ordered_groups:
        out.extend(sorted(g, key=lambda e: (e.position, e.pk)))
    return out


def rank_for_practice(qs, seed: int | None = None) -> list[Exercise]:
    rng = random.Random(seed)
    candidates = list(qs)
    ids = [e.pk for e in candidates]
    attempted = set(Attempt.objects.filter(exercise_id__in=ids).values_list("exercise_id", flat=True))
    errors = dict(ReviewItem.objects.filter(exercise_id__in=ids).values_list("exercise_id", "error_count"))
    comp = mastery.competency_scores()

    def score(e: Exercise) -> float:
        s = 0.0
        if e.pk not in attempted:
            s += 3
        s += 2 * min(errors.get(e.pk, 0), 3)
        s += (100 - comp.get(e.competency_id, 0.0)) / 50
        return s + rng.random()

    return sorted(candidates, key=score, reverse=True)


def select_practice(*, chapter=None, topic: str = "", competency=None, difficulties=None, count=10,
                    include_assessment=False, seed=None) -> list[Exercise]:
    qs = base_queryset()
    if chapter:
        qs = qs.filter(chapter=chapter)
    if topic:
        kind, _, tid = topic.partition(":")
        if kind == "g" and tid.isdigit():
            qs = qs.filter(grammar_topics__id=int(tid))
        elif kind == "v" and tid.isdigit():
            qs = qs.filter(vocabulary_topics__id=int(tid))
    if competency:
        qs = qs.filter(competency=competency)
    if difficulties:
        qs = qs.filter(difficulty__in=difficulties)
    if not include_assessment:
        qs = qs.filter(is_assessment=False)
    ranked = rank_for_practice(qs.distinct(), seed)
    return progressive_order(pick_diverse(ranked, count))


def select_review(count=15, now=None) -> list[Exercise]:
    now = now or timezone.now()
    comp = mastery.competency_scores()
    items = sorted(review.due_queryset(now), key=lambda i: review.priority(i, comp, now), reverse=True)
    order = {i.exercise_id: n for n, i in enumerate(items)}
    ranked = list(base_queryset().filter(pk__in=list(order)))
    ranked.sort(key=lambda e: order[e.pk])
    return pick_diverse(ranked, count, topic_cap=max(2, math.ceil(count / 3)))


def select_chapter_review(chapter: Chapter, count=12, seed=None) -> list[Exercise]:
    qs = base_queryset().filter(chapter=chapter, is_assessment=False)
    ranked = rank_for_practice(qs, seed)
    return progressive_order(pick_diverse(ranked, count))


def select_chapter_assessment(chapter: Chapter) -> list[Exercise]:
    exs = list(base_queryset().filter(chapter=chapter, is_assessment=True))
    return sorted(exs, key=lambda e: (e.difficulty, e.position, e.pk))


def select_passage(passage: Passage) -> list[Exercise]:
    return list(base_queryset().filter(passage=passage).order_by("position", "id"))


# ---------------------------------------------------------------------------
# Criação e ciclo de vida
# ---------------------------------------------------------------------------

@transaction.atomic
def create_session(exercises: list[Exercise], *, mode=StudySession.Mode.PRACTICE,
                   kind=StudySession.Kind.CUSTOM, chapter=None, passage=None, parent=None,
                   filters=None, title="") -> StudySession:
    if not exercises:
        raise ValueError("Nenhuma questão disponível com esses critérios.")
    session = StudySession.objects.create(mode=mode, kind=kind, chapter=chapter, passage=passage,
                                          parent=parent, filters=filters or {}, title=title)
    SessionItem.objects.bulk_create(
        [SessionItem(session=session, exercise=ex, position=i) for i, ex in enumerate(exercises, start=1)])
    return session


def mark_shown(item: SessionItem) -> None:
    if item.shown_at is None:
        item.shown_at = timezone.now()
        item.save(update_fields=["shown_at"])


@transaction.atomic
def answer_item(item: SessionItem, data, used_translation: bool = False) -> Attempt:
    """Corrige e grava a resposta de um item da sessão (uma única vez)."""
    item = SessionItem.objects.select_for_update().select_related("session", "exercise").get(pk=item.pk)
    if item.answered_at:
        return item.attempt
    session = item.session
    ex = item.exercise
    answer = grading.parse_answer(ex, data)
    result = grading.grade(ex, answer)
    now = timezone.now()
    started = item.shown_at or now
    duration = int(min(MAX_ANSWER_SECONDS, max(0, (now - started).total_seconds())))
    version = ex.current_version()
    attempt = Attempt.objects.create(
        exercise=ex, exercise_version=version.number, session=session, mode=session.mode,
        answer=answer, answer_display=result.answer_display, correct_display=result.correct_display,
        result=result.result, score=result.score, feedback=result.feedback,
        duration_seconds=duration, used_translation=bool(used_translation and not session.is_assessment),
        created_at=now)
    if result.result == "pending":
        text = answer.get("text") or result.answer_display
        WrittenAnswer.objects.create(attempt=attempt, text=text)
    else:
        review.register(ex, result.score, result.answer_display, now,
                        from_review=session.kind == StudySession.Kind.SPACED_REVIEW)
        mastery.refresh_for_exercise(ex)
    item.answered_at = now
    item.attempt = attempt
    item.save(update_fields=["answered_at", "attempt"])
    session.last_activity_at = now
    session.status = StudySession.Status.ACTIVE
    session.save(update_fields=["last_activity_at", "status"])
    return attempt


@transaction.atomic
def self_assess(written: WrittenAnswer, checked: list[int], marked_for_review: bool,
                overall: str | None = None, by: str = "self") -> WrittenAnswer:
    """Registra autoavaliação (ou correção manual) de uma produção escrita."""
    attempt = written.attempt
    ex = attempt.exercise
    criteria = ex.criteria_list()
    valid = sorted({i for i in checked if 0 <= i < len(criteria)})
    if overall in ("correct", "partial", "incorrect"):
        score = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}[overall]
    elif criteria:
        score = len(valid) / len(criteria)
    else:
        score = 0.0
    first_time = written.assessed_score is None
    written.criteria_checked = valid
    written.assessed_score = round(score, 3)
    written.assessed_by = by
    written.assessed_at = timezone.now()
    written.marked_for_review = marked_for_review
    written.save()
    if first_time:
        review.register(ex, score, written.text[:300], from_review=False)
    if marked_for_review:
        review.flag(ex)
    mastery.refresh_for_exercise(ex)
    return written


def pause(session: StudySession) -> None:
    if session.status != StudySession.Status.FINISHED:
        session.status = StudySession.Status.PAUSED
        session.last_activity_at = timezone.now()
        session.save(update_fields=["status", "last_activity_at"])


def finish(session: StudySession) -> StudySession:
    if session.status == StudySession.Status.FINISHED:
        return session
    scores = [a.effective_score for a in Attempt.objects.filter(session=session).select_related("written")]
    graded = [s for s in scores if s is not None]
    session.result_score = round(sum(graded) / len(graded), 3) if graded else None
    session.status = StudySession.Status.FINISHED
    session.finished_at = timezone.now()
    session.save(update_fields=["result_score", "status", "finished_at"])
    return session


def resumable_session():
    return (StudySession.objects.exclude(status=StudySession.Status.FINISHED)
            .order_by("-last_activity_at").first())


def wrong_exercises(session: StudySession) -> list[Exercise]:
    ids = []
    for a in Attempt.objects.filter(session=session).select_related("written").order_by("created_at"):
        s = a.effective_score
        if s is not None and s < 0.99 and a.exercise_id not in ids:
            ids.append(a.exercise_id)
    exs = {e.pk: e for e in base_queryset().filter(pk__in=ids)}
    return [exs[i] for i in ids if i in exs]


# ---------------------------------------------------------------------------
# Estado dos capítulos
# ---------------------------------------------------------------------------

STATUS_LABELS = {
    "not_started": "Não iniciado",
    "in_progress": "Em andamento",
    "needs_review": "Revisão necessária",
    "ready": "Apto para avaliação",
    "completed": "Concluído",
}
READY_MASTERY = 60
READY_COVERAGE = 50


def best_assessment(chapter: Chapter):
    return (StudySession.objects.filter(chapter=chapter, kind=StudySession.Kind.CHAPTER_ASSESSMENT,
                                        status=StudySession.Status.FINISHED, result_score__isnull=False)
            .order_by("-result_score").first())


def chapter_status(chapter: Chapter, now=None) -> dict:
    now = now or timezone.now()
    data = mastery.compute_scope("chapter", chapter.pk)
    ids = list(Exercise.objects.filter(chapter=chapter, is_active=True).values_list("id", flat=True))
    due_errors = ReviewItem.objects.filter(exercise_id__in=ids, due_at__lte=now, error_count__gt=0).count()
    recent = list(Attempt.objects.filter(exercise_id__in=ids, created_at__gte=now - timedelta(days=14),
                                         result__in=["correct", "partial", "incorrect"]).values_list("score", flat=True))
    recent_acc = sum(recent) / len(recent) if recent else None
    best = best_assessment(chapter)
    assessment_count = Exercise.objects.filter(chapter=chapter, is_active=True, is_assessment=True).count()
    if data["attempts"] == 0:
        status = "not_started"
    elif best and best.result_score >= PASS_SCORE:
        status = "completed"
    elif due_errors >= 3 or (recent_acc is not None and len(recent) >= 5 and recent_acc < 0.5):
        status = "needs_review"
    elif data["score"] >= READY_MASTERY and data["coverage"] >= READY_COVERAGE:
        status = "ready"
    else:
        status = "in_progress"
    return {
        "status": status,
        "status_label": STATUS_LABELS[status],
        "mastery": data["score"],
        "mastery_level": data["level"],
        "progress": data["coverage"],
        "details": data,
        "total": len(ids),
        "due_errors": due_errors,
        "assessment_count": assessment_count,
        "assessment_available": assessment_count > 0,
        "best_assessment": round(best.result_score * 100) if best else None,
    }
