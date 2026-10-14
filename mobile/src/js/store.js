// Estado do app e persistência local (IndexedDB). Nada sai do aparelho sem uma exportação manual.
import { masteryAll } from "./core/stats.js";
import { register, replay, flag as flagItem } from "./core/review.js";
import { uid } from "./util.js";

const DB_NAME = "cahier";
const DB_VERSION = 1;
const STORES = { attempts: "uid", flags: "uid", sessions: "id", assessments: "uid", issues: "uid", kv: "key" };

export const DEFAULT_SETTINGS = {
  display_name: "", session_size: 10, daily_goal: 15, keyboard: true, font: "normal", theme: "auto", current_chapter: "",
};

export const state = {
  content: null, exByCode: new Map(), chapterByCode: new Map(), passageByCode: new Map(),
  attempts: [], flags: [], sessions: [], assessments: [], issues: [], attemptByUid: new Map(),
  book: new Map(), settings: { ...DEFAULT_SETTINGS },
  meta: { device_id: "", seq: 0, last_export: null, last_import: null, exported_uids: 0 },
  persistent: false, storageOk: true, revision: 0,
  chapterNumber: (code) => state.chapterByCode.get(code)?.number ?? 0,
};

let db = null;

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      for (const [name, keyPath] of Object.entries(STORES)) {
        if (!req.result.objectStoreNames.contains(name)) req.result.createObjectStore(name, { keyPath });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx(store, mode, fn) {
  if (!db) return Promise.resolve(null);
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const s = t.objectStore(store);
    const r = fn(s);
    t.oncomplete = () => resolve(r?.result ?? null);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  });
}

const getAll = (store) => tx(store, "readonly", (s) => s.getAll());
export const put = (store, value) => tx(store, "readwrite", (s) => s.put(value)).catch(storageError);
export function putMany(store, values) {
  if (!values.length) return Promise.resolve();
  return tx(store, "readwrite", (s) => { values.forEach((v) => s.put(v)); }).catch(storageError);
}
const clearStore = (store) => tx(store, "readwrite", (s) => s.clear());

function storageError(err) {
  console.error(err);
  state.storageOk = false;
  document.dispatchEvent(new CustomEvent("cahier:storage-error"));
}

export async function init() {
  const resp = await fetch("content.json");
  if (!resp.ok) throw new Error(`content.json: ${resp.status}`);
  state.content = await resp.json();
  state.content.exercises.forEach((e, i) => {
    e._i = i;
    e.objectives = e.objectives || []; e.grammar = e.grammar || []; e.vocab = e.vocab || [];
    state.exByCode.set(e.code, e);
  });
  state.content.chapters.forEach((c) => state.chapterByCode.set(c.code, c));
  state.content.passages.forEach((p) => state.passageByCode.set(p.code, p));
  try {
    db = await openDB();
    const [attempts, flags, sessions, assessments, issues, kv] = await Promise.all(
      ["attempts", "flags", "sessions", "assessments", "issues", "kv"].map(getAll));
    state.attempts = attempts.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
    state.flags = flags;
    state.sessions = sessions;
    state.assessments = assessments;
    state.issues = issues;
    for (const row of kv) {
      if (row.key === "settings") state.settings = { ...DEFAULT_SETTINGS, ...row.value };
      if (row.key === "meta") state.meta = { ...state.meta, ...row.value };
    }
  } catch (err) {
    console.error(err);
    state.storageOk = false;
  }
  if (!state.meta.device_id) {
    state.meta.device_id = uid();
    await saveMeta();
  }
  state.attemptByUid = new Map(state.attempts.map((a) => [a.uid, a]));
  rebuildBook();
  if (navigator.storage?.persisted) state.persistent = await navigator.storage.persisted().catch(() => false);
}

export function rebuildBook() {
  state.book = replay(state.attempts, state.flags, new Set(state.exByCode.keys()));
  touch();
}

export function touch() {
  state.revision++;
  masteryCache = null;
}

let masteryCache = null;
export function mastery() {
  if (!masteryCache) masteryCache = masteryAll(state);
  return masteryCache;
}

export const saveSettings = () => put("kv", { key: "settings", value: state.settings });
export const saveMeta = () => put("kv", { key: "meta", value: state.meta });
export const saveSession = (s) => put("sessions", s);

export async function requestPersistence() {
  if (state.persistent || !navigator.storage?.persist) return state.persistent;
  state.persistent = await navigator.storage.persist().catch(() => false);
  return state.persistent;
}

/** Grava uma tentativa nova (imutável) e atualiza a fila de revisão. */
export async function addAttempt(attempt, scoreForReview) {
  state.meta.seq += 1;
  attempt.seq = state.meta.seq;
  state.attempts.push(attempt);
  state.attemptByUid.set(attempt.uid, attempt);
  if (scoreForReview != null) {
    register(state.book, attempt.exercise, scoreForReview, attempt.answer_display, Date.parse(attempt.created_at),
      Boolean(attempt.from_review));
  }
  touch();
  await Promise.all([put("attempts", attempt), saveMeta()]);
  return attempt;
}

/** Atualiza a parte de autoavaliação de uma resposta de texto livre. */
export async function updateWritten(attempt) {
  touch();
  await put("attempts", attempt);
}

export async function addFlag(code) {
  state.meta.seq += 1;
  const f = { uid: uid(), exercise: code, created_at: new Date().toISOString(), seq: state.meta.seq, device: "mobile" };
  state.flags.push(f);
  flagItem(state.book, code, Date.parse(f.created_at));
  touch();
  await Promise.all([put("flags", f), saveMeta()]);
}

export async function addAssessment(record) {
  state.assessments.push(record);
  touch();
  await put("assessments", record);
}

export async function addIssue(issue) {
  state.issues.push(issue);
  await put("issues", issue);
}

export async function resetAll() {
  for (const s of Object.keys(STORES)) await clearStore(s).catch(() => {});
  Object.assign(state, { attempts: [], flags: [], sessions: [], assessments: [], issues: [], attemptByUid: new Map() });
  state.settings = { ...DEFAULT_SETTINGS };
  state.meta = { device_id: uid(), seq: 0, last_export: null, last_import: null, exported_uids: 0 };
  await Promise.all([saveSettings(), saveMeta()]);
  rebuildBook();
}
