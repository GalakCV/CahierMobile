"""Exportações em JSON: conteúdo (tudo ou um capítulo), progresso, caderno de erros e completo."""
from __future__ import annotations

from django.utils import timezone

from content.models import Chapter, Competency, Course, Exercise, Source
from learning.models import Attempt, Mastery, ReviewItem, StudySession, UserSetting

from .importer import FORMAT, FORMAT_VERSION


def _pairs(items):
    return [{"fr": i.get("fr", ""), "pt": i.get("pt", "")} for i in items or []]


def export_exercise(ex: Exercise) -> dict:
    d = {
        "code": ex.code, "type": ex.exercise_type, "interaction": ex.interaction,
        "instruction": ex.instruction, "prompt": ex.prompt, "explanation": ex.explanation,
        "difficulty": ex.difficulty, "cefr_level": ex.cefr_level, "estimated_seconds": ex.estimated_seconds,
        "competency": ex.competency.code, "origin": ex.origin, "source": ex.source.key,
        "review_status": ex.review_status, "comparison": ex.comparison_mode,
        "accent_insensitive": ex.accent_insensitive, "is_assessment": ex.is_assessment,
        "position": ex.position, "is_active": ex.is_active,
        "objectives": list(ex.objectives.values_list("code", flat=True)),
        "grammar_topics": list(ex.grammar_topics.values_list("code", flat=True)),
        "vocabulary_topics": list(ex.vocabulary_topics.values_list("code", flat=True)),
    }
    for key, value in (("context", ex.context), ("translation_pt", ex.translation_pt), ("evidence", ex.evidence),
                       ("model_answer", ex.model_answer), ("adaptation_notes", ex.adaptation_notes),
                       ("reading_skill", ex.reading_skill)):
        if value:
            d[key] = value
    if ex.criteria:
        d["criteria"] = list(ex.criteria)
    if ex.passage_id:
        d["passage"] = ex.passage.code
    choices = list(ex.choices.all().order_by("position", "id"))
    if choices:
        if ex.interaction == "order":
            d["choices"] = [{"text": c.text, "order": c.correct_position} for c in
                            sorted(choices, key=lambda c: c.correct_position or 0)]
        else:
            out = []
            for c in choices:
                item = {"text": c.text}
                if ex.interaction in ("single", "multiple"):
                    item["correct"] = c.is_correct
                if c.match_text:
                    item["match"] = c.match_text
                if c.feedback:
                    item["feedback"] = c.feedback
                out.append(item)
            d["choices"] = out
    answers = list(ex.accepted_answers.all())
    if answers:
        d["answers"] = [{"text": a.text, "blank": a.blank_index, "primary": a.is_primary} for a in answers]
    related = [{"code": r.to_exercise.code, "kind": r.kind} for r in ex.relations_from.select_related("to_exercise")]
    if related:
        d["related"] = related
    return d


def export_chapter(ch: Chapter) -> dict:
    return {
        "code": ch.code, "number": ch.number, "title": ch.title, "theme": ch.theme,
        "description": ch.description, "cefr_level": ch.cefr_level, "is_active": ch.is_active,
        "is_planned": ch.is_planned, "useful_expressions": _pairs(ch.useful_expressions),
        "review_summary": ch.review_points(), "reference_note": ch.reference_note,
        "objectives": [{"code": o.code, "description": o.description, "position": o.position,
                        "competencies": list(o.competencies.values_list("code", flat=True))}
                       for o in ch.objectives.all()],
        "grammar_topics": [{"code": g.code, "title": g.title, "summary": g.summary, "examples": _pairs(g.examples),
                            "tables": g.tables, "notes": g.notes, "common_errors": g.common_errors,
                            "position": g.position} for g in ch.grammar_topics.all()],
        "vocabulary_topics": [{"code": v.code, "title": v.title, "position": v.position,
                               "items": [{"fr": i.french, "pt": i.portuguese, "gender": i.gender,
                                          "example": i.example} for i in v.items.all()]}
                              for v in ch.vocabulary_topics.all()],
        "passages": [{"code": p.code, "title": p.title, "text_type": p.text_type, "body": p.body,
                      "translation_pt": p.translation_pt, "cefr_level": p.cefr_level, "difficulty": p.difficulty,
                      "key_vocabulary": _pairs(p.key_vocabulary), "useful_structures": _pairs(p.useful_structures),
                      "grammar_topics": list(p.grammar_topics.values_list("code", flat=True)),
                      "vocabulary_topics": list(p.vocabulary_topics.values_list("code", flat=True)),
                      "author": p.author, "source": p.source.key, "origin": p.origin,
                      "adaptation_notes": p.adaptation_notes, "review_status": p.review_status,
                      "position": p.position, "is_active": p.is_active} for p in ch.passages.all()],
        "exercises": [export_exercise(e) for e in
                      ch.exercises.select_related("competency", "source", "passage").order_by("position", "id")],
    }


