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
    showToast("Human First is checking your prompt...", null, true);
    const res = await ask("check", prompt);
    busy = false;

    if (!res.ok) {
      // Fail open when the server is unreachable: never lock someone out of Claude. But say so.
      showToast(`Human First is offline (${res.error}). Your prompt was sent unchecked.`);
      releaseSend();
      return;
    }
    const r = res.data;
    if (r.decision === "allow") {
      showToast(footprintText(r.footprint, true), r.injection_attempt ? "Human First noticed instructions aimed at it and checked the real question." : null);
      releaseSend();
    } else if (r.decision === "repeat") {
      hideToast();
      showModal(repeatHtml(r), {
        onOverride: async () => {
          const o = await ask("override", prompt);
          closeModal();
          showToast(o.ok ? footprintText(o.data.footprint, true) : "Sent to Claude.");
          releaseSend();
        },
      });
    } else {
      hideToast();
      showModal(cardHtml(r));
    }
  }

  // ---------- UI (inside a shadow root so claude.ai's styles don't leak in) ----------
  const host = document.createElement("div");
  host.id = "human-first-root";
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = `<style>${CSS()}</style><div class="toast" hidden></div><div class="backdrop" hidden><div class="modal" role="dialog" aria-modal="true"></div></div>`;
  (document.body || document.documentElement).appendChild(host);
  const toast = root.querySelector(".toast");
  const backdrop = root.querySelector(".backdrop");
  const modal = root.querySelector(".modal");
  let toastTimer;

  function showToast(text, note = null, sticky = false) {
    clearTimeout(toastTimer);
    toast.innerHTML = `<div class="brand">Human First</div><div>${esc(text)}</div>${note ? `<div class="note">${esc(note)}</div>` : ""}`;
    toast.hidden = false;
    if (!sticky) toastTimer = setTimeout(hideToast, 7000);
  }
  function hideToast() { toast.hidden = true; }

  function showModal(html, { onOverride } = {}) {
    modal.innerHTML = html;
    backdrop.hidden = false;
    modal.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeModal));
    const ov = modal.querySelector("[data-override]");
    if (ov && onOverride) ov.addEventListener("click", () => { ov.disabled = true; onOverride(); });
    const first = modal.querySelector("button");
    first && first.focus();
  }
  function closeModal() { backdrop.hidden = true; modal.innerHTML = ""; const ed = editor(); ed && ed.focus(); }
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeModal(); });
  root.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

  const LABELS = { personal: "A human conversation", high_stakes: "Needs a professional", searchable: "Already a better tool",
    crisis: "Emergency", filtered: "Not sent" };

  function cardHtml(r) {
    const cat = r.decision === "crisis" ? "crisis" : r.category;
    const c = r.card;
    const who = (c.who_to_talk_to || []).map((w) => `<li>${esc(w)}</li>`).join("");
    const links = (c.resources || []).map((l) => `<a href="${safeUrl(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label)}</a>`).join("");
    const hint = cat === "crisis" ? "" : `<div class="note">Still want to ask Claude? Send it again and Human First will show you what that costs first.</div>`;
    const inj = r.injection_attempt ? `<div class="note">This prompt tried to give Human First instructions, so it checked the real question instead.</div>` : "";
    return `<div class="card cat-${esc(cat)}">
      <span class="tag">${esc(LABELS[cat] || cat)}</span>
      <h2>${esc(c.headline)}</h2>
      <p>${esc(c.message)}</p>
      ${who ? `<div class="small">Who to turn to</div><ul>${who}</ul>` : ""}
      <div class="links">${links}</div>
      <div class="foot">${esc(footprintText(r.footprint, false))}</div>
      ${inj}${hint}
      <div class="actions"><button class="primary" data-close>Got it</button></div>
    </div>`;
  }

  function repeatHtml(r) {
    const cites = (r.citations || []).map((c) => `<div class="cite">
      <a href="${safeUrl(c.url)}" target="_blank" rel="noopener noreferrer">${esc(c.title)}</a>
      <div class="src">${esc(c.source)}</div><div>${esc(c.takeaway)}</div></div>`).join("");
    return `<div class="card cat-repeat">
      <span class="tag">You asked again</span>
      <h2>Before you ask again, here is what the research says</h2>
      <p>You were pointed elsewhere on this a moment ago. AI answers carry real costs: to the planet, and to the human
        connections that questions like this one build.</p>
      ${cites}
      <div class="foot">${esc(footprintText(r.footprint, true, true))}</div>
      <div class="actions">
        <button class="primary" data-close>I'll ask a person</button>
        <button class="secondary" data-override>Ask Claude anyway</button>
      </div></div>`;
  }

  function footprintText(fp, sent, hypothetical = false) {
    const lead = hypothetical ? "Asking Claude would use about" : sent ? "This prompt used about" : "Not asking AI saved about";
    return `${lead} ${num(fp.kwh)} kWh (${fp.energy_comparison}) and ${num(fp.gallons)} gal of water (${fp.water_comparison}).`;
  }

  function num(x) { return !x ? "0" : x >= 1 ? x.toFixed(2) : Number(x.toPrecision(2)).toString(); }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function safeUrl(u) { try { const x = new URL(u); return x.protocol === "https:" ? x.href : "#"; } catch { return "#"; } }

  function CSS() {
    return `
      :host { all: initial; }
      * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; }
      [hidden] { display: none !important; }
      .toast { position: fixed; right: 20px; bottom: 20px; z-index: 2147483647; max-width: 360px;
        background: #fffdf8; color: #23302a; border: 1px solid #e4ded1; border-left: 5px solid #3f6f5a;
        border-radius: 12px; padding: 12px 14px; font-size: 13px; line-height: 1.45;
        box-shadow: 0 6px 24px rgba(0,0,0,.15); }
      .brand { font-weight: 700; color: #3f6f5a; font-size: 12px; margin-bottom: 2px; }
      .note { font-size: 12px; color: #6b756f; margin-top: 6px; }
      .backdrop { position: fixed; inset: 0; z-index: 2147483647; background: rgba(20, 28, 24, .45);
        display: flex; align-items: center; justify-content: center; padding: 20px; }
      .modal { max-width: 560px; width: 100%; max-height: 85vh; overflow: auto; }
      .card { background: #fffdf8; color: #23302a; border-radius: 16px; padding: 22px 24px; font-size: 15px;
        line-height: 1.5; box-shadow: 0 10px 40px rgba(0,0,0,.25); border-left: 6px solid #3f6f5a; }
      .card h2 { font-size: 20px; margin: 6px 0 6px; line-height: 1.25; }
      .card p { margin: 4px 0 10px; }
      .card ul { margin: 4px 0 12px; padding-left: 20px; }
      .small { font-size: 12px; color: #6b756f; text-transform: uppercase; letter-spacing: .04em; font-weight: 700; }
      .tag { display: inline-block; font-size: 11px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
        padding: 3px 9px; border-radius: 999px; background: #e3eee7; color: #3f6f5a; }
      .links { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 10px; }
      .links a { text-decoration: none; padding: 7px 12px; border-radius: 9px; font-size: 14px; font-weight: 600;
        border: 1px solid currentColor; color: #3f6f5a; }
      .foot { font-size: 13px; color: #6b756f; margin-top: 8px; }
      .actions { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
      button { font-size: 14px; font-weight: 600; border-radius: 10px; padding: 9px 16px; cursor: pointer; }
      button.primary { background: #3f6f5a; color: #fff; border: 0; }
      button.secondary { background: #fff; color: #23302a; border: 1px solid #d8d1c2; }
      button:disabled { opacity: .5; }
      .cite { border-top: 1px solid #e4ded1; padding: 9px 0; font-size: 14px; }
      .cite a { color: #3f6f5a; font-weight: 700; }
      .src { font-size: 12px; color: #6b756f; }
      .cat-personal { border-left-color: #b8603c; } .cat-personal .tag { background: #f6e3d8; color: #b8603c; }
      .cat-personal .links a { color: #b8603c; }
      .cat-high_stakes, .cat-filtered { border-left-color: #2f6690; }
      .cat-high_stakes .tag, .cat-filtered .tag { background: #e0ecf5; color: #2f6690; }
      .cat-high_stakes .links a, .cat-filtered .links a { color: #2f6690; }
      .cat-searchable { border-left-color: #a07a1c; } .cat-searchable .tag { background: #f5ecd2; color: #a07a1c; }
      .cat-searchable .links a { color: #a07a1c; }
      .cat-crisis { border-left-color: #b3261e; background: #fbe3e1; } .cat-crisis .tag { background: #b3261e; color: #fff; }
      .cat-crisis .links a { color: #b3261e; background: #fff; }
      .cat-repeat { border-left-color: #23302a; } .cat-repeat .tag { background: #23302a; color: #fff; }
    `;
  }
})();
