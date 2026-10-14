import { chapterStatus } from "../core/select.js";
import { mastery, state } from "../store.js";
import { dialogue, html, meter, pct, raw } from "../util.js";

export function chapterList() {
  const rows = state.content.chapters.map((ch) => ({ ch, info: chapterStatus(state, ch.code) }));
  return {
    title: "Capítulos", nav: "chapters",
    html: html`<h1>Capítulos</h1>
      <p class="muted small">Organizados a partir do <em>Français interactif</em> (UT Austin). Exercícios e textos originais.</p>
      <ul class="cards">${rows.map(({ ch, info }) => html`<li><a class="card chapter-card" href="#/capitulos/${ch.code}">
        <span class="chapter-num">${ch.number}</span>
        <span class="grow"><strong lang="fr">${ch.title}</strong><br><span class="muted small">${ch.theme}</span>
          <span class="row small"><span class="tag tag-status-${info.status}">${info.label}</span><span>${pct(info.mastery)}</span></span>
          ${meter(info.mastery, "small")}
          <span class="muted small">${info.total} exercícios · ${pct(info.progress)} respondidos${info.bestAssessment != null ? ` · avaliação ${info.bestAssessment}%` : ""}</span></span>
      </a></li>`)}</ul>
      ${state.content.planned?.length ? html`<h2 class="h-small">Planejados</h2><ul class="list">${state.content.planned.map((p) => html`<li><span lang="fr">${p.number}. ${p.title}</span> <span class="muted small">— ${p.theme}</span></li>`)}</ul>` : ""}`,
  };
}

const TABS = [["visao", "Visão geral"], ["explicacoes", "Explicações"], ["vocabulario", "Vocabulário"], ["textos", "Textos"], ["revisao", "Revisão"]];

