import { chapterStatus } from "../core/select.js";
import { currentChapter, overview } from "../core/stats.js";
import { mastery, state } from "../store.js";
import { answeredCount, pendingExport, resumable } from "../study.js";
import { html, meter, minutesLabel, pct, plural } from "../util.js";

export function home() {
  const m = mastery();
  const o = overview(state, m);
  const s = state.settings;
  const resume = resumable();
  const chCode = currentChapter(state);
  const ch = state.chapterByCode.get(chCode);
  const info = ch ? chapterStatus(state, chCode) : null;
  const goal = s.daily_goal || 15;
  const goalPct = Math.min(100, Math.round((100 * o.minutesToday) / goal));
  const unsent = pendingExport();
  const firstTime = state.attempts.length === 0;

  return {
    title: "Cahier", nav: "home",
    html: html`
    <h1 class="hello">${s.display_name ? `Bonjour, ${s.display_name} !` : "Bonjour !"}</h1>
    ${firstTime ? html`<p class="lead">Exercícios curtos de francês A1, mesmo sem internet. Comece por uma sessão rápida.</p>` : ""}

    <section class="resume">
      ${resume ? html`
        <h2>Continue de onde parou</h2>
        <p><strong>${resume.title}</strong><br><span class="muted">${answeredCount(resume)} de ${resume.items.length} respondidas</span></p>
        ${meter(100 * answeredCount(resume) / resume.items.length, "small")}
        <a class="btn block" href="#/sessao/${resume.id}">Retomar sessão</a>`
      : html`
        <h2>Sessão rápida</h2>
        <p class="muted">5 questões do capítulo atual${ch ? html` (<span lang="fr">${ch.title}</span>)` : ""}, cerca de 3 minutos.</p>
        <button class="btn block" data-action="quick" data-count="5">Começar agora</button>`}
      ${o.dueReviews ? html`<button class="btn ghost block" data-action="review">Revisar ${plural(o.dueReviews, "pendente", "pendentes")}</button>` : ""}
    </section>

    <section class="today" aria-label="Hoje">
      <div class="row"><strong>Hoje</strong><span class="muted">${o.minutesToday} de ${goal} min</span></div>
      ${meter(goalPct, "small")}
      <p class="muted small">${o.streak ? `Sequência de ${plural(o.streak, "dia", "dias")} estudando.` : "Estude hoje para começar uma sequência."}</p>
    </section>

    ${ch && info ? html`<a class="card chapter-card" href="#/capitulos/${ch.code}">
      <span class="chapter-num">${ch.number}</span>
      <span class="grow"><strong lang="fr">${ch.title}</strong><br><span class="muted small">${info.label} · domínio ${pct(info.mastery)}</span>${meter(info.mastery, "small")}</span>
    </a>` : ""}

    <dl class="figures">
      <div><dt>Progresso geral</dt><dd>${pct(o.general)}</dd></div>
      <div><dt>Taxa de acertos</dt><dd>${pct(o.accuracy)}</dd></div>
      <div><dt>Exercícios feitos</dt><dd>${o.attemptCount}</dd></div>
      <div><dt>Tempo total</dt><dd>${minutesLabel(o.totalMinutes)}</dd></div>
    </dl>

    ${o.weak.length ? html`<section><h2 class="h-small">Precisam de atenção</h2>
      <ul class="list">${o.weak.map((c) => html`<li><div class="row"><span>${c.name}</span><span class="muted">${pct(c.accuracy)} de acerto</span></div>${meter(c.score, "small")}</li>`)}</ul></section>` : ""}

    ${o.errors.length ? html`<section><h2 class="h-small">Erros mais recorrentes</h2>
      <ul class="list">${o.errors.slice(0, 3).map((r) => html`<li><div class="row"><span class="fr" lang="fr">${state.exByCode.get(r.exercise).prompt.slice(0, 60)}</span><span class="tag tag-${r.recovery}">${plural(r.error_count, "erro", "erros")}</span></div></li>`)}</ul>
      <a href="#/caderno" class="link">Abrir o caderno de erros</a></section>` : ""}

    ${unsent >= 20 ? html`<a class="card notice" href="#/sincronizar"><strong>${unsent} respostas ainda não foram para o computador.</strong><br><span class="small">Exporte o progresso quando puder.</span></a>` : ""}
    `,
  };
}
