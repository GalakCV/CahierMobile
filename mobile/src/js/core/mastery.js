// Domínio (0–100) — espelho de learning/mastery.py. Ver docs/ALGORITMOS.md.
import { pyRound } from "./text.js";

const DIFFICULTY_WEIGHT = { 1: 0.6, 2: 0.8, 3: 1.0, 4: 1.2, 5: 1.4 };
const RECENCY_DECAY = 0.9;
const RECENCY_FLOOR = 0.2;
const SLOW_FACTOR = 0.85;
const RETENTION_BONUS = 1.3;
const RETENTION_GAP_MS = 3 * 86400 * 1000;
const EVIDENCE_TARGET = 12;
const EVIDENCE_FLOOR = 0.3;
const CAP_WITHOUT_RETENTION = 0.9;
const REPEAT_PENALTY = 0.05;
const MAX_PENALTY = 0.2;
export const CONSTANTS = { cap: 90, evidence: EVIDENCE_TARGET };

const LEVELS = [[90, "Dominado"], [75, "Forte"], [50, "Bom"], [20, "Em desenvolvimento"], [0, "Inicial"]];

export function levelLabel(score) {
  for (const [t, label] of LEVELS) if (score >= t) return label;
  return "Inicial";
}

/** Nota que conta para domínio/revisão: a da correção ou a da autoavaliação. */
export function effectiveScore(a) {
  if (a.result !== "pending") return a.score;
  return a.written && a.written.assessed_score != null ? a.written.assessed_score : null;
}

export const attemptTime = (a) => Date.parse(a.created_at);

export function byTime(a, b) {
  return attemptTime(a) - attemptTime(b) || (a.seq ?? 0) - (b.seq ?? 0);
}

function empty(total) {
  return { score: 0, level: "Inicial", accuracy: 0, coverage: 0, variety: 0, evidence: 0, confidence: 0,
    attempts: 0, attempted_exercises: 0, total_exercises: total, repeated_errors: 0, penalty: 0,
    retention: false, cap: 90 };
}

/** Função pura: questões do escopo e tentativas sobre elas. */
export function compute(exercises, attempts) {
  const total = exercises.length;
  if (!total) return empty(total);
  const info = new Map(exercises.map((e) => [e.code, e]));
  const graded = [];
  for (const a of attempts) {
    if (!info.has(a.exercise)) continue;
    const s = effectiveScore(a);
    if (s != null) graded.push([a, s]);
  }
  if (!graded.length) return empty(total);
  graded.sort((x, y) => byTime(x[0], y[0]));

  const lastSeen = new Map();
  const retention = graded.map(([a, s]) => {
    const prev = lastSeen.get(a.exercise);
    const t = attemptTime(a);
    lastSeen.set(a.exercise, t);
    return prev != null && s >= 0.99 && t - prev >= RETENTION_GAP_MS;
  });

  const n = graded.length;
  let num = 0, den = 0;
  graded.forEach(([a, s], idx) => {
    const e = info.get(a.exercise);
    let w = DIFFICULTY_WEIGHT[e.difficulty] ?? 1.0;
    w *= Math.max(RECENCY_FLOOR, RECENCY_DECAY ** (n - 1 - idx));
    const est = Math.max(10, e.seconds ?? 45);
    if (a.duration_seconds && a.duration_seconds > 2 * est) w *= SLOW_FACTOR;
    if (retention[idx]) w *= RETENTION_BONUS;
    num += w * s;
    den += w;
  });
  const accuracy = den ? num / den : 0;

  const attempted = new Set(graded.map(([a]) => a.exercise));
  const coverage = attempted.size / total;
  const typesAvailable = new Set(exercises.map((e) => e.type));
  const typesDone = new Set([...attempted].map((c) => info.get(c).type));
  const variety = Math.min(1, typesDone.size / Math.max(1, Math.min(5, typesAvailable.size)));
  const evidence = Math.min(1, n / EVIDENCE_TARGET);
  let confidence = 0.5 * coverage + 0.25 * variety + 0.25 * evidence;
  confidence = Math.min(confidence, EVIDENCE_FLOOR + (1 - EVIDENCE_FLOOR) * evidence);

  const history = new Map();
  for (const [a, s] of graded) {
    if (!history.has(a.exercise)) history.set(a.exercise, []);
    history.get(a.exercise).push(s);
  }
  let repeated = 0;
  for (const sc of history.values()) {
    if (sc.length >= 2 && sc[sc.length - 1] < 0.5 && sc[sc.length - 2] < 0.5) repeated++;
  }
  const penalty = Math.min(MAX_PENALTY, REPEAT_PENALTY * repeated);
  const hasRetention = retention.some(Boolean);
  const cap = hasRetention ? 1.0 : CAP_WITHOUT_RETENTION;
  const value = Math.max(0, Math.min(cap, accuracy * confidence) - penalty);
  const score = pyRound(value * 100, 1);
  return {
    score, level: levelLabel(score), accuracy: pyRound(accuracy * 100, 1), coverage: pyRound(coverage * 100, 1),
    variety: pyRound(variety * 100, 1), evidence: pyRound(evidence * 100, 1),
    confidence: pyRound(confidence * 100, 1), attempts: n, attempted_exercises: attempted.size,
    total_exercises: total, repeated_errors: repeated, penalty: pyRound(penalty * 100, 1),
    retention: hasRetention, cap: Math.round(cap * 100),
  };
}

/** Questões de cada escopo (capítulo, objetivo, gramática, vocabulário, competência). */
export function scopeExercises(exercises, scope, id) {
  switch (scope) {
    case "chapter": return exercises.filter((e) => e.chapter === id);
    case "objective": return exercises.filter((e) => e.objectives.includes(id));
    case "grammar": return exercises.filter((e) => e.grammar.includes(id));
    case "vocabulary": return exercises.filter((e) => e.vocab.includes(id));
    case "competency": return exercises.filter((e) => e.competency === id);
    default: return exercises;
  }
}
