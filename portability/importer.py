"""
Importação de conteúdo em JSON (formato documentado em docs/FORMATO_JSON.md).

Etapas:
1. ``validate_structure``: verifica o esquema (campos obrigatórios, tipos,
   valores permitidos) e a coerência de cada questão — sem tocar no banco.
2. ``apply``: grava tudo dentro de UMA transação. Qualquer erro crítico
   desfaz a importação inteira.

Duplicações: códigos repetidos dentro do arquivo são recusados. Códigos que já
existem no banco também são recusados, a menos que ``update_existing=True``.
Fontes, competências e o curso já existentes são reaproveitados; capítulos
existentes também (sem alterar seus campos) para permitir cadastrar novas
questões em um capítulo aos poucos.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from content.models import (CEFR_LEVELS, AcceptedAnswer, Chapter, Choice, Competency, Course, Exercise,
                            ExerciseRelation, GrammarTopic, LearningObjective, Origin, Passage, ReviewStatus,
                            Source, VocabularyItem, VocabularyTopic, code_validator_re)

FORMAT = "cahier-content"
FORMAT_VERSION = 1
CEFR = {c for c, _ in CEFR_LEVELS}


class ImportAborted(Exception):
    pass


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    reused: dict[str, int] = field(default_factory=dict)
    dry_run: bool = False
    applied: bool = False

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    def bump(self, bucket: str, kind: str) -> None:
        d = getattr(self, bucket)
        d[kind] = d.get(kind, 0) + 1

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "applied": self.applied, "dry_run": self.dry_run, "errors": self.errors,
                "warnings": self.warnings, "created": self.created, "updated": self.updated, "reused": self.reused}


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------
STR, INT, BOOL, LIST, DICT = "texto", "número inteiro", "verdadeiro/falso", "lista", "objeto"
PYTYPES = {STR: str, INT: int, BOOL: bool, LIST: list, DICT: dict}

SOURCE_SPEC = {"key": (STR, True), "title": (STR, True), "author": (STR, True), "url": (STR, False),
               "license": (STR, True), "license_url": (STR, False), "notes": (STR, False)}
COMPETENCY_SPEC = {"code": (STR, True), "name": (STR, True), "description": (STR, False), "position": (INT, False)}
COURSE_SPEC = {"code": (STR, True), "title": (STR, True), "description": (STR, False), "reference_source": (STR, False)}
CHAPTER_SPEC = {"code": (STR, True), "number": (INT, True), "title": (STR, True), "theme": (STR, True),
                "description": (STR, True), "cefr_level": (STR, False), "is_active": (BOOL, False),
                "is_planned": (BOOL, False), "useful_expressions": (LIST, False), "review_summary": (LIST, False),
                "reference_note": (STR, False), "objectives": (LIST, False), "grammar_topics": (LIST, False),
                "vocabulary_topics": (LIST, False), "passages": (LIST, False), "exercises": (LIST, False)}
OBJECTIVE_SPEC = {"code": (STR, True), "description": (STR, True), "competencies": (LIST, False),
                  "position": (INT, False)}
GRAMMAR_SPEC = {"code": (STR, True), "title": (STR, True), "summary": (STR, True), "examples": (LIST, False),
                "tables": (LIST, False), "notes": (STR, False), "common_errors": (LIST, False),
                "position": (INT, False)}
VOCAB_SPEC = {"code": (STR, True), "title": (STR, True), "items": (LIST, True), "position": (INT, False)}
VOCAB_ITEM_SPEC = {"fr": (STR, True), "pt": (STR, True), "gender": (STR, False), "example": (STR, False)}
PAIR_SPEC = {"fr": (STR, True), "pt": (STR, True)}
PASSAGE_SPEC = {"code": (STR, True), "title": (STR, True), "text_type": (STR, True), "body": (STR, True),
                "translation_pt": (STR, False), "cefr_level": (STR, False), "difficulty": (INT, True),
                "key_vocabulary": (LIST, False), "useful_structures": (LIST, False),
                "grammar_topics": (LIST, False), "vocabulary_topics": (LIST, False), "author": (STR, True),
                "source": (STR, True), "origin": (STR, True), "adaptation_notes": (STR, False),
                "review_status": (STR, False), "position": (INT, False), "is_active": (BOOL, False)}
EXERCISE_SPEC = {"code": (STR, True), "type": (STR, True), "interaction": (STR, False),
                 "instruction": (STR, True), "prompt": (STR, True), "context": (STR, False),
                 "translation_pt": (STR, False), "explanation": (STR, True), "evidence": (STR, False),
                 "model_answer": (STR, False), "criteria": (LIST, False), "difficulty": (INT, True),
                 "cefr_level": (STR, False), "estimated_seconds": (INT, False), "competency": (STR, True),
                 "objectives": (LIST, False), "grammar_topics": (LIST, False), "vocabulary_topics": (LIST, False),
                 "passage": (STR, False), "reading_skill": (STR, False), "is_assessment": (BOOL, False),
                 "origin": (STR, True), "source": (STR, True), "adaptation_notes": (STR, False),
                 "review_status": (STR, False), "comparison": (STR, False), "accent_insensitive": (BOOL, False),
                 "choices": (LIST, False), "answers": (LIST, False), "answer": (BOOL, False),
                 "related": (LIST, False), "position": (INT, False), "is_active": (BOOL, False)}
CHOICE_SPEC = {"text": (STR, True), "correct": (BOOL, False), "order": (INT, False), "match": (STR, False),
               "feedback": (STR, False)}
ANSWER_SPEC = {"text": (STR, True), "blank": (INT, False), "primary": (BOOL, False)}
RELATED_SPEC = {"code": (STR, True), "kind": (STR, False)}


def _check(obj, spec: dict, where: str, rep: Report) -> bool:
    if not isinstance(obj, dict):
        rep.error(where, f"deveria ser um {DICT}")
        return False
    ok = True
    for key, (typ, required) in spec.items():
        if key not in obj or obj[key] is None:
            if required:
                rep.error(where, f"campo obrigatório ausente: '{key}'")
                ok = False
            continue
        value = obj[key]
        if key == "review_summary" and isinstance(value, str):
            continue  # aceita texto ou lista
        expected = PYTYPES[typ]
        if typ == INT and (isinstance(value, bool) or not isinstance(value, int)):
            rep.error(where, f"'{key}' deve ser {typ}")
            ok = False
        elif typ != INT and not isinstance(value, expected):
            rep.error(where, f"'{key}' deve ser {typ}")
            ok = False
        elif typ == STR and required and not value.strip():
            rep.error(where, f"'{key}' não pode ficar vazio")
            ok = False
    for key in obj:
        if key not in spec:
            rep.warn(where, f"campo desconhecido ignorado: '{key}'")
    return ok


def _check_list(items, spec, where, rep, label_key="code"):
    """Valida cada item e devolve todos os objetos para que os filhos também sejam verificados."""
    out = []
    if not isinstance(items, list):
        return out
    for i, it in enumerate(items):
        w = f"{where}[{i}]" + (f" ({it.get(label_key)})" if isinstance(it, dict) and it.get(label_key) else "")
        _check(it, spec, w, rep)
        if isinstance(it, dict):
            out.append((w, it))
    return out


def _code_ok(code: str, where: str, rep: Report) -> None:
    if code is None:
        return  # ausência já relatada pela verificação de esquema
    if not isinstance(code, str) or not code_validator_re.match(code or ""):
        rep.error(where, f"código inválido '{code}' (use minúsculas, números, '.', '-' ou '_')")


def _choice_value(value, allowed, where, field_name, rep):
    if value is not None and value not in allowed:
        rep.error(where, f"'{field_name}' inválido: '{value}'. Valores aceitos: {', '.join(sorted(allowed))}")


def normalize_answers(raw) -> list[dict]:
    out = []
    for a in raw or []:
        if isinstance(a, str):
            out.append({"text": a, "blank": 0, "primary": not out or all(x["blank"] != 0 for x in out)})
        elif isinstance(a, dict):
            out.append({"text": a.get("text", ""), "blank": a.get("blank", 0), "primary": a.get("primary", True)})
    return out


def validate_structure(data, rep: Report | None = None) -> Report:
    rep = rep or Report()
    if not isinstance(data, dict):
        rep.error("arquivo", "o JSON deve ser um objeto")
        return rep
    if data.get("format") != FORMAT:
        rep.error("arquivo", f"'format' deve ser '{FORMAT}'")
    if data.get("version") != FORMAT_VERSION:
        rep.error("arquivo", f"'version' deve ser {FORMAT_VERSION}")
    for key in ("sources", "competencies", "chapters"):
        if key in data and not isinstance(data[key], list):
            rep.error("arquivo", f"'{key}' deve ser uma lista")
    if "course" in data:
        _check(data["course"], COURSE_SPEC, "course", rep)

    seen: dict[str, set] = {k: set() for k in ("source", "competency", "chapter", "objective", "grammar",
                                                 "vocabulary", "passage", "exercise")}

    def unique(kind, code, where):
        if code is None:
            return
        if code in seen[kind]:
            rep.error(where, f"código duplicado no arquivo: '{code}'")
        seen[kind].add(code)

    for w, s in _check_list(data.get("sources", []), SOURCE_SPEC, "sources", rep, "key"):
        unique("source", s.get("key"), w)
    for w, c in _check_list(data.get("competencies", []), COMPETENCY_SPEC, "competencies", rep):
        _code_ok(c.get("code"), w, rep)
        unique("competency", c.get("code"), w)

    numbers = set()
    for wc, ch in _check_list(data.get("chapters", []), CHAPTER_SPEC, "chapters", rep):
        _code_ok(ch.get("code"), wc, rep)
        unique("chapter", ch.get("code"), wc)
        if ch.get("number") is not None and ch.get("number") in numbers:
            rep.error(wc, f"número de capítulo repetido: {ch['number']}")
        numbers.add(ch.get("number"))
        _choice_value(ch.get("cefr_level"), CEFR, wc, "cefr_level", rep)
        for i, e in enumerate(ch.get("useful_expressions", []) or []):
            _check(e, PAIR_SPEC, f"{wc}.useful_expressions[{i}]", rep)
        for w, o in _check_list(ch.get("objectives", []), OBJECTIVE_SPEC, f"{wc}.objectives", rep):
            _code_ok(o.get("code"), w, rep)
            unique("objective", o.get("code"), w)
        for w, g in _check_list(ch.get("grammar_topics", []), GRAMMAR_SPEC, f"{wc}.grammar_topics", rep):
            _code_ok(g.get("code"), w, rep)
            unique("grammar", g.get("code"), w)
            for i, ex in enumerate(g.get("examples", []) or []):
                _check(ex, PAIR_SPEC, f"{w}.examples[{i}]", rep)
            for i, t in enumerate(g.get("tables", []) or []):
                if not isinstance(t, dict) or not isinstance(t.get("rows"), list) or not t.get("title"):
                    rep.error(f"{w}.tables[{i}]", "tabela precisa de 'title' e 'rows' (lista de linhas)")
            for i, ce in enumerate(g.get("common_errors", []) or []):
                _check(ce, {"wrong": (STR, True), "right": (STR, True), "why": (STR, True)},
                       f"{w}.common_errors[{i}]", rep)
        for w, v in _check_list(ch.get("vocabulary_topics", []), VOCAB_SPEC, f"{wc}.vocabulary_topics", rep):
            _code_ok(v.get("code"), w, rep)
            unique("vocabulary", v.get("code"), w)
            _check_list(v.get("items", []), VOCAB_ITEM_SPEC, f"{w}.items", rep, "fr")
        chapter_passages = set()
        for w, p in _check_list(ch.get("passages", []), PASSAGE_SPEC, f"{wc}.passages", rep):
            _code_ok(p.get("code"), w, rep)
            unique("passage", p.get("code"), w)
            chapter_passages.add(p.get("code"))
            _choice_value(p.get("text_type"), set(Passage.TextType.values), w, "text_type", rep)
            _choice_value(p.get("origin"), set(Origin.values), w, "origin", rep)
            _choice_value(p.get("review_status"), set(ReviewStatus.values), w, "review_status", rep)
            _choice_value(p.get("cefr_level"), CEFR, w, "cefr_level", rep)
            if not isinstance(p.get("difficulty"), int) or not 1 <= p.get("difficulty") <= 5:
                rep.error(w, "'difficulty' deve estar entre 1 e 5")
            if p.get("origin") == Origin.ADAPTED and not p.get("adaptation_notes"):
                rep.error(w, "conteúdo adaptado precisa de 'adaptation_notes'")
        for w, e in _check_list(ch.get("exercises", []), EXERCISE_SPEC, f"{wc}.exercises", rep):
            _code_ok(e.get("code"), w, rep)
            unique("exercise", e.get("code"), w)
            _validate_exercise(e, w, rep)
    return rep


def _validate_exercise(e: dict, w: str, rep: Report) -> None:
    etype = e.get("type")
    if etype not in Exercise.TYPE_INTERACTIONS:
        rep.error(w, f"tipo de exercício desconhecido: '{etype}'")
        return
    interaction = e.get("interaction") or Exercise.TYPE_INTERACTIONS[etype][0]
    if interaction not in Exercise.TYPE_INTERACTIONS[etype]:
        rep.error(w, f"o tipo '{etype}' não aceita a interação '{interaction}'")
        return
    comparison = e.get("comparison") or ("self" if interaction == "writing" else "accepted_list")
    _choice_value(comparison, set(Exercise.Comparison.values), w, "comparison", rep)
    _choice_value(e.get("origin"), set(Origin.values), w, "origin", rep)
    _choice_value(e.get("review_status"), set(ReviewStatus.values), w, "review_status", rep)
    _choice_value(e.get("cefr_level"), CEFR, w, "cefr_level", rep)
    if e.get("reading_skill"):
        _choice_value(e.get("reading_skill"), set(Exercise.ReadingSkill.values), w, "reading_skill", rep)
    if e.get("origin") == Origin.ADAPTED and not e.get("adaptation_notes"):
        rep.error(w, "conteúdo adaptado precisa de 'adaptation_notes'")
    if not isinstance(e.get("difficulty"), int) or not 1 <= e.get("difficulty") <= 5:
        rep.error(w, "'difficulty' deve estar entre 1 e 5")
    if not str(e.get("explanation", "")).strip():
        rep.error(w, "toda questão precisa de explicação")
    choices = _check_list(e.get("choices", []) or [], CHOICE_SPEC, f"{w}.choices", rep, "text")
    choices = [c for _, c in choices]
    if etype == "true_false" and "answer" in e and not choices:
        choices = [{"text": "Vrai", "correct": e["answer"] is True}, {"text": "Faux", "correct": e["answer"] is False}]
        e["choices"] = choices
    answers = normalize_answers(e.get("answers"))
    for i, a in enumerate(answers):
        if not isinstance(a["text"], str) or not a["text"].strip():
            rep.error(f"{w}.answers[{i}]", "resposta vazia")
        if not isinstance(a["blank"], int) or isinstance(a["blank"], bool) or a["blank"] < 0:
            rep.error(f"{w}.answers[{i}]", "'blank' deve ser inteiro ≥ 0")
    if interaction in ("single", "multiple"):
        correct = sum(1 for c in choices if c.get("correct"))
        if len(choices) < 2:
            rep.error(w, "precisa de pelo menos 2 alternativas")
        elif interaction == "single" and correct != 1:
            rep.error(w, f"escolha única precisa de exatamente 1 alternativa correta (há {correct})")
        elif interaction == "multiple" and (correct < 1 or correct == len(choices)):
            rep.error(w, "múltipla seleção precisa de alternativas corretas e incorretas")
        texts = [str(c.get("text", "")).strip().casefold() for c in choices]
        if len(set(texts)) != len(texts):
            rep.error(w, "alternativas repetidas")
    elif interaction == "order":
        if len(choices) < 2:
            rep.error(w, "ordenação precisa de pelo menos 2 elementos")
        orders = [c.get("order") for c in choices]
        if any(o is not None for o in orders) and sorted(o for o in orders if o is not None) != list(range(1, len(choices) + 1)):
            rep.error(w, "'order' deve numerar os elementos de 1 a N, sem repetição")
    elif interaction == "match":
        if len(choices) < 2 or any(not c.get("match") for c in choices):
            rep.error(w, "relacionar precisa de pelo menos 2 pares com 'match'")
        rights = [str(c.get("match", "")).strip().casefold() for c in choices]
        if len(set(rights)) != len(rights):
            rep.error(w, "itens da coluna da direita repetidos")
    elif interaction == "text":
        if comparison not in ("manual", "self"):
            blanks = max(1, str(e.get("prompt") or "").count(Exercise.BLANK))
            if not answers:
                rep.error(w, "resposta digitada precisa de 'answers'")
            for b in range(blanks):
                if not any(a["blank"] == b for a in answers):
                    rep.error(w, f"lacuna {b + 1} sem resposta aceita")
            if any(a["blank"] >= blanks for a in answers):
                rep.error(w, f"há respostas para lacunas inexistentes (o enunciado tem {blanks})")
            if comparison == "regex":
                for a in answers:
                    try:
                        re.compile(a["text"])
                    except re.error as exc:
                        rep.error(w, f"expressão regular inválida '{a['text']}': {exc}")
        elif not e.get("model_answer"):
            rep.error(w, "correção manual/autoavaliação precisa de 'model_answer'")
    elif interaction == "writing":
        if not e.get("model_answer"):
            rep.error(w, "produção escrita precisa de 'model_answer'")
        if not e.get("criteria"):
            rep.error(w, "produção escrita precisa de 'criteria'")
        if comparison not in ("self", "manual"):
            rep.error(w, "produção escrita usa 'comparison' = 'self' ou 'manual'")
    if e.get("reading_skill") and not e.get("passage") and etype == "text_interpretation":
        rep.warn(w, "questão de interpretação sem texto associado")
    if e.get("passage") and not e.get("evidence"):
        rep.warn(w, "questão de texto sem 'evidence' (trecho que fundamenta a resposta)")


# ---------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------

def run_import(data, *, update_existing=False, dry_run=False) -> Report:
    rep = validate_structure(data)
    rep.dry_run = dry_run
    if not rep.ok:
        return rep
    try:
        with transaction.atomic():
            _apply(data, rep, update_existing)
            if rep.errors:
                raise ImportAborted()
            if dry_run:
                raise ImportAborted()
        rep.applied = True
    except ImportAborted:
        rep.applied = False
    except ValidationError as exc:
        rep.error("banco de dados", "; ".join(exc.messages))
        rep.applied = False
    except Exception as exc:  # erro inesperado: tudo é desfeito
        rep.error("banco de dados", f"{type(exc).__name__}: {exc}")
        rep.applied = False
    if not rep.ok:
        rep.applied = False
    return rep


def load_json_bytes(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise ValueError("O arquivo precisa estar em UTF-8.")
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido (linha {exc.lineno}, coluna {exc.colno}): {exc.msg}")


def _apply(data: dict, rep: Report, update: bool) -> None:
    for s in data.get("sources", []):
        values = {"title": s["title"], "author": s["author"], "url": s.get("url", ""),
                  "license_name": s["license"], "license_url": s.get("license_url", ""), "notes": s.get("notes", "")}
        _upsert_simple(Source, {"key": s["key"]}, values, update, rep, "fontes")
    for c in data.get("competencies", []):
        values = {"name": c["name"], "description": c.get("description", ""), "position": c.get("position", 0)}
        _upsert_simple(Competency, {"code": c["code"]}, values, update, rep, "competências")

    course = None
    if "course" in data:
        cd = data["course"]
        ref = Source.objects.filter(key=cd.get("reference_source")).first() if cd.get("reference_source") else None
        course = _upsert_simple(Course, {"code": cd["code"]},
                                {"title": cd["title"], "description": cd.get("description", ""),
                                 "reference_source": ref}, update, rep, "cursos")
    if course is None:
        course = Course.objects.order_by("id").first()
    if course is None and data.get("chapters"):
        rep.error("course", "nenhum curso cadastrado; inclua 'course' no arquivo")
        return

    relations = []
    for i, ch in enumerate(data.get("chapters", [])):
        where = f"chapters[{i}] ({ch['code']})"
        chapter = _apply_chapter(ch, course, update, rep, where)
        if chapter is None:
            continue
        objectives = {}
        for o in ch.get("objectives", []):
            obj = _upsert_child(LearningObjective, o["code"], {
                "chapter": chapter, "description": o["description"], "position": o.get("position", 0)},
                update, rep, "objetivos", f"{where} objetivo {o['code']}")
            if obj:
                comps = _lookup(Competency, o.get("competencies", []), rep, f"{where} objetivo {o['code']}")
                obj.competencies.set(comps)
                objectives[o["code"]] = obj
        for g in ch.get("grammar_topics", []):
            _upsert_child(GrammarTopic, g["code"], {
                "chapter": chapter, "title": g["title"], "summary": g["summary"],
                "examples": g.get("examples", []), "tables": g.get("tables", []), "notes": g.get("notes", ""),
                "common_errors": g.get("common_errors", []), "position": g.get("position", 0)},
                update, rep, "tópicos gramaticais", f"{where} gramática {g['code']}")
        for v in ch.get("vocabulary_topics", []):
            topic = _upsert_child(VocabularyTopic, v["code"], {
                "chapter": chapter, "title": v["title"], "position": v.get("position", 0)},
                update, rep, "temas de vocabulário", f"{where} vocabulário {v['code']}")
            if topic:
                topic.items.all().delete()
                VocabularyItem.objects.bulk_create([
                    VocabularyItem(topic=topic, french=it["fr"], portuguese=it["pt"], gender=it.get("gender", ""),
                                   example=it.get("example", ""), position=n) for n, it in enumerate(v["items"])])
        for n, p in enumerate(ch.get("passages", [])):
            pw = f"{where} texto {p['code']}"
            source = _lookup_one(Source, "key", p["source"], rep, pw)
            passage = _upsert_child(Passage, p["code"], {
                "chapter": chapter, "title": p["title"], "text_type": p["text_type"], "body": p["body"],
                "translation_pt": p.get("translation_pt", ""), "cefr_level": p.get("cefr_level", "A1"),
                "difficulty": p["difficulty"], "key_vocabulary": p.get("key_vocabulary", []),
                "useful_structures": p.get("useful_structures", []), "author": p["author"], "source": source,
                "origin": p["origin"], "adaptation_notes": p.get("adaptation_notes", ""),
                "review_status": p.get("review_status", "draft"), "position": p.get("position", n),
                "is_active": p.get("is_active", True)}, update, rep, "textos", pw) if source else None
            if passage:
                passage.grammar_topics.set(_lookup(GrammarTopic, p.get("grammar_topics", []), rep, pw))
                passage.vocabulary_topics.set(_lookup(VocabularyTopic, p.get("vocabulary_topics", []), rep, pw))
        for n, e in enumerate(ch.get("exercises", [])):
            ex = _apply_exercise(e, chapter, n, update, rep, f"{where} questão {e['code']}")
            if ex and e.get("related"):
                relations.append((ex, e["related"], f"{where} questão {e['code']}"))
    for ex, related, where in relations:
        for r in related:
            other = Exercise.objects.filter(code=r["code"]).first()
            if not other:
                rep.error(where, f"questão relacionada inexistente: '{r['code']}'")
                continue
            kind = r.get("kind", "similar")
            if kind not in ExerciseRelation.Kind.values:
                rep.error(where, f"tipo de relação inválido: '{kind}'")
                continue
            ExerciseRelation.objects.get_or_create(from_exercise=ex, to_exercise=other, kind=kind)


def _upsert_simple(model, lookup, values, update, rep, label):
    obj = model.objects.filter(**lookup).first()
    if obj is None:
        obj = model(**lookup, **values)
        obj.full_clean()
        obj.save()
        rep.bump("created", label)
    elif update:
        for k, v in values.items():
            setattr(obj, k, v)
        obj.full_clean()
        obj.save()
        rep.bump("updated", label)
    else:
        rep.bump("reused", label)
    return obj


def _apply_chapter(ch, course, update, rep, where):
    values = {"course": course, "number": ch["number"], "title": ch["title"], "theme": ch["theme"],
              "description": ch["description"], "cefr_level": ch.get("cefr_level", "A1"),
              "is_active": ch.get("is_active", True), "is_planned": ch.get("is_planned", False),
              "useful_expressions": ch.get("useful_expressions", []),
              "review_summary": "\n".join(ch["review_summary"]) if isinstance(ch.get("review_summary"), list)
              else ch.get("review_summary", ""), "reference_note": ch.get("reference_note", "")}
    obj = Chapter.objects.filter(code=ch["code"]).first()
    clash = Chapter.objects.filter(course=course, number=ch["number"]).exclude(code=ch["code"]).first()
    if clash:
        rep.error(where, f"o número {ch['number']} já pertence ao capítulo '{clash.code}'")
        return None
    if obj is None:
        obj = Chapter(code=ch["code"], **values)
        obj.full_clean()
        obj.save()
        rep.bump("created", "capítulos")
    elif update:
        for k, v in values.items():
            setattr(obj, k, v)
        obj.full_clean()
        obj.save()
        rep.bump("updated", "capítulos")
    else:
        rep.bump("reused", "capítulos")
        rep.warn(where, "capítulo já existe; seus dados não foram alterados (novos itens serão acrescentados)")
    return obj


def _upsert_child(model, code, values, update, rep, label, where):
    obj = model.objects.filter(code=code).first()
    if obj is not None and not update:
        rep.error(where, "já existe no banco (marque 'atualizar existentes' para substituir)")
        return None
    if obj is None:
        obj = model(code=code, **values)
        rep.bump("created", label)
    else:
        for k, v in values.items():
            setattr(obj, k, v)
        rep.bump("updated", label)
    obj.full_clean()
    obj.save()
    return obj


def _lookup(model, codes, rep, where):
    objs = list(model.objects.filter(code__in=codes))
    found = {o.code for o in objs}
    for c in codes:
        if c not in found:
            rep.error(where, f"{model._meta.verbose_name} inexistente: '{c}'")
    return objs


def _lookup_one(model, field_name, value, rep, where):
    obj = model.objects.filter(**{field_name: value}).first()
    if obj is None:
        rep.error(where, f"{model._meta.verbose_name} inexistente: '{value}'")
    return obj


def scrambled_positions(code: str, n: int) -> list[int]:
    """Ordem de exibição embaralhada, estável e diferente da ordem correta."""
    rng = random.Random(code)
    idx = list(range(n))
    for _ in range(20):
        rng.shuffle(idx)
        if idx != list(range(n)):
            break
    return idx


def _apply_exercise(e, chapter, n, update, rep, where):
    etype = e["type"]
    interaction = e.get("interaction") or Exercise.TYPE_INTERACTIONS[etype][0]
    comparison = e.get("comparison") or ("self" if interaction == "writing" else "accepted_list")
    source = _lookup_one(Source, "key", e["source"], rep, where)
    competency = _lookup_one(Competency, "code", e["competency"], rep, where)
    passage = None
    if e.get("passage"):
        passage = Passage.objects.filter(code=e["passage"]).first()
        if passage is None:
            rep.error(where, f"texto inexistente: '{e['passage']}'")
        elif passage.chapter_id != chapter.pk:
            rep.error(where, "o texto associado pertence a outro capítulo")
            passage = None
    if not source or not competency:
        return None
    existing = Exercise.objects.filter(code=e["code"]).first()
    if existing and not update:
        rep.error(where, "já existe no banco (marque 'atualizar existentes' para substituir)")
        return None
    ex = existing or Exercise(code=e["code"])
    fields = {
        "chapter": chapter, "passage": passage, "exercise_type": etype, "interaction": interaction,
        "instruction": e["instruction"], "prompt": e["prompt"], "context": e.get("context", ""),
        "translation_pt": e.get("translation_pt", ""), "explanation": e["explanation"],
        "evidence": e.get("evidence", ""), "model_answer": e.get("model_answer", ""),
        "criteria": e.get("criteria", []), "difficulty": e["difficulty"], "cefr_level": e.get("cefr_level", "A1"),
        "estimated_seconds": e.get("estimated_seconds", _default_seconds(interaction, e["difficulty"])),
        "competency": competency, "comparison_mode": comparison,
        "accent_insensitive": e.get("accent_insensitive", False), "reading_skill": e.get("reading_skill", ""),
        "is_assessment": e.get("is_assessment", False), "origin": e["origin"], "source": source,
        "adaptation_notes": e.get("adaptation_notes", ""), "review_status": e.get("review_status", "draft"),
        "position": e.get("position", n), "is_active": e.get("is_active", True),
    }
    for k, v in fields.items():
        setattr(ex, k, v)
    ex.full_clean(exclude=["version"])
    ex.save()
    rep.bump("updated" if existing else "created", "questões")
    ex.objectives.set(_lookup(LearningObjective, e.get("objectives", []), rep, where))
    ex.grammar_topics.set(_lookup(GrammarTopic, e.get("grammar_topics", []), rep, where))
    ex.vocabulary_topics.set(_lookup(VocabularyTopic, e.get("vocabulary_topics", []), rep, where))

    ex.choices.all().delete()
    ex.accepted_answers.all().delete()
    choices = e.get("choices", []) or []
    if interaction == "order":
        n_ch = len(choices)
        display = scrambled_positions(e["code"], n_ch)
        objs = []
        for disp_pos, src_idx in enumerate(display):
            c = choices[src_idx]
            objs.append(Choice(exercise=ex, text=c["text"], correct_position=c.get("order") or src_idx + 1,
                               feedback=c.get("feedback", ""), position=disp_pos))
        Choice.objects.bulk_create(objs)
    else:
        Choice.objects.bulk_create([
            Choice(exercise=ex, text=c["text"], is_correct=bool(c.get("correct")), match_text=c.get("match", ""),
                   feedback=c.get("feedback", ""), position=i) for i, c in enumerate(choices)])
    AcceptedAnswer.objects.bulk_create([
        AcceptedAnswer(exercise=ex, text=a["text"], blank_index=a["blank"], is_primary=a["primary"])
        for a in normalize_answers(e.get("answers"))])
    ex.snapshot_version("importação" if not existing else "atualização por importação")
    return ex


def _default_seconds(interaction: str, difficulty: int) -> int:
    base = {"single": 25, "multiple": 40, "text": 45, "order": 50, "match": 60, "writing": 600}.get(interaction, 45)
    return base + 10 * (difficulty - 1)
