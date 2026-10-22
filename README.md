# Human First

**AI when it helps. People when it matters.**

Human First is a gatekeeper for Claude. Before a prompt reaches Claude, it checks whether AI is the right tool:

| If you ask... | Human First... |
|---|---|
| a **personal** question ("How should I ask my boss for time off?") | points you to the people in your life, because these conversations build relationships |
| a **high-stakes** medical, legal, or money question | points you to a doctor, clinic, legal aid, or counselor near you |
| something **searchable** ("Where is the nearest cafe?") | gives you a Google Maps / Yelp / web search link, which saves energy and water |
| an **emergency** (suicide, overdose, chest pain) | shows 911, 988, and Poison Control right away, with no AI involved |
| anything else (coding, writing, learning...) | lets it through to Claude |

Every redirect card carries a fresh, **word-for-word quote** from current research on AI's costs. Quotes rotate
so you see something new each time. If you ask a redirected question again, Human First shows three of them,
then lets you choose to **ask Claude anyway**.

New research is found automatically: once a day, a research agent searches the web for recent articles. New
sources wait on the dashboard's **Sources** tab until the owner approves them.

Every prompt's estimated **energy (kWh)** and **water (gallons)** is tracked per user over their whole history,
with everyday comparisons (phone charges, LED-bulb hours, teaspoons, showers). The total includes the energy and
water Human First itself uses to check prompts.

**Online copy:** see the link at the top of the report (a Hugging Face Space; the free tier sleeps when idle, so the first
visit can take about a minute, and its data resets when the Space restarts). The steps below run it on your own computer.

It has two parts that share one small Python server:
- **Chrome extension** that works on **claude.ai** (the real product)
- **Web dashboard** with your lifetime footprint, plus a **test chat** that works without the extension

---

## Run it (about 5 minutes)

You need **Python 3.10+** and (for the extension) **Google Chrome**.

### 1. Get the code and install

macOS / Linux:
```bash
git clone <this repo's URL> human-first
cd human-first
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Windows (PowerShell):
```powershell
git clone <this repo's URL> human-first
cd human-first
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. API key

The app needs `PORTKEY_API_KEY` (it uses the course model `gpt-6-luna` through Portkey).
It looks for a `.env` file in **this folder first, then in the folder one level above**.
If your `.env` is already one folder up, skip this step. Otherwise:

```bash
cp .env.example .env      # then paste your key after PORTKEY_API_KEY=
```

### 3. Start the server

macOS / Linux:
```bash
.venv/bin/python backend/app.py
```
Windows:
```powershell
.venv\Scripts\python backend\app.py
```

You should see `Human First running at http://127.0.0.1:8787`.
Leave this window open. To stop it, press **Ctrl+C** (this ends the whole server process).

### 4. Try it in the browser (no extension needed)

Open **http://127.0.0.1:8787**, pick any username, and use the **Try it** tab. You'll get a private **sign-in code**
(top right). Keep it: you need it for the extension, or to sign in on another device.
Click the example chips to see each kind of redirect. Prompts that pass the check are answered by a
stand-in model (`gpt-6-luna`), since the course key cannot call Claude.
The **My footprint** tab shows your lifetime energy and water totals.

### 5. Use it on claude.ai (Chrome extension)

1. Open `chrome://extensions` in Chrome.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and choose the `extension` folder inside this repo.
4. Click the Human First icon in the toolbar (pin it from the puzzle-piece menu). Leave the server as
   `http://127.0.0.1:8787`, enter the **same username and sign-in code** you have on the dashboard, and click
   **Save and connect**. It should say **Connected**. (Or download a ready-made copy from the "Try it" page.)
5. Go to **https://claude.ai** and send a prompt. Try "Where is the nearest cafe?"

The server from step 3 must be running. If it isn't, the extension lets prompts through to Claude
unchecked and tells you so, so it never locks you out.

---

## How it works