def export_content(chapter: Chapter | None = None) -> dict:
    chapters = [chapter] if chapter else list(Chapter.objects.order_by("number"))
    used_sources = set()
    for ch in chapters:
        used_sources |= set(ch.exercises.values_list("source__key", flat=True))
        used_sources |= set(ch.passages.values_list("source__key", flat=True))
    course = chapters[0].course if chapters else Course.objects.first()
    if course and course.reference_source:
        used_sources.add(course.reference_source.key)
    sources = Source.objects.all() if chapter is None else Source.objects.filter(key__in=used_sources)
    data = {
        "format": FORMAT, "version": FORMAT_VERSION, "exported_at": timezone.now().isoformat(),
        "sources": [{"key": s.key, "title": s.title, "author": s.author, "url": s.url, "license": s.license_name,
                     "license_url": s.license_url, "notes": s.notes} for s in sources],
        "competencies": [{"code": c.code, "name": c.name, "description": c.description, "position": c.position}
                         for c in Competency.objects.all()],
        "chapters": [export_chapter(ch) for ch in chapters],
    }
    if course:
        data["course"] = {"code": course.code, "title": course.title, "description": course.description,
                          "reference_source": course.reference_source.key if course.reference_source else ""}
        if not data["course"]["reference_source"]:
            del data["course"]["reference_source"]
    return data


def export_progress() -> dict:
    s = UserSetting.get()
    return {
        "format": "cahier-progress", "version": 1, "exported_at": timezone.now().isoformat(),
        "settings": {"display_name": s.display_name, "default_session_size": s.default_session_size,
                     "daily_goal_minutes": s.daily_goal_minutes, "show_keyboard": s.show_keyboard,
                     "font_size": s.font_size, "theme": s.theme},
        "attempts": [{
            "id": a.pk, "exercise": a.exercise.code, "version": a.exercise_version,
            "session": a.session_id, "mode": a.mode, "answer": a.answer, "answer_display": a.answer_display,
            "correct_display": a.correct_display, "result": a.result, "score": a.score,
            "effective_score": a.effective_score, "duration_seconds": a.duration_seconds,
            "used_translation": a.used_translation, "created_at": a.created_at.isoformat(),
            "written": ({"text": a.written.text, "assessed_score": a.written.assessed_score,
                         "assessed_by": a.written.assessed_by, "criteria_checked": a.written.criteria_checked}
                        if hasattr(a, "written") else None),
        } for a in Attempt.objects.select_related("exercise", "written").order_by("created_at", "id")],
        "sessions": [{
            "id": ss.pk, "kind": ss.kind, "mode": ss.mode, "status": ss.status, "title": ss.title,
            "chapter": ss.chapter.code if ss.chapter else None, "started_at": ss.started_at.isoformat(),
            "finished_at": ss.finished_at.isoformat() if ss.finished_at else None,
            "result_score": ss.result_score,
            "items": list(ss.items.order_by("position").values_list("exercise__code", flat=True)),
        } for ss in StudySession.objects.select_related("chapter").order_by("started_at")],
        "review_items": [_review_dict(r) for r in ReviewItem.objects.select_related("exercise")],
        "mastery": [{"scope": m.scope, "label": m.label, "score": m.score, "details": m.details}
                    for m in Mastery.objects.all()],
    }


def _review_dict(r: ReviewItem) -> dict:
    return {"exercise": r.exercise.code, "stage": r.stage, "interval_days": r.interval_days,
            "due_at": r.due_at.isoformat(), "error_count": r.error_count, "correct_streak": r.correct_streak,
            "recovery": r.recovery, "flagged": r.flagged}


def export_error_notebook() -> dict:
    rows = []
    for r in (ReviewItem.objects.filter(error_count__gt=0)
              .select_related("exercise", "exercise__chapter", "exercise__competency")):
        ex = r.exercise
        last = Attempt.objects.filter(exercise=ex).exclude(result="correct").order_by("-created_at").first()
        rows.append({
            "questao": ex.prompt, "codigo": ex.code, "resposta_do_usuario": r.last_answer,
            "resposta_correta": last.correct_display if last else "", "explicacao": ex.explanation,
            "capitulo": str(ex.chapter), "competencia": ex.competency.name,
            "topicos_gramaticais": [str(g) for g in ex.grammar_topics.all()],
            "vocabulario": [str(v) for v in ex.vocabulary_topics.all()],
            "quantidade_de_erros": r.error_count,
            "ultima_tentativa": r.last_attempt_at.isoformat() if r.last_attempt_at else None,
            "proxima_revisao": r.due_at.isoformat(), "estado": r.get_recovery_display(),
        })
    return {"format": "cahier-error-notebook", "version": 1, "exported_at": timezone.now().isoformat(),
            "items": rows}


def export_full() -> dict:
    return {"format": "cahier-full", "version": 1, "exported_at": timezone.now().isoformat(),
            "content": export_content(), "progress": export_progress(), "error_notebook": export_error_notebook()}
