import { CONSTANTS, effectiveScore } from "../core/mastery.js";
import { writtenBlock } from "../exercise.js";
import { addIssue, mastery, requestPersistence, resetAll, saveSettings, state } from "../store.js";
import { exportSync, importSync, markExported, pendingExport } from "../study.js";
import { download, fmtDateTime, go, html, MARK, meter, native, nowIso, pct, plural, raw, stamp, toast, uid } from "../util.js";

/** Página de downloads do APK (sempre a versão mais recente). */
export const APK_PAGE = "https://github.com/GalakCV/CahierMobile/releases/latest";
import { bindAssessForm } from "./practice.js";

export function moreMenu() {
  const unsent = pendingExport();
  const pendingW = state.attempts.filter((a) => a.result === "pending" && a.written?.assessed_score == null).length;
  const item = (href, label, note = "") => html`<li><a class="menu-item" href="${href}"><span>${label}</span>${note ? html`<span class="badge">${note}</span>` : ""}</a></li>`;
  return {
    title: "Mais", nav: "more",
    html: html`<h1>Mais</h1>
      <ul class="menu">
        ${item("#/caderno", "Caderno de erros")}
        ${item("#/escrita", "Produção escrita", pendingW ? String(pendingW) : "")}
        ${item("#/progresso", "Progresso e domínio")}
        ${item("#/historico", "Histórico de respostas")}
      </ul>
      <ul class="menu">
        ${item("#/sincronizar", "Sincronizar com o computador", unsent ? String(unsent) : "")}
        ${item("#/instalar", native ? "Sobre o app e atualizações" : "Instalar e usar offline")}
        ${item("#/preferencias", "Preferências")}
        ${item("#/creditos", "Créditos e fontes")}
      </ul>
      <p class="muted small">Seus dados ficam só neste aparelho. Nada é enviado a servidores.</p>`,
  };
}

export function writingList({ query }) {
  const flt = query.get("filtro") || "";
  let rows = state.attempts.filter((a) => a.result === "pending" && a.written);
  if (flt === "pendentes") rows = rows.filter((a) => a.written.assessed_score == null);
  if (flt === "revisar") rows = rows.filter((a) => a.written.marked_for_review);
  rows = [...rows].reverse();
  return {
    title: "Produção escrita", nav: "more", back: "#/mais",
    html: html`<h1>Produção escrita</h1>
      <p class="muted small">Textos não recebem nota automática: compare com a resposta-modelo e se autoavalie pelos critérios.</p>
      <div class="chips scroll">${[["", "Todos"], ["pendentes", "Aguardando avaliação"], ["revisar", "Marcados"]].map(([k, l]) => html`<a class="chip ${k === flt ? "on" : ""}" href="#/escrita${k ? `?filtro=${k}` : ""}">${l}</a>`)}</div>
      ${rows.length ? rows.map((a) => {
        const ex = state.exByCode.get(a.exercise);
        return html`<a class="card" href="#/escrita/${a.uid}"><div class="row"><strong class="small">${ex ? ex.instruction : a.exercise}</strong>
          ${a.written.assessed_score == null ? html`<span class="tag tag-reviewing">aguardando</span>` : html`<span class="tag">${Math.round(a.written.assessed_score * 100)}%</span>`}</div>
          <p class="fr small" lang="fr">${a.written.text.slice(0, 160)}</p><span class="muted small">${fmtDateTime(Date.parse(a.created_at))}</span></a>`;
      }) : html`<div class="empty">Nenhum texto aqui ainda.</div>`}`,
  };
}

export function writingAssess({ id }) {
  const a = state.attemptByUid.get(id);
  if (!a || !a.written) return null;
  const ex = state.exByCode.get(a.exercise);
  return {
    title: "Avaliar texto", nav: "more", back: "#/escrita",
    html: html`<h1>Avaliar texto</h1><p class="instruction">${ex?.instruction || ""}</p><p class="fr prewrap" lang="fr">${ex?.prompt || ""}</p>
      ${ex ? html`<div class="explanation prewrap">${ex.explanation}</div>` : ""}
      ${writtenBlock(ex || { criteria: [] }, a, a.written.assessed_score != null)}`,
    mount(root) { bindAssessForm(root, () => go("#/escrita")); },
  };
}

