// Renderização de uma questão, leitura da resposta e tela de correção.
import { BLANK, blankCount } from "./core/grading.js";
import { rng } from "./core/select.js";
import { state } from "./store.js";
import { dialogue, dots, html, MARK, raw } from "./util.js";

export const ACCENTS = ["é", "è", "ê", "ë", "à", "â", "ç", "ù", "û", "î", "ï", "ô", "œ", "æ", "’", "« ", " »"];

const typeLabel = (ex) => state.content.labels.types[ex.type] || ex.type;
const compName = (code) => state.content.competencies.find((c) => c.code === code)?.name || code;
const inputAttrs = 'autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" lang="fr" enterkeyhint="done"';

function hashSeed(s) {
  let h = 2166136261;
  for (const ch of s) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return h >>> 0;
}

export function rightColumn(ex) {
  const idx = (ex.choices || []).map((_, i) => i);
  const r = rng(hashSeed(`match-${ex.code}`));
  for (let i = idx.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1));
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  return idx;
}

export function passageCard(code, { open = true, hideTranslation = false } = {}) {
  const p = state.passageByCode.get(code);
  if (!p) return "";
  return html`<details class="reading" ${open ? raw("open") : ""} data-passage="${p.code}">
    <summary><span lang="fr">${p.title}</span><small>${state.content.labels.text_types[p.type] || ""} · ${p.words} palavras</small></summary>
    <div class="fr reading-body" lang="fr">${dialogue(p.body)}</div>
    ${p.translation && !hideTranslation ? html`<details class="help" data-translation><summary>Ver tradução do texto</summary><div class="prewrap">${p.translation}</div></details>` : ""}
  </details>`;
}

function metaRow(ex) {
  const comp = compName(ex.competency);
  return html`<div class="sheet-meta"><span class="tag">${typeLabel(ex)}</span>${dots(ex.difficulty)}
    ${comp !== typeLabel(ex) ? html`<span>${comp}</span>` : ""}
    ${ex.reading_skill ? html`<span>${state.content.labels.reading[ex.reading_skill] || ""}</span>` : ""}</div>`;
}

export function renderQuestion(ex, { hideTranslation = false } = {}) {
  const choices = ex.choices || [];
  let body;
  const n = blankCount(ex);
  let prompt;
  if (ex.interaction === "text" && n) {
    const parts = ex.prompt.split(BLANK);
    prompt = html`<p class="prompt" lang="fr">${parts.map((part, i) => html`${part}${i < parts.length - 1
      ? raw(`<input class="blank" type="text" name="blank_${i}" aria-label="Lacuna ${i + 1}" ${inputAttrs}>`) : ""}`)}</p>`;
  } else {
    prompt = html`<p class="prompt" lang="fr">${ex.prompt}</p>`;
  }
  switch (ex.interaction) {
    case "single":
    case "multiple": {
      const type = ex.interaction === "single" ? "radio" : "checkbox";
      body = html`<fieldset class="options"><legend class="visually-hidden">Alternativas</legend>
        ${choices.map((c, i) => html`<label class="option"><input type="${type}" name="choice" value="${i}"><span lang="fr">${c.t}</span></label>`)}
      </fieldset>${ex.interaction === "multiple" ? html`<p class="helptext">Marque todas as alternativas corretas.</p>` : ""}`;
      break;
    }
    case "text":
      body = n ? "" : raw(`<input class="text-answer" type="text" name="blank_0" aria-label="Sua resposta" maxlength="500" ${inputAttrs}>`);
      break;
    case "order": {
      const vertical = ex.type !== "order_words";
      body = html`<div class="order ${vertical ? "vertical" : ""}" data-order>
        <p class="helptext">Toque nos itens na ordem certa. Toque de novo para devolver.</p>
        <div class="order-zone" data-empty="Sua sequência aparece aqui." aria-label="Sua sequência"></div>
        <div class="order-bank" aria-label="Itens disponíveis">${choices.map((c, i) => html`<button type="button" class="token" data-i="${i}" lang="fr">${c.t}</button>`)}</div>
        <button type="button" class="link-btn" data-action="order-reset">Recomeçar</button>
      </div>`;
      break;
    }
    case "match": {
      const rights = rightColumn(ex);
      body = html`<div class="match">${choices.map((c, i) => html`<label class="match-row"><span lang="fr">${c.t}</span>
        <select name="match_${i}"><option value="">— escolha —</option>${rights.map((j) => html`<option value="${j}">${choices[j].m}</option>`)}</select></label>`)}</div>`;
      break;
    }
    case "writing":
      body = html`${ex.criteria?.length ? html`<details class="help" open><summary>O que seu texto deve conter</summary><ul>${ex.criteria.map((c) => html`<li>${c}</li>`)}</ul></details>` : ""}
        <textarea class="text-answer" name="text" rows="7" maxlength="5000" aria-label="Seu texto" ${raw(inputAttrs)}></textarea>`;
      break;
    default:
      body = "";
  }
  return html`${metaRow(ex)}<p class="instruction">${ex.instruction}</p>
    ${ex.context ? html`<div class="context" lang="fr">${dialogue(ex.context)}</div>` : ""}
    ${prompt}${body}
    ${ex.translation && !hideTranslation ? html`<details class="help" data-translation><summary>Ver tradução</summary><div class="prewrap">${ex.translation}</div></details>` : ""}`;
}

