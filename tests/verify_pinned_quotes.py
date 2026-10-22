"""
Re-check that every pinned quote still appears word-for-word on its source page (live HTTP).

    .venv/bin/python tests/verify_pinned_quotes.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import sources  # noqa: E402


async def main():
    bad = 0
    for s in sources.PINNED:
        text = await sources.fetch_text(s["verify_url"] or s["url"])
        if not text:
            print(f"UNREACHABLE  {s['outlet']}")
            bad += 1
            continue
        for quote, _ in s["quotes"]:
            ok = sources.quote_on_page(quote, text)
            bad += not ok
            print(f"{'OK ' if ok else 'XX '} {s['outlet']:28} {quote[:70]}")
    print("\nall verified" if not bad else f"\n{bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    asyncio.run(main())
