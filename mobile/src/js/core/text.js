// Normalização de texto — espelho exato de learning/grading.py (testado por paridade).

const APOSTROPHES = /[’‘`´ʼ]/g;
const PUNCT = /[.,;:!?¡¿«»"“”()\[\]…]/g;

export function nfc(text) {
  return String(text ?? "").normalize("NFC");
}

/** Normalização tolerante, preservando acentos. */
export function normalize(text) {
  let t = nfc(text).replace(APOSTROPHES, "'");
  t = t.replace(/ /g, " ").replace(/ /g, " ");
  t = t.toLowerCase();
  t = t.replace(PUNCT, " ");
  t = t.replace(/\s*'\s*/g, "'");
  t = t.replace(/\s*-\s*/g, "-");
  return t.replace(/\s+/g, " ").trim();
}

/** Aceita 'oe' no lugar de 'œ' e 'ae' no lugar de 'æ'. */
export function ligatureFold(text) {
  return text.replace(/œ/g, "oe").replace(/æ/g, "ae");
}

export function stripAccents(text) {
  return String(text).normalize("NFD").replace(/\p{Mn}/gu, "");
}

export function exactForm(text) {
  return nfc(text).replace(APOSTROPHES, "'").trim();
}

/** Arredondamento como o round() do Python (meio para o par). */
export function pyRound(value, digits = 0) {
  const m = 10 ** digits;
  const x = value * m;
  const r = Math.round(x);
  const isHalf = Math.abs(x % 1) === 0.5;
  const v = isHalf ? (r % 2 === 0 ? r : r - 1) : r;
  return v / m;
}
