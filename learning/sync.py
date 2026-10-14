"""
Sincronização de progresso entre o computador e o celular (formato ``cahier-sync``).

O mesmo arquivo serve nos dois sentidos. A mescla é por identificador (uid):
- tentativas novas são acrescentadas (as existentes nunca são alteradas);
- a autoavaliação de um texto é atualizada se a do arquivo for mais recente;
- marcações para revisão, avaliações finais de capítulo e problemas sinalizados também são somados.

Depois da mescla, a fila de revisão é reconstruída a partir do histórico completo
(``rebuild_review``) e o domínio é recalculado — com as mesmas regras do celular.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from content.models import Chapter, ContentIssue, Exercise

from . import mastery, review
from .models import Attempt, ReviewFlag, ReviewItem, StudySession, WrittenAnswer

FORMAT = "cahier-sync"
VERSION = 1
RESULTS = {"correct", "partial", "incorrect", "pending"}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt


def export_sync() -> dict:
    attempts = []
    for a in Attempt.objects.select_related("exercise", "written", "session").order_by("created_at", "id"):
        w = getattr(a, "written", None)
        attempts.append({
            "uid": str(a.uid), "exercise": a.exercise.code, "version": a.exercise_version, "mode": a.mode,
            "from_review": a.from_review, "answer": a.answer, "answer_display": a.answer_display,
            "correct_display": a.correct_display, "result": a.result, "score": a.score, "feedback": a.feedback,
            "duration_seconds": a.duration_seconds, "used_translation": a.used_translation,
            "created_at": _iso(a.created_at), "device": a.device,
            "written": None if w is None else {
                "text": w.text, "criteria_checked": w.criteria_checked, "assessed_score": w.assessed_score,
                "assessed_by": w.assessed_by, "assessed_at": _iso(w.assessed_at),
                "marked_for_review": w.marked_for_review, "notes": w.notes},
        })
    return {
        "format": FORMAT, "version": VERSION, "device": "desktop", "exported_at": timezone.now().isoformat(),
        "attempts": attempts,
        "flags": [{"uid": str(f.uid), "exercise": f.exercise.code, "created_at": _iso(f.created_at), "device": f.device}
                  for f in ReviewFlag.objects.select_related("exercise").order_by("created_at")],
        "assessments": [{"uid": str(s.uid), "chapter": s.chapter.code, "result_score": s.result_score,
                         "finished_at": _iso(s.finished_at), "title": s.title, "device": s.device}
                        for s in StudySession.objects.filter(kind=StudySession.Kind.CHAPTER_ASSESSMENT,
                                                             status=StudySession.Status.FINISHED,
                                                             result_score__isnull=False).select_related("chapter")],
        "issues": [{"uid": str(i.uid), "exercise": i.exercise.code, "version": i.exercise_version, "kind": i.kind,
                    "comment": i.comment, "user_answer": i.user_answer, "created_at": _iso(i.created_at)}
                   for i in ContentIssue.objects.select_related("exercise")],
    }


@dataclass
class SyncReport:
    added: dict = field(default_factory=lambda: {"tentativas": 0, "marcações": 0, "avaliações": 0, "problemas": 0})
    updated_written: int = 0
    skipped: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def total_added(self) -> int:
        return sum(self.added.values())


def _uid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def validate(data) -> list[str]:
    if not isinstance(data, dict):
        return ["O arquivo deve conter um objeto JSON."]
    errors = []
    if data.get("format") != FORMAT:
        errors.append("Este não é um arquivo de sincronização do Cahier (format = cahier-sync).")
    if data.get("version") != VERSION:
        errors.append(f"Versão do arquivo não suportada: {data.get('version')}.")
    for key in ("attempts", "flags", "assessments", "issues"):
        if key in data and not isinstance(data[key], list):
            errors.append(f"'{key}' deve ser uma lista.")
    for i, a in enumerate(data.get("attempts", []) or []):
        if not isinstance(a, dict) or not _uid(a.get("uid")) or not isinstance(a.get("exercise"), str) \
                or a.get("result") not in RESULTS or not isinstance(a.get("score"), (int, float)) \
                or not _dt(a.get("created_at")):
            errors.append(f"tentativa {i + 1}: dados incompletos ou inválidos.")
            if len(errors) > 20:
                break
    return errors


@transaction.atomic
def import_sync(data) -> SyncReport:
    rep = SyncReport()
    rep.errors = validate(data)
    if rep.errors:
        return rep
    exercises = {e.code: e for e in Exercise.objects.all()}
    known = set(Attempt.objects.values_list("uid", flat=True))
    device = "mobile" if data.get("device") == "mobile" else "desktop"
    missing = set()
    for a in data.get("attempts", []):
        uid = _uid(a["uid"])
        ex = exercises.get(a["exercise"])
        if ex is None:
            missing.add(a["exercise"])
            continue
        w = a.get("written") if isinstance(a.get("written"), dict) else None
        if uid in known:
            if w and w.get("assessed_score") is not None:
                local = WrittenAnswer.objects.filter(attempt__uid=uid).first()
                incoming_at = _dt(w.get("assessed_at"))
                if local and (local.assessed_at is None or (incoming_at and incoming_at > local.assessed_at)):
                    local.criteria_checked = w.get("criteria_checked") or []
                    local.assessed_score = max(0.0, min(1.0, float(w["assessed_score"])))
                    local.assessed_by = w.get("assessed_by") if w.get("assessed_by") in ("self", "manual") else "self"
                    local.assessed_at = incoming_at or timezone.now()
                    local.marked_for_review = bool(w.get("marked_for_review"))
                    local.notes = str(w.get("notes") or "")[:2000]
                    local.save()
                    rep.updated_written += 1
            continue
        attempt = Attempt.objects.create(
            uid=uid, exercise=ex, exercise_version=int(a.get("version") or ex.version or 1),
            mode=a.get("mode") if a.get("mode") in ("practice", "assessment") else "practice",
            from_review=bool(a.get("from_review")), answer=a.get("answer") or {},
            answer_display=str(a.get("answer_display") or "")[:5000],
            correct_display=str(a.get("correct_display") or "")[:5000], result=a["result"],
            score=max(0.0, min(1.0, float(a["score"]))), feedback=str(a.get("feedback") or "")[:2000],
            duration_seconds=max(0, min(600, int(a.get("duration_seconds") or 0))),
            used_translation=bool(a.get("used_translation")), created_at=_dt(a["created_at"]),
            device=a.get("device") if a.get("device") in ("mobile", "desktop") else device)
        known.add(uid)
        rep.added["tentativas"] += 1
        if a["result"] == "pending":
            w = w or {}
            score = w.get("assessed_score")
            WrittenAnswer.objects.create(
                attempt=attempt, text=str(w.get("text") or a.get("answer_display") or "")[:5000],
                criteria_checked=w.get("criteria_checked") or [],
                assessed_score=None if score is None else max(0.0, min(1.0, float(score))),
                assessed_by=w.get("assessed_by") if w.get("assessed_by") in ("self", "manual") else "",
                assessed_at=_dt(w.get("assessed_at")), marked_for_review=bool(w.get("marked_for_review")),
                notes=str(w.get("notes") or "")[:2000])
    flag_uids = set(ReviewFlag.objects.values_list("uid", flat=True))
    for f in data.get("flags", []) or []:
        uid, ex, at = _uid(f.get("uid")), exercises.get(f.get("exercise")), _dt(f.get("created_at"))
        if not uid or not ex or not at or uid in flag_uids:
            continue
        ReviewFlag.objects.create(uid=uid, exercise=ex, created_at=at, device=device)
        flag_uids.add(uid)
        rep.added["marcações"] += 1
    session_uids = set(StudySession.objects.values_list("uid", flat=True))
    chapters = {c.code: c for c in Chapter.objects.all()}
    for s in data.get("assessments", []) or []:
        uid, ch, at = _uid(s.get("uid")), chapters.get(s.get("chapter")), _dt(s.get("finished_at"))
        if not uid or not ch or not at or uid in session_uids or not isinstance(s.get("result_score"), (int, float)):
            continue
        StudySession.objects.create(
            uid=uid, device=device, mode=StudySession.Mode.ASSESSMENT, kind=StudySession.Kind.CHAPTER_ASSESSMENT,
            status=StudySession.Status.FINISHED, chapter=ch, started_at=at, last_activity_at=at, finished_at=at,
            result_score=max(0.0, min(1.0, float(s["result_score"]))),
            title=str(s.get("title") or f"Avaliação final — {ch.title}")[:180] + (" (celular)" if device == "mobile" else ""))
        session_uids.add(uid)
        rep.added["avaliações"] += 1
    issue_uids = set(ContentIssue.objects.values_list("uid", flat=True))
    for i in data.get("issues", []) or []:
        uid, ex = _uid(i.get("uid")), exercises.get(i.get("exercise"))
        if not uid or not ex or uid in issue_uids or i.get("kind") not in ContentIssue.Kind.values:
            continue
        ContentIssue.objects.create(uid=uid, exercise=ex, exercise_version=int(i.get("version") or 0), kind=i["kind"],
                                    comment=str(i.get("comment") or "")[:2000],
                                    user_answer=str(i.get("user_answer") or "")[:1000])
        issue_uids.add(uid)
        rep.added["problemas"] += 1
    if missing:
        rep.skipped.append(f"{len(missing)} questão(ões) do arquivo não existem neste computador: "
                           + ", ".join(sorted(missing)[:10]))
    if rep.total_added() or rep.updated_written:
        rebuild_review()
        mastery.refresh_all()
    return rep


def rebuild_review() -> int:
    """Reconstrói a fila de revisão a partir de todas as tentativas avaliadas e marcações."""
    events = []
    for a in Attempt.objects.select_related("exercise", "written").order_by("created_at", "id"):
        s = a.effective_score
        if s is None:
            continue
        at = a.created_at
        if a.result == Attempt.Result.PENDING and a.written.assessed_at:
            at = a.written.assessed_at
        events.append((at, 0, a.id, "a", a, s))
    for f in ReviewFlag.objects.select_related("exercise"):
        events.append((f.created_at, 1, f.id, "f", f, None))
    events.sort(key=lambda e: (e[0], e[1], e[2]))
    ReviewItem.objects.all().delete()
    for at, _, _, kind, obj, score in events:
        if kind == "f":
            review.flag(obj.exercise, now=at, record=False)
        else:
            review.register(obj.exercise, score, obj.answer_display, now=at, from_review=obj.from_review)
    return len(events)
