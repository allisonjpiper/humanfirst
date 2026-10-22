"""
config.py

Settings shared by the whole backend.

API keys are read from a .env file in two places, in this order:
  1. the repo folder itself            (Final Project/.env)
  2. the folder one level above it     (where the teaching staff keep theirs)
A key already found in step 1 is never overwritten by step 2.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent

load_dotenv(REPO_DIR / ".env")
load_dotenv(REPO_DIR.parent / ".env")

PORTKEY_API_KEY = os.environ.get("PORTKEY_API_KEY", "")
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# Course key: gpt-6-luna only.
MODEL_NAME = os.environ.get("HUMANFIRST_MODEL", "gpt-6-luna")

HOST = "127.0.0.1"
PORT = int(os.environ.get("HUMANFIRST_PORT") or os.environ.get("PORT") or 8787)

DB_PATH = Path(os.environ.get("HUMANFIRST_DB", REPO_DIR / "data" / "humanfirst.db"))

# --- Overspending guards -------------------------------------------------
MAX_PROMPT_CHARS = 4000            # longer prompts are truncated before the model sees them
USER_REQUESTS_PER_MINUTE = 12      # per signed-in user
USER_DAILY_TOKEN_BUDGET = 60_000   # gatekeeper + redirect tokens per user per day
GLOBAL_DAILY_TOKEN_BUDGET = 2_000_000

# How close a new prompt must be to an earlier blocked one to count as "asking again".
REPEAT_TEXT_SIMILARITY = 0.6
REPEAT_SAME_CATEGORY_MINUTES = 15
REPEAT_WORD_OVERLAP = 0.34  # rephrasings must also share about a third of their content words