```
prompt ─▶ 1. Crisis screen (keywords, no AI) ──▶ emergency card (911 / 988)
       ─▶ 2. Repeat check (no AI) ─────────────▶ research citations + "Ask anyway"
       ─▶ 3. Gatekeeper agent (gpt-6-luna) ─────▶ appropriate ─▶ Claude answers
                                               └▶ personal / high-stakes ─▶ 4. Redirect agent + tools
                                               └▶ searchable ─▶ map / search links (no AI)
```

- **Gatekeeper agent:** classifies the prompt with a structured output (category, subtype, confidence,
  search query, injection flag). It only blocks when confidence ≥ 0.7.
- **Redirect agent:** writes a short, kind card. Its tools are `map_search`, `web_search`,
  `find_professional`, and `human_support`. Any link it writes that did not come from a tool is removed.
- **Research agent + Quote picker (daily, background):** the research agent web-searches for recent articles. The server
  fetches each page itself, and the quote picker chooses sentences **by number only**, so every quote is copied from the page.
  New sources stay hidden until approved on the Admin tab (open on the computer running the server, or with ADMIN_PASSWORD online).
- **Cost controls:** a shared verdict cache (the same question is never classified twice), provider prompt
  caching (about 85% of gatekeeper input tokens are cached), no AI call for crises, repeats, or searchable
  cards, per-call token limits, 12 prompts per minute and 60k tokens per day per user, and a 2M tokens per day
  global cap.

### Where the footprint numbers come from

Anthropic doesn't publish per-prompt energy or water figures, so these are **estimates**
(see `backend/footprint.py` for the full method):
- Energy per prompt: **low** 0.24 Wh (Google's measured Gemini median, Aug 2025),
  **high** 1.86 Wh (MIT Technology Review's Llama 3.1 405B measurement, May 2025),
  **central** about 0.67 Wh (geometric mean). Longer prompts scale up.
- Water: Google's on-site rate (1.08 mL/Wh) times 4, to include the water used to generate the electricity
  (Harvard Salata Institute, 2026).

---

## Deploying your own online copy (optional)

1. Create a free [Hugging Face](https://huggingface.co) account and a **write** access token.
2. `.venv/bin/hf auth login` and paste the token.
3. `.venv/bin/python deploy/deploy_space.py <your-hf-username>/humanfirst` (uploads only the app files).
4. In the Space's **Settings → Variables and secrets**, add the secrets `PORTKEY_API_KEY` and `ADMIN_PASSWORD`.
5. Open `https://<your-hf-username>-humanfirst.hf.space`. The Admin tab asks for `ADMIN_PASSWORD`.

## Tests

```bash
.venv/bin/python -m pytest tests -q            # 33 safety tests, no API calls
.venv/bin/python tests/eval_gatekeeper.py      # live: 48 hard labeled prompts + 8 attacks (about 56 API calls)
.venv/bin/python tests/measure_pipeline.py     # live: tokens/cost through the full pipeline + prompt-size experiment
.venv/bin/python tests/verify_pinned_quotes.py # live: re-checks every pinned quote word-for-word on its source page
```

## Project layout

```
backend/
  app.py          FastAPI server and the decision pipeline
  agents.py       crisis screen, gatekeeper agent, redirect agent + tools, stand-in answerer
  footprint.py    energy / water estimates and everyday comparisons
  sources.py      research sources, rotating quotes, research agent + quote picker
  db.py           SQLite: users, prompt history, verdict cache
  config.py       .env loading (repo folder, then parent), budgets
  static/         web dashboard + test chat
extension/        Chrome extension for claude.ai (Manifest V3)
deploy/           Hugging Face Space upload script and Space page
Dockerfile        container for the hosted copy
tests/            offline safety tests + live evaluation
data/             created on first run (local database, eval results)
```

## Known limits

- claude.ai's page layout is not a public API. If Anthropic changes it, update the selectors at the top of
  `extension/content.js`.
- Accounts are a username plus a private sign-in code. They are not linked to your Claude account.
- Footprint numbers are estimates from public data, not measurements of Claude.
