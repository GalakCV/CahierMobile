"""
Geração do app móvel (PWA) a partir do conteúdo do banco.

``build(dest)`` copia ``mobile/src`` para ``dest`` e grava:
- ``content.json``: pacote de conteúdo (capítulos, textos, questões, fontes) no formato lido pelo app;
- ``sw.js``: service worker com a lista de arquivos e uma versão de cache derivada do conteúdo,
  para que o celular baixe a atualização automaticamente quando algo mudar.

O app móvel identifica as questões pelo ``code`` (estável entre instalações) e as alternativas
pela posição de exibição — por isso a ordem exportada é a mesma do computador.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from content.models import (Chapter, Competency, Course, Exercise, ExerciseRelation, Origin, Passage, Source)

MOBILE_SRC = Path(settings.BASE_DIR) / "mobile" / "src"
BUNDLE_FORMAT = "cahier-mobile-content"
BUNDLE_VERSION = 1


def _pairs(items):
    return [{"fr": i.get("fr", ""), "pt": i.get("pt", "")} for i in items or []]


def content_bundle() -> dict:
    chapters = list(Chapter.objects.filter(is_active=True, is_planned=False).order_by("number")
                    .prefetch_related("objectives", "grammar_topics", "vocabulary_topics__items"))
    planned = list(Chapter.objects.filter(is_planned=True).order_by("number"))
    exercises = list(Exercise.objects.filter(is_active=True, chapter__in=chapters)
                     .select_related("chapter", "passage", "competency", "source")
                     .prefetch_related("choices", "accepted_answers", "objectives", "grammar_topics",
                                       "vocabulary_topics")
                     .order_by("chapter__number", "position", "id"))
    similar: dict[str, set] = {}
    for r in ExerciseRelation.objects.filter(kind__in=["similar", "variant"]).select_related("from_exercise", "to_exercise"):
        similar.setdefault(r.from_exercise.code, set()).add(r.to_exercise.code)
        similar.setdefault(r.to_exercise.code, set()).add(r.from_exercise.code)

    def ex_dict(e: Exercise) -> dict:
        d = {
            "code": e.code, "chapter": e.chapter.code, "type": e.exercise_type, "interaction": e.interaction,
            "instruction": e.instruction, "prompt": e.prompt, "explanation": e.explanation,
            "difficulty": e.difficulty, "seconds": e.estimated_seconds, "competency": e.competency.code,
            "comparison": e.comparison_mode, "position": e.position, "version": e.version or 1,
            "objectives": [o.code for o in e.objectives.all()],
            "grammar": [g.code for g in e.grammar_topics.all()],
            "vocab": [v.code for v in e.vocabulary_topics.all()],
            "origin": e.origin, "source": e.source.key,
        }
        optional = {"passage": e.passage.code if e.passage_id else "", "context": e.context,
                    "translation": e.translation_pt, "evidence": e.evidence, "model": e.model_answer,
                    "reading_skill": e.reading_skill, "adaptation": e.adaptation_notes}
        d.update({k: v for k, v in optional.items() if v})
        if e.accent_insensitive:
            d["accent_insensitive"] = True
        if e.is_assessment:
            d["assessment"] = True
        crit = e.criteria_list()
        if crit:
            d["criteria"] = crit
        choices = sorted(e.choices.all(), key=lambda c: (c.position, c.pk))
        if choices:
            out = []
            for c in choices:
                item = {"t": c.text}
                if c.is_correct:
                    item["ok"] = True
                if c.correct_position:
                    item["pos"] = c.correct_position
                if c.match_text:
                    item["m"] = c.match_text
                if c.feedback:
                    item["fb"] = c.feedback
                out.append(item)
            d["choices"] = out
        answers = sorted(e.accepted_answers.all(), key=lambda a: (a.blank_index, not a.is_primary, a.pk))
        if answers:
            d["answers"] = [{"t": a.text, "b": a.blank_index, "p": a.is_primary} for a in answers]
        if e.code in similar:
            d["similar"] = sorted(similar[e.code])
        return d

    course = Course.objects.select_related("reference_source").first()
    return {
        "format": BUNDLE_FORMAT, "version": BUNDLE_VERSION, "generated_at": timezone.now().isoformat(),
        "course": {"title": course.title if course else "Francês A1",
                   "reference": course.reference_source.key if course and course.reference_source else ""},
        "labels": {
            "types": dict(Exercise.Type.choices), "reading": dict(Exercise.ReadingSkill.choices),
            "origins": dict(Origin.choices), "text_types": dict(Passage.TextType.choices),
            "interactions": dict(Exercise.Interaction.choices),
        },
        "competencies": [{"code": c.code, "name": c.name, "description": c.description}
                         for c in Competency.objects.all()],
        "sources": [{"key": s.key, "title": s.title, "author": s.author, "url": s.url, "license": s.license_name,
                     "license_url": s.license_url, "notes": s.notes} for s in Source.objects.all()],
        "chapters": [{
            "code": ch.code, "number": ch.number, "title": ch.title, "theme": ch.theme,
            "description": ch.description, "reference_note": ch.reference_note,
            "expressions": _pairs(ch.useful_expressions), "review": ch.review_points(),
            "objectives": [{"code": o.code, "text": o.description} for o in ch.objectives.all() if o.is_active],
            "grammar": [{"code": g.code, "title": g.title, "summary": g.summary, "examples": _pairs(g.examples),
                         "tables": g.tables, "notes": g.notes, "errors": g.common_errors}
                        for g in ch.grammar_topics.all() if g.is_active],
            "vocab": [{"code": v.code, "title": v.title,
                       "items": [{"fr": i.french, "pt": i.portuguese, "g": i.gender, "ex": i.example}
                                 for i in v.items.all()]}
                      for v in ch.vocabulary_topics.all() if v.is_active],
        } for ch in chapters],
        "planned": [{"number": p.number, "title": p.title, "theme": p.theme} for p in planned],
        "passages": [{
            "code": p.code, "chapter": p.chapter.code, "title": p.title, "type": p.text_type, "body": p.body,
            "translation": p.translation_pt, "difficulty": p.difficulty, "words": p.word_count,
            "level": p.cefr_level, "vocab": _pairs(p.key_vocabulary), "structures": _pairs(p.useful_structures),
            "author": p.author, "source": p.source.key, "origin": p.origin, "position": p.position,
        } for p in Passage.objects.filter(is_active=True, chapter__in=chapters).select_related("chapter", "source")
            .order_by("chapter__number", "position", "id")],
        "exercises": [ex_dict(e) for e in exercises],
    }


def _precache_list(root: Path) -> list[str]:
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name not in ("sw.js",) and not p.name.startswith("."):
            files.append(p.relative_to(root).as_posix())
    return ["./"] + files


def build(dest: Path, bundle: dict | None = None) -> dict:
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(MOBILE_SRC, dest, ignore=shutil.ignore_patterns("sw.template.js", "*.test.mjs", "tests"))
    bundle = bundle or content_bundle()
    raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    (dest / "content.json").write_text(raw, encoding="utf-8")
    files = _precache_list(dest)
    digest = hashlib.sha256()
    for f in files[1:]:
        digest.update(f.encode())
        digest.update((dest / f).read_bytes())
    cache_version = digest.hexdigest()[:12]
    template = (MOBILE_SRC / "sw.template.js").read_text(encoding="utf-8")
    sw = (template.replace("__CACHE_VERSION__", cache_version)
          .replace("__PRECACHE__", json.dumps(files, ensure_ascii=False)))
    (dest / "sw.js").write_text(sw, encoding="utf-8")
    (dest / "version.json").write_text(json.dumps({"version": cache_version,
                                                   "built_at": bundle["generated_at"]}), encoding="utf-8")
    return {"dest": str(dest), "files": len(files), "cache_version": cache_version,
            "exercises": len(bundle["exercises"]), "content_kb": round(len(raw.encode()) / 1024)}
