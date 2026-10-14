// Executa os vetores de teste gerados pelo Python (tests/test_mobile_parity.py) com o núcleo JS
// e imprime os resultados em JSON. Uso: node parity_runner.mjs vetores.json conteudo.json
import { readFileSync } from "node:fs";
import { grade } from "../src/js/core/grading.js";
import { compute } from "../src/js/core/mastery.js";
import { replay } from "../src/js/core/review.js";

const vectors = JSON.parse(readFileSync(process.argv[2], "utf8"));
const content = JSON.parse(readFileSync(process.argv[3], "utf8"));
const byCode = new Map(content.exercises.map((e) => [e.code, e]));

const out = { grading: [], mastery: [], review: [] };
for (const v of vectors.grading) {
  const r = grade(byCode.get(v.code), v.answer);
  out.grading.push({ result: r.result, score: r.score, answer_display: r.answerDisplay,
    correct_display: r.correctDisplay, feedback: r.feedback });
}
for (const v of vectors.mastery) {
  out.mastery.push(compute(v.exercises.map((c) => byCode.get(c)), v.attempts));
}
for (const v of vectors.review) {
  const states = [];
  for (let k = 1; k <= v.attempts.length + v.flags.length; k++) {
    // estado após os k primeiros eventos (replay do prefixo)
    const evs = v.order.slice(0, k);
    const book = replay(evs.filter((e) => e.t === "a").map((e) => v.attempts[e.i]), evs.filter((e) => e.t === "f").map((e) => v.flags[e.i]));
    const it = book.get(v.code);
    states.push({ stage: it.stage, interval_days: it.interval_days, due_at: it.due_at, error_count: it.error_count,
      correct_streak: it.correct_streak, review_count: it.review_count, flagged: it.flagged, recovery: it.recovery,
      last_result: it.last_result });
  }
  out.review.push(states);
}
process.stdout.write(JSON.stringify(out));
