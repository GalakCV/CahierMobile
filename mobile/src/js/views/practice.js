import { answerIsEmpty } from "../core/grading.js";
import { effectiveScore } from "../core/mastery.js";
import { chapterStatus, PASS_SCORE, selectPractice, wrongExercises } from "../core/select.js";
import { renderFeedback, renderQuestion, collectAnswer, passageCard } from "../exercise.js";
import { state } from "../store.js";
import { answerItem, createSession, finish, getSession, markShown, nextIndex, pause, selfAssess } from "../study.js";
import { dialogue, go, html, MARK, meter, raw, toast } from "../util.js";

export function practiceSetup({ query }) {
  const s = state.settings;
  const chapter = query.get("capitulo") || "";
  const topics = [];
  for (const ch of state.content.chapters) {
    for (const g of ch.grammar) topics.push([`g:${g.code}`, `${ch.number}. ${g.title}`, "Gramática"]);
    for (const v of ch.vocab) topics.push([`v:${v.code}`, `${ch.number}. ${v.title}`, "Vocabulário"]);
  }
  const opt = (v, l, sel) => html`<option value="${v}" ${sel ? raw("selected") : ""}>${l}</option>`;
  return {
    title: "Praticar", nav: "practice",
    html: html`<h1>Praticar</h1>
      <div class="quick-grid">
        <button class="card quick" data-action="quick" data-count="5"><strong>Rápida</strong><span class="muted small">5 questões · ~3 min</span></button>
        <button class="card quick" data-action="quick" data-count="10"><strong>Média</strong><span class="muted small">10 questões · ~7 min</span></button>
        <button class="card quick" data-action="quick" data-count="20"><strong>Longa</strong><span class="muted small">20 questões · ~15 min</span></button>
        <button class="card quick" data-action="review"><strong>Revisões</strong><span class="muted small">só o que venceu</span></button>
      </div>
      <h2 class="h-small">Sessão personalizada</h2>
      <form class="form" data-form="practice">
        <label class="field"><span>Capítulo</span><select name="chapter">${opt("", "Todos os capítulos", !chapter)}${state.content.chapters.map((c) => opt(c.code, `${c.number}. ${c.title}`, c.code === chapter))}</select></label>
        <label class="field"><span>Tema</span><select name="topic">${opt("", "Todos os temas", true)}
          <optgroup label="Gramática">${topics.filter((t) => t[2] === "Gramática").map((t) => opt(t[0], t[1]))}</optgroup>
          <optgroup label="Vocabulário">${topics.filter((t) => t[2] === "Vocabulário").map((t) => opt(t[0], t[1]))}</optgroup></select></label>
        <label class="field"><span>Competência</span><select name="competency">${opt("", "Todas", true)}${state.content.competencies.map((c) => opt(c.code, c.name))}</select></label>
        <fieldset class="field"><legend>Dificuldade</legend><div class="chips">
          ${[[1, "reconhecer"], [2, "guiada"], [3, "contexto"], [4, "combinar"], [5, "autonomia"]].map(([d, l]) => html`<label class="chip"><input type="checkbox" name="difficulty" value="${d}"><span>${d} · ${l}</span></label>`)}
        </div><span class="helptext">Deixe em branco para misturar.</span></fieldset>
        <label class="field"><span>Quantidade</span><input type="number" name="count" min="3" max="50" value="${s.session_size}" inputmode="numeric"></label>
        <fieldset class="field"><legend>Modo</legend><div class="chips">
          <label class="chip"><input type="radio" name="mode" value="practice" checked><span>Prática</span></label>
          <label class="chip"><input type="radio" name="mode" value="assessment"><span>Avaliação</span></label></div>
          <span class="helptext">Na avaliação, a correção aparece só no final.</span></fieldset>
        <button class="btn block" type="submit">Começar sessão</button>
      </form>`,
    mount(root) {
      root.querySelector('[data-form="practice"]').addEventListener("submit", (e) => {
        e.preventDefault();
        const f = new FormData(e.target);
        const count = Math.max(3, Math.min(50, Number(f.get("count")) || 10));
        const mode = f.get("mode") === "assessment" ? "assessment" : "practice";
        const chapterCode = f.get("chapter") || "";
        const exs = selectPractice(state, { chapter: chapterCode, topic: f.get("topic") || "", competency: f.get("competency") || "",
          difficulties: f.getAll("difficulty").map(Number), count, includeAssessment: mode === "assessment",
          seed: Math.floor(Math.random() * 1e9) });
        if (!exs.length) { toast("Nenhuma questão com esses filtros. Amplie a seleção.", "error"); return; }
        const ch = state.chapterByCode.get(chapterCode);
        const s = createSession(exs, { mode, chapter: chapterCode, title: `${mode === "assessment" ? "Avaliação" : "Prática"}${ch ? ` — ${ch.title}` : ""}` });
        if (exs.length < count) toast(`Foram encontradas ${exs.length} questões com esses filtros.`);
        go(`#/sessao/${s.id}`);
      });
    },
  };
}