export function progress() {
  const m = mastery();
  const groups = [
    ["Capítulos", state.content.chapters.map((c) => [`${c.number}. ${c.title}`, m.chapter[c.code]])],
    ["Competências", state.content.competencies.map((c) => [c.name, m.competency[c.code]])],
    ["Gramática", state.content.chapters.flatMap((c) => c.grammar.map((g) => [g.title, m.grammar[g.code]]))],
    ["Vocabulário", state.content.chapters.flatMap((c) => c.vocab.map((v) => [v.title, m.vocabulary[v.code]]))],
    ["Objetivos", state.content.chapters.flatMap((c) => c.objectives.map((o) => [o.text, m.objective[o.code]]))],
  ];
  return {
    title: "Progresso", nav: "more", back: "#/mais",
    html: html`<h1>Progresso</h1>
      <p>Domínio geral: <strong>${pct(m.overall.score)}</strong> (${m.overall.level})</p>${meter(m.overall.score)}
      <details class="help"><summary>Como o domínio é calculado</summary><div>
        <p>Domínio = <strong>precisão</strong> × <strong>confiança</strong>.</p>
        <ul class="bullets"><li>Precisão: média das notas, com mais peso para questões difíceis, respostas recentes e acertos depois de alguns dias.</li>
        <li>Confiança: cobertura do tema, variedade de tipos de exercício e quantidade de respostas (até ${CONSTANTS.evidence}).</li>
        <li>Errar duas vezes seguidas a mesma questão tira 5 pontos. Sem acertar de novo após 3 dias, o máximo é ${CONSTANTS.cap}%.</li></ul>
        <p>É o mesmo cálculo do computador.</p></div></details>
      ${groups.map(([label, rows]) => html`<h2 class="h-small">${label}</h2><ul class="list">${[...rows].sort((a, b) => b[1].score - a[1].score).map(([name, d]) => html`<li>
        <div class="row"><span>${name}</span><span class="small"><strong>${pct(d.score)}</strong></span></div>${meter(d.score, "small")}
        <span class="muted small">precisão ${pct(d.accuracy)} · cobertura ${pct(d.coverage)} · ${plural(d.attempts, "resposta", "respostas")}</span></li>`)}</ul>`)}`,
  };
}

export function historyView() {
  const rows = [...state.attempts].reverse().slice(0, 200);
  return {
    title: "Histórico", nav: "more", back: "#/mais",
    html: html`<h1>Histórico</h1><p class="muted small">${plural(state.attempts.length, "resposta registrada", "respostas registradas")}. As últimas 200:</p>
      <ul class="list">${rows.map((a) => html`<li><div class="row"><span class="small"><span class="result-mark ${a.result === "pending" && effectiveScore(a) != null ? "correct" : a.result}">${MARK[a.result]}</span> <code>${a.exercise}</code></span>
        <span class="muted small">${fmtDateTime(Date.parse(a.created_at))}${a.device === "desktop" ? " · computador" : ""}</span></div>
        <span class="fr small" lang="fr">${a.answer_display.slice(0, 90)}</span></li>`)}</ul>`,
  };
}

