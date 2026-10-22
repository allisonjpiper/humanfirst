"""
app.py

Human First backend: one small web server shared by the Chrome extension
(on claude.ai) and the web dashboard / test chat.

Run (from the repo folder):
    .venv/bin/python backend/app.py
Then open http://127.0.0.1:8787

Endpoints
  POST /api/login      {username}                          -> sign in (creates the account)
  POST /api/check      {username, prompt, source}          -> gatekeeper decision for one prompt
  POST /api/override   {username, prompt, source}          -> user chose "Ask AI anyway"; logs the footprint
  POST /api/chat       {username, prompt, override?}       -> test chat: check, then answer if allowed
  GET  /api/stats?username=...                             -> lifetime totals and recent prompts
  GET  /api/tokenomics                                     -> token usage across all real runs
"""

from __future__ import annotations

import asyncio
import difflib
from contextlib import asynccontextmanager
import os
import re
import secrets
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import io
import zipfile

from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agents
import db
import sources
from config import (
    ADMIN_PASSWORD,
    NEW_ACCOUNTS_PER_IP_PER_HOUR,
    GLOBAL_DAILY_TOKEN_BUDGET,
    HOST,
    MAX_PROMPT_CHARS,
    MODEL_NAME,
    PORT,
    PORTKEY_API_KEY,
    REPEAT_SAME_CATEGORY_MINUTES,
    REPEAT_TEXT_SIMILARITY,
    REPEAT_WORD_OVERLAP,
    USER_DAILY_TOKEN_BUDGET,
    USER_REQUESTS_PER_MINUTE,
)
from footprint import describe, estimate_tokens, gatekeeper_footprint, prompt_footprint

STATIC_DIR = Path(__file__).resolve().parent / "static"

sources.init()  # creates the source tables and the three pinned sources (idempotent)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Look for new research in the background (at most once a day). Users never wait on it,
    # and nothing it finds is shown until the owner approves it on the Sources tab.
    task = asyncio.create_task(sources.refresh("startup")) if PORTKEY_API_KEY else None
    yield
    if task and not task.done():
        task.cancel()


app = FastAPI(title="Human First", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://claude.ai"],
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- request models ------------------------------------------------------

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{2,40}$")


class LoginIn(BaseModel):
    username: str
    code: str = ""


class PromptIn(BaseModel):
    username: str
    prompt: str = Field(min_length=1)
    source: str = "web"
    override: bool = False


class FeedbackIn(BaseModel):
    username: str
    rating: int = Field(ge=1, le=5)
    keep_using: str = Field(default="", pattern="^(|yes|maybe|no)$")
    comment: str = Field(default="", max_length=2000)
    page: str = Field(default="", max_length=40)


def clean_username(username: str) -> str:
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "Usernames are 2-40 letters, numbers, or . _ @ -")
    return username


def check_username(username: str) -> str:
    """Validate and create the user if needed (used by internal calls and tests)."""
    username = clean_username(username)
    db.ensure_user(username)
    return username


def authed(username: str, code: str | None) -> str:
    """Every user endpoint needs the user's private sign-in code, so nobody can read someone else's prompts."""
    username = clean_username(username)
    real = db.user_code(username)
    if not real or not code or not secrets.compare_digest(real, code.strip().upper()):
        raise HTTPException(401, "Please sign in again (your sign-in code is missing or wrong).")
    return username


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


_new_accounts: dict[str, deque] = defaultdict(deque)


def new_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I mix-ups
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2))


# --- helpers -------------------------------------------------------------

def find_repeat(username: str, prompt: str, category: str | None = None, subtype: str | None = None) -> dict | None:
    """Is this the user asking an earlier redirected question again?

    Either the text is close to an earlier blocked prompt (any time this week),
    or it lands in the same blocked category AND subtype within the last few
    minutes (catches rephrasing: "ok but how do I ask my manager for a day off"),
    without treating a different personal question as a repeat.
    """
    norm = db.normalize(prompt)
    cutoff = db.now() - timedelta(minutes=REPEAT_SAME_CATEGORY_MINUTES)
    for row in db.recent_blocks(username):
        if difflib.SequenceMatcher(None, norm, db.normalize(row["prompt"])).ratio() >= REPEAT_TEXT_SIMILARITY:
            return dict(row)
        if (category and row["category"] == category and subtype and row["subtype"] == subtype
                and datetime.fromisoformat(row["created_at"]) >= cutoff
                and word_overlap(prompt, row["prompt"]) >= REPEAT_WORD_OVERLAP):
            return dict(row)
    return None