function sessionHeader(s, idx, done) {
  const total = s.items.length;
  const pctDone = (100 * (done ? idx + 1 : idx)) / total;
  return html`<header class="session-head">
    <button class="icon-btn" data-action="pause" data-session="${s.id}" aria-label="Interromper e sair">✕</button>
    <div class="grow"><div class="small"><strong>${s.title}</strong></div>
      <div class="muted small">Questão ${idx + 1} de ${total}${s.mode === "assessment" ? " · avaliação" : ""}</div>${meter(pctDone, "small")}</div>
  </header>`;
}

export function sessionPlay({ id }) {
  const s = getSession(id);
  if (!s) return null;
  if (s.status === "finished") return { redirect: `#/resultado/${id}` };
  const idx = nextIndex(s);
  if (idx < 0) return { redirect: `#/resultado/${id}`, before: () => finish(s) };
  const ex = state.exByCode.get(s.items[idx].exercise);
  if (!ex) return { redirect: `#/resultado/${id}`, before: () => finish(s) };
  markShown(s, idx);
  const assessment = s.mode === "assessment";
  let passageOpen = true;
  try { passageOpen = sessionStorage.getItem(`passage-${id}`) !== "closed"; } catch { /* sem sessionStorage */ }
  return {
    title: s.title, focus: true,
    html: html`${sessionHeader(s, idx, false)}
      ${ex.passage ? passageCard(ex.passage, { open: passageOpen, hideTranslation: assessment }) : ""}
      <form class="sheet" data-form="answer" data-code="${ex.code}" novalidate>
        ${renderQuestion(ex, { hideTranslation: assessment })}
        <p class="form-error" role="alert" hidden></p>
        <div class="sticky-actions"><button class="btn block" type="submit">${ex.interaction === "writing" ? "Enviar texto" : "Responder"}</button></div>
      </form>
      <div class="actions small-actions">
        <button class="link-btn" data-action="flag" data-code="${ex.code}">Marcar para revisão</button>
        <a class="link-btn" href="#/sinalizar/${ex.code}">Sinalizar problema</a>
        ${s.items.some((i) => i.answered_at) ? html`<button class="link-btn" data-action="finish" data-session="${s.id}">Encerrar sessão</button>` : ""}
      </div>`,
    mount(root) {
      let usedTranslation = false;
      root.querySelectorAll("details[data-translation]").forEach((d) => d.addEventListener("toggle", () => { if (d.open) usedTranslation = true; }));
      const pd = root.querySelector("details[data-passage]");
      if (pd) pd.addEventListener("toggle", () => { try { sessionStorage.setItem(`passage-${id}`, pd.open ? "open" : "closed"); } catch { /* ignora */ } });
      const form = root.querySelector('[data-form="answer"]');
      let busy = false;
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (busy) return;
        const answer = collectAnswer(form, ex);
        const err = form.querySelector(".form-error");
        if (answerIsEmpty(ex, answer)) {
          err.textContent = "Escreva ou selecione uma resposta antes de enviar.";
          err.hidden = false;
          return;
        }
        busy = true;
        document.activeElement?.blur?.();
        await answerItem(s, idx, answer, usedTranslation);
        go(assessment ? `#/sessao/${id}` : `#/sessao/${id}/${idx + 1}`);
      });
      const first = form.querySelector("input.blank, input.text-answer");
      if (first && matchMedia("(pointer: fine)").matches) first.focus();
    },
  };
}

