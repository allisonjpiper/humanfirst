// Human First background worker: the only part of the extension that talks to the Human First
// server (local or hosted). Content scripts on claude.ai can't call it directly because of CORS.

const DEFAULT_SERVER = "http://127.0.0.1:8787";

async function settings() {
  const s = await chrome.storage.sync.get({ hf_user: "", hf_code: "", hf_server: DEFAULT_SERVER });
  return { user: s.hf_user, code: s.hf_code, server: (s.hf_server || DEFAULT_SERVER).replace(/\/+$/, "") };
}

async function post(path, body) {
  const { server, code } = await settings();
  const res = await fetch(server + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Human-First-Code": code },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Server error ${res.status}`);
  return data;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      const { user, server } = await settings();
      if (!user && msg.type !== "settings") {
        sendResponse({ ok: false, error: "not signed in (click the Human First icon)" });
        return;
      }
      if (msg.type === "check") {
        sendResponse({ ok: true, data: await post("/api/check", { username: user, prompt: msg.prompt, source: "claude.ai" }) });
      } else if (msg.type === "override") {
        sendResponse({ ok: true, data: await post("/api/override", { username: user, prompt: msg.prompt, source: "claude.ai" }) });
      } else if (msg.type === "settings") {
        sendResponse({ ok: true, data: { user, server } });
      }
    } catch (err) {
      sendResponse({ ok: false, error: String(err.message || err) });
    }
  })();
  return true; // keep the channel open for the async response
});
