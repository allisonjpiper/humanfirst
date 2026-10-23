const DEFAULT_SERVER = "http://127.0.0.1:8787";
const $ = (id) => document.getElementById(id);

function num(x) { return !x ? "0" : x >= 1 ? x.toFixed(2) : Number(x.toPrecision(2)).toString(); }
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

async function load() {
  return chrome.storage.sync.get({ hf_user: "", hf_code: "", hf_server: DEFAULT_SERVER });
}

async function refresh() {
  const { hf_user, hf_code, hf_server } = await load();
  const server = (hf_server || DEFAULT_SERVER).replace(/\/+$/, "");
  $("server").value = server;
  $("user").value = hf_user;
  $("code").value = hf_code;
  $("dash").href = server + "/#footprint";
  try {
    const h = await (await fetch(server + "/api/health")).json();
    $("status").innerHTML = h.key_loaded
      ? `<span class="ok">&#9679; Connected</span> &middot; checking prompts with ${esc(h.model)}`
      : `<span class="bad">&#9679; Server is running but has no API key</span>`;
  } catch {
    $("status").innerHTML = `<span class="bad">&#9679; Can't reach the server.</span> Until it's reachable, prompts go to Claude unchecked.`;
    return;
  }
  if (!hf_user || !hf_code) return;
  try {
    const res = await fetch(`${server}/api/stats?username=${encodeURIComponent(hf_user)}`, { headers: { "X-Human-First-Code": hf_code } });
    if (!res.ok) { $("status").innerHTML += `<br><span class="bad">Sign-in code doesn't match this username.</span>`; return; }
    const s = await res.json();
    const t = s.totals;
    $("stats").hidden = false;
    $("stats").innerHTML = `
      <div><b>${t.prompts}</b> prompts checked, <b>${t.redirected}</b> sent to people or better tools</div>
      <div>Used: <b>${num(s.used.kwh)}</b> kWh, <b>${num(s.used.gallons)}</b> gal (${esc(s.used.energy_comparison)})</div>
      <div>Saved: <b>${num(s.saved.kwh)}</b> kWh, <b>${num(s.saved.gallons)}</b> gal</div>`;
  } catch { /* stats are optional */ }
}

$("save").addEventListener("click", async () => {
  let server = $("server").value.trim().replace(/\/+$/, "") || DEFAULT_SERVER;
  if (!/^http:\/\/(127\.0\.0\.1|localhost):8787$/i.test(server)) {
    $("status").innerHTML = `<span class="bad">Use http://127.0.0.1:8787 (the server running on this computer)</span>`;
    return;
  }
  const name = $("user").value.trim().toLowerCase();
  const code = $("code").value.trim().toUpperCase();
  try {
    const res = await fetch(server + "/api/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: name, code }) });
    const data = await res.json();
    if (!res.ok) { $("status").innerHTML = `<span class="bad">${esc(data.detail || "Couldn't sign in.")}</span>`; return; }
    await chrome.storage.sync.set({ hf_server: server, hf_user: data.username, hf_code: data.code });
    await refresh();
    if (data.new) $("status").innerHTML += `<br>New account. Your sign-in code is <b>${esc(data.code)}</b>. Save it to see your footprint on the website.`;
  } catch {
    $("status").innerHTML = `<span class="bad">Can't reach that server.</span>`;
  }
});

refresh();
