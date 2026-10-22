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

import difflib
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agents
import db
from citations import citations_for
from config import (
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

app = FastAPI(title="Human First")
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


class PromptIn(BaseModel):
    username: str
    prompt: str = Field(min_length=1)
    source: str = "web"
    override: bool = False


def check_username(username: str) -> str:
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        raise HTTPException(400, "Usernames are 2-40 letters, numbers, or . _ @ -")
    db.ensure_user(username)
    return username


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
    """Run one prompt through the full pipeline and log it."""
    budget_guard(username)
    started = time.perf_counter()
    prompt = prompt.strip()
    truncated = len(prompt) > MAX_PROMPT_CHARS
    fp = footprint_payload(prompt)
    central = fp["range"]["central"]

    def log(decision, category, reason, usage=None, cache_hit=False, subtype="") -> int:
        u = usage or {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "model_calls": 0}
        gate = gatekeeper_footprint(u["input_tokens"] + u["output_tokens"]) if u["model_calls"] else {"kwh": 0, "gallons": 0}
        sent = decision == "allow"
        return db.add_event(
            username=username, source=source, prompt=prompt[:MAX_PROMPT_CHARS], decision=decision,
            category=category, subtype=subtype, reason=reason,
            ai_kwh=central["kwh"] if sent else 0, ai_gallons=central["gallons"] if sent else 0,
            saved_kwh=0 if sent else central["kwh"], saved_gallons=0 if sent else central["gallons"],
            gate_kwh=gate["kwh"], gate_gallons=gate["gallons"],
            cache_hit=int(cache_hit), latency_ms=int((time.perf_counter() - started) * 1000), **u,
        )

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
                "earlier_prompt": earlier["prompt"], "citations": citations_for(earlier["category"])}

    # 3. Gatekeeper (with a shared cache so the same question is never classified twice).
    injection_flag = agents.injection_screen(prompt)
    verdict_dict = db.cached_verdict(prompt)
    gate_usage = None
    cache_hit = verdict_dict is not None
    if verdict_dict is None:
        try:
            verdict, gate_usage = await agents.run_gatekeeper(prompt, injection_flag)
        except agents.ContentFiltered:
            # Fail closed: the provider's filter would not even read it, so it is not sent to Claude.
            log("redirect", "filtered", "Provider safety filter refused the prompt", subtype="filtered")
            return {**base, "decision": "redirect", "category": "filtered", "injection_attempt": True,
                    "card": agents.FILTERED_CARD}
        except Exception as exc:  # model down, budget hit, bad output: fail open, say so
            log("allow", "unchecked", f"Gatekeeper error: {type(exc).__name__}")
            return {**base, "decision": "allow", "category": "unchecked",
                    "reason": "Human First couldn't check this prompt, so it was sent as usual.",
                    "error": type(exc).__name__}
        verdict_dict = verdict.model_dump()
        db.store_verdict(prompt, verdict_dict)
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
                "earlier_prompt": earlier["prompt"], "citations": citations_for(verdict.category)}

    # 5. Redirect card.
    redirect_usage = None
    if verdict.category == "searchable":
        card = agents.searchable_card(verdict)  # no model call needed
    else:
        try:
            card, redirect_usage = await agents.run_redirect(prompt, verdict)
        except Exception:
            card = agents.fallback_card(verdict.category, verdict.search_query)
    log("redirect", verdict.category, verdict.reason, usage_numbers(gate_usage, redirect_usage), cache_hit, verdict.subtype)
    return {**base, "decision": "redirect", "category": verdict.category, "verdict": verdict_dict,
            "card": card, "injection_attempt": verdict.injection_attempt or injection_flag}


# --- routes --------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL_NAME, "key_loaded": bool(PORTKEY_API_KEY)}


@app.post("/api/login")
def login(body: LoginIn):
    username = check_username(body.username)
    return {"username": username}


@app.post("/api/check")
async def check(body: PromptIn):
    username = check_username(body.username)
    return await decide(username, body.prompt, body.source)


@app.post("/api/override")
def override(body: PromptIn):
    """The user saw the citations and chose to ask AI anyway. Respect it, and count it."""
    username = check_username(body.username)
    fp = footprint_payload(body.prompt)
    c = fp["range"]["central"]
    db.add_event(username=username, source=body.source, prompt=body.prompt[:MAX_PROMPT_CHARS],
                 decision="override", category="override", reason="User chose to ask AI anyway",
                 ai_kwh=c["kwh"], ai_gallons=c["gallons"])
    return {"ok": True, "footprint": fp}


@app.post("/api/chat")
async def chat(body: PromptIn):
    """Web test chat: the same gate as the extension, then a stand-in model answers allowed prompts."""
    username = check_username(body.username)
    if body.override:
        result = override(body)
        result["decision"] = "override"
    else:
        result = await decide(username, body.prompt, "web")
    if result["decision"] in ("allow", "override"):
        try:
            answer, usage = await agents.run_answer(body.prompt)
            result["answer"] = answer
            result["answer_usage"] = usage_numbers(usage)
        except Exception as exc:
            result["answer"] = f"(The stand-in model could not answer: {type(exc).__name__})"
        result["answered_by"] = MODEL_NAME
    return result


@app.get("/api/stats")
def stats(username: str):
    username = check_username(username)
    t = db.user_totals(username)
    return {
        "username": username,
        "totals": t,
        "used": describe(t["ai_kwh"], t["ai_gallons"]),
        "saved": describe(t["saved_kwh"], t["saved_gallons"]),
        "gatekeeper": describe(t["gate_kwh"], t["gate_gallons"]),
        "categories": db.category_counts(username),
        "events": db.user_events(username),
    }


@app.get("/api/citations")
def citations():
    return citations_for("environment")


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
