// Correção de respostas — espelho de learning/grading.py.
// As alternativas são identificadas pelo índice na ordem de exibição.
import { exactForm, ligatureFold, normalize, pyRound, stripAccents } from "./text.js";

export const BLANK = "___";

export function blankCount(ex) {
  return ex.interaction === "text" ? ex.prompt.split(BLANK).length - 1 : 0;
}

export function answerIsEmpty(ex, answer) {
  switch (ex.interaction) {
    case "single": return answer.choice == null;
    case "multiple": return !answer.choices || answer.choices.length === 0;
    case "text": return (answer.blanks || []).every((b) => !String(b).trim());
    case "order": return !answer.order || answer.order.length === 0;
    case "match": return !Object.values(answer.pairs || {}).some((v) => v != null);
    case "writing": return !String(answer.text || "").trim();
    default: return true;
  }
}

function sep(ex) {
  return ex.type === "order_words" ? " " : " / ";
}

export function correctDisplay(ex) {
  const choices = ex.choices || [];
  const it = ex.interaction;
  if (it === "single" || it === "multiple") return choices.filter((c) => c.ok).map((c) => c.t).join(" | ");
  if (it === "order") {
    return choices.filter((c) => c.pos).sort((a, b) => a.pos - b.pos).map((c) => c.t).join(sep(ex));
  }
  if (it === "match") return choices.map((c) => `${c.t} → ${c.m}`).join("; ");
  if (it === "writing") return ex.model || "";
  const answers = ex.answers || [];
  const n = Math.max(1, blankCount(ex));
  const parts = [];
  for (let i = 0; i < n; i++) {
    const prim = answers.filter((a) => a.b === i && a.p).map((a) => a.t);
    const any = answers.filter((a) => a.b === i).map((a) => a.t);
    parts.push((prim.length ? prim : any)[0] || "");
  }
  if (["manual", "self", "regex"].includes(ex.comparison) && ex.model) return ex.model;
  return n === 1 ? parts[0] : parts.map((p, i) => `${i + 1}) ${p}`).join(" · ");
}

const result = (r, score, answerDisplay, correct, feedback = "", parts = []) =>
  ({ result: r, score: pyRound(score, 3), answerDisplay, correctDisplay: correct, feedback, parts });

export function grade(ex, answer) {
  switch (ex.interaction) {
    case "single": return gradeSingle(ex, answer);
    case "multiple": return gradeMultiple(ex, answer);
    case "order": return gradeOrder(ex, answer);
    case "match": return gradeMatch(ex, answer);
    case "writing":
      return result("pending", 0, answer.text || "", ex.model || "",
        "Compare seu texto com a resposta-modelo e use os critérios para se autoavaliar.");
    default: return gradeText(ex, answer);
  }
}

function gradeSingle(ex, answer) {
  const chosen = (ex.choices || [])[answer.choice];
  const ok = Boolean(chosen && chosen.ok);
  return result(ok ? "correct" : "incorrect", ok ? 1 : 0, chosen ? chosen.t : "(sem resposta)",
    correctDisplay(ex), chosen && chosen.fb ? chosen.fb : "");
}

function gradeMultiple(ex, answer) {
  const choices = ex.choices || [];
  const chosen = new Set((answer.choices || []).filter((i) => i >= 0 && i < choices.length));
  const correct = new Set(choices.map((c, i) => (c.ok ? i : -1)).filter((i) => i >= 0));
  let tp = 0, fp = 0;
  for (const i of chosen) (correct.has(i) ? tp++ : fp++);
  let score = correct.size ? Math.max(0, (tp - fp) / correct.size) : 0;
  const same = chosen.size === correct.size && [...chosen].every((i) => correct.has(i));
  let r;
  if (same) { r = "correct"; score = 1; } else if (score > 0) r = "partial"; else r = "incorrect";
  const shown = [...chosen].sort((a, b) => a - b).map((i) => choices[i].t).join(" | ") || "(sem resposta)";
  let fb = "";
  if (r === "partial") {
    const missing = [...correct].filter((i) => !chosen.has(i)).length;
    fb = `Você acertou ${tp} de ${correct.size} alternativas corretas` +
      (fp ? ` e marcou ${fp} incorreta(s).` : `; faltou marcar ${missing}.`);
  }
  return result(r, score, shown, correctDisplay(ex), fb);
}

