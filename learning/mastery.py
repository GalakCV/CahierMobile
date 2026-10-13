"""
Cálculo de domínio (0–100). Algoritmo documentado em docs/ALGORITMOS.md.

Resumo:
    domínio = min(teto, precisão × confiança) − penalidade

    precisão  = média ponderada das notas das tentativas, com pesos por
                dificuldade (0,6 a 1,4), recência (0,9^posição, mínimo 0,2),
                velocidade (×0,85 se demorou mais que o dobro do estimado) e
                retenção (×1,3 se acertou após ≥3 dias da tentativa anterior).
    confiança = 0,5 × cobertura + 0,25 × variedade + 0,25 × evidência,
                limitada a 0,3 + 0,7 × evidência (pouca evidência = pouca confiança)
                cobertura  = questões diferentes respondidas / questões do escopo
                variedade  = tipos diferentes respondidos / min(5, tipos disponíveis)
                evidência  = min(1, tentativas avaliadas / 12)
    teto      = 0,90 enquanto não houver prova de retenção; 1,00 depois.
    penalidade = 0,05 por questão com dois erros seguidos mais recentes (máx. 0,20).

Uma única resposta certa nunca gera 100%: cobertura, variedade e evidência
continuam baixas.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from content.models import Chapter, Competency, Exercise, GrammarTopic, LearningObjective, VocabularyTopic

from .models import Attempt, Mastery

DIFFICULTY_WEIGHT = {1: 0.6, 2: 0.8, 3: 1.0, 4: 1.2, 5: 1.4}
RECENCY_DECAY = 0.9
RECENCY_FLOOR = 0.2
SLOW_FACTOR = 0.85
RETENTION_BONUS = 1.3
RETENTION_GAP = timedelta(days=3)
EVIDENCE_TARGET = 12
EVIDENCE_FLOOR = 0.3
CAP_WITHOUT_RETENTION = 0.90
REPEAT_PENALTY = 0.05
MAX_PENALTY = 0.20

LEVELS = [(90, "Dominado"), (75, "Forte"), (50, "Bom"), (20, "Em desenvolvimento"), (0, "Inicial")]


def level_label(score: float) -> str:
    for threshold, label in LEVELS:
        if score >= threshold:
            return label
    return "Inicial"


def compute(exercises: list[Exercise], attempts: list[Attempt]) -> dict:
    """Função pura: recebe questões do escopo e tentativas (qualquer ordem)."""
    total = len(exercises)
    if not total:
        return _empty(total)
    graded = []
    for a in attempts:
        s = a.effective_score
        if s is not None:
            graded.append((a, s))
    if not graded:
        return _empty(total)

    graded.sort(key=lambda p: (p[0].created_at, p[0].pk or 0))
    by_ex_type = {e.pk: e.exercise_type for e in exercises}
    diff = {e.pk: e.difficulty for e in exercises}
    est = {e.pk: max(10, e.estimated_seconds) for e in exercises}

    last_seen: dict[int, object] = {}
    retention_flags = []
    for a, s in graded:
        prev = last_seen.get(a.exercise_id)
        retention_flags.append(bool(prev and s >= 0.99 and a.created_at - prev >= RETENTION_GAP))
        last_seen[a.exercise_id] = a.created_at

    n = len(graded)
    num = den = 0.0
    for idx, ((a, s), retained) in enumerate(zip(graded, retention_flags)):
        rank_from_newest = n - 1 - idx
        w = DIFFICULTY_WEIGHT.get(diff.get(a.exercise_id, 3), 1.0)
        w *= max(RECENCY_FLOOR, RECENCY_DECAY ** rank_from_newest)
        if a.duration_seconds and a.duration_seconds > 2 * est.get(a.exercise_id, 45):
            w *= SLOW_FACTOR
        if retained:
            w *= RETENTION_BONUS
        num += w * s
        den += w
    accuracy = num / den if den else 0.0

    attempted = {a.exercise_id for a, _ in graded}
    coverage = len(attempted) / total
    types_available = {e.exercise_type for e in exercises}
    types_done = {by_ex_type.get(eid) for eid in attempted if eid in by_ex_type}
    variety = min(1.0, len(types_done) / max(1, min(5, len(types_available))))
    evidence = min(1.0, n / EVIDENCE_TARGET)
    confidence = 0.5 * coverage + 0.25 * variety + 0.25 * evidence
    # Com pouca evidência a confiança fica limitada, mesmo num escopo pequeno.
    confidence = min(confidence, EVIDENCE_FLOOR + (1 - EVIDENCE_FLOOR) * evidence)

    history = defaultdict(list)
    for a, s in graded:
        history[a.exercise_id].append(s)
    repeated = sum(1 for scores in history.values() if len(scores) >= 2 and scores[-1] < 0.5 and scores[-2] < 0.5)
    penalty = min(MAX_PENALTY, REPEAT_PENALTY * repeated)
    has_retention = any(retention_flags)
    cap = 1.0 if has_retention else CAP_WITHOUT_RETENTION

    value = max(0.0, min(cap, accuracy * confidence) - penalty)
    score = round(value * 100, 1)
    return {
        "score": score,
        "level": level_label(score),
        "accuracy": round(accuracy * 100, 1),
        "coverage": round(coverage * 100, 1),
        "variety": round(variety * 100, 1),
        "evidence": round(evidence * 100, 1),
        "confidence": round(confidence * 100, 1),
        "attempts": n,
        "attempted_exercises": len(attempted),
        "total_exercises": total,
        "repeated_errors": repeated,
        "penalty": round(penalty * 100, 1),
        "retention": has_retention,
        "cap": round(cap * 100),
    }


def _empty(total: int) -> dict:
    return {"score": 0.0, "level": "Inicial", "accuracy": 0.0, "coverage": 0.0, "variety": 0.0, "evidence": 0.0,
            "confidence": 0.0, "attempts": 0, "attempted_exercises": 0, "total_exercises": total,
            "repeated_errors": 0, "penalty": 0.0, "retention": False, "cap": 90}


# ---------------------------------------------------------------------------
# Escopos
# ---------------------------------------------------------------------------

def _active_exercises():
    return Exercise.objects.filter(is_active=True, chapter__is_active=True)


def scope_queryset(scope: str, object_id: int):
    qs = _active_exercises()
    if scope == Mastery.Scope.CHAPTER:
        return qs.filter(chapter_id=object_id)
    if scope == Mastery.Scope.OBJECTIVE:
        return qs.filter(objectives__id=object_id)
    if scope == Mastery.Scope.GRAMMAR:
        return qs.filter(grammar_topics__id=object_id)
    if scope == Mastery.Scope.VOCABULARY:
        return qs.filter(vocabulary_topics__id=object_id)
    if scope == Mastery.Scope.COMPETENCY:
        return qs.filter(competency_id=object_id)
    return qs


def scope_label(scope: str, object_id: int) -> str:
    model = {Mastery.Scope.CHAPTER: Chapter, Mastery.Scope.OBJECTIVE: LearningObjective,
             Mastery.Scope.GRAMMAR: GrammarTopic, Mastery.Scope.VOCABULARY: VocabularyTopic,
             Mastery.Scope.COMPETENCY: Competency}.get(scope)
    if model is None:
        return "Geral"
    obj = model.objects.filter(pk=object_id).first()
    return str(obj) if obj else "—"


def compute_scope(scope: str, object_id: int = 0) -> dict:
    exercises = list(scope_queryset(scope, object_id).distinct())
    ids = [e.pk for e in exercises]
    attempts = list(Attempt.objects.filter(exercise_id__in=ids).select_related("written"))
    return compute(exercises, attempts)


def refresh_scope(scope: str, object_id: int = 0) -> Mastery:
    data = compute_scope(scope, object_id)
    obj, _ = Mastery.objects.update_or_create(
        scope=scope, object_id=object_id,
        defaults={"label": scope_label(scope, object_id), "score": data["score"], "details": data})
    return obj


def refresh_for_exercise(exercise: Exercise) -> None:
    """Recalcula todos os escopos afetados por uma nova tentativa."""
    refresh_scope(Mastery.Scope.OVERALL, 0)
    refresh_scope(Mastery.Scope.CHAPTER, exercise.chapter_id)
    refresh_scope(Mastery.Scope.COMPETENCY, exercise.competency_id)
    for oid in exercise.objectives.values_list("id", flat=True):
        refresh_scope(Mastery.Scope.OBJECTIVE, oid)
    for gid in exercise.grammar_topics.values_list("id", flat=True):
        refresh_scope(Mastery.Scope.GRAMMAR, gid)
    for vid in exercise.vocabulary_topics.values_list("id", flat=True):
        refresh_scope(Mastery.Scope.VOCABULARY, vid)


def refresh_all() -> None:
    refresh_scope(Mastery.Scope.OVERALL, 0)
    for cid in Chapter.objects.filter(is_active=True).values_list("id", flat=True):
        refresh_scope(Mastery.Scope.CHAPTER, cid)
    for cid in Competency.objects.values_list("id", flat=True):
        refresh_scope(Mastery.Scope.COMPETENCY, cid)
    for oid in LearningObjective.objects.filter(is_active=True).values_list("id", flat=True):
        refresh_scope(Mastery.Scope.OBJECTIVE, oid)
    for gid in GrammarTopic.objects.filter(is_active=True).values_list("id", flat=True):
        refresh_scope(Mastery.Scope.GRAMMAR, gid)
    for vid in VocabularyTopic.objects.filter(is_active=True).values_list("id", flat=True):
        refresh_scope(Mastery.Scope.VOCABULARY, vid)


def get_score(scope: str, object_id: int = 0) -> float:
    m = Mastery.objects.filter(scope=scope, object_id=object_id).first()
    return m.score if m else 0.0


def competency_scores() -> dict[int, float]:
    return dict(Mastery.objects.filter(scope=Mastery.Scope.COMPETENCY).values_list("object_id", "score"))


def recent_window(days: int = 14):
    return Q(created_at__gte=timezone.now() - timedelta(days=days))
