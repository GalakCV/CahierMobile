// Utilidades de interface: templates com escape automático, datas e pequenos helpers.

/** Funções nativas quando o app roda dentro do APK Android (null no navegador). */
export const native = typeof window !== "undefined" && window.CahierAndroid ? window.CahierAndroid : null;

export class Raw {
  constructor(s) { this.s = s; }
  toString() { return this.s; }
}
export const raw = (s) => new Raw(String(s));

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ESC[c]);

function renderValue(v) {
  if (v == null || v === false || v === true) return "";
  if (v instanceof Raw) return v.s;
  if (Array.isArray(v)) return v.map(renderValue).join("");
  return esc(v);
}

/** Template HTML: tudo que é interpolado é escapado, exceto valores criados com raw()/html. */
export function html(strings, ...values) {
  let out = strings[0];
  values.forEach((v, i) => { out += renderValue(v) + strings[i + 1]; });
  return new Raw(out);
}

export function uid() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export const nowIso = () => new Date().toISOString();

const dateFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
export const fmtDate = (v) => (v == null ? "—" : dateFmt.format(new Date(v)));
export const fmtDateTime = (v) => (v == null ? "—" : dateTimeFmt.format(new Date(v)));

export function relDays(ms, now = Date.now()) {
  const d = Math.round((ms - now) / 86400000);
  if (d <= 0) return "hoje";
  if (d === 1) return "amanhã";
  return `em ${d} dias`;
}

export const pct = (v) => (v == null ? "—" : `${Math.round(v)}%`);
export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
export function minutesLabel(total) {
  total = Math.round(total || 0);
  return total < 60 ? `${total} min` : `${Math.floor(total / 60)} h ${String(total % 60).padStart(2, "0")} min`;
}

export function meter(value, cls = "") {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  return html`<div class="meter ${cls}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(v)}"><span style="width:${v}%"></span></div>`;
}

export function dots(level) {
  const n = Number(level) || 0;
  return html`<span class="dots" role="img" aria-label="Dificuldade ${n} de 5">${[1, 2, 3, 4, 5].map((i) => raw(`<i class="${i <= n ? "on" : ""}"></i>`))}</span>`;
}

export const MARK = { correct: "✓", incorrect: "✗", partial: "½", pending: "…" };

/** Texto com linhas "Nome : fala" (diálogos) e parágrafos separados por linha em branco. */
export function dialogue(text) {
  return raw(String(text || "").split(/\n\s*\n/).map((para) => {
    const lines = para.trim().split("\n").filter(Boolean).map((line) => {
      const m = line.match(/^([^:\n]{1,30}) : (.*)$/);
      return m ? `<span class="dialogue-line"><b>${esc(m[1])}</b> : ${esc(m[2])}</span>` : esc(line);
    });
    return lines.length ? `<p>${lines.join("<br>")}</p>` : "";
  }).join(""));
}

let toastTimer;
export function toast(message, kind = "info") {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = "toast"; }, 3800);
}

export function go(hash) {
  if (location.hash === hash) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else location.hash = hash;
}

export function download(filename, text, type = "application/json") {
  const blob = new Blob([text], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

export function stamp(d = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}