STOPWORDS = set("""a an the i me my we you your it is are was be to of in on at for with and or but if so do does did
how what when where who why which should would could can will just about this that there their they them
he she his her our us im ive its from as by into up out over any some all get got""".split())


def word_overlap(a: str, b: str) -> float:
    """Share of content words in common (overlap coefficient). 'ask boss time off' vs
    'ask manager day off next week' = 0.5; 'nearest cafe' vs 'best mechanic area' = 0."""
    wa = {w for w in db.normalize(a).split() if w not in STOPWORDS}
    wb = {w for w in db.normalize(b).split() if w not in STOPWORDS}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def usage_numbers(*usages) -> dict:
    out = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "model_calls": 0}
    for u in usages:
        if u is None:
            continue
        out["input_tokens"] += u.input_tokens or 0
        out["cached_tokens"] += u.cache_read_tokens or 0
        out["output_tokens"] += u.output_tokens or 0
        out["model_calls"] += u.requests or 0
    return out


def budget_guard(username: str) -> None:
    if db.requests_last_minute(username) >= USER_REQUESTS_PER_MINUTE:
        raise HTTPException(429, "Slow down a little: too many prompts in the last minute.")
    if db.tokens_today(username) >= USER_DAILY_TOKEN_BUDGET:
        raise HTTPException(429, "Daily gatekeeper budget reached for this account. It resets at midnight UTC.")
    if db.tokens_today() >= GLOBAL_DAILY_TOKEN_BUDGET:
        raise HTTPException(503, "Human First has reached its daily budget. Prompts are not being checked.")


def footprint_payload(prompt: str) -> dict:
    fp = prompt_footprint(estimate_tokens(prompt))
    c = fp["central"]
    return {**describe(c["kwh"], c["gallons"]), "range": fp}


# --- core decision -------------------------------------------------------

async def decide(username: str, prompt: str, source: str) -> dict:
    """Run one prompt through the full pipeline, log it, and report what checking it cost."""
    checked = {"kwh": 0.0, "gallons": 0.0, "event_id": None}
    result = await _decide(username, prompt, source, checked)
    result["check"] = describe(checked["kwh"], checked["gallons"])
    result["event_id"] = checked["event_id"]
    return result


