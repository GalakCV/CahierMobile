// Revisão espaçada e caderno de erros — espelho de learning/review.py.
// O estado de revisão é uma função do histórico (tentativas + marcações), por isso
// pode ser reconstruído com replay() depois de uma sincronização.
import { effectiveScore } from "./mastery.js";

export const INTERVALS = [1, 3, 7, 14, 30];
const FIRST_CORRECT_STAGE = 2;
const DAY = 86400 * 1000;

function roundHalfEven(x) {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

export function intervalFor(stage, errorCount) {
  let base = INTERVALS[Math.max(0, Math.min(stage, INTERVALS.length - 1))];
  if (errorCount >= 2) {
    const factor = 1 + 0.25 * Math.min(errorCount - 1, 4);
    base = Math.max(1, roundHalfEven(base / factor));
  }
  return base;
}

export function outcome(score) {
  if (score >= 0.99) return "correct";
  if (score >= 0.5) return "partial";
  return "incorrect";
}

export const RECOVERY_LABELS = { recent: "Erro recente", reviewing: "Em revisão", improving: "Melhorando", overcome: "Superado" };

export function recoveryState(item) {
  if (item.error_count === 0) return "";
  if (item.last_result === "incorrect" || item.last_result === "partial") return "recent";
  if (item.correct_streak >= 3 && item.stage >= 3) return "overcome";
  if (item.correct_streak >= 2) return "improving";
  return "reviewing";
}

function newItem(code, now) {
  return { exercise: code, stage: 0, interval_days: 1, due_at: now, error_count: 0, correct_streak: 0,
    review_count: 0, last_result: "", last_answer: "", last_attempt_at: null, last_error_at: null,
    flagged: false, recovery: "" };
}

/** Atualiza (e devolve) o item de revisão de uma questão depois de uma resposta avaliada. */
export function register(book, code, score, answerDisplay, now, fromReview = false) {
  const r = outcome(score);
  let item = book.get(code);
  if (!item) {
    item = newItem(code, now);
    if (r === "correct") {
      item.stage = FIRST_CORRECT_STAGE;
      item.correct_streak = 1;
    } else {
      item.stage = 0;
      item.error_count = 1;
      item.last_error_at = now;
      item.last_answer = answerDisplay;
    }
    book.set(code, item);
  } else {
    if (r === "correct") {
      item.stage = Math.min(item.stage + 1, INTERVALS.length - 1);
      item.correct_streak += 1;
      item.flagged = false;
    } else {
      item.stage = Math.max(item.stage - (r === "partial" ? 1 : 2), 0);
      item.correct_streak = 0;
      item.error_count += 1;
      item.last_error_at = now;
      item.last_answer = answerDisplay;
    }
    if (fromReview) item.review_count += 1;
  }
  item.last_result = r;
  item.last_attempt_at = now;
  item.interval_days = intervalFor(item.stage, item.error_count);
  item.due_at = now + item.interval_days * DAY;
  if (item.flagged) item.due_at = now;
  item.recovery = recoveryState(item);
  return item;
}

export function flag(book, code, now) {
  let item = book.get(code);
  if (!item) {
    item = newItem(code, now);
    book.set(code, item);
  }
  item.flagged = true;
  item.due_at = now;
  return item;
}

/**
 * Reconstrói a fila a partir do histórico. Respostas de texto livre contam
 * no momento da avaliação (como no computador); marcações contam na data em que foram feitas.
 */
export function replay(attempts, flags, knownCodes = null) {
  const events = [];
  for (const a of attempts) {
    if (knownCodes && !knownCodes.has(a.exercise)) continue;
    const s = effectiveScore(a);
    if (s == null) continue;
    const at = a.result === "pending" ? Date.parse(a.written.assessed_at || a.created_at) : Date.parse(a.created_at);
    events.push({ at, seq: a.seq ?? 0, kind: "attempt", a, s });
  }
  for (const f of flags) {
    if (knownCodes && !knownCodes.has(f.exercise)) continue;
    events.push({ at: Date.parse(f.created_at), seq: f.seq ?? 0, kind: "flag", f });
  }
  // mesma ordem do computador (learning/sync.py): data, tentativas antes de marcações, ordem de criação
  events.sort((x, y) => x.at - y.at || (x.kind === "flag") - (y.kind === "flag") || x.seq - y.seq);
  const book = new Map();
  for (const ev of events) {
    if (ev.kind === "flag") flag(book, ev.f.exercise, ev.at);
    else register(book, ev.a.exercise, ev.s, ev.a.answer_display, ev.at, Boolean(ev.a.from_review));
  }
  return book;
}

export function isDue(item, now) {
  return item.due_at <= now;
}

/** Maior = mais urgente. */
export function priority(item, competencyOf, compScores, now) {
  const overdue = Math.max(0, (now - item.due_at) / DAY);
  const comp = (100 - (compScores[competencyOf(item.exercise)] ?? 0)) / 50;
  return overdue + 1.5 * Math.min(item.error_count, 5) + (item.flagged ? 3 : 0) + comp;
}
