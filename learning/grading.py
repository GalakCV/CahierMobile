"""
Correção de respostas.

Modos de comparação para respostas digitadas (configurados em cada questão):

- ``exact``: igualdade exata com alguma resposta cadastrada. Só os tipos de
  apóstrofo (’ ‘ `) são unificados e espaços nas pontas removidos.
- ``normalized``: ignora maiúsculas, espaços excedentes, pontuação final ou
  intermediária (. , ; : ! ? « » " ( )), unifica apóstrofos e remove espaços em
  volta de apóstrofos e hífens. **Acentos continuam valendo.** Compara só com as
  respostas marcadas como principais.
- ``accepted_list``: mesma normalização, comparando com todas as variantes aceitas.
- ``regex``: a resposta normalizada deve casar por completo com a expressão.
- ``manual`` / ``self``: a resposta é guardada e avaliada depois (pendente).

Acentos: se a resposta só difere nos acentos, ela é considerada errada (com aviso
"confira os acentos"), a menos que a questão tenha ``accent_insensitive=True``.
Em ortografia e conjugação esse campo deve ficar desmarcado.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from content.models import Exercise

APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", "ʼ": "'"})
PUNCT_RE = re.compile(r"[.,;:!?¡¿«»\"“”()\[\]…]")
SPACES_RE = re.compile(r"\s+")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def normalize(text: str) -> str:
    """Normalização tolerante, preservando acentos."""
    t = nfc(text).translate(APOSTROPHES)
    t = t.replace(" ", " ").replace(" ", " ")
    t = t.casefold()
    t = PUNCT_RE.sub(" ", t)
    t = re.sub(r"\s*'\s*", "'", t)          # j' ai → j'ai
    t = re.sub(r"\s*-\s*", "-", t)          # est - ce → est-ce
    t = SPACES_RE.sub(" ", t).strip()
    return t


def ligature_fold(text: str) -> str:
    """Aceita 'oe' por 'œ' e 'ae' por 'æ' (limitação comum de teclado)."""
    return text.replace("œ", "oe").replace("æ", "ae")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def exact_form(text: str) -> str:
    return nfc(text).translate(APOSTROPHES).strip()


@dataclass
class GradeResult:
    result: str                      # correct | partial | incorrect | pending
    score: float
    answer_display: str
    correct_display: str
    feedback: str = ""
    parts: list[dict] = field(default_factory=list)

    @property
    def is_correct(self) -> bool:
        return self.result == "correct"


# ---------------------------------------------------------------------------
# Leitura da resposta enviada pelo formulário
# ---------------------------------------------------------------------------

def parse_answer(exercise: Exercise, data) -> dict:
    """Converte o POST em uma estrutura serializável. ``data`` é um QueryDict ou dict."""
    def getlist(key):
        if hasattr(data, "getlist"):
            return data.getlist(key)
        value = data.get(key, [])
        return value if isinstance(value, list) else [value]

    it = exercise.interaction
    if it == Exercise.Interaction.SINGLE:
        return {"choice": _to_int(data.get("choice"))}
    if it == Exercise.Interaction.MULTIPLE:
        return {"choices": sorted({_to_int(v) for v in getlist("choice") if _to_int(v) is not None})}
    if it == Exercise.Interaction.TEXT:
        n = max(1, exercise.blank_count)
        return {"blanks": [str(data.get(f"blank_{i}", ""))[:500] for i in range(n)]}
    if it == Exercise.Interaction.ORDER:
        raw = str(data.get("order", ""))
        return {"order": [i for i in (_to_int(x) for x in raw.split(",")) if i is not None]}
    if it == Exercise.Interaction.MATCH:
        pairs = {}
        for key in data.keys():
            if key.startswith("match_"):
                left = _to_int(key[6:])
                right = _to_int(data.get(key))
                if left is not None:
                    pairs[str(left)] = right
        return {"pairs": pairs}
    if it == Exercise.Interaction.WRITING:
        return {"text": str(data.get("text", ""))[:5000]}
    return {}


def answer_is_empty(exercise: Exercise, answer: dict) -> bool:
    it = exercise.interaction
    if it == "single":
        return answer.get("choice") is None
    if it == "multiple":
        return not answer.get("choices")
    if it == "text":
        return all(not b.strip() for b in answer.get("blanks", []))
    if it == "order":
        return not answer.get("order")
    if it == "match":
        return not any(v is not None for v in answer.get("pairs", {}).values())
    if it == "writing":
        return not answer.get("text", "").strip()
    return True


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Correção
# ---------------------------------------------------------------------------

def correct_display(exercise: Exercise) -> str:
    it = exercise.interaction
    choices = list(exercise.choices.all().order_by("position", "id"))
    if it in ("single", "multiple"):
        return " | ".join(c.text for c in choices if c.is_correct)
    if it == "order":
        ordered = sorted((c for c in choices if c.correct_position), key=lambda c: c.correct_position)
        sep = " " if exercise.exercise_type == Exercise.Type.ORDER_WORDS else " / "
        return sep.join(c.text for c in ordered)
    if it == "match":
        return "; ".join(f"{c.text} → {c.match_text}" for c in choices)
    if it == "writing":
        return exercise.model_answer
    answers = list(exercise.accepted_answers.all())
    n = max(1, exercise.blank_count)
    parts = []
    for i in range(n):
        prim = [a.text for a in answers if a.blank_index == i and a.is_primary] or \
               [a.text for a in answers if a.blank_index == i]
        parts.append(prim[0] if prim else "")
    if exercise.comparison_mode in ("manual", "self", "regex") and exercise.model_answer:
        return exercise.model_answer  # uma expressão regular não deve ser mostrada como resposta
    return parts[0] if n == 1 else " · ".join(f"{i + 1}) {p}" for i, p in enumerate(parts))


def grade(exercise: Exercise, answer: dict) -> GradeResult:
    it = exercise.interaction
    if it == "single":
        return _grade_single(exercise, answer)
    if it == "multiple":
        return _grade_multiple(exercise, answer)
    if it == "order":
        return _grade_order(exercise, answer)
    if it == "match":
        return _grade_match(exercise, answer)
    if it == "writing":
        text = answer.get("text", "")
        return GradeResult("pending", 0.0, text, exercise.model_answer,
                           "Compare seu texto com a resposta-modelo e use os critérios para se autoavaliar.")
    return _grade_text(exercise, answer)


def _grade_single(ex: Exercise, answer: dict) -> GradeResult:
    choices = {c.pk: c for c in ex.choices.all()}
    chosen = choices.get(answer.get("choice"))
    shown = chosen.text if chosen else "(sem resposta)"
    ok = bool(chosen and chosen.is_correct)
    feedback = chosen.feedback if chosen and chosen.feedback else ""
    return GradeResult("correct" if ok else "incorrect", 1.0 if ok else 0.0, shown, correct_display(ex), feedback)


def _grade_multiple(ex: Exercise, answer: dict) -> GradeResult:
    choices = {c.pk: c for c in ex.choices.all()}
    chosen = {cid for cid in answer.get("choices", []) if cid in choices}
    correct = {cid for cid, c in choices.items() if c.is_correct}
    tp = len(chosen & correct)
    fp = len(chosen - correct)
    score = max(0.0, (tp - fp) / len(correct)) if correct else 0.0
    if chosen == correct:
        result, score = "correct", 1.0
    elif score > 0:
        result = "partial"
    else:
        result = "incorrect"
    shown = " | ".join(choices[c].text for c in sorted(chosen, key=lambda k: choices[k].position)) or "(sem resposta)"
    fb = ""
    if result == "partial":
        missing = len(correct - chosen)
        fb = f"Você acertou {tp} de {len(correct)} alternativas corretas" + (
            f" e marcou {fp} incorreta(s)." if fp else f"; faltou marcar {missing}.")
    return GradeResult(result, round(score, 3), shown, correct_display(ex), fb)


def _grade_order(ex: Exercise, answer: dict) -> GradeResult:
    choices = {c.pk: c for c in ex.choices.all()}
    order = [cid for cid in answer.get("order", []) if cid in choices]
    expected = [c.pk for c in sorted((c for c in choices.values() if c.correct_position),
                                     key=lambda c: c.correct_position)]
    sep = " " if ex.exercise_type == Exercise.Type.ORDER_WORDS else " / "
    shown = sep.join(choices[c].text for c in order) or "(sem resposta)"
    if order == expected:
        return GradeResult("correct", 1.0, shown, correct_display(ex))
    # Ordens alternativas válidas podem ser cadastradas como respostas aceitas.
    joined = normalize(" ".join(choices[c].text for c in order))
    for acc in ex.accepted_answers.all():
        if normalize(acc.text) == joined and len(order) == len(expected):
            return GradeResult("correct", 1.0, shown, correct_display(ex),
                               "Esta ordem também é aceita.")
    placed = sum(1 for a, b in zip(order, expected) if a == b)
    score = placed / len(expected) if expected else 0.0
    result = "partial" if score >= 0.5 else "incorrect"
    fb = f"{placed} de {len(expected)} elementos na posição certa."
    return GradeResult(result, round(score, 3), shown, correct_display(ex), fb)


def _grade_match(ex: Exercise, answer: dict) -> GradeResult:
    choices = {c.pk: c for c in ex.choices.all()}
    pairs = answer.get("pairs", {})
    good = 0
    shown_parts = []
    for cid, c in choices.items():
        chosen_right = choices.get(_to_int(pairs.get(str(cid))))
        shown_parts.append(f"{c.text} → {chosen_right.match_text if chosen_right else '?'}")
        if chosen_right is not None and (chosen_right.pk == cid or chosen_right.match_text == c.match_text):
            good += 1
    total = len(choices)
    score = good / total if total else 0.0
    result = "correct" if good == total else ("partial" if score >= 0.5 else "incorrect")
    fb = "" if result == "correct" else f"{good} de {total} pares corretos."
    return GradeResult(result, round(score, 3), "; ".join(shown_parts), correct_display(ex), fb)


def _grade_text(ex: Exercise, answer: dict) -> GradeResult:
    blanks = answer.get("blanks", [""])
    n = max(1, ex.blank_count)
    blanks = (blanks + [""] * n)[:n]
    shown = blanks[0] if n == 1 else " · ".join(f"{i + 1}) {b}" for i, b in enumerate(blanks))
    mode = ex.comparison_mode
    if mode in (Exercise.Comparison.MANUAL, Exercise.Comparison.SELF):
        return GradeResult("pending", 0.0, shown, correct_display(ex),
                           "Resposta guardada. Compare com a resposta-modelo para avaliá-la.")
    answers = list(ex.accepted_answers.all())
    parts = []
    good = 0
    accent_issue = False
    for i, typed in enumerate(blanks):
        cands = [a for a in answers if a.blank_index == i]
        if mode == Exercise.Comparison.NORMALIZED:
            cands = [a for a in cands if a.is_primary] or cands
        status = _match_blank(typed, [a.text for a in cands], mode, ex.accent_insensitive)
        if status in ("ok", "ok_accent"):
            good += 1
        if status in ("accent", "ok_accent"):
            accent_issue = True
        parts.append({"typed": typed, "status": status})
    score = good / n
    result = "correct" if good == n else ("partial" if good > 0 else "incorrect")
    feedback = ""
    if accent_issue:
        feedback = ("Atenção aos acentos: aqui eles não foram considerados, mas a grafia correta usa acento."
                    if ex.accent_insensitive else
                    "Quase! A resposta só difere nos acentos — e neste exercício eles fazem parte da correção.")
    if result == "partial":
        feedback = (feedback + " " if feedback else "") + f"{good} de {n} lacunas corretas."
    return GradeResult(result, round(score, 3), shown, correct_display(ex), feedback, parts)


def _match_blank(typed: str, candidates: list[str], mode: str, accent_insensitive: bool) -> str:
    """Devolve 'ok', 'ok_accent' (aceito apesar dos acentos), 'accent' (só acentos errados) ou 'wrong'."""
    if not typed.strip():
        return "wrong"
    if mode == Exercise.Comparison.EXACT:
        t = exact_form(typed)
        if any(t == exact_form(c) for c in candidates):
            return "ok"
        if any(strip_accents(t) == strip_accents(exact_form(c)) for c in candidates):
            return "ok_accent" if accent_insensitive else "accent"
        return "wrong"
    t = normalize(typed)
    if mode == Exercise.Comparison.REGEX:
        for c in candidates:
            try:
                if re.fullmatch(c, t, flags=re.IGNORECASE):
                    return "ok"
                if re.fullmatch(strip_accents(c), strip_accents(t), flags=re.IGNORECASE):
                    return "ok_accent" if accent_insensitive else "accent"
            except re.error:
                continue
        return "wrong"
    tf = ligature_fold(t)
    for c in candidates:
        if tf == ligature_fold(normalize(c)):
            return "ok"
    for c in candidates:
        if strip_accents(tf) == strip_accents(ligature_fold(normalize(c))):
            return "ok_accent" if accent_insensitive else "accent"
    return "wrong"