async def _decide(username: str, prompt: str, source: str, checked: dict) -> dict:
    budget_guard(username)
    started = time.perf_counter()
    prompt = prompt.strip()
    truncated = len(prompt) > MAX_PROMPT_CHARS
    fp = footprint_payload(prompt)
    central = fp["range"]["central"]

    def log(decision, category, reason, usage=None, cache_hit=False, subtype="") -> int:
        u = usage or {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "model_calls": 0}
        gate = gatekeeper_footprint(u["input_tokens"] + u["output_tokens"]) if u["model_calls"] else {"kwh": 0, "gallons": 0}
        checked.update(gate)  # Human First's own cost for this prompt, shown to the user and added to their total
        sent = decision == "allow"
        checked["event_id"] = db.add_event(
            username=username, source=source, prompt=prompt[:MAX_PROMPT_CHARS], decision=decision,
            category=category, subtype=subtype, reason=reason,
            ai_kwh=central["kwh"] if sent else 0, ai_gallons=central["gallons"] if sent else 0,
            saved_kwh=0 if sent else central["kwh"], saved_gallons=0 if sent else central["gallons"],
            gate_kwh=gate["kwh"], gate_gallons=gate["gallons"],
            cache_hit=int(cache_hit), latency_ms=int((time.perf_counter() - started) * 1000), **u,
        )
        return checked["event_id"]

    base = {"footprint": fp, "truncated": truncated}

    # 1. Crisis screen: no model, no waiting.
    if agents.crisis_screen(prompt):
        log("crisis", "crisis", "Emergency keywords detected")
        return {**base, "decision": "crisis", "category": "high_stakes", "card": agents.CRISIS_RESPONSE}

    # 2. Repeat of a recently blocked question with near-identical text: skip the model entirely.
    earlier = find_repeat(username, prompt)
    if earlier:
        log("repeat", earlier["category"], "Asked again")
        return {**base, "decision": "repeat", "category": earlier["category"],
                "earlier_prompt": earlier["prompt"], "citations": sources.pick_quotes(earlier["category"], 3)}

    # 3. Gatekeeper (with a shared cache so the same question is never classified twice).
    injection_flag = agents.injection_screen(prompt)
    verdict_dict = db.cached_verdict(prompt, agents.GATEKEEPER_VERSION)
    gate_usage = None
    cache_hit = verdict_dict is not None
    if verdict_dict is None:
        try:
            verdict, gate_usage = await agents.run_gatekeeper(prompt, injection_flag)
        except agents.ContentFiltered:
            # Fail closed: the provider's filter would not even read it, so it is not sent to Claude.
            log("redirect", "filtered", "Provider safety filter refused the prompt", subtype="filtered")
            return {**base, "decision": "redirect", "category": "filtered", "injection_attempt": True,
                    "card": {**agents.FILTERED_CARD, "quote": next(iter(sources.pick_quotes("filtered", 1)), None)}}
        except Exception as exc:  # model down, budget hit, bad output: fail open, say so
            log("allow", "unchecked", f"Gatekeeper error: {type(exc).__name__}")
            return {**base, "decision": "allow", "category": "unchecked",
                    "reason": "Human First couldn't check this prompt, so it was sent as usual.",
                    "error": type(exc).__name__}
        verdict_dict = verdict.model_dump()
        db.store_verdict(prompt, verdict_dict, agents.GATEKEEPER_VERSION)
    verdict = agents.GateVerdict(**verdict_dict)

    blocked = verdict.category != "appropriate" and verdict.confidence >= agents.BLOCK_CONFIDENCE
    category = verdict.category if blocked else "appropriate"

    if not blocked:
        log("allow", category, verdict.reason, usage_numbers(gate_usage), cache_hit, verdict.subtype)
        return {**base, "decision": "allow", "category": category, "verdict": verdict_dict,
                "injection_attempt": verdict.injection_attempt or injection_flag}

    # 4. Rephrased repeat: same blocked category within a few minutes.
    earlier = find_repeat(username, prompt, category=verdict.category, subtype=verdict.subtype)
    if earlier:
        log("repeat", verdict.category, "Asked again (rephrased)", usage_numbers(gate_usage), cache_hit, verdict.subtype)
        return {**base, "decision": "repeat", "category": verdict.category, "verdict": verdict_dict,
                "earlier_prompt": earlier["prompt"], "citations": sources.pick_quotes(verdict.category, 3)}

    # 5. Redirect card.
    redirect_usage = None
    if verdict.category == "searchable":
        card = agents.searchable_card(verdict)  # no model call needed
    else:
        try:
            # Give the redirect agent only the real question, never the injected instructions.
            clean = agents.strip_injection(prompt) if injection_flag else prompt
            card, redirect_usage = await agents.run_redirect(clean or prompt, verdict)
        except Exception:
            card = agents.fallback_card(verdict.category, verdict.search_query)
    # A fresh, verbatim research quote on every redirect card (rotates; least-shown first).
    card["quote"] = next(iter(sources.pick_quotes(verdict.category, 1)), None)
    log("redirect", verdict.category, verdict.reason, usage_numbers(gate_usage, redirect_usage), cache_hit, verdict.subtype)
    return {**base, "decision": "redirect", "category": verdict.category, "verdict": verdict_dict,
            "card": card, "injection_attempt": verdict.injection_attempt or injection_flag}