export function sessionFeedback({ id, pos }) {
  const s = getSession(id);
  if (!s) return null;
  const idx = Number(pos) - 1;
  const item = s.items[idx];
  if (!item || !item.attempt) return { redirect: `#/sessao/${id}` };
  if (s.mode === "assessment" && s.status !== "finished") return { redirect: `#/sessao/${id}` };
  const attempt = state.attemptByUid.get(item.attempt);
  const ex = state.exByCode.get(item.exercise);
  const next = nextIndex(s);
  const nextHref = next >= 0 ? `#/sessao/${id}` : `#/resultado/${id}`;
  const review = state.book.get(ex.code);
  const pendingWritten = attempt.result === "pending" && attempt.written?.assessed_score == null;
  return {
    title: s.title, focus: true,
    html: html`${sessionHeader(s, idx, true)}
      ${ex.passage ? passageCard(ex.passage, { open: false }) : ""}
      <section class="sheet" aria-live="polite">${renderFeedback(ex, attempt)}</section>
      <div class="sticky-actions"><a class="btn block ${pendingWritten ? "ghost" : ""}" href="${nextHref}" data-next>${pendingWritten ? "Avaliar mais tarde" : next >= 0 ? "Próxima questão" : "Ver resultado"}</a></div>
      <div class="actions small-actions">
        ${review?.flagged ? html`<span class="tag">Marcada para revisão</span>` : html`<button class="link-btn" data-action="flag" data-code="${ex.code}">Marcar para revisão</button>`}
        <a class="link-btn" href="#/sinalizar/${ex.code}?resposta=${encodeURIComponent(attempt.answer_display)}">Sinalizar problema</a>
      </div>`,
    mount(root) {
      bindAssessForm(root, () => go(nextHref));
    },
  };
}

export function bindAssessForm(root, after) {
  const form = root.querySelector('[data-form="assess"]');
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(form);
    const attempt = state.attemptByUid.get(form.dataset.uid);
    await selfAssess(attempt, f.getAll("criteria").map(Number), f.get("marked") === "1", f.get("overall") || null);
    toast("Avaliação registrada.", "success");
    after();
  });
}

