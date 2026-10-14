// Inicialização, rotas (hash), ações globais, teclado de acentos e atualização offline.
import { selectChapterAssessment, selectChapterReview, selectPassage, selectPractice, selectReview } from "./core/select.js";
import { currentChapter } from "./core/stats.js";
import { ACCENTS } from "./exercise.js";
import { addFlag, init, state } from "./store.js";
import { dueItems } from "./core/select.js";
import { go, html, toast } from "./util.js";
import { chapterDetail, chapterList, passageDetail } from "./views/chapters.js";
import { home } from "./views/home.js";
import { credits, flagIssue, historyView, installView, moreMenu, progress, settingsView, syncView, writingAssess, writingList } from "./views/more.js";
import { finishSession, pauseSession, practiceSetup, retry, sessionFeedback, sessionPlay, sessionResult, startFrom } from "./views/practice.js";
import { notebook, reviewQueue } from "./views/review.js";

const ROUTES = [
  [/^\/$/, home],
  [/^\/capitulos$/, chapterList],
  [/^\/capitulos\/([^/]+)(?:\/([^/]+))?$/, (p, m) => chapterDetail({ ...p, code: m[1], tab: m[2] || "visao" })],
  [/^\/texto\/([^/]+)$/, (p, m) => passageDetail({ ...p, code: decodeURIComponent(m[1]) })],
  [/^\/praticar$/, practiceSetup],
  [/^\/sessao\/([^/]+)$/, (p, m) => sessionPlay({ ...p, id: m[1] })],
  [/^\/sessao\/([^/]+)\/(\d+)$/, (p, m) => sessionFeedback({ ...p, id: m[1], pos: m[2] })],
  [/^\/resultado\/([^/]+)$/, (p, m) => sessionResult({ ...p, id: m[1] })],
  [/^\/revisoes$/, reviewQueue],
  [/^\/caderno$/, notebook],
  [/^\/escrita$/, writingList],
  [/^\/escrita\/([^/]+)$/, (p, m) => writingAssess({ ...p, id: m[1] })],
  [/^\/progresso$/, progress],
  [/^\/historico$/, historyView],
  [/^\/mais$/, moreMenu],
  [/^\/sincronizar$/, syncView],
  [/^\/preferencias$/, settingsView],
  [/^\/creditos$/, credits],
  [/^\/instalar$/, installView],
  [/^\/sinalizar\/([^/]+)$/, (p, m) => flagIssue({ ...p, code: decodeURIComponent(m[1]) })],
];

const main = () => document.getElementById("main");

async function render() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, qs = ""] = raw.split("?");
  const params = { query: new URLSearchParams(qs) };
  let view = null;
  try {
    for (const [re, fn] of ROUTES) {
      const m = path.match(re);
      if (m) { view = await fn(params, m); break; }
    }
  } catch (err) {
    console.error(err);
    view = { title: "Erro", html: html`<h1>Algo deu errado</h1><p>${String(err.message || err)}</p><a class="btn" href="#/">Voltar ao início</a>` };
  }
  if (view && view.redirect) {
    if (view.before) await view.before();
    location.replace(`#${view.redirect.replace(/^#/, "")}`);
    return;
  }
  if (!view) view = { title: "Não encontrado", html: html`<h1>Página não encontrada</h1><a class="btn" href="#/">Voltar ao início</a>` };
  document.title = view.title === "Cahier" ? "Cahier" : `${view.title} · Cahier`;
  document.body.classList.toggle("focus-mode", Boolean(view.focus));
  const back = document.getElementById("back");
  back.hidden = !view.back;
  back.dataset.href = view.back || "";
  document.getElementById("top-title").textContent = view.focus ? "" : (view.title === "Cahier" ? "" : view.title);
  document.querySelectorAll(".tabbar a").forEach((a) => a.setAttribute("aria-current", a.dataset.nav === view.nav ? "page" : "false"));
  updateBadge();
  const root = main();
  root.innerHTML = String(view.html);
  if (view.mount) view.mount(root);
  bindOrder(root);
  if (!view.keepScroll) window.scrollTo(0, 0);
  root.focus({ preventScroll: true });
}