export function syncView() {
  const unsent = pendingExport();
  const m = state.meta;
  return {
    title: "Sincronizar", nav: "more", back: "#/mais",
    html: html`<h1>Sincronizar com o computador</h1>
      <p>O progresso não sai do celular sozinho. Para juntar com o Cahier do computador, troque um arquivo entre os dois:</p>
      <section class="panel">
        <h2 class="h-small">1. Enviar progresso deste celular</h2>
        <p class="small">${unsent ? `${plural(unsent, "resposta nova", "respostas novas")} desde a última exportação.` : "Nada novo desde a última exportação."}
          Última exportação: ${m.last_export ? fmtDateTime(Date.parse(m.last_export)) : "nunca"}.</p>
        <button class="btn block" data-action="export-sync">Exportar progresso</button>
        <p class="muted small">Envie o arquivo para você mesmo (e-mail, Drive, WhatsApp…) e, no computador, abra <em>Dados e backup → Importar progresso do celular</em>.</p>
      </section>
      <section class="panel">
        <h2 class="h-small">2. Receber progresso do computador</h2>
        <p class="small">No computador: <em>Dados e backup → Baixar progresso para o celular</em>. Depois escolha o arquivo aqui.</p>
        <label class="btn ghost block file-btn">Importar arquivo<input type="file" accept=".json,application/json" data-input="import-sync" hidden></label>
        <p class="muted small">Última importação: ${m.last_import ? fmtDateTime(Date.parse(m.last_import)) : "nunca"}. As respostas são somadas sem duplicar e a revisão é recalculada.</p>
      </section>`,
    mount(root) {
      root.querySelector('[data-action="export-sync"]').addEventListener("click", async () => {
        const data = exportSync();
        const name = `cahier-sync-celular-${stamp()}.json`;
        const text = JSON.stringify(data);
        if (native) {
          if (!native.shareFile(name, text)) {
            toast("Não foi possível gerar o arquivo. Libere espaço no aparelho e tente de novo.", "error");
            return;
          }
          await markExported();
          toast(`Progresso exportado (${plural(data.attempts.length, "resposta", "respostas")}). Escolha para onde enviar.`, "success");
          go("#/sincronizar");
          return;
        }
        const file = typeof File === "function" ? new File([text], name, { type: "application/json" }) : null;
        let shared = false;
        if (file && navigator.canShare?.({ files: [file] })) {
          try {
            await navigator.share({ files: [file], title: "Progresso do Cahier" });
            shared = true;
          } catch (e) {
            if (e.name === "AbortError") return;
          }
        }
        if (!shared) download(name, text);
        await markExported();
        toast(`Progresso exportado (${plural(data.attempts.length, "resposta", "respostas")}).`, "success");
        go("#/sincronizar");
      });
      root.querySelector('[data-input="import-sync"]').addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        let data;
        try {
          data = JSON.parse(await file.text());
        } catch {
          toast("O arquivo não é um JSON válido.", "error");
          return;
        }
        const rep = await importSync(data);
        if (rep.errors.length) { toast(rep.errors[0], "error"); return; }
        const parts = [];
        if (rep.attempts) parts.push(plural(rep.attempts, "resposta", "respostas"));
        if (rep.flags) parts.push(plural(rep.flags, "marcação", "marcações"));
        if (rep.assessments) parts.push(plural(rep.assessments, "avaliação", "avaliações"));
        if (rep.written) parts.push(plural(rep.written, "autoavaliação", "autoavaliações"));
        toast(parts.length ? `Importado: ${parts.join(", ")}.` : "Nada novo: o celular já tinha esse progresso.", "success");
        go("#/sincronizar");
      });
    },
  };
}

