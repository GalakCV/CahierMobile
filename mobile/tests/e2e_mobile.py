"""
Teste de ponta a ponta do app móvel num navegador real (Chromium, tela de celular, modo offline).

Uso (com o app gerado em mobile/dist e servido em BASE_URL):
    python -m http.server 8765 --directory mobile/dist --bind 127.0.0.1 &
    python mobile/tests/e2e_mobile.py [pasta-de-capturas]

Variáveis: BASE_URL (padrão http://127.0.0.1:8765/), CHROMIUM (caminho opcional do executável).
Gera também os arquivos de sincronização para o teste com o Django (sync-celular.json).
"""
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8765/")
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "e2e-mobile")
OUT.mkdir(parents=True, exist_ok=True)
DIST = Path(__file__).resolve().parents[1] / "dist"
CONTENT = json.loads((DIST / "content.json").read_text(encoding="utf-8"))
EX = {e["code"]: e for e in CONTENT["exercises"]}
log = []
COUNT_JS = """() => new Promise((r) => { const q = indexedDB.open('cahier'); q.onsuccess = () => {
  const t = q.result.transaction('attempts').objectStore('attempts').count(); t.onsuccess = () => r(t.result); }; })"""


def step(msg):
    log.append(msg)
    print(f"✓ {msg}", flush=True)


def shot(page, name, full=False):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def correct_text(ex, blank):
    if ex.get("comparison") in ("regex", "self", "manual"):
        return ex["model"]
    answers = [a for a in ex.get("answers", []) if a["b"] == blank]
    prim = [a for a in answers if a["p"]] or answers
    return prim[0]["t"]


def answer_current(page, correct=True):
    form = page.locator('form[data-form="answer"]')
    handle = form.element_handle()
    code = form.get_attribute("data-code")
    ex = EX[code]
    it = ex["interaction"]
    choices = ex.get("choices", [])
    if it == "single":
        idx = next(i for i, c in enumerate(choices) if bool(c.get("ok")) == correct)
        form.locator(f'input[name="choice"][value="{idx}"]').check()
    elif it == "multiple":
        for i, c in enumerate(choices):
            if c.get("ok") if correct else i == 0:
                form.locator(f'input[name="choice"][value="{i}"]').check()
    elif it == "order":
        order = sorted(range(len(choices)), key=lambda i: choices[i]["pos"])
        if not correct:
            order.reverse()
        for i in order:
            form.locator(f'.order-bank .token[data-i="{i}"]').tap()
    elif it == "match":
        for i in range(len(choices)):
            target = i if correct else (i + 1) % len(choices)
            form.locator(f'select[name="match_{i}"]').select_option(str(target))
    elif it == "writing":
        form.locator("textarea").fill("Bonjour ! Je m'appelle Gui. Je suis de Rio.")
    else:
        inputs = form.locator("input.blank, input.text-answer")
        for k in range(inputs.count()):
            inputs.nth(k).fill(correct_text(ex, k) if correct else "zzz")
    if page.locator("#accent-submit").is_visible():
        page.locator("#accent-submit").tap()  # botão OK do teclado de acentos
    else:
        form.locator('button[type="submit"]').tap()
    page.wait_for_function("(el) => !el.isConnected", arg=handle)  # a tela seguinte já foi desenhada
    return ex


def finish_feedback(page):
    if page.locator('[data-form="assess"]').count():
        crit = page.locator('[data-form="assess"] input[name="criteria"]')
        (crit.first if crit.count() else page.locator('[data-form="assess"] input[value="correct"]')).check()
        page.locator('[data-form="assess"] button[type="submit"]').tap()
    else:
        page.locator("[data-next]").tap()
    page.wait_for_timeout(150)


