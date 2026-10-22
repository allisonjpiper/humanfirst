const SERVER = "http://127.0.0.1:8787";
const $ = (id) => document.getElementById(id);

function num(x) { return !x ? "0" : x >= 1 ? x.toFixed(2) : Number(x.toPrecision(2)).toString(); }

async function refresh() {
  const { hf_user } = await chrome.storage.sync.get({ hf_user: "" });
  $("user").value = hf_user;
  try {
    const h = await (await fetch(SERVER + "/api/health")).json();
    $("status").innerHTML = h.key_loaded
      ? `<span class="ok">&#9679; Connected</span> &middot; checking prompts with ${h.model}`
      : `<span class="bad">&#9679; Server is running but has no PORTKEY_API_KEY</span>`;
  } catch {
    $("status").innerHTML = `<span class="bad">&#9679; Server not running.</span> Start it with <code>python backend/app.py</code>. Until then, prompts go to Claude unchecked.`;
    return;
  }
  if (!hf_user) return;
  try {
    const s = await (await fetch(`${SERVER}/api/stats?username=${encodeURIComponent(hf_user)}`)).json();
    const t = s.totals;
    $("stats").hidden = false;
    $("stats").innerHTML = `
      <div><b>${t.prompts}</b> prompts checked, <b>${t.redirected}</b> sent to people or better tools</div>
      <div>Used: <b>${num(s.used.kwh)}</b> kWh, <b>${num(s.used.gallons)}</b> gal (${s.used.energy_comparison})</div>
      <div>Saved: <b>${num(s.saved.kwh)}</b> kWh, <b>${num(s.saved.gallons)}</b> gal</div>`;
  } catch { /* stats are optional */ }
}

$("save").addEventListener("click", async () => {
  const name = $("user").value.trim().toLowerCase();
  if (!/^[a-z0-9_.@-]{2,40}$/.test(name)) { $("status").textContent = "Use 2-40 letters, numbers, or . _ @ -"; return; }
  try {
    await fetch(SERVER + "/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: name }) });
  } catch { /* saved locally; account is created on first check */ }
  await chrome.storage.sync.set({ hf_user: name });
  refresh();
});

refresh();