function updateBadge() {
  const n = dueItems(state).length;
  const b = document.getElementById("due-badge");
  b.textContent = n > 99 ? "99+" : String(n);
  b.hidden = n === 0;
}

// ---------- Ações globais (delegação) ----------
document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const a = el.dataset.action;
  const size = state.settings.session_size || 10;
  if (a === "quick") {
    const chapter = el.dataset.chapter || currentChapter(state);
    const count = Number(el.dataset.count) || 5;
    const ch = state.chapterByCode.get(chapter);
    const exs = selectPractice(state, { chapter, count, seed: Math.floor(Math.random() * 1e9) });
    startFrom(exs, { chapter, title: `${count <= 5 ? "Sessão rápida" : "Prática"}${ch ? ` — ${ch.title}` : ""}` });
  } else if (a === "review") {
    const exs = selectReview(state, Number(el.dataset.count) || 15);
    if (!exs.length) { toast("Nenhuma revisão pendente agora."); return; }
    startFrom(exs, { kind: "spaced_review", title: "Revisões pendentes" });
  } else if (a === "chapter-review") {
    const ch = state.chapterByCode.get(el.dataset.chapter);
    startFrom(selectChapterReview(state, ch.code, size + 2, Math.floor(Math.random() * 1e9)),
      { kind: "chapter_review", chapter: ch.code, title: `Revisão — ${ch.title}` });
  } else if (a === "chapter-assessment") {
    const ch = state.chapterByCode.get(el.dataset.chapter);
    startFrom(selectChapterAssessment(state, ch.code), { mode: "assessment", kind: "chapter_assessment", chapter: ch.code,
      title: `Avaliação final — ${ch.title}` });
  } else if (a === "passage") {
    const p = state.passageByCode.get(el.dataset.passage);
    startFrom(selectPassage(state, p.code), { mode: el.dataset.mode === "assessment" ? "assessment" : "practice", kind: "passage",
      chapter: p.chapter, passage: p.code, title: `Texto — ${p.title}` });
  } else if (a === "flag") {
    await addFlag(el.dataset.code);
    toast("Marcada para revisão: ela aparece nas revisões pendentes.", "success");
    el.replaceWith(Object.assign(document.createElement("span"), { className: "tag", textContent: "Marcada para revisão" }));
    updateBadge();
  } else if (a === "pause") {
    await pauseSession(el.dataset.session);
  } else if (a === "finish") {
    if (confirm("Encerrar agora? As questões não respondidas ficam de fora do resultado.")) await finishSession(el.dataset.session);
  } else if (a === "retry") {
    retry(el.dataset.session);
  } else if (a === "order-reset") {
    const box = el.closest("[data-order]");
    box.querySelectorAll(".order-zone .token").forEach((t) => box.querySelector(".order-bank").appendChild(t));
  }
});

document.getElementById("back").addEventListener("click", (e) => {
  go(e.currentTarget.dataset.href || "#/");
});

// ---------- Ordenação por toque ----------
function bindOrder(root) {
  root.querySelectorAll("[data-order]").forEach((box) => {
    const zone = box.querySelector(".order-zone");
    const bank = box.querySelector(".order-bank");
    box.addEventListener("click", (e) => {
      const tok = e.target.closest(".token");
      if (!tok) return;
      (tok.parentElement === bank ? zone : bank).appendChild(tok);
      tok.setAttribute("aria-pressed", tok.parentElement === zone ? "true" : "false");
    });
  });
}

// ---------- Teclado de acentos (acima do teclado do celular) ----------
const accentBar = document.getElementById("accents");
accentBar.innerHTML = '<div class="accent-keys">'
  + ACCENTS.map((c) => `<button type="button" data-char="${c}" aria-label="Inserir ${c.trim()}">${c.trim()}</button>`).join("")
  + '<button type="button" data-case aria-label="Maiúscula" class="case">⇧</button></div>'
  + '<button type="button" id="accent-submit" class="accent-submit" aria-label="Enviar resposta">OK</button>';
let lastField = null;
let upper = false;