export function collectAnswer(root, ex) {
  switch (ex.interaction) {
    case "single": {
      const el = root.querySelector('input[name="choice"]:checked');
      return { choice: el ? Number(el.value) : null };
    }
    case "multiple":
      return { choices: [...root.querySelectorAll('input[name="choice"]:checked')].map((e) => Number(e.value)) };
    case "text": {
      const n = Math.max(1, blankCount(ex));
      return { blanks: Array.from({ length: n }, (_, i) => root.querySelector(`[name="blank_${i}"]`)?.value ?? "") };
    }
    case "order":
      return { order: [...root.querySelectorAll(".order-zone .token")].map((t) => Number(t.dataset.i)) };
    case "match": {
      const pairs = {};
      (ex.choices || []).forEach((_, i) => {
        const v = root.querySelector(`[name="match_${i}"]`)?.value;
        pairs[String(i)] = v === "" || v == null ? null : Number(v);
      });
      return { pairs };
    }
    case "writing":
      return { text: root.querySelector('[name="text"]')?.value ?? "" };
    default:
      return {};
  }
}

const VERDICT = {
  correct: "Correto!", partial: "Parcialmente correto", incorrect: "Não foi dessa vez", pending: "Resposta guardada — agora avalie",
};

export function renderFeedback(ex, attempt) {
  const r = attempt.result;
  const assessed = attempt.written && attempt.written.assessed_score != null;
  return html`${metaRow(ex)}<p class="instruction">${ex.instruction}</p>
    ${ex.context ? html`<div class="context" lang="fr">${dialogue(ex.context)}</div>` : ""}
    <p class="prompt" lang="fr">${ex.prompt}</p>
    <div class="verdict verdict-${r}" role="status"><span class="mark" aria-hidden="true">${MARK[r]}</span><span>${VERDICT[r]}</span></div>
    ${attempt.feedback ? html`<p class="feedback">${attempt.feedback}</p>` : ""}
    ${r !== "pending" ? html`<dl class="compare"><dt>Sua resposta</dt><dd lang="fr" class="${r !== "correct" ? "wrong" : ""}">${attempt.answer_display}</dd>
      ${r !== "correct" ? html`<dt>Resposta correta</dt><dd lang="fr" class="right">${attempt.correct_display}</dd>` : ""}</dl>` : ""}
    <div class="explanation"><strong>Por quê?</strong><div class="prewrap">${ex.explanation}</div></div>
    ${ex.evidence ? html`<p class="muted small">Trecho do texto que fundamenta a resposta:</p><blockquote class="evidence" lang="fr">${ex.evidence}</blockquote>` : ""}
    ${ex.translation ? html`<details class="help"><summary>Ver tradução</summary><div class="prewrap">${ex.translation}</div></details>` : ""}
    ${r === "pending" ? writtenBlock(ex, attempt, assessed) : ""}`;
}

export function writtenBlock(ex, attempt, assessed) {
  const w = attempt.written;
  return html`<h2 class="h-small">Compare com a resposta-modelo</h2><div class="model" lang="fr">${ex.model || attempt.correct_display}</div>
    <h3 class="h-small">Seu texto</h3><div class="model mine" lang="fr">${w.text}</div>
    <form class="self-assess" data-form="assess" data-uid="${attempt.uid}">
      ${ex.criteria?.length
        ? html`<fieldset><legend><strong>Autoavaliação:</strong> marque o que seu texto cumpre</legend>
          ${ex.criteria.map((c, i) => html`<label class="check"><input type="checkbox" name="criteria" value="${i}" ${w.criteria_checked.includes(i) ? raw("checked") : ""}> ${c}</label>`)}</fieldset>`
        : html`<fieldset><legend><strong>Como foi?</strong></legend>
          ${[["correct", "Acertei"], ["partial", "Acertei em parte"], ["incorrect", "Errei"]].map(([v, l]) => html`<label class="check"><input type="radio" name="overall" value="${v}"> ${l}</label>`)}</fieldset>`}
      <label class="check"><input type="checkbox" name="marked" value="1" ${w.marked_for_review ? raw("checked") : ""}> Quero rever este texto depois</label>
      <button class="btn block" type="submit">${assessed ? "Atualizar avaliação" : "Registrar avaliação"}</button>
      ${assessed ? html`<p class="muted small">Avaliado: ${Math.round(w.assessed_score * 100)}%.</p>` : ""}
    </form>`;
}