with sync_playwright() as p:
    kwargs = {"args": ["--no-sandbox", "--disable-gpu", "--no-zygote", "--single-process"]}
    if os.environ.get("CHROMIUM"):
        kwargs["executable_path"] = os.environ["CHROMIUM"]
    browser = p.chromium.launch(**kwargs)
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                              has_touch=True, accept_downloads=True, locale="pt-BR",
                              user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    page.goto(BASE)
    page.wait_for_function("() => navigator.serviceWorker.controller !== null", timeout=20000)
    expect(page.locator("h1")).to_contain_text("Bonjour")
    step("App aberto; service worker instalado e controlando a página")

    ctx.set_offline(True)
    page.reload()
    expect(page.locator("h1")).to_contain_text("Bonjour")
    expect(page.locator("#offline")).to_be_visible()
    shot(page, "01-inicio-offline")
    step("Recarregado SEM internet: o app abre normalmente (modo offline)")

    # Sessão rápida
    page.locator('[data-action="quick"]').first.tap()
    expect(page.locator(".session-head")).to_contain_text("Questão 1 de 5")
    shot(page, "02-questao")
    answer_current(page, correct=True)
    expect(page.locator(".verdict")).to_contain_text("Correto")
    shot(page, "03-acerto")
    step("Sessão rápida: resposta certa corrigida como 'Correto!'")
    finish_feedback(page)
    answer_current(page, correct=False)
    expect(page.locator(".verdict")).not_to_contain_text("Correto")
    expect(page.locator(".explanation")).to_be_visible()
    shot(page, "04-erro", full=True)
    step("Resposta errada: veredito, resposta correta e explicação")
    page.locator('[data-action="flag"]').first.tap()
    expect(page.locator(".toast")).to_contain_text("Marcada")
    step("Questão marcada para revisão")
    finish_feedback(page)

    # Interromper, recarregar e retomar
    page.locator('[data-action="pause"]').tap()
    expect(page.locator(".resume")).to_contain_text("Retomar sessão")
    page.reload()
    expect(page.locator(".resume")).to_contain_text("2 de 5 respondidas")
    page.locator(".resume a.btn").tap()
    expect(page.locator(".session-head")).to_contain_text("Questão 3 de 5")
    step("Sessão interrompida, app recarregado offline e sessão retomada na questão 3")

    for k in range(3):
        answer_current(page, correct=k != 1)
        finish_feedback(page)
    expect(page.locator(".score-big")).to_be_visible()
    shot(page, "05-resultado", full=True)
    step(f"Sessão concluída: {page.locator('.score-big').inner_text()}")

    # Todos os tipos de interação: sessões dos capítulos com 20 questões
    seen = set()
    for ch in ["ch01", "ch02", "ch03", "ch04"]:
        page.goto(f"{BASE}#/praticar?capitulo={ch}")
        page.locator('input[name="count"]').fill("20")
        page.locator('[data-form="practice"] button[type="submit"]').tap()
        for _ in range(20):
            if not page.locator('form[data-form="answer"]').count():
                break
            ex = answer_current(page, correct=True)
            seen.add(ex["interaction"])
            verdict = page.locator(".verdict").inner_text()
            assert "Correto" in verdict or "guardada" in verdict, (ex["code"], verdict)
            finish_feedback(page)
    assert {"single", "multiple", "text", "order", "match", "writing"} <= seen, seen
    step(f"80 questões respondidas com o gabarito: todas corrigidas como certas ({', '.join(sorted(seen))})")

    # Texto de interpretação
    page.goto(f"{BASE}#/capitulos/ch02/textos")
    page.locator(".cards a.card").first.tap()
    page.locator('[data-action="passage"][data-mode="practice"]').tap()
    expect(page.locator("details.reading")).to_be_visible()
    shot(page, "06-texto")
    while page.locator('form[data-form="answer"]').count():
        answer_current(page, correct=True)
        finish_feedback(page)
    expect(page.get_by_text("Vocabulário novo")).to_be_visible()
    step("Interpretação de texto: texto junto às perguntas, vocabulário novo e estruturas no fim")

    # Teclado de acentos
    page.goto(f"{BASE}#/praticar?capitulo=ch01")
    page.locator('input[name="count"]').fill("30")
    page.locator('[data-form="practice"] button[type="submit"]').tap()
    for _ in range(30):
        inp = page.locator('form[data-form="answer"] input.blank, form[data-form="answer"] input.text-answer')
        if inp.count():
            inp.first.tap()
            expect(page.locator("#accents")).to_be_visible()
            page.locator('#accents [data-char="é"]').tap()
            assert inp.first.input_value().endswith("é")
            shot(page, "07-teclado-acentos")
            break
        answer_current(page, correct=True)
        finish_feedback(page)
    step("Teclado de acentos aparece ao digitar e insere 'é' no campo")
    page.locator('[data-action="pause"]').tap()

    # Revisões e caderno de erros
    page.goto(f"{BASE}#/revisoes")
    shot(page, "08-revisoes")
    page.locator('[data-action="review"]').first.tap()
    expect(page.locator(".session-head")).to_contain_text("Revisões pendentes")
    answer_current(page, correct=True)
    finish_feedback(page)
    step("Sessão de revisões pendentes iniciada e respondida")
    page.goto(f"{BASE}#/caderno")
    expect(page.locator(".result-item").first).to_be_visible()
    shot(page, "09-caderno")
    step(f"Caderno de erros: {page.locator('.result-item').count()} questões")

    # Avaliação final do capítulo 1
    page.goto(f"{BASE}#/capitulos/ch01/revisao")
    page.locator('[data-action="chapter-assessment"]').tap()
    n = 0
    while page.locator('form[data-form="answer"]').count():
        assert not page.locator(".verdict").count()
        answer_current(page, correct=True)
        n += 1
    expect(page.locator(".verdict-correct")).to_contain_text("aprovada")
    step(f"Avaliação final ({n} questões, correção só no fim): aprovada")
    page.goto(f"{BASE}#/capitulos")
    expect(page.locator(".chapter-card").first).to_contain_text("Concluído")
    shot(page, "10-capitulos")

    # Progresso e escrita
    page.goto(f"{BASE}#/progresso")
    shot(page, "11-progresso")
    page.goto(f"{BASE}#/escrita")
    step("Progresso e produção escrita abertos")

    # Exportar sincronização
    page.goto(f"{BASE}#/sincronizar")
    with page.expect_download() as d:
        page.locator('[data-action="export-sync"]').tap()
    sync_path = OUT / "sync-celular.json"
    d.value.save_as(sync_path)
    data = json.loads(sync_path.read_text(encoding="utf-8"))
    assert data["format"] == "cahier-sync" and len(data["attempts"]) > 90, len(data["attempts"])
    step(f"Progresso exportado: {len(data['attempts'])} respostas, {len(data['flags'])} marcações, {len(data['assessments'])} avaliações")

    # Importar arquivo do computador, se fornecido
    desk = os.environ.get("DESKTOP_SYNC")
    if desk:
        before = page.evaluate(COUNT_JS)
        page.locator('[data-input="import-sync"]').set_input_files(desk)
        expect(page.locator(".toast")).to_contain_text("Importado")
        after = page.evaluate(COUNT_JS)
        step(f"Progresso do computador importado: {before} → {after} respostas no celular")
        page.locator('[data-input="import-sync"]').set_input_files(desk)
        expect(page.locator(".toast")).to_contain_text("Nada novo")
        step("Importar o mesmo arquivo de novo não duplica nada")

    # Preferências: tema escuro e texto grande
    page.goto(f"{BASE}#/preferencias")
    page.locator('select[name="theme"]').select_option("dark")
    page.locator('select[name="font"]').select_option("large")
    page.locator('[data-form="settings"] button[type="submit"]').tap()
    expect(page.locator(".toast")).to_contain_text("Preferências salvas")
    page.goto(f"{BASE}#/capitulos/ch03/explicacoes")
    shot(page, "12-escuro")
    page.reload()
    page.wait_for_function("() => document.body.classList.contains('ready')")
    assert page.evaluate("() => document.documentElement.dataset.theme") == "dark"
    step("Preferências (tema escuro, texto grande) salvas e mantidas após recarregar")

    ctx.set_offline(False)
    bad = [e for e in errors if "favicon" not in e]
    assert not bad, bad
    step("Nenhum erro de JavaScript no console")
    browser.close()

(OUT / "log.txt").write_text("\n".join(log), encoding="utf-8")