# --- routes --------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_NAME, "key_loaded": bool(PORTKEY_API_KEY)}


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    """New name: create the account and hand out its private code. Existing name: the code is required."""
    username = clean_username(body.username)
    code = body.code.strip().upper()
    if db.user_exists(username) and db.user_code(username):
        if not code or not secrets.compare_digest(db.user_code(username), code):
            raise HTTPException(403, "That username is taken. Enter its sign-in code, or pick a different name.")
        return {"username": username, "code": code, "new": False}
    if not db.user_exists(username):
        ip, window = client_ip(request), _new_accounts[client_ip(request)]
        while window and time.time() - window[0] > 3600:
            window.popleft()
        if len(window) >= NEW_ACCOUNTS_PER_IP_PER_HOUR:
            raise HTTPException(429, "Too many new accounts from this network in the last hour.")
        window.append(time.time())
    db.ensure_user(username)
    code = new_code()  # also covers accounts made before sign-in codes existed
    db.set_user_code(username, code)
    return {"username": username, "code": code, "new": True}


@app.post("/api/check")
async def check(body: PromptIn, x_human_first_code: str = Header(default="")):
    username = authed(body.username, x_human_first_code)
    return await decide(username, body.prompt, body.source)


def record_override(username: str, prompt: str, source: str) -> dict:
    """The user saw the citations and chose to ask AI anyway. Respect it, and count it."""
    fp = footprint_payload(prompt)
    c = fp["range"]["central"]
    event_id = db.add_event(username=username, source=source, prompt=prompt[:MAX_PROMPT_CHARS],
                            decision="override", category="override", reason="User chose to ask AI anyway",
                            ai_kwh=c["kwh"], ai_gallons=c["gallons"])
    return {"ok": True, "footprint": fp, "event_id": event_id}


@app.post("/api/override")
def override(body: PromptIn, x_human_first_code: str = Header(default="")):
    username = authed(body.username, x_human_first_code)
    return record_override(username, body.prompt, body.source)


@app.post("/api/chat")
async def chat(body: PromptIn, x_human_first_code: str = Header(default="")):
    """Web test chat: the same gate as the extension, then a stand-in model answers allowed prompts."""
    username = authed(body.username, x_human_first_code)
    if body.override:
        budget_guard(username)
        result = record_override(username, body.prompt, "web")
        result["decision"] = "override"
    else:
        result = await decide(username, body.prompt, "web")
    if result["decision"] in ("allow", "override"):
        try:
            answer, usage = await agents.run_answer(body.prompt)
            result["answer"] = answer
            result["answer_usage"] = usage_numbers(usage)
            if result.get("event_id"):  # stand-in answers count toward the daily spending caps
                db.add_answer_tokens(result["event_id"], usage.input_tokens or 0, usage.output_tokens or 0)
        except Exception as exc:
            result["answer"] = f"(The stand-in model could not answer: {type(exc).__name__})"
        result["answered_by"] = MODEL_NAME
    return result


def user_stats(username: str) -> dict:
    t = db.user_totals(username)
    return {
        "username": username,
        "totals": t,
        # Lifetime "used" includes Human First's own checking, not just the prompts sent to Claude.
        "used": describe(t["ai_kwh"] + t["gate_kwh"], t["ai_gallons"] + t["gate_gallons"]),
        "used_by_claude": describe(t["ai_kwh"], t["ai_gallons"]),
        "saved": describe(t["saved_kwh"], t["saved_gallons"]),
        "gatekeeper": describe(t["gate_kwh"], t["gate_gallons"]),
        "categories": db.category_counts(username),
        "events": db.user_events(username),
    }


@app.get("/api/stats")
def stats(username: str, x_human_first_code: str = Header(default="")):
    return user_stats(authed(username, x_human_first_code))


@app.post("/api/feedback")
def feedback(body: FeedbackIn, x_human_first_code: str = Header(default="")):
    username = authed(body.username, x_human_first_code)
    if db.feedback_count_last_hour(username) >= 5:
        raise HTTPException(429, "Thanks! You've sent a lot of feedback this hour. Please try again later.")
    db.add_feedback(username, body.rating, body.keep_using, body.comment.strip(), body.page)
    return {"ok": True}


