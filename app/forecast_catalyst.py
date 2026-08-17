"""Catalyst overlay: a bounded, model-driven adjustment to the quant prior.

The quantitative engine in :mod:`app.forecast_quant` reads price history and
nothing else, so it is structurally blind to anything that has not happened yet
— an earnings date, a Fed decision, a supply shock. This module fills that gap
by asking Claude to research current conditions and return a *bounded tilt* on
each ticker's prior.

Two properties matter more than anything else here:

1. **The overlay can never author a forecast.** It returns a shift in log-odds
   and a volatility multiplier, both clamped to narrow ranges. If the model
   returns nonsense, the worst it can do is nudge a probability by a few points.
   The numbers on the board always originate in market data.
2. **It is optional.** No API key, no network, a refusal, a malformed response —
   every failure path degrades to the pure quant forecast rather than raising.
   ``ANTHROPIC_API_KEY`` being unset is a supported configuration, not an error.

The API key is read from the server environment and never leaves this process.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"

# Bounds on what the overlay is allowed to do to the prior. A shift of 0.6 in
# log-odds moves a 50% probability to roughly 65%; that is the ceiling on the
# model's influence over direction, and it applies even to a screaming catalyst.
MAX_LOGIT_SHIFT = 0.6
MIN_VOL_MULTIPLIER = 0.7
MAX_VOL_MULTIPLIER = 1.8

# Research is expensive and changes slowly relative to a trading session.
RESEARCH_TTL_SECONDS = 30 * 60

_cache_lock = threading.Lock()
_research_cache: dict[str, tuple[float, str]] = {}


@dataclass
class CatalystTilt:
    """A bounded adjustment to one ticker's quant prior."""

    ticker: str
    logit_shift: float
    vol_multiplier: float
    rationale: str
    catalyst: str = ""

    @property
    def is_material(self) -> bool:
        return abs(self.logit_shift) > 0.02 or abs(self.vol_multiplier - 1.0) > 0.02


class CatalystUnavailable(RuntimeError):
    """Raised internally when the overlay cannot run; always caught by callers."""


