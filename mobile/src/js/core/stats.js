// Indicadores do painel — espelho de learning/stats.py.
import { compute, scopeExercises } from "./mastery.js";

export function localDay(ms) {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function streak(attempts, now = Date.now()) {
  const days = new Set(attempts.map((a) => localDay(Date.parse(a.created_at))));
  if (!days.size) return 0;
  let cursor = new Date(now);
  if (!days.has(localDay(cursor.getTime()))) cursor.setDate(cursor.getDate() - 1);
  let count = 0;
  while (days.has(localDay(cursor.getTime()))) {
    count++;
    cursor.setDate(cursor.getDate() - 1);
  }
  return count;
}

export function accuracy(attempts) {
  const graded = attempts.filter((a) => a.result !== "pending");
  if (!graded.length) return null;
  return Math.round(1000 * graded.reduce((s, a) => s + a.score, 0) / graded.length) / 10;
}

export function minutes(attempts, since = 0) {
  const secs = attempts.filter((a) => Date.parse(a.created_at) >= since).reduce((s, a) => s + (a.duration_seconds || 0), 0);
  return Math.round(secs / 60);
}

export function startOfToday(now = Date.now()) {
  const d = new Date(now);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

export function masteryAll(state) {
  const { content, attempts } = state;
  const ex = content.exercises;
  const out = { overall: compute(ex, attempts), chapter: {}, competency: {}, objective: {}, grammar: {}, vocabulary: {} };
  for (const ch of content.chapters) {
    out.chapter[ch.code] = compute(scopeExercises(ex, "chapter", ch.code), attempts);
    for (const o of ch.objectives) out.objective[o.code] = compute(scopeExercises(ex, "objective", o.code), attempts);
    for (const g of ch.grammar) out.grammar[g.code] = compute(scopeExercises(ex, "grammar", g.code), attempts);
    for (const v of ch.vocab) out.vocabulary[v.code] = compute(scopeExercises(ex, "vocabulary", v.code), attempts);
  }
  for (const c of content.competencies) out.competency[c.code] = compute(scopeExercises(ex, "competency", c.code), attempts);
  return out;
}

export function overview(state, m, now = Date.now()) {
  const { content, attempts } = state;
  const chapterScores = content.chapters.map((c) => m.chapter[c.code].score);
  const general = content.chapters.length
    ? Math.round(10 * chapterScores.reduce((a, b) => a + b, 0) / content.chapters.length) / 10 : 0;
  const comps = content.competencies.map((c) => ({ code: c.code, name: c.name, ...m.competency[c.code] }))
    .filter((r) => r.attempts >= 3);
  const strong = [...comps].sort((a, b) => b.score - a.score).slice(0, 3);
  let weak = [...comps].sort((a, b) => a.accuracy - b.accuracy).slice(0, 3);
  weak = weak.filter((r) => !strong.includes(r) || comps.length <= 3);
  const errors = [...state.book.values()].filter((i) => i.error_count > 0 && state.exByCode.has(i.exercise))
    .sort((a, b) => b.error_count - a.error_count || (b.last_error_at || 0) - (a.last_error_at || 0)).slice(0, 5);
  return {
    general, attemptCount: attempts.length, distinct: new Set(attempts.map((a) => a.exercise)).size,
    accuracy: accuracy(attempts), streak: streak(attempts, now), totalMinutes: minutes(attempts),
    minutesToday: minutes(attempts, startOfToday(now)),
    dueReviews: [...state.book.values()].filter((i) => i.due_at <= now && state.exByCode.has(i.exercise)).length,
    strong, weak, errors,
  };
}

export function currentChapter(state) {
  const pref = state.settings.current_chapter;
  if (pref && state.content.chapters.some((c) => c.code === pref)) return pref;
  let last = null;
  for (const a of state.attempts) if (!last || Date.parse(a.created_at) >= Date.parse(last.created_at)) last = a;
  if (last && state.exByCode.has(last.exercise)) return state.exByCode.get(last.exercise).chapter;
  return state.content.chapters[0]?.code || "";
}