@app.get("/api/citations")
def citations():
    """Live sources (pinned + approved), for the How it works page."""
    return [s for s in sources.list_sources() if s["status"] in ("pinned", "approved")]


# --- research sources (owner review) -----------------------------------------
# These change what every user sees (or show everyone's feedback), so they need the owner:
# either a request from the computer running the server, or the ADMIN_PASSWORD on a hosted copy.

def local_only(request: Request) -> None:
    pw = request.headers.get("x-admin-password", "")
    if ADMIN_PASSWORD and pw and secrets.compare_digest(pw, ADMIN_PASSWORD):
        return
    behind_proxy = "x-forwarded-for" in request.headers
    if not behind_proxy and request.client and request.client.host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return
    raise HTTPException(403, "Admin only. Enter the admin password.")


@app.get("/api/feedback")
def list_feedback(request: Request):
    local_only(request)
    return {"feedback": db.all_feedback()}


@app.get("/api/sources")
def list_sources(request: Request):
    local_only(request)
    return {"sources": sources.list_sources(), "runs": sources.research_runs()}


@app.post("/api/sources/{source_id}/{action}")
def review_source(source_id: int, action: str, request: Request):
    local_only(request)
    status = {"approve": "approved", "reject": "rejected"}.get(action)
    if not status or not sources.set_status(source_id, status):
        raise HTTPException(400, "Unknown source or action.")
    return {"ok": True, "status": status}


@app.post("/api/quotes/{quote_id}/remove")
def remove_quote(quote_id: int, request: Request):
    local_only(request)
    if not sources.remove_quote(quote_id):
        raise HTTPException(400, "Unknown quote, or a pinned quote (those stay).")
    return {"ok": True}


@app.post("/api/research/refresh")
async def research_now(request: Request):
    local_only(request)
    return await sources.refresh("manual", force=True)


@app.get("/api/tokenomics")
def tokenomics():
    rows = [r for r in db.all_token_stats() if r["model_calls"] > 0]
    by = {}
    for r in rows:
        key = r["decision"]
        b = by.setdefault(key, {"runs": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0,
                                "model_calls": 0, "latency_ms": 0})
        b["runs"] += 1
        for k in ("input_tokens", "cached_tokens", "output_tokens", "model_calls", "latency_ms"):
            b[k] += r[k]
    for b in by.values():
        n = b["runs"]
        b.update({f"avg_{k}": round(b[k] / n, 1) for k in ("input_tokens", "cached_tokens", "output_tokens", "model_calls", "latency_ms")})
    all_rows = db.all_token_stats()
    return {"by_decision": by, "total_checks": len(all_rows),
            "checks_without_model": sum(1 for r in all_rows if r["model_calls"] == 0)}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


EXTENSION_DIR = Path(__file__).resolve().parent.parent / "extension"
SERVER_RE = re.compile(r"^(https://[a-z0-9-]+\.hf\.space|http://(127\.0\.0\.1|localhost):8787)$", re.I)


@app.get("/extension.zip")
def extension_zip(request: Request):
    """The Chrome extension, pre-set to talk to whichever Human First server you downloaded it from."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    server = f"{proto}://{host}"
    if not SERVER_RE.match(server):
        server = "http://127.0.0.1:8787"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(EXTENSION_DIR.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                if path.name in ("background.js", "popup.js"):
                    data = data.replace(b'const DEFAULT_SERVER = "http://127.0.0.1:8787";',
                                        f'const DEFAULT_SERVER = "{server}";'.encode())
                z.writestr(f"human-first-extension/{path.relative_to(EXTENSION_DIR)}", data)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="human-first-extension.zip"'})


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    if not PORTKEY_API_KEY:
        print("WARNING: PORTKEY_API_KEY not found in .env (repo folder or the folder above). "
              "Prompts will be sent through unchecked.")
    print(f"Human First running at http://{HOST}:{PORT}  (model: {MODEL_NAME})")
    # reload=False: one process, so an edit never spawns a second server.
    uvicorn.run(app, host=HOST, port=PORT, reload=False, log_level="warning")
