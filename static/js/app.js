/* Cahier — JavaScript mínimo, sem dependências. */
(function () {
  "use strict";

  // Menu em telas pequenas
  document.querySelectorAll("[data-menu-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var side = document.querySelector(".side");
      var open = side.classList.toggle("open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });

  // ---------- Teclado de caracteres franceses ----------
  var lastField = null;
  document.addEventListener("focusin", function (e) {
    var t = e.target;
    if (t.matches && t.matches("input[type=text], textarea")) lastField = t;
  });
  document.querySelectorAll("[data-keyboard] button[data-char]").forEach(function (btn) {
    btn.addEventListener("mousedown", function (e) { e.preventDefault(); }); // mantém o foco no campo
    btn.addEventListener("click", function (e) {
      var field = lastField || document.querySelector(".sheet input[type=text], .sheet textarea");
      if (!field) return;
      var ch = btn.dataset.char;
      if (e.shiftKey) ch = ch.toLocaleUpperCase("fr");
      var start = field.selectionStart != null ? field.selectionStart : field.value.length;
      var end = field.selectionEnd != null ? field.selectionEnd : field.value.length;
      field.value = field.value.slice(0, start) + ch + field.value.slice(end);
      field.focus();
      field.setSelectionRange(start + ch.length, start + ch.length);
      field.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });

  // ---------- Ordenação (tocar para montar a sequência) ----------
  document.querySelectorAll("[data-order]").forEach(function (box) {
    var bank = box.querySelector(".order-bank");
    var zone = box.querySelector(".order-zone");
    var input = box.querySelector("input[name=order]");
    var clear = box.querySelector("[data-order-clear]");
    function sync() {
      input.value = Array.prototype.map.call(zone.querySelectorAll(".token"), function (t) { return t.dataset.id; }).join(",");
    }
    box.addEventListener("click", function (e) {
      var tok = e.target.closest(".token");
      if (!tok) return;
      e.preventDefault();
      (tok.parentElement === bank ? zone : bank).appendChild(tok);
      tok.setAttribute("aria-pressed", tok.parentElement === zone ? "true" : "false");
      sync();
      tok.focus();
    });
    if (clear) clear.addEventListener("click", function (e) {
      e.preventDefault();
      Array.prototype.slice.call(zone.querySelectorAll(".token")).forEach(function (t) {
        bank.appendChild(t); t.setAttribute("aria-pressed", "false");
      });
      sync();
    });
    // Restaura uma tentativa anterior (quando o formulário volta com erro)
    if (input.value) {
      input.value.split(",").forEach(function (id) {
        var t = bank.querySelector('.token[data-id="' + id + '"]');
        if (t) zone.appendChild(t);
      });
    }
    sync();
  });

  // ---------- Tradução consultada ----------
  document.querySelectorAll("details[data-translation]").forEach(function (d) {
    d.addEventListener("toggle", function () {
      var f = document.querySelector("input[name=used_translation]");
      if (d.open && f) f.value = "1";
    });
  });

  // ---------- Evita envio duplo ----------
  document.querySelectorAll("form[data-once]").forEach(function (form) {
    form.addEventListener("submit", function () {
      form.querySelectorAll("button[type=submit]").forEach(function (b) {
        setTimeout(function () { b.disabled = true; }, 0);
      });
    });
  });

  // ---------- Confirmação de ações irreversíveis ----------
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      if (!window.confirm(el.dataset.confirm)) e.preventDefault();
    });
  });

  // Atalho: Enter envia a resposta nos campos de lacuna
  document.querySelectorAll(".sheet input.blank, .sheet input.text-answer").forEach(function (inp) {
    inp.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); inp.form.requestSubmit ? inp.form.requestSubmit() : inp.form.submit(); }
    });
  });
})();
