// Montagem de sessões e estado dos capítulos — espelho de learning/sessions.py.
import { compute, effectiveScore, scopeExercises } from "./mastery.js";
import { priority } from "./review.js";

export const PASS_SCORE = 0.7;
const READY_MASTERY = 60;
const READY_COVERAGE = 50;
const DAY = 86400 * 1000;

export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function competencyScores(content, attempts) {
  const out = {};
  for (const c of content.competencies) out[c.code] = compute(scopeExercises(content.exercises, "competency", c.code), attempts).score;
  return out;
}

export function pickDiverse(ranked, count, topicCap = null) {
  topicCap = topicCap || Math.max(2, Math.ceil(count / 2));
  const chosen = [];
  const blocked = new Set();
  const perTopic = new Map();
  const deferred = [];
  for (const ex of ranked) {
    if (chosen.length >= count) break;
    if (blocked.has(ex.code)) continue;
    if (ex.grammar.length && ex.grammar.some((t) => (perTopic.get(t) || 0) >= topicCap)) {
      deferred.push(ex);
      continue;
    }
    chosen.push(ex);
    (ex.similar || []).forEach((c) => blocked.add(c));
    ex.grammar.forEach((t) => perTopic.set(t, (perTopic.get(t) || 0) + 1));
  }
  for (const ex of deferred) {
    if (chosen.length >= count) break;
    if (!blocked.has(ex.code)) {
      chosen.push(ex);
      (ex.similar || []).forEach((c) => blocked.add(c));
    }
  }
  return chosen;
}

export function progressiveOrder(exercises, chapterNumber) {
  const groups = new Map();
  for (const ex of exercises) {
    const key = ex.passage ? `p:${ex.passage}` : `e:${ex.code}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(ex);
  }
  const ordered = [...groups.values()].sort((a, b) =>
    Math.min(...a.map((e) => e.difficulty)) - Math.min(...b.map((e) => e.difficulty)) ||
    Math.min(...a.map((e) => chapterNumber(e.chapter))) - Math.min(...b.map((e) => chapterNumber(e.chapter))));
  return ordered.flatMap((g) => g.sort((x, y) => x.position - y.position || x._i - y._i));
}

function rankForPractice(candidates, state, seed) {
  const random = rng(seed);
  const attempted = new Set(state.attempts.map((a) => a.exercise));
  const comp = competencyScores(state.content, state.attempts);
  const scored = candidates.map((e) => {
    const item = state.book.get(e.code);
    let s = attempted.has(e.code) ? 0 : 3;
    s += 2 * Math.min(item ? item.error_count : 0, 3);
    s += (100 - (comp[e.competency] ?? 0)) / 50;
    return [s + random(), e];
  });
  return scored.sort((a, b) => b[0] - a[0]).map(([, e]) => e);
}

export function selectPractice(state, { chapter = "", topic = "", competency = "", difficulties = [], count = 10,
  includeAssessment = false, seed = Date.now() } = {}) {
  let qs = state.content.exercises;
  if (chapter) qs = qs.filter((e) => e.chapter === chapter);
  if (topic) {
    const [kind, code] = topic.split(":");
    if (kind === "g") qs = qs.filter((e) => e.grammar.includes(code));
    if (kind === "v") qs = qs.filter((e) => e.vocab.includes(code));
  }
  if (competency) qs = qs.filter((e) => e.competency === competency);
  if (difficulties.length) qs = qs.filter((e) => difficulties.includes(e.difficulty));
  if (!includeAssessment) qs = qs.filter((e) => !e.assessment);
  return progressiveOrder(pickDiverse(rankForPractice(qs, state, seed), count), state.chapterNumber);
}

export function dueItems(state, now = Date.now()) {
  const comp = competencyScores(state.content, state.attempts);
  const competencyOf = (code) => state.exByCode.get(code)?.competency;
  return [...state.book.values()]
    .filter((i) => i.due_at <= now && state.exByCode.has(i.exercise))
    .sort((a, b) => priority(b, competencyOf, comp, now) - priority(a, competencyOf, comp, now));
}

export function selectReview(state, count = 15, now = Date.now()) {
  const ranked = dueItems(state, now).map((i) => state.exByCode.get(i.exercise));
  return pickDiverse(ranked, count, Math.max(2, Math.ceil(count / 3)));
}

export function selectChapterReview(state, chapter, count, seed = Date.now()) {
  const qs = state.content.exercises.filter((e) => e.chapter === chapter && !e.assessment);
  return progressiveOrder(pickDiverse(rankForPractice(qs, state, seed), count), state.chapterNumber);
}

export function selectChapterAssessment(state, chapter) {
  return state.content.exercises.filter((e) => e.chapter === chapter && e.assessment)
    .sort((a, b) => a.difficulty - b.difficulty || a.position - b.position || a._i - b._i);
}

export function selectPassage(state, passage) {
  return state.content.exercises.filter((e) => e.passage === passage)
    .sort((a, b) => a.position - b.position || a._i - b._i);
}

export function wrongExercises(state, session) {
  const codes = [];
  for (const item of session.items) {
    const a = item.attempt && state.attemptByUid.get(item.attempt);
    if (!a) continue;
    const s = effectiveScore(a);
    if (s != null && s < 0.99 && !codes.includes(a.exercise)) codes.push(a.exercise);
  }
  return codes.map((c) => state.exByCode.get(c)).filter(Boolean);
}

export const STATUS_LABELS = {
  not_started: "Não iniciado", in_progress: "Em andamento", needs_review: "Revisão necessária",
  ready: "Apto para avaliação", completed: "Concluído",
};

export function bestAssessment(state, chapter) {
  const done = state.assessments.filter((s) => s.chapter === chapter && s.result_score != null);
  return done.sort((a, b) => b.result_score - a.result_score)[0] || null;
}

export function chapterStatus(state, chapter, now = Date.now()) {
  const exs = state.content.exercises.filter((e) => e.chapter === chapter);
  const codes = new Set(exs.map((e) => e.code));
  const data = compute(exs, state.attempts);
  let dueErrors = 0;
  for (const it of state.book.values()) if (codes.has(it.exercise) && it.due_at <= now && it.error_count > 0) dueErrors++;
  const recent = state.attempts.filter((a) => codes.has(a.exercise) && a.result !== "pending" &&
    Date.parse(a.created_at) >= now - 14 * DAY).map((a) => a.score);
  const recentAcc = recent.length ? recent.reduce((x, y) => x + y, 0) / recent.length : null;
  const best = bestAssessment(state, chapter);
  const assessmentCount = exs.filter((e) => e.assessment).length;
  let status;
  if (data.attempts === 0) status = "not_started";
  else if (best && best.result_score >= PASS_SCORE) status = "completed";
  else if (dueErrors >= 3 || (recentAcc != null && recent.length >= 5 && recentAcc < 0.5)) status = "needs_review";
  else if (data.score >= READY_MASTERY && data.coverage >= READY_COVERAGE) status = "ready";
  else status = "in_progress";
  return { status, label: STATUS_LABELS[status], mastery: data.score, level: data.level, progress: data.coverage,
    details: data, total: exs.length, dueErrors, assessmentCount,
    bestAssessment: best ? Math.round(best.result_score * 100) : null };
}
