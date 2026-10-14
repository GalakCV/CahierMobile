"""
Revisão espaçada e caderno de erros. Algoritmo documentado em docs/ALGORITMOS.md.

Etapas e intervalos: 0→1 dia, 1→3, 2→7, 3→14, 4→30 dias.
- Acerto: avança uma etapa (questão nova acertada de primeira entra direto na etapa 2).
- Parcial: recua uma etapa.
- Erro: recua duas etapas (mínimo 0) e soma um erro.
- Questões com erros repetidos têm o intervalo encurtado: intervalo ÷ (1 + 0,25 × (erros − 1)), até 4 erros.
- Na etapa 4 a questão segue sendo revisada a cada 30 dias (manutenção).
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from content.models import Exercise

from .models import ReviewFlag, ReviewItem

INTERVALS = ReviewItem.INTERVALS
FIRST_CORRECT_STAGE = 2


def interval_for(stage: int, error_count: int) -> int:
    base = INTERVALS[max(0, min(stage, len(INTERVALS) - 1))]
    if error_count >= 2:
        factor = 1 + 0.25 * min(error_count - 1, 4)
        base = max(1, round(base / factor))
    return base


def outcome(score: float) -> str:
    if score >= 0.99:
        return "correct"
    if score >= 0.5:
        return "partial"
    return "incorrect"


def recovery_state(item: ReviewItem) -> str:
    if item.error_count == 0:
        return ""
    if item.last_result in ("incorrect", "partial"):
        return ReviewItem.Recovery.RECENT
    if item.correct_streak >= 3 and item.stage >= 3:
        return ReviewItem.Recovery.OVERCOME
    if item.correct_streak >= 2:
        return ReviewItem.Recovery.IMPROVING
    return ReviewItem.Recovery.REVIEWING


def register(exercise: Exercise, score: float, answer_display: str = "", now=None,
             from_review: bool = False) -> ReviewItem:
    """Atualiza a fila de revisão depois de uma resposta avaliada."""
    now = now or timezone.now()
    result = outcome(score)
    item = ReviewItem.objects.filter(exercise=exercise).first()
    if item is None:
        item = ReviewItem(exercise=exercise, due_at=now)
        if result == "correct":
            item.stage = FIRST_CORRECT_STAGE
            item.correct_streak = 1
        else:
            item.stage = 0
            item.error_count = 1
            item.last_error_at = now
            item.last_answer = answer_display
    else:
        if result == "correct":
            item.stage = min(item.stage + 1, len(INTERVALS) - 1)
            item.correct_streak += 1
            item.flagged = False
        elif result == "partial":
            item.stage = max(item.stage - 1, 0)
            item.correct_streak = 0
            item.error_count += 1
            item.last_error_at = now
            item.last_answer = answer_display
        else:
            item.stage = max(item.stage - 2, 0)
            item.correct_streak = 0
            item.error_count += 1
            item.last_error_at = now
            item.last_answer = answer_display
        if from_review:
            item.review_count += 1
    item.last_result = result
    item.last_attempt_at = now
    item.interval_days = interval_for(item.stage, item.error_count)
    item.due_at = now + timedelta(days=item.interval_days)
    if item.flagged:
        item.due_at = now  # marcada pelo estudante: continua pendente até ser acertada
    item.recovery = recovery_state(item)
    item.save()
    return item


def flag(exercise: Exercise, now=None, record: bool = True) -> ReviewItem:
    now = now or timezone.now()
    if record:
        ReviewFlag.objects.create(exercise=exercise, created_at=now)
    item, created = ReviewItem.objects.get_or_create(exercise=exercise, defaults={"due_at": now})
    item.flagged = True
    item.due_at = now
    item.save(update_fields=["flagged", "due_at"])
    return item


def due_queryset(now=None):
    now = now or timezone.now()
    return ReviewItem.objects.filter(due_at__lte=now, exercise__is_active=True,
                                     exercise__chapter__is_active=True).select_related("exercise")


def priority(item: ReviewItem, weak_competency: dict[int, float], now=None) -> float:
    """Maior = mais urgente. Atraso + erros + marcação + fragilidade da competência."""
    now = now or timezone.now()
    overdue_days = max(0.0, (now - item.due_at).total_seconds() / 86400)
    comp_gap = (100 - weak_competency.get(item.exercise.competency_id, 0.0)) / 50  # 0 a 2
    return overdue_days + 1.5 * min(item.error_count, 5) + (3 if item.flagged else 0) + comp_gap
