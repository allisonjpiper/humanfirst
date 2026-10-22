"""
footprint.py

Estimates the electricity (kWh) and water (gallons) one AI prompt uses, and
turns those numbers into everyday comparisons.

Anthropic does not publish per-prompt figures for Claude, so every number here
is an ESTIMATE built from public sources and shown as a low / central / high
range. The central estimate is what the app adds to a user's running total.

Sources
-------
Energy per text response
  LOW   0.24 Wh  Google, "Measuring the environmental impact of delivering AI at
                 Google scale" (Aug 2025): median Gemini Apps text prompt,
                 including idle machines, host CPU/RAM and cooling overhead.
  HIGH  1.86 Wh  MIT Technology Review, O'Donnell & Crownhart, "We did the math
                 on AI's energy footprint" (May 20, 2025): Llama 3.1 405B,
                 6,706 J per response. The closest public analog to a large
                 frontier model like Claude.
  CENTRAL        geometric mean of LOW and HIGH (~0.67 Wh).

Water per Wh
  ON-SITE   1.08 mL/Wh   Google (Aug 2025): 0.26 mL for a 0.24 Wh prompt
                         (data-center cooling only).
  TOTAL     x4           Harvard Salata Institute (2026) study of 472 U.S. data
                         centers: about three-quarters of operational water is
                         used generating the electricity, not cooling. So total
                         water is roughly 4x the on-site cooling water.

Longer prompts (pasted documents, long chats) cost more to process; we scale
the estimate by 1 + input_tokens / 2000.

Everyday comparisons
  Smartphone full charge     15 Wh    (about a 13 Wh battery plus charger losses)
  10 W LED bulb for 1 hour   10 Wh
  Average U.S. home, 1 day   29.6 kWh (EIA, 10,791 kWh per year in 2023)
  Teaspoon                   4.93 mL
  16.9 oz water bottle       500 mL
  Toilet flush               1.6 gal  (U.S. federal maximum)
  5-minute shower            10 gal   (2.0 gal/min WaterSense showerhead)
"""

from __future__ import annotations

import math

WH_LOW = 0.24
WH_HIGH = 1.86
WH_CENTRAL = math.sqrt(WH_LOW * WH_HIGH)

ONSITE_ML_PER_WH = 0.26 / 0.24
TOTAL_WATER_MULTIPLIER = 4.0

ML_PER_GALLON = 3785.41

ENERGY_COMPARISONS = [
    # (Wh, singular, plural)
    (29_600.0, "day of electricity for an average U.S. home", "days of electricity for an average U.S. home"),
    (15.0, "full smartphone charge", "full smartphone charges"),
    (10.0, "hour of a 10 W LED bulb", "hours of a 10 W LED bulb"),
]
WATER_COMPARISONS = [
    # (mL, singular, plural)
    (10 * ML_PER_GALLON, "5-minute shower", "5-minute showers"),
    (1.6 * ML_PER_GALLON, "toilet flush", "toilet flushes"),
    (500.0, "16.9 oz bottle of water", "16.9 oz bottles of water"),
    (4.93, "teaspoon of water", "teaspoons of water"),
]


def estimate_tokens(text: str) -> int:
    """Rough token count (about 4 characters per token) when we have no real count."""
    return max(1, math.ceil(len(text) / 4))


def prompt_footprint(input_tokens: int) -> dict:
    """Low / central / high footprint for one prompt sent to a large chat model like Claude."""
    scale = 1 + input_tokens / 2000
    out = {}
    for label, wh in (("low", WH_LOW), ("central", WH_CENTRAL), ("high", WH_HIGH)):
        energy_wh = wh * scale
        if label == "low":
            water_ml = energy_wh * ONSITE_ML_PER_WH  # Google's own on-site-only figure
        else:
            water_ml = energy_wh * ONSITE_ML_PER_WH * TOTAL_WATER_MULTIPLIER
        out[label] = {"kwh": energy_wh / 1000, "gallons": water_ml / ML_PER_GALLON}
    return out


def gatekeeper_footprint(total_tokens: int) -> dict:
    """Our own classifier's footprint, so the app is honest about what checking costs.

    A short classification call is closer to Google's efficient median prompt than
    to a long chat answer, so we use the LOW figure scaled by tokens (~1,000 per call).
    """
    energy_wh = WH_LOW * max(total_tokens, 1) / 1000
    water_ml = energy_wh * ONSITE_ML_PER_WH * TOTAL_WATER_MULTIPLIER
    return {"kwh": energy_wh / 1000, "gallons": water_ml / ML_PER_GALLON}


def _pick(amount: float, table: list[tuple[float, str, str]]) -> str:
    """Choose the comparison that gives the most readable number."""
    for unit, singular, plural in table:
        n = amount / unit
        if n >= 0.5:
            return _phrase(n, singular, plural)
    unit, singular, plural = table[-1]
    return _phrase(amount / unit, singular, plural)


def _phrase(n: float, singular: str, plural: str) -> str:
    if n >= 0.995 and round(n, 1) == 1.0:
        return f"about 1 {singular}"
    if n >= 10:
        return f"about {n:,.0f} {plural}"
    if n >= 1:
        return f"about {n:.1f} {plural}"
    pct = n * 100
    article = "an" if singular[0] in "aeiou" or singular.startswith("hour") else "a"
    if pct >= 1:
        return f"about {pct:.0f}% of {article} {singular}"
    return f"about {pct:.2f}% of {article} {singular}"


def compare_energy(kwh: float) -> str:
    return _pick(kwh * 1000, ENERGY_COMPARISONS)


def compare_water(gallons: float) -> str:
    return _pick(gallons * ML_PER_GALLON, WATER_COMPARISONS)


def describe(kwh: float, gallons: float) -> dict:
    return {
        "kwh": kwh,
        "gallons": gallons,
        "energy_comparison": compare_energy(kwh),
        "water_comparison": compare_water(gallons),
    }