function placeAccentBar() {
  const vv = window.visualViewport;
  if (!vv) return;
  const offset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
  accentBar.style.transform = `translateY(${-offset}px)`;
}
if (window.visualViewport) {
  visualViewport.addEventListener("resize", placeAccentBar);
  visualViewport.addEventListener("scroll", placeAccentBar);
}
document.addEventListener("focusin", (e) => {
  if (e.target.matches?.(".sheet input[type=text], .sheet textarea")) {
    lastField = e.target;
    if (state.settings.keyboard) {
      document.body.classList.add("typing");
      placeAccentBar();
    }
  }
});
document.addEventListener("focusout", () => {
  setTimeout(() => {
    if (!document.activeElement?.matches?.(".sheet input[type=text], .sheet textarea")) document.body.classList.remove("typing");
  }, 120);
});
accentBar.addEventListener("pointerdown", (e) => e.preventDefault()); // não tira o foco do campo
accentBar.addEventListener("mousedown", (e) => e.preventDefault());
accentBar.addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b || !lastField) return;
  if (b.id === "accent-submit") {
    const form = lastField.form;
    lastField.blur();
    document.body.classList.remove("typing");
    form?.requestSubmit?.();
    return;
  }
  if (b.hasAttribute("data-case")) {
    upper = !upper;
    b.classList.toggle("on", upper);
    accentBar.querySelectorAll("[data-char]").forEach((x) => { x.textContent = upper ? x.dataset.char.trim().toLocaleUpperCase("fr") : x.dataset.char.trim(); });
    return;
  }
  let ch = b.dataset.char;
  if (upper) ch = ch.toLocaleUpperCase("fr");
  const f = lastField;
  const start = f.selectionStart ?? f.value.length;
  const end = f.selectionEnd ?? f.value.length;
  f.value = f.value.slice(0, start) + ch + f.value.slice(end);
  f.setSelectionRange(start + ch.length, start + ch.length);
  f.focus();
  if (upper) accentBar.querySelector("[data-case]").click();
});
// Enter num campo de lacuna envia a resposta
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.matches?.('.sheet input[type=text]')) {
    e.preventDefault();
    e.target.form?.requestSubmit?.();
  }
});

// ---------- Aparência ----------
function applySettings() {
  const s = state.settings;
  document.documentElement.dataset.theme = s.theme || "auto";
  document.documentElement.dataset.font = s.font || "normal";
}
document.addEventListener("cahier:settings", applySettings);
document.addEventListener("cahier:storage-error", () => toast("Não foi possível salvar no aparelho. Libere espaço ou saia do modo anônimo.", "error"));

// ---------- Offline e atualizações ----------
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); window.__installPrompt = e; });

function registerSW() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("sw.js").then((reg) => {
    const offer = (worker) => {
      const bar = document.getElementById("update");
      bar.hidden = false;
      bar.querySelector("button").onclick = () => worker.postMessage("skip-waiting");
    };
    if (reg.waiting && navigator.serviceWorker.controller) offer(reg.waiting);
    reg.addEventListener("updatefound", () => {
      const w = reg.installing;
      w?.addEventListener("statechange", () => {
        if (w.state === "installed" && navigator.serviceWorker.controller) offer(w);
      });
    });
    setInterval(() => reg.update().catch(() => {}), 60 * 60 * 1000);
  }).catch((err) => console.warn("Service worker indisponível", err));
  // Só recarrega quando uma versão nova substitui a anterior (não na primeira instalação).
  const hadController = Boolean(navigator.serviceWorker.controller);
  let reloading = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController && !reloading) { reloading = true; location.reload(); }
  });
}

function updateOnline() {
  document.getElementById("offline").hidden = navigator.onLine;
}
window.addEventListener("online", updateOnline);
window.addEventListener("offline", updateOnline);

async function start() {
  try {
    await init();
  } catch (err) {
    console.error(err);
    main().innerHTML = '<h1>Não foi possível abrir o conteúdo</h1><p>Abra o app uma vez com internet para baixar os exercícios.</p>';
    return;
  }
  applySettings();
  if (!state.storageOk) toast("O armazenamento do navegador não está disponível: o progresso não será salvo.", "error");
  window.addEventListener("hashchange", render);
  updateOnline();
  await render();
  document.body.classList.add("ready");
  registerSW();
}

start();