export async function sessionResult({ id }) {
  const s = getSession(id);
  if (!s) return null;
  if (s.status !== "finished" && nextIndex(s) < 0) await finish(s);
  const items = s.items.map((it) => ({ it, ex: state.exByCode.get(it.exercise), a: it.attempt ? state.attemptByUid.get(it.attempt) : null }));
  const answered = items.filter((x) => x.a);
  const scores = answered.map((x) => effectiveScore(x.a)).filter((v) => v != null);
  const scorePct = scores.length ? Math.round((100 * scores.reduce((a, b) => a + b, 0)) / scores.length) : null;
  const correct = scores.filter((v) => v >= 0.99).length;
  const wrong = answered.filter((x) => { const v = effectiveScore(x.a); return v != null && v < 0.99; }).length;
  const pending = answered.filter((x) => effectiveScore(x.a) == null);
  const passed = s.kind === "chapter_assessment" && s.result_score != null ? s.result_score >= PASS_SCORE : null;
  const passages = [...new Set(items.map((x) => x.ex?.passage).filter(Boolean))].map((c) => state.passageByCode.get(c));
  const minutes = Math.round(answered.reduce((t, x) => t + (x.a.duration_seconds || 0), 0) / 6) / 10;
  return {
    title: "Resultado", nav: "practice", back: "#/",
    html: html`<h1>${s.title}</h1>
      <p class="muted small">${answered.length} de ${items.length} questões · ${String(minutes).replace(".", ",")} min</p>
      <div class="score-row"><p class="score-big">${scorePct == null ? "—" : `${scorePct}%`}</p>
        <p>${correct} correta${correct === 1 ? "" : "s"}, ${wrong} com erro${pending.length ? `, ${pending.length} aguardando avaliação` : ""}.</p></div>
      ${passed === true ? html`<p class="verdict verdict-correct"><span class="mark">✓</span> Avaliação aprovada: capítulo concluído.</p>` : ""}
      ${passed === false ? html`<p class="verdict verdict-incorrect"><span class="mark">✗</span> É preciso 70% para concluir o capítulo. Revise e tente de novo.</p>` : ""}
      <div class="actions">
        ${wrong ? html`<button class="btn" data-action="retry" data-session="${s.id}">Refazer só as erradas (${wrong})</button>` : ""}
        <a class="btn ghost" href="#/">Início</a>
      </div>
      ${passages.map((p) => html`<section class="panel"><h2 class="h-small" lang="fr">${p.title}</h2>
        ${p.vocab?.length ? html`<h3 class="h-tiny">Vocabulário novo</h3><ul class="vocab one">${p.vocab.map((v) => html`<li><span class="fr" lang="fr">${v.fr}</span> — ${v.pt}</li>`)}</ul>` : ""}
        ${p.structures?.length ? html`<h3 class="h-tiny">Estruturas úteis</h3><ul class="examples">${p.structures.map((v) => html`<li><span class="fr" lang="fr">${v.fr}</span><span class="pt">${v.pt}</span></li>`)}</ul>` : ""}
        <details class="help"><summary>Reler o texto</summary><div class="fr" lang="fr">${dialogue(p.body)}</div></details></section>`)}
      <h2 class="h-small">Questão por questão</h2>
      ${items.map(({ it, ex, a }, i) => html`<article class="result-item">
        <div class="row-start"><span class="result-mark ${a ? (a.result === "pending" && effectiveScore(a) != null ? "correct" : a.result) : ""}">${a ? MARK[a.result] : "–"}</span>
        <div class="grow"><p class="instruction">${i + 1}. ${ex?.instruction || it.exercise}</p>
          <p class="fr prewrap" lang="fr">${ex?.prompt || ""}</p>
          ${a ? html`<dl class="compare"><dt>Sua resposta</dt><dd lang="fr" class="${a.result !== "correct" && a.result !== "pending" ? "wrong" : ""}">${a.answer_display}</dd>
            ${a.result !== "correct" ? html`<dt>${a.result === "pending" ? "Modelo" : "Correta"}</dt><dd lang="fr" class="right">${a.correct_display}</dd>` : ""}</dl>
            <details class="help"><summary>Explicação</summary><div class="prewrap">${ex?.explanation || ""}</div>${ex?.evidence ? html`<blockquote class="evidence" lang="fr">${ex.evidence}</blockquote>` : ""}</details>
            ${a.result === "pending" && effectiveScore(a) == null ? html`<a class="btn ghost small-btn" href="#/escrita/${a.uid}">Autoavaliar este texto</a>` : ""}`
          : html`<p class="muted small">Não respondida.</p>`}
        </div></div></article>`)}`,
  };
}

export function startFrom(exercises, opts) {
  try {
    const s = createSession(exercises, opts);
    go(`#/sessao/${s.id}`);
  } catch (e) {
    toast(e.message, "error");
  }
}

export function retry(sessionId) {
  const parent = getSession(sessionId);
  const exs = wrongExercises(state, parent);
  if (!exs.length) { toast("Não há questões erradas nesta sessão."); return; }
  startFrom(exs, { kind: "retry", chapter: parent.chapter, passage: parent.passage, parent: parent.id, title: `Refazer erradas — ${parent.title}` });
}

export async function pauseSession(id) {
  const s = getSession(id);
  if (s) await pause(s);
  toast("Sessão interrompida. Retome pelo início quando quiser.");
  go("#/");
}

export async function finishSession(id) {
  const s = getSession(id);
  if (s) await finish(s);
  go(`#/resultado/${id}`);
}

export { chapterStatus };