export function settingsView() {
  const s = state.settings;
  const sel = (name, options) => html`<select name="${name}">${options.map(([v, l]) => html`<option value="${v}" ${String(s[name]) === String(v) ? raw("selected") : ""}>${l}</option>`)}</select>`;
  return {
    title: "Preferências", nav: "more", back: "#/mais",
    html: html`<h1>Preferências</h1>
      <form class="form" data-form="settings">
        <label class="field"><span>Como chamar você</span><input type="text" name="display_name" maxlength="40" value="${s.display_name}" autocomplete="given-name"></label>
        <label class="field"><span>Capítulo atual</span>${sel("current_chapter", [["", "Automático (último estudado)"], ...state.content.chapters.map((c) => [c.code, `${c.number}. ${c.title}`])])}</label>
        <label class="field"><span>Questões por sessão</span><input type="number" name="session_size" min="3" max="50" value="${s.session_size}" inputmode="numeric"></label>
        <label class="field"><span>Meta diária (minutos)</span><input type="number" name="daily_goal" min="5" max="240" value="${s.daily_goal}" inputmode="numeric"></label>
        <label class="field"><span>Tamanho do texto</span>${sel("font", [["normal", "Normal"], ["large", "Grande"], ["xlarge", "Muito grande"]])}</label>
        <label class="field"><span>Tema</span>${sel("theme", [["auto", "Seguir o sistema"], ["light", "Claro"], ["dark", "Escuro"]])}</label>
        <label class="check"><input type="checkbox" name="keyboard" ${s.keyboard ? raw("checked") : ""}> Mostrar teclado de acentos</label>
        <button class="btn block" type="submit">Salvar preferências</button>
      </form>
      <section class="panel danger"><h2 class="h-small">Apagar dados deste aparelho</h2>
        <p class="small">Remove respostas, sessões e preferências do celular. Exporte o progresso antes, se quiser guardá-lo.</p>
        <button class="btn danger block" data-action="reset">Apagar tudo</button></section>`,
    mount(root) {
      root.querySelector('[data-form="settings"]').addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = new FormData(e.target);
        const clamp = (v, a, b, d) => Math.max(a, Math.min(b, Number(v) || d));
        Object.assign(state.settings, {
          display_name: String(f.get("display_name") || "").trim().slice(0, 40),
          current_chapter: f.get("current_chapter") || "",
          session_size: clamp(f.get("session_size"), 3, 50, 10), daily_goal: clamp(f.get("daily_goal"), 5, 240, 15),
          font: f.get("font"), theme: f.get("theme"), keyboard: f.get("keyboard") === "on",
        });
        await saveSettings();
        document.dispatchEvent(new CustomEvent("cahier:settings"));
        toast("Preferências salvas.", "success");
      });
      root.querySelector('[data-action="reset"]').addEventListener("click", async () => {
        if (!confirm("Apagar todas as respostas e preferências deste aparelho? Isso não pode ser desfeito.")) return;
        await resetAll();
        document.dispatchEvent(new CustomEvent("cahier:settings"));
        toast("Dados apagados.");
        go("#/");
      });
    },
  };
}

export function credits() {
  const c = state.content;
  const counts = {};
  for (const e of c.exercises) counts[e.source] = (counts[e.source] || 0) + 1;
  return {
    title: "Créditos", nav: "more", back: "#/mais",
    html: html`<h1>Créditos e fontes</h1>
      <p class="small">Questões apenas no formato do DELF são “inspiradas em formato de exame” — nenhuma é oficial.</p>
      ${c.sources.map((s) => html`<section class="panel"><h2 class="h-small">${s.title}</h2>
        <p class="small">${s.author}<br>Licença: ${s.license_url ? html`<a href="${s.license_url}" rel="noreferrer noopener">${s.license}</a>` : s.license}
        ${s.url ? html`<br><a href="${s.url}" rel="noreferrer noopener">${s.url}</a>` : ""}</p>
        ${s.notes ? html`<p class="muted small prewrap">${s.notes}</p>` : ""}
        ${counts[s.key] ? html`<p class="muted small">${plural(counts[s.key], "questão", "questões")}</p>` : ""}</section>`)}
      <p class="muted small">Conteúdo gerado em ${fmtDateTime(Date.parse(c.generated_at))}. Sem telemetria.</p>`,
  };
}

export function flagIssue({ code, query }) {
  const ex = state.exByCode.get(code);
  if (!ex) return null;
  const kinds = [["ambiguous", "Questão ambígua"], ["wrong_answer", "Resposta correta parece errada"], ["french_error", "Erro no francês"],
    ["explanation", "Explicação confusa"], ["other", "Outro"]];
  return {
    title: "Sinalizar problema", back: "#/", focus: false, nav: "practice",
    html: html`<h1>Sinalizar problema</h1><blockquote class="evidence" lang="fr">${ex.prompt}</blockquote>
      <form class="form" data-form="issue">
        <fieldset class="field"><legend>O que há de errado?</legend>${kinds.map(([v, l], i) => html`<label class="check"><input type="radio" name="kind" value="${v}" ${i === 0 ? raw("checked") : ""}> ${l}</label>`)}</fieldset>
        <label class="field"><span>Detalhes (opcional)</span><textarea name="comment" rows="4" maxlength="2000"></textarea></label>
        <button class="btn block" type="submit">Registrar</button>
        <p class="muted small">O registro vai para o painel editorial do computador na próxima sincronização.</p>
      </form>`,
    mount(root) {
      root.querySelector('[data-form="issue"]').addEventListener("submit", async (e) => {
        e.preventDefault();
        const f = new FormData(e.target);
        await addIssue({ uid: uid(), exercise: code, version: ex.version || 1, kind: f.get("kind"),
          comment: String(f.get("comment") || "").slice(0, 2000), user_answer: query.get("resposta") || "", created_at: nowIso() });
        toast("Obrigado! Problema registrado.", "success");
        window.history.back();
      });
    },
  };
}

