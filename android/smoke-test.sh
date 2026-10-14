#!/usr/bin/env bash
# Teste de fumaça do APK num emulador Android: instala, abre e confere se a tela inicial aparece
# (o conteúdo do WebView é lido pela árvore de acessibilidade via uiautomator).
# Uso: android/smoke-test.sh Cahier.apk [pasta-de-saída]
set -uo pipefail
APK="$1"
OUT="${2:-smoke}"
PKG=io.github.galakcv.cahier
mkdir -p "$OUT"

adb install -r "$APK" || exit 1
adb logcat -c || true
adb shell am start -W -n "$PKG/.MainActivity" || exit 1

found() {  # $1 = rótulo; demais = textos que precisam estar na tela
  local label="$1"; shift
  for _ in $(seq 1 25); do
    sleep 3
    adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 || continue
    adb pull /sdcard/ui.xml "$OUT/$label.xml" >/dev/null 2>&1 || continue
    local all=1
    for t in "$@"; do grep -q "$t" "$OUT/$label.xml" || all=""; done
    if [ -n "$all" ]; then echo "ok: $label"; return 0; fi
  done
  echo "falhou: $label (esperado: $*)"
  return 1
}

status=0
found inicio "Praticar" "Revis" "Cap.tulos" || status=1
adb exec-out screencap -p > "$OUT/inicio.png"

# Toca na aba "Capítulos" e confere se a lista de capítulos aparece.
if [ $status -eq 0 ]; then
  bounds=$(grep -o 'text="Cap[^"]*tulos"[^>]*bounds="\[[0-9]*,[0-9]*\]\[[0-9]*,[0-9]*\]"' "$OUT/inicio.xml" | head -1 | grep -o '\[[0-9]*,[0-9]*\]\[[0-9]*,[0-9]*\]')
  if [ -n "$bounds" ]; then
    read -r x1 y1 x2 y2 <<<"$(echo "$bounds" | tr '[],' '   ')"
    adb shell input tap $(( (x1 + x2) / 2 )) $(( (y1 + y2) / 2 ))
    found capitulos "Bonjour et bienvenue" "Les gens" || status=1
    adb exec-out screencap -p > "$OUT/capitulos.png"
  else
    echo "aviso: botão Capítulos sem coordenadas; pulando a navegação"
  fi
fi

# Fecha e abre de novo: o app precisa voltar normalmente.
adb shell am force-stop "$PKG"
adb shell am start -W -n "$PKG/.MainActivity" >/dev/null
found reaberto "Praticar" || status=1

adb logcat -d > "$OUT/logcat.txt" 2>/dev/null || true
if grep -E "chromium.*(Uncaught|CONSOLE.*[Ee]rror)" "$OUT/logcat.txt" > "$OUT/erros-js.txt"; then
  echo "erros de JavaScript:"; cat "$OUT/erros-js.txt"; status=1
fi
exit $status
