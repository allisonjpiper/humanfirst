// Human First card designs, shared by the Chrome extension (claude.ai) and the website.
// One source of truth: the website loads this same file from /static/cards.js.
// Everything is scoped under .hfc so it never clashes with the host page's styles.

(() => {
  const ICONS = {
    personal: '<path d="M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM2 20c0-3.3 2.7-6 6-6s6 2.7 6 6M12 20c0-3.3 1.8-6 4-6s6 2.7 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    high_stakes: '<path d="M12 3v18M3 12h18" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/><circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    searchable: '<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21Z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="9.5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    crisis: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
    filtered: '<path d="M12 3 2 20h20L12 3Zm0 6v5m0 3v.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    repeat: '<path d="M4 12a8 8 0 0 1 13.7-5.7L20 8.5M20 4v4.5h-4.5M20 12a8 8 0 0 1-13.7 5.7L4 15.5M4 20v-4.5h4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" fill="currentColor"/>',
    drop: '<path d="M12 2.5S5 10 5 14.5a7 7 0 0 0 14 0C19 10 12 2.5 12 2.5Z" fill="currentColor"/>',
    out: '<path d="M7 17 17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    person: '<circle cx="12" cy="8" r="4" fill="currentColor"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8" fill="currentColor"/>',
    logo: '<circle cx="9" cy="8" r="3.4" fill="currentColor"/><circle cx="16" cy="8" r="3.4" fill="currentColor" opacity=".55"/><path d="M2.5 21c0-3.9 2.9-7 6.5-7s6.5 3.1 6.5 7" fill="currentColor"/><path d="M9.5 21c0-3.9 2.9-7 6.5-7s6 3.1 6 7" fill="currentColor" opacity=".55"/>',
  };
  const icon = (name, size = 18) => `<svg class="hfc-ic" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;

  const LABELS = {
    personal: "A human conversation", high_stakes: "Needs a professional", searchable: "Already a better tool",
    crisis: "Emergency", filtered: "Not sent", repeat: "You asked again",
  };

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function safeUrl(u) { try { const x = new URL(u); return x.protocol === "https:" ? x.href : "#"; } catch { return "#"; } }
  function num(x) { return !x ? "0" : x >= 100 ? Math.round(x).toLocaleString() : x >= 1 ? x.toFixed(1) : Number(x.toPrecision(2)).toString(); }

  function band(cat) {
    return `<div class="hfc-band">${icon(cat === "repeat" ? "repeat" : cat, 20)}<span class="hfc-label">${esc(LABELS[cat] || cat)}</span>
      <span class="hfc-brand">${icon("logo", 16)} Human First</span></div>`;
  }

  function quote(q) {
    if (!q) return "";
    return `<figure class="hfc-quote"><blockquote>${esc(q.quote)}</blockquote>
      <figcaption>${q.speaker ? `<span class="hfc-who">${esc(q.speaker)}</span>` : ""}
        <a href="${safeUrl(q.url)}" target="_blank" rel="noopener noreferrer">${esc(q.title)}</a>
        <span class="hfc-src">${esc(q.source)}${q.new ? ' <span class="hfc-new">new</span>' : ""}</span></figcaption></figure>`;
  }

  // mode: "saved" (blocked), "used" (sent to AI), "would" (repeat card, not yet sent)
  function impact(fp, check, mode) {
    if (!fp) return "";
    const u = fp.units || { wh: fp.kwh * 1000, ml: fp.gallons * 3785.41, teaspoons: (fp.gallons * 3785.41) / 4.93 };
    const head = mode === "saved" ? "What not asking AI saved" : mode === "would" ? "What asking Claude would use" : "What this prompt used";
    const tsp = u.teaspoons >= 1 ? `${u.teaspoons.toFixed(1)} teaspoons` : `${Math.round(u.teaspoons * 100)}% of a teaspoon`;
    const chk = check && check.kwh ? `Checking it used ${num(check.kwh * 1000)} Wh, added to your total.` : "";
    const scale = fp.scale ? `<div class="hfc-scale"><b>× 2.5 billion</b> chatbot prompts a day = power for
        <b>${esc(fp.scale.homes)} homes</b> and <b>${esc(fp.scale.pools)} Olympic pools</b> of water, every day.</div>` : "";
    return `<div class="hfc-impact hfc-${mode}">
      <div class="hfc-impact-head">${esc(head)}</div>
      <div class="hfc-stats">
        <div class="hfc-stat">${icon("bolt", 22)}<div><b>${num(u.wh)} Wh</b><span>${esc(fp.energy_comparison)}</span></div></div>
        <div class="hfc-stat hfc-water">${icon("drop", 22)}<div><b>${num(u.ml)} mL</b><span>about ${tsp} of water</span></div></div>
      </div>
      ${scale}
      <div class="hfc-fine">${num(fp.kwh)} kWh · ${num(fp.gallons)} gal. ${chk} Estimates; see How it works.</div>
    </div>`;
  }

  function redirect(r, { actions = "", hint = true } = {}) {
    const cat = r.decision === "crisis" ? "crisis" : r.category;
    const c = r.card || {};
    const people = (c.who_to_talk_to || []).map((w) => `<li>${icon("person", 14)}<span>${esc(w)}</span></li>`).join("");
    const links = (c.resources || []).map((l) =>
      `<a class="hfc-link" href="${safeUrl(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label)}${icon("out", 14)}</a>`).join("");
    const inj = !r.injection_attempt ? "" : cat === "filtered"
      ? "This prompt tried to give Human First instructions and couldn't be checked safely, so it was blocked rather than sent unchecked."
      : "This prompt tried to give Human First instructions, so it checked the real question instead.";
    return `<article class="hfc hfc-${esc(cat)}">${band(cat)}<div class="hfc-body">
      <h2 class="hfc-title">${esc(c.headline)}</h2>
      <p class="hfc-msg">${esc(c.message)}</p>
      ${people ? `<div class="hfc-sub">Who to turn to</div><ul class="hfc-people">${people}</ul>` : ""}
      ${links ? `<div class="hfc-links">${links}</div>` : ""}
      ${quote(c.quote)}
      ${cat === "crisis" ? "" : impact(r.footprint, r.check, "saved")}
      ${inj ? `<p class="hfc-note">${esc(inj)}</p>` : ""}
      ${hint && cat !== "crisis" ? `<p class="hfc-note">Still want to ask Claude? Send it again and Human First will show you what that costs first.</p>` : ""}
      ${actions ? `<div class="hfc-actions">${actions}</div>` : ""}
    </div></article>`;
  }

  function repeat(r, { actions = "" } = {}) {
    const cites = (r.citations || []).map(quote).join("");
    return `<article class="hfc hfc-repeat">${band("repeat")}<div class="hfc-body">
      <h2 class="hfc-title">Before you ask again, here is what the research says</h2>
      <p class="hfc-msg">You were pointed elsewhere on this a moment ago. AI answers carry real costs: to the planet, and to the
        human connections that questions like this one build.</p>
      ${cites}
      ${impact(r.footprint, r.check, "would")}
      ${actions ? `<div class="hfc-actions">${actions}</div>` : ""}
    </div></article>`;
  }

  function toast(fp, check, note) {
    const u = fp && (fp.units || { wh: fp.kwh * 1000, ml: fp.gallons * 3785.41 });
    return `<div class="hfc-toast">
      <div class="hfc-toast-head">${icon("logo", 16)} Human First</div>
      ${fp ? `<div class="hfc-toast-stats"><span>${icon("bolt", 16)}<b>${num(u.wh)} Wh</b></span><span class="hfc-water">${icon("drop", 16)}<b>${num(u.ml)} mL</b></span></div>
      <div class="hfc-toast-line">${fp.scale ? `At chatbot scale (2.5 billion prompts a day), that's power for ${esc(fp.scale.homes)} homes and ${esc(fp.scale.pools)} Olympic pools of water, daily.` : esc(fp.energy_comparison)}</div>` : ""}
      ${check && check.kwh ? `<div class="hfc-toast-fine">Checking it used ${num(check.kwh * 1000)} Wh, added to your total.</div>` : ""}
      ${note ? `<div class="hfc-toast-fine">${esc(note)}</div>` : ""}
    </div>`;
  }

  const css = `
  .hfc, .hfc-toast { --ink:#23302a; --muted:#66716b; --line:#e7e1d4; --paper:#fffdf8; --cream:#f7f3ea;
    --accent:#3f6f5a; --accent-soft:#e3eee7; --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
    font-family:var(--sans); color:var(--ink); line-height:1.5; text-align:left; box-sizing:border-box; }
  .hfc *, .hfc-toast * { box-sizing:border-box; }
  .hfc-personal { --accent:#b4572f; --accent-soft:#f8e6dc; }
  .hfc-high_stakes, .hfc-filtered { --accent:#2c618c; --accent-soft:#e0ecf6; }
  .hfc-searchable { --accent:#9a7212; --accent-soft:#f6eccf; }
  .hfc-crisis { --accent:#b3261e; --accent-soft:#fbe3e1; }
  .hfc-repeat { --accent:#2f3d36; --accent-soft:#e6e9e6; }
  .hfc { background:var(--paper); border-radius:20px; overflow:hidden; border:1px solid var(--line);
    box-shadow:0 1px 2px rgba(35,48,42,.06),0 12px 32px rgba(35,48,42,.12); animation:hfc-in .22s ease-out; }
  @keyframes hfc-in { from { opacity:0; transform:translateY(6px) scale(.985); } to { opacity:1; transform:none; } }
  .hfc-band { display:flex; align-items:center; gap:.5em; padding:.7em 1.2em; color:#fff;
    background:linear-gradient(120deg,var(--accent),color-mix(in srgb,var(--accent) 72%,#000)); }
  .hfc-label { font-size:.74em; font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
  .hfc-brand { margin-left:auto; display:flex; align-items:center; gap:.35em; font-size:.74em; font-weight:600; opacity:.85; }
  .hfc-ic { flex-shrink:0; vertical-align:middle; }
  .hfc-body { padding:1.1em 1.3em 1.2em; }
  .hfc-title { font-family:var(--serif); font-weight:600; font-size:1.42em; line-height:1.2; margin:0 0 .35em; color:var(--ink); letter-spacing:-.005em; }
  .hfc-msg { margin:0 0 .9em; font-size:.98em; color:#34423b; }
  .hfc-sub { font-size:.7em; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:.2em 0 .45em; }
  .hfc-people { list-style:none; padding:0; margin:0 0 .9em; display:flex; flex-wrap:wrap; gap:.4em; }
  .hfc-people li { display:flex; align-items:center; gap:.4em; background:var(--accent-soft); color:var(--ink);
    border-radius:999px; padding:.3em .8em .3em .55em; font-size:.88em; }
  .hfc-people li .hfc-ic { color:var(--accent); }
  .hfc-links { display:flex; flex-wrap:wrap; gap:.45em; margin:0 0 1em; }
  .hfc-link { display:inline-flex; align-items:center; gap:.35em; text-decoration:none; font-weight:600; font-size:.9em;
    color:#fff; background:var(--accent); border-radius:11px; padding:.5em .85em; transition:filter .15s, transform .15s; }
  .hfc-link:hover { filter:brightness(1.1); transform:translateY(-1px); }
  .hfc-quote { position:relative; margin:.2em 0 1em; padding:.85em 1em .85em 2.6em; background:var(--cream); border-radius:14px; }
  .hfc-quote::before { content:"\\201C"; position:absolute; left:.3em; top:-.12em; font-family:var(--serif); font-size:3.4em;
    line-height:1; color:var(--accent); opacity:.55; }
  .hfc-quote blockquote { margin:0; font-family:var(--serif); font-style:italic; font-size:1.02em; line-height:1.45; color:var(--ink); }
  .hfc-quote figcaption { margin-top:.45em; font-size:.78em; color:var(--muted); display:flex; flex-direction:column; gap:.05em; }
  .hfc-quote figcaption a { color:var(--ink); font-weight:600; text-decoration:none; border-bottom:1px solid var(--line); }
  .hfc-quote figcaption a:hover { border-color:var(--accent); }
  .hfc-who { font-weight:600; color:var(--accent); }
  .hfc-new { background:#e3eee7; color:#3f6f5a; font-weight:700; font-size:.85em; text-transform:uppercase; padding:.02em .45em; border-radius:999px; }
  .hfc-impact { border:1px solid var(--line); border-radius:14px; padding:.8em .95em; margin:.2em 0 .8em; background:#fff; }
  .hfc-impact-head { font-size:.7em; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin-bottom:.5em; }
  .hfc-stats { display:grid; grid-template-columns:1fr 1fr; gap:.6em; }
  .hfc-stat { display:flex; gap:.55em; align-items:flex-start; }
  .hfc-stat .hfc-ic { color:#d89b16; margin-top:.15em; }
  .hfc-stat.hfc-water .hfc-ic, .hfc-toast .hfc-water .hfc-ic { color:#2f86c4; }
  .hfc-stat b { display:block; font-size:1.3em; line-height:1.15; }
  .hfc-stat span { font-size:.8em; color:var(--muted); }
  .hfc-scale { margin-top:.65em; padding-top:.6em; border-top:1px dashed var(--line); font-size:.88em; color:#34423b; }
  .hfc-scale b { color:var(--ink); }
  .hfc-fine { margin-top:.45em; font-size:.72em; color:var(--muted); }
  .hfc-note { font-size:.8em; color:var(--muted); margin:.3em 0; }
  .hfc-actions { display:flex; gap:.5em; flex-wrap:wrap; margin-top:.9em; }
  .hfc-actions button { font:inherit; font-size:.92em; font-weight:600; border-radius:11px; padding:.6em 1.1em; cursor:pointer; }
  .hfc-actions .hfc-primary { background:#3f6f5a; color:#fff; border:0; }
  .hfc-actions .hfc-primary:hover { filter:brightness(1.08); }
  .hfc-actions .hfc-secondary { background:#fff; color:var(--ink); border:1px solid #d6cfbf; }
  .hfc-actions button:disabled { opacity:.5; }
  .hfc-crisis .hfc-body { background:#fff8f7; }
  .hfc-toast { background:var(--paper); border:1px solid var(--line); border-radius:16px; padding:.75em .95em; font-size:13px;
    box-shadow:0 10px 30px rgba(0,0,0,.18); max-width:340px; animation:hfc-in .22s ease-out; }
  .hfc-toast-head { display:flex; align-items:center; gap:.35em; font-weight:700; color:#3f6f5a; font-size:.9em; margin-bottom:.35em; }
  .hfc-toast-stats { display:flex; gap:1em; font-size:1.25em; }
  .hfc-toast-stats span { display:flex; align-items:center; gap:.3em; }
  .hfc-toast-stats .hfc-ic { color:#d89b16; }
  .hfc-toast-line { margin-top:.35em; color:#34423b; }
  .hfc-toast-fine { margin-top:.3em; font-size:.85em; color:var(--muted); }
  @media (max-width:520px) { .hfc-stats { grid-template-columns:1fr; } }
  `;

  globalThis.HFCards = { css, redirect, repeat, toast, impact, quote, esc, safeUrl, num };
})();
