import { dueItems } from "../core/select.js";
import { INTERVALS, RECOVERY_LABELS } from "../core/review.js";
import { state } from "../store.js";
import { fmtDate, fmtDateTime, html, plural, raw, relDays } from "../util.js";

export function reviewQueue() {
  const now = Date.now();
  const due = dueItems(state, now);
  const upcoming = [...state.book.values()].filter((i) => i.due_at > now && state.exByCode.has(i.exercise))
    .sort((a, b) => a.due_at - b.due_at).slice(0, 12);
  const ex = (c) => state.exByCode.get(c);
  return {
    title: "Revisões", nav: "review",
    html: html`<h1>Revisões</h1>
      <p class="muted small">As questões voltam em ${INTERVALS.join(", ")} dias. Errar encurta o intervalo; acertar aumenta.</p>
      ${due.length ? html`
        <div class="quick-grid two">
          ${[5, 10, 15].filter((n) => n <= Math.max(5, due.length)).map((n) => html`<button class="card quick" data-action="review" data-count="${n}"><strong>${Math.min(n, due.length)} questões</strong><span class="muted small">das mais urgentes</span></button>`)}
        </div>
        <h2 class="h-small">${plural(due.length, "pendente", "pendentes")}</h2>
        <ul class="list">${due.slice(0, 40).map((i) => html`<li><div class="row"><span class="fr" lang="fr">${ex(i.exercise).prompt.slice(0, 70)}</span>
          ${i.recovery ? html`<span class="tag tag-${i.recovery}">${RECOVERY_LABELS[i.recovery]}</span>` : html`<span class="tag">manutenção</span>`}</div>
          <span class="muted small">Cap. ${state.chapterNumber(ex(i.exercise).chapter)} · ${i.error_count ? plural(i.error_count, "erro", "erros") : "sem erros"}${i.flagged ? " · marcada" : ""}</span></li>`)}</ul>`
      : html`<div class="empty"><p>Nenhuma revisão pendente agora.</p><a class="btn" href="#/praticar">Praticar algo novo</a></div>`}
      ${upcoming.length ? html`<h2 class="h-small">Próximas</h2><ul class="list">${upcoming.map((i) => html`<li class="row"><span class="fr" lang="fr">${ex(i.exercise).prompt.slice(0, 50)}</span><span class="muted small">${relDays(i.due_at, now)}</span></li>`)}</ul>` : ""}`,
  };
}

const STATES = [["", "Todos"], ["recent", "Erro recente"], ["reviewing", "Em revisão"], ["improving", "Melhorando"], ["overcome", "Superado"]];

export function notebook({ query }) {
  const f = query.get("estado") || "";
  const chap = query.get("capitulo") || "";
  let rows = [...state.book.values()].filter((i) => i.error_count > 0 && state.exByCode.has(i.exercise));
  const counts = Object.fromEntries(STATES.slice(1).map(([k]) => [k, rows.filter((r) => r.recovery === k).length]));
  if (f) rows = rows.filter((r) => r.recovery === f);
  if (chap) rows = rows.filter((r) => state.exByCode.get(r.exercise).chapter === chap);
  rows.sort((a, b) => b.error_count - a.error_count || (b.last_error_at || 0) - (a.last_error_at || 0));
  const lastWrong = (code) => {
    for (let k = state.attempts.length - 1; k >= 0; k--) {
      const a = state.attempts[k];
      if (a.exercise === code && a.result !== "correct") return a;
    }
    return null;
  };
  const link = (params) => {
    const q = new URLSearchParams({ estado: f, capitulo: chap, ...params });
    for (const [k, v] of [...q]) if (!v) q.delete(k);
    return `#/caderno${q.toString() ? `?${q}` : ""}`;
  };
  const comp = (code) => state.content.competencies.find((c) => c.code === code)?.name;
  const topicTitle = (code) => {
    for (const ch of state.content.chapters) {
      const g = ch.grammar.find((x) => x.code === code) || ch.vocab.find((x) => x.code === code);
      if (g) return g.title;
    }
    return code;
  };
  return {
    title: "Caderno de erros", nav: "more", back: "#/mais",
    html: html`<h1>Caderno de erros</h1>
      <p class="muted small">A questão fica aqui até ser superada: três acertos seguidos e intervalo de 14 dias ou mais.</p>
      <div class="chips scroll">${STATES.map(([k, l]) => html`<a class="chip ${k === f ? "on" : ""}" href="${link({ estado: k })}">${l}${k ? ` · ${counts[k]}` : ""}</a>`)}</div>
      <div class="chips scroll"><a class="chip ${!chap ? "on" : ""}" href="${link({ capitulo: "" })}">Todos os capítulos</a>${state.content.chapters.map((c) => html`<a class="chip ${c.code === chap ? "on" : ""}" href="${link({ capitulo: c.code })}">Cap. ${c.number}</a>`)}</div>
      ${rows.length ? rows.map((r) => {
        const ex = state.exByCode.get(r.exercise);
        const lw = lastWrong(r.exercise);
        return html`<article class="result-item">
          <div class="row"><p class="instruction">${ex.instruction}</p><span class="tag tag-${r.recovery}">${RECOVERY_LABELS[r.recovery] || ""}</span></div>
          <p class="fr prewrap" lang="fr">${ex.prompt}</p>
          <dl class="compare"><dt>Sua resposta</dt><dd lang="fr" class="wrong">${r.last_answer || "—"}</dd>
            <dt>Correta</dt><dd lang="fr" class="right">${lw ? lw.correct_display : "—"}</dd></dl>
          <details class="help"><summary>Explicação</summary><div class="prewrap">${ex.explanation}</div></details>
          <p class="muted small">Cap. ${state.chapterNumber(ex.chapter)} · ${comp(ex.competency)}${[...ex.grammar, ...ex.vocab].map((t) => ` · ${topicTitle(t)}`).join("")}<br>
            ${plural(r.error_count, "erro", "erros")} · última tentativa ${fmtDateTime(r.last_attempt_at)} · próxima revisão ${fmtDate(r.due_at)}</p>
        </article>`;
      }) : html`<div class="empty">Nenhum erro com esses filtros.</div>`}`,
  };
}

export { raw };
