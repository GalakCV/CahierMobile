// Sessões de estudo e sincronização — equivalente a learning/sessions.py e learning/sync.py.
import { grade } from "./core/grading.js";
import { effectiveScore } from "./core/mastery.js";
import { register } from "./core/review.js";
import { addAssessment, addAttempt, addFlag, put, putMany, rebuildBook, requestPersistence, saveMeta, saveSession,
  state, touch, updateWritten } from "./store.js";
import { nowIso, uid } from "./util.js";

const MAX_ANSWER_SECONDS = 600;

export function createSession(exercises, { mode = "practice", kind = "custom", chapter = "", passage = "", parent = "",
  title = "", filters = {} } = {}) {
  if (!exercises.length) throw new Error("Nenhuma questão disponível com esses critérios.");
  const now = nowIso();
  const s = { id: uid(), mode, kind, status: "active", chapter, passage, parent, title, filters, started_at: now,
    last_activity_at: now, finished_at: null, result_score: null,
    items: exercises.map((e) => ({ exercise: e.code, shown_at: null, answered_at: null, attempt: null })) };
  state.sessions.push(s);
  saveSession(s);
  return s;
}

export const getSession = (id) => state.sessions.find((s) => s.id === id);
export const nextIndex = (s) => s.items.findIndex((i) => !i.answered_at);
export const answeredCount = (s) => s.items.filter((i) => i.answered_at).length;

export function resumable() {
  return state.sessions.filter((s) => s.status !== "finished" && nextIndex(s) >= 0)
    .sort((a, b) => Date.parse(b.last_activity_at) - Date.parse(a.last_activity_at))[0] || null;
}

export function markShown(s, idx) {
  const item = s.items[idx];
  if (!item.shown_at) {
    item.shown_at = nowIso();
    if (s.status === "paused") s.status = "active";
    saveSession(s);
  }
}

export async function answerItem(s, idx, answer, usedTranslation = false) {
  const item = s.items[idx];
  if (item.answered_at) return state.attemptByUid.get(item.attempt);
  const ex = state.exByCode.get(item.exercise);
  const r = grade(ex, answer);
  const now = new Date();
  const started = item.shown_at ? Date.parse(item.shown_at) : now.getTime();
  const duration = Math.round(Math.min(MAX_ANSWER_SECONDS, Math.max(0, (now.getTime() - started) / 1000)));
  const attempt = {
    uid: uid(), exercise: ex.code, version: ex.version || 1, session: s.id, mode: s.mode,
    from_review: s.kind === "spaced_review", answer, answer_display: r.answerDisplay,
    correct_display: r.correctDisplay, result: r.result, score: r.score, feedback: r.feedback, parts: r.parts,
    duration_seconds: duration, used_translation: Boolean(usedTranslation && s.mode !== "assessment"),
    created_at: now.toISOString(), device: "mobile",
    written: r.result === "pending" ? { text: answer.text ?? r.answerDisplay, criteria_checked: [], assessed_score: null,
      assessed_by: "", assessed_at: null, marked_for_review: false, notes: "" } : null,
  };
  await addAttempt(attempt, r.result === "pending" ? null : r.score);
  item.answered_at = attempt.created_at;
  item.attempt = attempt.uid;
  s.last_activity_at = attempt.created_at;
  s.status = "active";
  await saveSession(s);
  if (state.attempts.length === 1 || state.attempts.length % 10 === 0) requestPersistence();
  return attempt;
}

/** Autoavaliação (ou correção posterior) de um texto livre. */
export async function selfAssess(attempt, checked, markedForReview, overall = null, by = "self", notes = "") {
  const ex = state.exByCode.get(attempt.exercise);
  const criteria = ex?.criteria || [];
  const valid = [...new Set(checked)].filter((i) => i >= 0 && i < criteria.length).sort((a, b) => a - b);
  let score;
  if (overall && overall in { correct: 1, partial: 1, incorrect: 1 }) score = { correct: 1, partial: 0.5, incorrect: 0 }[overall];
  else score = criteria.length ? valid.length / criteria.length : 0;
  const first = attempt.written.assessed_score == null;
  const now = nowIso();
  Object.assign(attempt.written, { criteria_checked: valid, assessed_score: Math.round(score * 1000) / 1000,
    assessed_by: by, assessed_at: now, marked_for_review: Boolean(markedForReview), notes });
  if (first) register(state.book, attempt.exercise, attempt.written.assessed_score, attempt.written.text.slice(0, 300), Date.parse(now));
  await updateWritten(attempt);
  if (markedForReview) await addFlag(attempt.exercise);
}

