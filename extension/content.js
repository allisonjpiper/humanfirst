// Human First content script for claude.ai.
//
// It catches the moment you send a prompt (Enter key or the Send button), asks the
// local Human First server whether this is a good use of AI, and then either lets
// the prompt through to Claude or shows a card pointing you to people and better tools.
//
// claude.ai's page layout is not a public API. The selectors below match it as of
// October 2026 and are kept in one place so they are easy to update.

(() => {
  const SELECTORS = {
    editor: ['div.ProseMirror[contenteditable="true"]', 'div[contenteditable="true"]', "fieldset textarea", "textarea"],
    send: ['button[aria-label="Send message"]', 'button[aria-label="Send Message"]', 'button[aria-label*="Send" i]',
      'fieldset button[type="submit"]'],
  };

  let bypass = false; // true for the moment we re-send a prompt that was approved
  let busy = false;

  // ---------- finding claude.ai's composer ----------
  function editor() {
    for (const s of SELECTORS.editor) {
      const el = document.querySelector(s);
      if (el) return el;
    }
    return null;
  }
  function sendButton() {
    for (const s of SELECTORS.send) {
      const els = [...document.querySelectorAll(s)];
      const el = els.find((b) => b.offsetParent !== null);
      if (el) return el;
    }
    return null;
  }
  function promptText() {
    const ed = editor();
    if (!ed) return "";
    return (ed.value !== undefined ? ed.value : ed.innerText || "").trim();
  }
  function inEditor(target) {
    const ed = editor();
    return ed && target && (target === ed || ed.contains(target));
  }
  function isSendButton(btn) {
    return btn && SELECTORS.send.some((s) => btn.matches(s));
  }

  // ---------- intercepting send ----------
  window.addEventListener("keydown", (e) => {
    if (bypass || e.key !== "Enter" || e.shiftKey || e.isComposing || !inEditor(e.target)) return;
    if (!promptText()) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    gate();
  }, true);

  window.addEventListener("click", (e) => {
    if (bypass) return;
    const btn = e.target.closest && e.target.closest("button");
    if (!isSendButton(btn) || !promptText()) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    gate();
  }, true);

  function releaseSend() {
    bypass = true;
    const btn = sendButton();
    if (btn && !btn.disabled) {
      btn.click();
    } else {
      const ed = editor();
      ed && ed.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true, cancelable: true }));
    }
    setTimeout(() => (bypass = false), 600);
  }

  function ask(type, prompt) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type, prompt }, (res) => resolve(res || { ok: false, error: "No response" }));
      } catch (err) {
        resolve({ ok: false, error: String(err) });
      }
    });
  }

  async function gate() {
    if (busy) return;
    const prompt = promptText();
    if (!prompt) return;
    busy = true;
    showToastText("Checking your prompt...", true);
    const res = await ask("check", prompt);
    busy = false;

    if (!res.ok) {
      // Fail open when the server is unreachable: never lock someone out of Claude. But say so.
      showToastText(`Human First is offline (${res.error}). Your prompt was sent unchecked.`);
      releaseSend();
      return;
    }
    const r = res.data;
    if (r.decision === "allow") {
      showToastHtml(HFCards.toast(r.footprint, r.check, r.injection_attempt ? "Human First noticed instructions aimed at it and checked the real question." : null));
      releaseSend();
    } else if (r.decision === "repeat") {
      hideToast();
      showModal(HFCards.repeat(r, { actions: `<button class="hfc-primary" data-close>I'll ask a person</button>
        <button class="hfc-secondary" data-override>Ask Claude anyway</button>` }), {
        onOverride: async () => {
          const o = await ask("override", prompt);
          closeModal();
          if (o.ok) showToastHtml(HFCards.toast(o.data.footprint, null, null)); else showToastText("Sent to Claude.");
          releaseSend();
        },
      });
    } else {
      hideToast();
      showModal(HFCards.redirect(r, { actions: `<button class="hfc-primary" data-close>Got it</button>` }));
    }
  }

  // ---------- UI (inside a shadow root so claude.ai's styles don't leak in) ----------
  const host = document.createElement("div");
  host.id = "human-first-root";
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>${CSS()}${HFCards.css}</style><div class="toast" hidden></div><div class="backdrop" hidden><div class="modal" role="dialog" aria-modal="true"></div></div>`;
  (document.body || document.documentElement).appendChild(host);
  const toast = root.querySelector(".toast");
  const backdrop = root.querySelector(".backdrop");
  const modal = root.querySelector(".modal");
  let toastTimer;

  function showToastHtml(html, sticky = false) {
    clearTimeout(toastTimer);
    toast.innerHTML = html;
    toast.hidden = false;
    if (!sticky) toastTimer = setTimeout(hideToast, 9000);
  }
  function showToastText(text, sticky = false) {
    showToastHtml(`<div class="hfc-toast"><div class="hfc-toast-head">Human First</div><div>${esc(text)}</div></div>`, sticky);
  }
  function hideToast() { toast.hidden = true; }

  function showModal(html, { onOverride } = {}) {
    modal.innerHTML = html;
    backdrop.hidden = false;
    modal.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
    const ov = modal.querySelector("[data-override]");
    if (ov && onOverride) ov.addEventListener("click", () => { ov.disabled = true; onOverride(); });
    const first = modal.querySelector("button");
    first && first.focus({ preventScroll: true });
    modal.scrollTop = 0;
  }
  function closeModal() { backdrop.hidden = true; modal.innerHTML = ""; const ed = editor(); ed && ed.focus(); }
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeModal(); });
  root.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

  function num(x) { return !x ? "0" : x >= 1 ? x.toFixed(2) : Number(x.toPrecision(2)).toString(); }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function safeUrl(u) { try { const x = new URL(u); return x.protocol === "https:" ? x.href : "#"; } catch { return "#"; } }

  function CSS() {
    return `
      :host { all: initial; }
      [hidden] { display: none !important; }
      .toast { position: fixed; right: 20px; bottom: 20px; z-index: 2147483647; }
      .backdrop { position: fixed; inset: 0; z-index: 2147483647; background: rgba(20, 28, 24, .5);
        backdrop-filter: blur(2px); display: flex; align-items: center; justify-content: center; padding: 20px; }
      .modal { max-width: 600px; width: 100%; max-height: 88vh; overflow: auto; font-size: 15px; border-radius: 20px; }
    `;
  }
})();