function gradeOrder(ex, answer) {
  const choices = ex.choices || [];
  const order = (answer.order || []).filter((i) => i >= 0 && i < choices.length);
  const expected = choices.map((c, i) => [c.pos, i]).filter(([p]) => p).sort((a, b) => a[0] - b[0]).map(([, i]) => i);
  const shown = order.map((i) => choices[i].t).join(sep(ex)) || "(sem resposta)";
  if (order.length === expected.length && order.every((v, k) => v === expected[k])) {
    return result("correct", 1, shown, correctDisplay(ex));
  }
  const joined = normalize(order.map((i) => choices[i].t).join(" "));
  for (const acc of ex.answers || []) {
    if (normalize(acc.t) === joined && order.length === expected.length) {
      return result("correct", 1, shown, correctDisplay(ex), "Esta ordem também é aceita.");
    }
  }
  let placed = 0;
  for (let k = 0; k < Math.min(order.length, expected.length); k++) if (order[k] === expected[k]) placed++;
  const score = expected.length ? placed / expected.length : 0;
  return result(score >= 0.5 ? "partial" : "incorrect", score, shown, correctDisplay(ex),
    `${placed} de ${expected.length} elementos na posição certa.`);
}

function gradeMatch(ex, answer) {
  const choices = ex.choices || [];
  const pairs = answer.pairs || {};
  let good = 0;
  const shown = [];
  choices.forEach((c, i) => {
    const pick = pairs[String(i)];
    const right = pick == null ? undefined : choices[pick];
    shown.push(`${c.t} → ${right ? right.m : "?"}`);
    if (right !== undefined && (pick === i || right.m === c.m)) good++;
  });
  const total = choices.length;
  const score = total ? good / total : 0;
  const r = good === total ? "correct" : score >= 0.5 ? "partial" : "incorrect";
  return result(r, score, shown.join("; "), correctDisplay(ex), r === "correct" ? "" : `${good} de ${total} pares corretos.`);
}

function gradeText(ex, answer) {
  const n = Math.max(1, blankCount(ex));
  const blanks = [...(answer.blanks || [""]), ...Array(n).fill("")].slice(0, n).map(String);
  const shown = n === 1 ? blanks[0] : blanks.map((b, i) => `${i + 1}) ${b}`).join(" · ");
  const mode = ex.comparison;
  if (mode === "manual" || mode === "self") {
    return result("pending", 0, shown, correctDisplay(ex), "Resposta guardada. Compare com a resposta-modelo para avaliá-la.");
  }
  const answers = ex.answers || [];
  let good = 0, accentIssue = false;
  const parts = [];
  blanks.forEach((typed, i) => {
    let cands = answers.filter((a) => a.b === i);
    if (mode === "normalized") {
      const prim = cands.filter((a) => a.p);
      if (prim.length) cands = prim;
    }
    const status = matchBlank(typed, cands.map((a) => a.t), mode, Boolean(ex.accent_insensitive));
    if (status === "ok" || status === "ok_accent") good++;
    if (status === "accent" || status === "ok_accent") accentIssue = true;
    parts.push({ typed, status });
  });
  const score = good / n;
  const r = good === n ? "correct" : good > 0 ? "partial" : "incorrect";
  let feedback = "";
  if (accentIssue) {
    feedback = ex.accent_insensitive
      ? "Atenção aos acentos: aqui eles não foram considerados, mas a grafia correta usa acento."
      : "Quase! A resposta só difere nos acentos — e neste exercício eles fazem parte da correção.";
  }
  if (r === "partial") feedback = (feedback ? feedback + " " : "") + `${good} de ${n} lacunas corretas.`;
  return result(r, score, shown, correctDisplay(ex), feedback, parts);
}

function fullMatch(pattern, text) {
  try {
    return new RegExp(`^(?:${pattern})$`, "iu").test(text);
  } catch {
    return false;
  }
}

export function matchBlank(typed, candidates, mode, accentInsensitive) {
  if (!String(typed).trim()) return "wrong";
  if (mode === "exact") {
    const t = exactForm(typed);
    if (candidates.some((c) => t === exactForm(c))) return "ok";
    if (candidates.some((c) => stripAccents(t) === stripAccents(exactForm(c)))) return accentInsensitive ? "ok_accent" : "accent";
    return "wrong";
  }
  const t = normalize(typed);
  if (mode === "regex") {
    for (const c of candidates) {
      if (fullMatch(c, t)) return "ok";
      if (fullMatch(stripAccents(c), stripAccents(t))) return accentInsensitive ? "ok_accent" : "accent";
    }
    return "wrong";
  }
  const tf = ligatureFold(t);
  if (candidates.some((c) => tf === ligatureFold(normalize(c)))) return "ok";
  if (candidates.some((c) => stripAccents(tf) === stripAccents(ligatureFold(normalize(c))))) {
    return accentInsensitive ? "ok_accent" : "accent";
  }
  return "wrong";
}
