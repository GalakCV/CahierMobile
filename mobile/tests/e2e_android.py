"""
Teste do app web no modo APK Android: a ponte nativa (window.CahierAndroid) é simulada no Chromium.

Uso (com o app gerado em android/app/src/main/assets/www):
    python -m http.server 8766 --directory android/app/src/main/assets --bind 127.0.0.1 &
    python mobile/tests/e2e_android.py ARQUIVO_SYNC.json [pasta-de-capturas]

ARQUIVO_SYNC.json é um arquivo cahier-sync com respostas (por exemplo, o gerado por e2e_mobile.py).
Variáveis: BASE_URL (padrão http://127.0.0.1:8766/www/index.html), CHROMIUM (executável opcional).
"""
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8766/www/index.html")
SYNC = Path(sys.argv[1])
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "e2e-android")
OUT.mkdir(parents=True, exist_ok=True)

BRIDGE = """
window.CahierAndroid = {
  shared: [], dark: [],
  versionName() { return "1.2.7"; },
  shareFile(name, text) { this.shared.push([name, text]); return true; },
  setDarkTheme(d) { this.dark.push(d); },
};
"""


def step(msg):
    print(f"✓ {msg}", flush=True)


def main():
    errors = []
    with sync_playwright() as p:
        kw = {"executable_path": os.environ["CHROMIUM"]} if os.environ.get("CHROMIUM") else {}
        browser = p.chromium.launch(**kw)
        ctx = browser.new_context(viewport={"width": 390, "height": 800}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True, locale="pt-BR")
        ctx.add_init_script(BRIDGE)
        page = ctx.new_page()
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE)
        page.wait_for_selector("body.ready")
        assert page.evaluate("() => document.body.classList.contains('native')")
        page.wait_for_timeout(800)
        regs = page.evaluate("() => navigator.serviceWorker.getRegistrations().then((r) => r.length)")
        assert regs == 0, f"service worker registrado no modo APK: {regs}"
        step("abre no modo APK, sem service worker")

        # No APK os arquivos vêm de dentro do app; a falta de internet não muda nada.
        ctx.set_offline(True)
        page.wait_for_timeout(300)
        assert page.locator("#offline").is_hidden(), "aviso de offline não deveria aparecer no APK"
        ctx.set_offline(False)
        page.screenshot(path=str(OUT / "inicio.png"))
        step("sem internet: nenhum aviso de offline")

        page.goto(BASE + "#/mais")
        expect(page.get_by_text("Sobre o app e atualizações")).to_be_visible()
        page.goto(BASE + "#/instalar")
        expect(page.locator("h1")).to_have_text("Sobre o app")
        expect(page.get_by_text("versão 1.2.7")).to_be_visible()
        href = page.get_by_role("link", name="Abrir página de downloads").get_attribute("href")
        assert href == "https://github.com/GalakCV/CahierMobile/releases/latest", href
        page.screenshot(path=str(OUT / "sobre.png"))
        step("menu e tela Sobre o app com versão e link de atualização")

        page.goto(BASE + "#/sincronizar")
        page.locator('[data-input="import-sync"]').set_input_files(str(SYNC))
        expected = len(json.loads(SYNC.read_text(encoding="utf-8"))["attempts"])
        page.wait_for_function(
            """(n) => new Promise((r) => { const q = indexedDB.open('cahier'); q.onsuccess = () => {
              const t = q.result.transaction('attempts').objectStore('attempts').count();
              t.onsuccess = () => r(t.result >= n); }; })""", arg=expected, timeout=15000)
        step(f"importar arquivo: {expected} respostas")

        page.goto(BASE + "#/sincronizar")
        page.locator('[data-action="export-sync"]').click()
        page.wait_for_function("() => window.CahierAndroid.shared.length === 1")
        name, text = page.evaluate("() => window.CahierAndroid.shared[0]")
        data = json.loads(text)
        assert name.startswith("cahier-sync-celular-") and name.endswith(".json"), name
        assert data["format"] == "cahier-sync" and len(data["attempts"]) == expected, (data["format"], len(data["attempts"]))
        expect(page.get_by_text("Nada novo desde a última exportação.")).to_be_visible()
        step("exportar: arquivo entregue ao compartilhamento do Android e marcado como exportado")

        page.goto(BASE + "#/preferencias")
        page.wait_for_selector("form")
        before = page.evaluate("() => window.CahierAndroid.dark.length")
        page.select_option('select[name="theme"]', "dark")
        page.get_by_role("button", name="Salvar preferências").click()
        page.wait_for_function("(n) => window.CahierAndroid.dark.length > n && window.CahierAndroid.dark.at(-1) === true", arg=before)
        page.select_option('select[name="theme"]', "light")
        page.get_by_role("button", name="Salvar preferências").click()
        page.wait_for_function("() => window.CahierAndroid.dark.at(-1) === false")
        step("tema escuro/claro repassado às barras do sistema")

        page.goto(BASE + "#/")
        page.wait_for_selector("body.ready")
        page.screenshot(path=str(OUT / "inicio-com-progresso.png"))
        browser.close()

    assert not errors, errors
    step("nenhum erro no console")


if __name__ == "__main__":
    main()