export async function pause(s) {
  if (s.status !== "finished") {
    s.status = "paused";
    s.last_activity_at = nowIso();
    await saveSession(s);
  }
}

export async function finish(s) {
  if (s.status === "finished") return s;
  const scores = s.items.map((i) => i.attempt && state.attemptByUid.get(i.attempt)).filter(Boolean)
    .map(effectiveScore).filter((x) => x != null);
  s.result_score = scores.length ? Math.round(1000 * scores.reduce((a, b) => a + b, 0) / scores.length) / 1000 : null;
  s.status = "finished";
  s.finished_at = nowIso();
  await saveSession(s);
  if (s.kind === "chapter_assessment" && s.result_score != null) {
    await addAssessment({ uid: s.id, chapter: s.chapter, result_score: s.result_score, finished_at: s.finished_at,
      title: s.title, device: "mobile" });
  }
  return s;
}

// ---------------------------------------------------------------------------
// Sincronização (formato cahier-sync, o mesmo do computador)
// ---------------------------------------------------------------------------

export function exportSync() {
  const strip = ({ seq, parts, session, ...rest }) => rest;
  return {
    format: "cahier-sync", version: 1, device: "mobile", device_id: state.meta.device_id, exported_at: nowIso(),
    attempts: state.attempts.map(strip),
    flags: state.flags.map(({ seq, ...f }) => f),
    assessments: state.assessments,
    issues: state.issues,
  };
}

export async function markExported() {
  state.meta.last_export = nowIso();
  await saveMeta();
}

/** Respostas feitas neste celular depois da última exportação. */
export function pendingExport() {
  const since = state.meta.last_export ? Date.parse(state.meta.last_export) : 0;
  return state.attempts.filter((a) => a.device === "mobile" && Date.parse(a.created_at) > since).length;
}

const RESULTS = new Set(["correct", "partial", "incorrect", "pending"]);

export async function importSync(data) {
  const report = { attempts: 0, flags: 0, assessments: 0, written: 0, unknown: new Set(), errors: [] };
  if (!data || data.format !== "cahier-sync" || data.version !== 1) {
    report.errors.push("Este não é um arquivo de sincronização do Cahier.");
    return report;
  }
  const newAttempts = [];
  for (const a of data.attempts || []) {
    if (!a || typeof a.uid !== "string" || typeof a.exercise !== "string" || !RESULTS.has(a.result) ||
        typeof a.score !== "number" || Number.isNaN(Date.parse(a.created_at))) continue;
    const local = state.attemptByUid.get(a.uid);
    if (local) {
      const w = a.written;
      if (local.written && w && w.assessed_score != null &&
          (local.written.assessed_score == null || Date.parse(w.assessed_at || 0) > Date.parse(local.written.assessed_at || 0))) {
        Object.assign(local.written, { criteria_checked: w.criteria_checked || [], assessed_score: w.assessed_score,
          assessed_by: w.assessed_by || "self", assessed_at: w.assessed_at || nowIso(),
          marked_for_review: Boolean(w.marked_for_review), notes: w.notes || "" });
        await put("attempts", local);
        report.written++;
      }
      continue;
    }
    if (!state.exByCode.has(a.exercise)) report.unknown.add(a.exercise);
    state.meta.seq += 1;
    const copy = { ...a, seq: state.meta.seq, device: a.device || data.device || "desktop" };
    newAttempts.push(copy);
    state.attempts.push(copy);
    state.attemptByUid.set(copy.uid, copy);
    report.attempts++;
  }
  const known = new Set(state.flags.map((f) => f.uid));
  const newFlags = [];
  for (const f of data.flags || []) {
    if (!f || !f.uid || known.has(f.uid) || Number.isNaN(Date.parse(f.created_at))) continue;
    state.meta.seq += 1;
    const copy = { ...f, seq: state.meta.seq };
    state.flags.push(copy);
    newFlags.push(copy);
    known.add(f.uid);
    report.flags++;
  }
  const knownAssess = new Set(state.assessments.map((s) => s.uid));
  const newAssess = [];
  for (const s of data.assessments || []) {
    if (!s || !s.uid || knownAssess.has(s.uid) || typeof s.result_score !== "number") continue;
    state.assessments.push(s);
    newAssess.push(s);
    report.assessments++;
  }
  await Promise.all([putMany("attempts", newAttempts), putMany("flags", newFlags), putMany("assessments", newAssess)]);
  state.attempts.sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at) || a.seq - b.seq);
  state.meta.last_import = nowIso();
  await saveMeta();
  rebuildBook();
  touch();
  return report;
}