def is_configured() -> bool:
    """True when an API key is present, so callers can advertise the feature."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _client():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on deployment
        raise CatalystUnavailable("anthropic SDK not installed") from exc
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise CatalystUnavailable("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic()


def _finish(stream):
    """Drain a stream and return the final message."""
    with stream as s:
        for _ in s:
            pass
        return s.get_final_message()


def _text_of(message) -> str:
    return "\n".join(b.text for b in message.content if b.type == "text").strip()


def _run_with_server_tools(client, **kwargs):
    """Call the API, resuming the turn if a server tool pauses it.

    A long web-search turn can stop with ``stop_reason: "pause_turn"``. Resuming
    means re-sending the conversation with the paused assistant turn appended;
    the server picks up where it left off.
    """
    messages = list(kwargs.pop("messages"))
    for _ in range(5):
        message = _finish(client.beta.messages.stream(messages=messages, **kwargs))
        if message.stop_reason == "refusal":
            raise CatalystUnavailable("request declined by safety classifiers")
        if message.stop_reason != "pause_turn":
            return message
        messages = messages + [{"role": "assistant", "content": message.content}]
    raise CatalystUnavailable("server tool turn did not settle")


RESEARCH_SYSTEM = (
    "You are a market research assistant supporting a quantitative forecasting "
    "desk. You gather and report current, verifiable market facts. You do not "
    "predict prices and you do not give investment advice — a separate "
    "statistical model owns the forecast. Report what is known, with numbers and "
    "dates, and say plainly when something is unknown or unconfirmed."
)


def _research(client, tickers: list[str], session_label: str) -> str:
    """One web-search pass over current conditions for the requested tickers."""
    prompt = (
        f"Today is {session_label}. Research current US market conditions and "
        f"near-term catalysts for these tickers: {', '.join(tickers)}.\n\n"
        "Cover, using dense bullets with numbers and dates:\n"
        "- Index and futures levels, VIX, rates, and the overall tape\n"
        "- Scheduled catalysts in the next 1-2 sessions: earnings dates, Fed and "
        "macro data releases, known company events\n"
        "- Per ticker: recent price action, fresh news, and any pending event\n"
        "- Anything that would widen or compress expected volatility\n\n"
        "State explicitly when a ticker has no notable catalyst — that is a "
        "useful finding, not a gap to fill. Do not forecast prices."
    )
    message = _run_with_server_tools(
        client,
        model=MODEL,
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=RESEARCH_SYSTEM,
        output_config={"effort": "high"},
        tools=[{"type": "web_search_20260209", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    return _text_of(message)


TILT_SCHEMA = {
    "type": "object",
    "properties": {
        "tilts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Ticker symbol."},
                    "logit_shift": {
                        "type": "number",
                        "description": (
                            "Adjustment to the log-odds of an up session, in "
                            "[-0.6, 0.6]. 0.0 means the research gives no reason "
                            "to disagree with the statistical prior, which is the "
                            "correct answer for most tickers on most days. Use "
                            "0.3+ only for a confirmed, dated, directional "
                            "catalyst."
                        ),
                    },
                    "vol_multiplier": {
                        "type": "number",
                        "description": (
                            "Multiplier on the expected move, in [0.7, 1.8]. Use "
                            ">1 when a known event (earnings, Fed, data print) "
                            "lands in the next session; 1.0 when nothing is "
                            "scheduled."
                        ),
                    },
                    "catalyst": {
                        "type": "string",
                        "description": (
                            "The specific dated event driving the adjustment, or "
                            "an empty string when there is none."
                        ),
                    },
                    "rationale": {
                        "type": "string",
                        "description": "One short sentence grounded in the research.",
                    },
                },
                "required": ["ticker", "logit_shift", "vol_multiplier", "catalyst",
                             "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tilts"],
    "additionalProperties": False,
}


TILT_SYSTEM = (
    "You convert market research into bounded adjustments for a statistical "
    "forecasting model. The model already prices trend, momentum and volatility "
    "from history; your only job is to account for information the price history "
    "cannot contain, such as a scheduled event. Returning zero adjustment is the "
    "expected outcome for a ticker with no dated catalyst, and is always "
    "preferable to inventing a reason to move a number."
)


def _structure(client, research: str, priors: list[dict]) -> list[CatalystTilt]:
    """Turn free-text research into one bounded tilt per ticker."""
    prior_lines = "\n".join(
        f"- {p['ticker']}: model says P(up)={p['p_up']:.3f}, "
        f"expected move {p['expected_move_pct']:+.2f}%, "
        f"1-sigma {p['sigma_pct']:.2f}%, vol regime {p['vol_regime']}"
        for p in priors
    )
    prompt = (
        "Statistical priors for the next session:\n"
        f"{prior_lines}\n\n"
        "Market research:\n"
        f"{research}\n\n"
        "For each ticker listed above, return the adjustment the research "
        "justifies. Most should be 0.0 with a 1.0 multiplier."
    )
    message = client.beta.messages.create(
        model=MODEL,
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=TILT_SYSTEM,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": TILT_SCHEMA},
        },
        messages=[{"role": "user", "content": prompt}],
    )
    if message.stop_reason == "refusal":
        raise CatalystUnavailable("structuring request declined")

    payload = json.loads(_text_of(message))
    tilts = []
    for row in payload.get("tilts", []):
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        tilts.append(
            CatalystTilt(
                ticker=ticker,
                logit_shift=_clamp(row.get("logit_shift"), -MAX_LOGIT_SHIFT,
                                   MAX_LOGIT_SHIFT, 0.0),
                vol_multiplier=_clamp(row.get("vol_multiplier"), MIN_VOL_MULTIPLIER,
                                      MAX_VOL_MULTIPLIER, 1.0),
                rationale=str(row.get("rationale", ""))[:280],
                catalyst=str(row.get("catalyst", ""))[:140],
            )
        )
    return tilts


def _clamp(value, low: float, high: float, default: float) -> float:
    """Coerce a model-supplied number into range, falling back to ``default``."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric != numeric:  # NaN
        return default
    return min(max(numeric, low), high)


def fetch_tilts(priors: list[dict], session_label: str,
                use_cache: bool = True) -> dict[str, CatalystTilt]:
    """Return ``{ticker: CatalystTilt}`` for the given priors.

    Returns an empty mapping on any failure — callers treat the overlay as a
    bonus, never a requirement.
    """
    if not priors:
        return {}

    tickers = [p["ticker"] for p in priors]
    try:
        client = _client()
    except CatalystUnavailable as exc:
        logger.info("Catalyst overlay unavailable (%s); using quant-only forecast", exc)
        return {}

    cache_key = hashlib.sha256(
        (session_label + "|" + ",".join(sorted(tickers))).encode()
    ).hexdigest()

    research = None
    if use_cache:
        with _cache_lock:
            hit = _research_cache.get(cache_key)
            if hit and time.time() - hit[0] < RESEARCH_TTL_SECONDS:
                research = hit[1]

    try:
        if research is None:
            research = _research(client, tickers, session_label)
            with _cache_lock:
                _research_cache[cache_key] = (time.time(), research)
        tilts = _structure(client, research, priors)
    except CatalystUnavailable as exc:
        logger.warning("Catalyst overlay skipped: %s", exc)
        return {}
    except Exception as exc:  # network, parse, SDK — all non-fatal by design
        logger.warning("Catalyst overlay failed (%s: %s)", type(exc).__name__, exc)
        return {}

    requested = set(tickers)
    return {t.ticker: t for t in tilts if t.ticker in requested}