function nativeAbout() {
  let version = "";
  try { version = native.versionName(); } catch { /* sem versão */ }
  return {
    title: "Sobre o app", nav: "more", back: "#/mais",
    html: html`<h1>Sobre o app</h1>
      <section class="panel"><h2 class="h-small">Cahier para Android${version ? ` · versão ${version}` : ""}</h2>
        <p class="small">Todo o conteúdo está dentro do app: funciona sem internet (ônibus, metrô, avião). O app não tem permissão de acesso à internet.</p>
        <p class="small">Conteúdo: ${plural(state.content.exercises.length, "questão", "questões")} em ${plural(state.content.chapters.length, "capítulo", "capítulos")}.</p>
      </section>
      <section class="panel"><h2 class="h-small">Atualizar</h2>
        <p class="small">Quando houver conteúdo novo, baixe o APK mais recente e instale <strong>por cima</strong> deste. O progresso é mantido.</p>
        <a class="btn block" href="${APK_PAGE}">Abrir página de downloads</a>
      </section>
      <section class="panel"><h2 class="h-small">Seus dados</h2>
        <p class="small">As respostas ficam só neste aparelho. <strong>Desinstalar o app apaga o progresso</strong>: antes, use <a href="#/sincronizar">Sincronizar → Exportar progresso</a>.</p>
      </section>`,
  };
}

export function installView() {
  if (native) return nativeAbout();
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  return {
    title: "Instalar", nav: "more", back: "#/mais",
    html: html`<h1>Instalar e usar offline</h1>
      ${standalone ? html`<p class="notice">O Cahier já está instalado neste aparelho.</p>` : ""}
      <section class="panel"><h2 class="h-small">${ios ? "No iPhone (Safari)" : "No Android (Chrome)"}</h2>
        ${ios ? html`<ol class="bullets"><li>Toque em <strong>Compartilhar</strong> (quadrado com seta).</li><li>Escolha <strong>Adicionar à Tela de Início</strong>.</li><li>Abra o Cahier pelo ícone. Ele funciona sem internet.</li></ol>`
              : html`<ol class="bullets"><li>Toque no menu <strong>⋮</strong> do navegador.</li><li>Escolha <strong>Instalar app</strong> ou <strong>Adicionar à tela inicial</strong>.</li><li>Abra o Cahier pelo ícone. Ele funciona sem internet.</li></ol>
                <button class="btn block" data-action="install" hidden>Instalar agora</button>`}
      </section>
      <section class="panel"><h2 class="h-small">Funciona offline?</h2>
        <p class="small">Sim. Depois da primeira abertura, todo o conteúdo fica salvo no aparelho. Atualizações chegam sozinhas quando houver internet.</p>
        <p class="small">Armazenamento protegido contra limpeza automática: <strong>${state.persistent ? "sim" : "ainda não"}</strong>${state.persistent ? "" : ". Instale o app na tela inicial para proteger seus dados."}</p>
        ${state.persistent ? "" : html`<button class="btn ghost block" data-action="persist">Proteger meus dados</button>`}
      </section>`,
    mount(root) {
      const btn = root.querySelector('[data-action="install"]');
      if (btn && window.__installPrompt) {
        btn.hidden = false;
        btn.addEventListener("click", async () => { window.__installPrompt.prompt(); window.__installPrompt = null; btn.hidden = true; });
      }
      root.querySelector('[data-action="persist"]')?.addEventListener("click", async () => {
        const ok = await requestPersistence();
        toast(ok ? "Dados protegidos." : "O navegador não permitiu agora. Instale o app e tente de novo.");
        go("#/instalar");
      });
    },
  };
}
