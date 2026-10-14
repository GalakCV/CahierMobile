// Testes rápidos do núcleo do app móvel: node --test mobile/tests/core.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { grade, matchBlank } from "../src/js/core/grading.js";
import { compute } from "../src/js/core/mastery.js";
import { intervalFor, replay } from "../src/js/core/review.js";
import { normalize, pyRound } from "../src/js/core/text.js";
import { esc, html } from "../src/js/util.js";

test("normalização preserva acentos e unifica apóstrofos", () => {
  assert.equal(normalize("  J’ai  VINGT ans ! "), "j'ai vingt ans");
  assert.equal(normalize("Est - ce que"), "est-ce que");
  assert.equal(normalize("Vous êtes"), "vous êtes");
});

test("acentos contam, a menos que a questão tolere", () => {
  assert.equal(matchBlank("etes", ["êtes"], "accepted_list", false), "accent");
  assert.equal(matchBlank("etes", ["êtes"], "accepted_list", true), "ok_accent");
  assert.equal(matchBlank("ma soeur", ["ma sœur"], "accepted_list", false), "ok");
});

test("lacunas múltiplas dão nota parcial", () => {
  const ex = { interaction: "text", prompt: "Je ___ et tu ___.", comparison: "accepted_list",
    answers: [{ t: "suis", b: 0, p: true }, { t: "es", b: 1, p: true }] };
  const r = grade(ex, { blanks: ["suis", "est"] });
  assert.equal(r.result, "partial");
  assert.equal(r.score, 0.5);
});

test("uma resposta certa isolada não vira 100% de domínio", () => {
  const exs = Array.from({ length: 10 }, (_, i) => ({ code: `e${i}`, type: "mc_single", difficulty: 2, seconds: 30 }));
  const d = compute(exs, [{ exercise: "e0", created_at: new Date().toISOString(), result: "correct", score: 1, duration_seconds: 5 }]);
  assert.ok(d.score < 40, d.score);
});

test("revisão: erro volta amanhã, acertos espaçam", () => {
  const t0 = Date.parse("2026-01-01T10:00:00Z");
  const at = (h) => new Date(t0 + h * 3600e3).toISOString();
  const book = replay([
    { exercise: "x", created_at: at(0), result: "incorrect", score: 0, answer_display: "a", seq: 1 },
    { exercise: "x", created_at: at(30), result: "correct", score: 1, answer_display: "b", seq: 2 },
  ], []);
  const it = book.get("x");
  assert.equal(it.stage, 1);
  assert.equal(it.interval_days, 3);
  assert.equal(it.recovery, "reviewing");
  assert.equal(intervalFor(4, 1), 30);
});

test("arredondamento igual ao Python", () => {
  assert.equal(pyRound(2.5), 2);
  assert.equal(pyRound(3.5), 4);
});

test("templates escapam conteúdo", () => {
  assert.equal(esc("<b>"), "&lt;b&gt;");
  assert.equal(String(html`<p>${"<script>"}</p>`), "<p>&lt;script&gt;</p>");
});