export function chapterDetail({ code, tab = "visao" }) {
  const ch = state.chapterByCode.get(code);
  if (!ch) return null;
  const info = chapterStatus(state, code);
  const m = mastery();
  let body;
  if (tab === "explicacoes") {
    body = ch.grammar.map((g) => html`<section class="panel" id="g-${g.code}">
      <div class="row"><h2 class="h-small">${g.title}</h2><span class="muted small">${pct(m.grammar[g.code]?.score)}</span></div>
      <div class="prewrap">${g.summary}</div>
      ${g.examples?.length ? html`<h3 class="h-tiny">Exemplos</h3><ul class="examples">${g.examples.map((e) => html`<li><span class="fr" lang="fr">${e.fr}</span><span class="pt">${e.pt}</span></li>`)}</ul>` : ""}
      ${(g.tables || []).map((t) => html`<table class="conj"><caption lang="fr">${t.title}</caption><tbody>${t.rows.map((r) => html`<tr>${r.map((c) => html`<td lang="fr">${c}</td>`)}</tr>`)}</tbody></table>`)}
      ${g.notes ? html`<h3 class="h-tiny">Observações</h3><div class="prewrap">${g.notes}</div>` : ""}
      ${g.errors?.length ? html`<h3 class="h-tiny">Erros frequentes de quem fala português</h3>${g.errors.map((e) => html`<div class="pitfall"><s lang="fr">${e.wrong}</s> → <strong lang="fr">${e.right}</strong><br><small>${e.why}</small></div>`)}` : ""}
    </section>`);
  } else if (tab === "vocabulario") {
    body = html`${ch.vocab.map((v) => html`<section><h2 class="h-small">${v.title}</h2><ul class="vocab">${v.items.map((i) => html`<li><span class="fr" lang="fr">${i.fr}</span>${i.g ? html`<span class="g">(${i.g})</span>` : ""} — ${i.pt}${i.ex ? html`<span class="ex" lang="fr">${i.ex}</span>` : ""}</li>`)}</ul></section>`)}
      ${ch.expressions?.length ? html`<h2 class="h-small">Expressões úteis</h2><ul class="examples">${ch.expressions.map((e) => html`<li><span class="fr" lang="fr">${e.fr}</span><span class="pt">${e.pt}</span></li>`)}</ul>` : ""}`;
  } else if (tab === "textos") {
    const ps = state.content.passages.filter((p) => p.chapter === code);
    body = html`<p class="muted small">Leia e responda. No fim você vê o trecho que fundamenta cada resposta.</p>
      <ul class="cards">${ps.map((p) => html`<li><a class="card" href="#/texto/${encodeURIComponent(p.code)}"><strong lang="fr">${p.title}</strong><br>
        <span class="muted small">${state.content.labels.text_types[p.type]} · ${p.words} palavras · dificuldade ${p.difficulty} · ${state.content.exercises.filter((e) => e.passage === p.code).length} perguntas</span></a></li>`)}</ul>`;
  } else if (tab === "revisao") {
    body = html`<h2 class="h-small">Pontos para revisar</h2><ul class="bullets">${ch.review.map((l) => html`<li>${l}</li>`)}</ul>
      <button class="btn block" data-action="chapter-review" data-chapter="${code}">Começar revisão do capítulo</button>
      ${info.assessmentCount ? html`<button class="btn ghost block" data-action="chapter-assessment" data-chapter="${code}">Fazer a avaliação final (${info.assessmentCount} questões)</button>` : ""}
      <p class="muted small">Na avaliação a correção aparece só no final. Com 70% ou mais o capítulo fica concluído${info.bestAssessment != null ? `; seu melhor resultado é ${info.bestAssessment}%` : ""}.</p>`;
  } else {
    body = html`<h2 class="h-small">Ao fim do capítulo, você consegue…</h2>
      <ul class="list">${ch.objectives.map((o) => html`<li><div class="row"><span>${o.text}</span><span class="muted small">${m.objective[o.code]?.attempts ? pct(m.objective[o.code].score) : ""}</span></div></li>`)}</ul>
      <h2 class="h-small">Gramática</h2>
      <ul class="list">${ch.grammar.map((g) => html`<li><a class="row" href="#/capitulos/${code}/explicacoes"><span>${g.title}</span><span class="muted small">${m.grammar[g.code]?.attempts ? pct(m.grammar[g.code].score) : ""}</span></a></li>`)}</ul>
      <p class="muted small">${ch.reference_note}</p>`;
  }
  return {
    title: `${ch.number}. ${ch.title}`, nav: "chapters", back: "#/capitulos",
    html: html`<h1 lang="fr">${ch.number}. ${ch.title}</h1>
      <p>${ch.description}</p>
      <div class="row small"><span class="tag tag-status-${info.status}">${info.label}</span><span>Domínio <strong>${pct(info.mastery)}</strong> · ${info.level}</span></div>
      ${meter(info.mastery)}
      <div class="actions">
        <button class="btn" data-action="quick" data-chapter="${code}" data-count="${state.settings.session_size}">Praticar</button>
        <a class="btn ghost" href="#/praticar?capitulo=${code}">Personalizar</a>
      </div>
      ${info.status === "needs_review" ? html`<p class="notice">Há ${info.dueErrors} erros deste capítulo esperando revisão.</p>` : ""}
      <nav class="tabs" aria-label="Seções do capítulo">${TABS.map(([k, l]) => html`<a href="#/capitulos/${code}/${k}" ${k === tab ? raw('aria-current="page"') : ""}>${l}</a>`)}</nav>
      ${body}`,
  };
}

export function passageDetail({ code }) {
  const p = state.passageByCode.get(code);
  if (!p) return null;
  const src = state.content.sources.find((s) => s.key === p.source);
  const ch = state.chapterByCode.get(p.chapter);
  const n = state.content.exercises.filter((e) => e.passage === code).length;
  return {
    title: p.title, nav: "chapters", back: `#/capitulos/${p.chapter}/textos`,
    html: html`<p class="muted small">${ch.number}. <span lang="fr">${ch.title}</span></p>
      <h1 lang="fr">${p.title}</h1>
      <p class="muted small">${state.content.labels.text_types[p.type]} · nível ${p.level} · dificuldade ${p.difficulty} · ${p.words} palavras</p>
      ${p.vocab?.length ? html`<details class="help"><summary>Palavras-chave antes de ler</summary><ul class="vocab one">${p.vocab.map((v) => html`<li><span class="fr" lang="fr">${v.fr}</span> — ${v.pt}</li>`)}</ul></details>` : ""}
      <div class="sheet reading-sheet"><div class="fr" lang="fr">${dialogue(p.body)}</div></div>
      <div class="sticky-actions">
        <button class="btn" data-action="passage" data-passage="${code}" data-mode="practice">Responder (${n})</button>
        <button class="btn ghost" data-action="passage" data-passage="${code}" data-mode="assessment">Modo avaliação</button>
      </div>
      <p class="muted small">Autoria: ${p.author} · ${state.content.labels.origins[p.origin]} · ${src ? src.title : ""} (${src ? src.license : ""})</p>`,
  };
}
