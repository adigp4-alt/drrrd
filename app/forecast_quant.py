"""Quantitative next-session forecast engine.

Produces a calibrated probability distribution for the next trading session's
return from OHLCV history alone — no language model involved. This is the prior
that :mod:`app.forecast_engine` blends the catalyst overlay into.

The model is a location-scale Student-t on the next session's log return:

    r ~ mu + s * t(nu)

* ``sigma`` (the scale of the distribution) comes from a blend of the Yang-Zhang
  range estimator and an EWMA of squared returns. Yang-Zhang uses the full OHLC
  bar and is minimum-variance among drift-independent estimators, so it needs
  far less history than close-to-close for the same precision; EWMA reacts
  faster to a volatility regime change. Blending covers both.
* ``mu`` (the drift) is a heavily shrunk composite of momentum, trend, short-term
  reversal and moving-average displacement. Daily equity drift is almost pure
  noise, so the composite is clipped and scaled such that it can never move
  P(up) more than a few points away from a coin flip. A model that claims a 75%
  edge on tomorrow's candle is lying; this one is built so it cannot.
* ``nu`` is fixed at 4 degrees of freedom. Daily equity returns have fat tails,
  and a Gaussian materially understates the odds of a large move.

Everything here is pure Python + the standard library so the maths stays unit
testable without pulling scipy into the import path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field

# Degrees of freedom for the return distribution. Empirically daily equity
# returns sit around 3-5; 4 keeps the variance finite (defined for nu > 2).
T_DOF = 4.0

# RiskMetrics decay factor for the EWMA variance recursion.
EWMA_LAMBDA = 0.94

# Weight on the Yang-Zhang estimator when blending it with EWMA.
YZ_WEIGHT = 0.6

# Caps the drift composite before it is scaled into a return. See module docstring.
MAX_COMPOSITE_Z = 3.0

# Fraction of a standard deviation the composite may express as drift. At the
# cap this yields |mu| = 0.18 * sigma, i.e. P(up) in roughly [0.43, 0.57].
DRIFT_SHRINK = 0.06

# Below this fraction of the maximum expressible edge, the honest call is
# "no edge" — a doji. DOJI_ABS_RATIO is the same threshold as a plain
# |expected move| / sigma ratio, which is what callers actually compare against.
DOJI_EDGE_RATIO = 0.35
DOJI_ABS_RATIO = DOJI_EDGE_RATIO * DRIFT_SHRINK * MAX_COMPOSITE_Z

TRADING_DAYS = 252

# Minimum bars required before the engine will produce a forecast at all.
MIN_BARS = 60


@dataclass
class QuantForecast:
    """A next-session distribution plus the signals that produced it."""

    ticker: str
    asof_date: str
    ref_close: float
    p_up: float
    direction: str
    expected_move_pct: float
    sigma_pct: float
    band_68_pct: float
    band_95_pct: float
    conviction: int
    annualized_vol_pct: float
    vol_regime: str
    vol_percentile: float
    signals: dict = field(default_factory=dict)
    bars_used: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Student-t distribution (implemented locally to avoid a scipy dependency)
# ---------------------------------------------------------------------------


def _betacf(a: float, b: float, x: float) -> float:
    """Continued-fraction expansion for the incomplete beta function."""
    max_iter, eps, tiny = 300, 3.0e-16, 1.0e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta ``I_x(a, b)``."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_cdf(t: float, dof: float = T_DOF) -> float:
    """P(T <= t) for a standard Student-t with ``dof`` degrees of freedom."""
    x = dof / (dof + t * t)
    tail = 0.5 * regularized_incomplete_beta(dof / 2.0, 0.5, x)
    return 1.0 - tail if t > 0 else tail


def student_t_ppf(p: float, dof: float = T_DOF) -> float:
    """Inverse CDF by bisection. Accurate to ~1e-9 and fast enough here."""
    p = min(max(p, 1e-12), 1.0 - 1e-12)
    lo, hi = -1.0e3, 1.0e3
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if student_t_cdf(mid, dof) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def t_scale_for_sigma(sigma: float, dof: float = T_DOF) -> float:
    """Scale ``s`` such that ``s * t(dof)`` has standard deviation ``sigma``."""
    if dof <= 2.0:
        return sigma
    return sigma * math.sqrt((dof - 2.0) / dof)


# ---------------------------------------------------------------------------
# Volatility estimators
# ---------------------------------------------------------------------------


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def yang_zhang_volatility(bars: list[dict], window: int = 30) -> float | None:
    """Yang-Zhang per-session volatility estimate.

    Combines overnight-gap variance, open-to-close variance and the
    Rogers-Satchell drift-independent range term. Returns a daily standard
    deviation of log returns, or ``None`` when there are too few clean bars.
    """
    usable = bars[-(window + 1):]
    if len(usable) < 12:
        return None

    overnight, open_close, rogers_satchell = [], [], []
    for prev, cur in zip(usable, usable[1:]):
        o, h, low, c = cur["open"], cur["high"], cur["low"], cur["close"]
        prev_close = prev["close"]
        if min(o, h, low, c, prev_close) <= 0:
            continue
        # A bar whose high/low bracket is degenerate carries no range signal.
        if h < max(o, c) or low > min(o, c):
            continue
        overnight.append(math.log(o / prev_close))
        open_close.append(math.log(c / o))
        u, d, cc = math.log(h / o), math.log(low / o), math.log(c / o)
        rogers_satchell.append(u * (u - cc) + d * (d - cc))

    n = len(overnight)
    if n < 10:
        return None

    mean_o, mean_c = _mean(overnight), _mean(open_close)
    var_overnight = sum((x - mean_o) ** 2 for x in overnight) / (n - 1)
    var_open_close = sum((x - mean_c) ** 2 for x in open_close) / (n - 1)
    var_rs = sum(rogers_satchell) / n

    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    variance = var_overnight + k * var_open_close + (1.0 - k) * var_rs
    return math.sqrt(variance) if variance > 0 else None


def ewma_volatility(log_returns: list[float], lam: float = EWMA_LAMBDA) -> float | None:
    """RiskMetrics EWMA volatility, seeded on the first 20 observations."""
    if len(log_returns) < 20:
        return None
    seed = log_returns[:20]
    variance = sum(r * r for r in seed) / len(seed)
    for r in log_returns[20:]:
        variance = lam * variance + (1.0 - lam) * r * r
    return math.sqrt(variance) if variance > 0 else None


def _rolling_realized_vol(log_returns: list[float], window: int = 20) -> list[float]:
    out = []
    for i in range(window, len(log_returns) + 1):
        chunk = log_returns[i - window:i]
        m = _mean(chunk)
        var = sum((r - m) ** 2 for r in chunk) / (window - 1)
        out.append(math.sqrt(var))
    return out


def _percentile_rank(values: list[float], target: float) -> float:
    if not values:
        return 0.5
    below = sum(1 for v in values if v <= target)
    return below / len(values)


# ---------------------------------------------------------------------------
# Directional signals
# ---------------------------------------------------------------------------


def _ols_slope(ys: list[float]) -> float:
    """Least-squares slope of ``ys`` against 0..n-1."""
    n = len(ys)
    if n < 3:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = _mean(ys)
    num = sum((i - mean_x) * (y - mean_y) for i, y in enumerate(ys))
    den = sum((i - mean_x) ** 2 for i in range(n))
    return num / den if den else 0.0


def _clip(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def directional_signals(bars: list[dict], sigma_daily: float) -> dict:
    """Per-signal z-scores, each expressed in daily-volatility units.

    Every signal is normalised by the volatility over its own lookback so they
    are directly comparable and can be averaged without one dominating simply
    because it looks at a longer window.
    """
    closes = [b["close"] for b in bars]
    volumes = [b.get("volume") or 0 for b in bars]
    log_closes = [math.log(c) for c in closes if c > 0]

    if sigma_daily <= 0 or len(log_closes) < 25:
        return {"momentum": 0.0, "trend": 0.0, "reversal": 0.0, "ma_gap": 0.0,
                "volume_ratio": 1.0}

    # 12-day momentum, skipping the most recent session to sidestep the
    # short-horizon reversal effect that the reversal signal handles instead.
    mom_window = 12
    mom = log_closes[-2] - log_closes[-2 - mom_window]
    momentum_z = mom / (sigma_daily * math.sqrt(mom_window))

    # Slope of log price over 20 sessions, converted to a per-day drift z.
    slope = _ols_slope(log_closes[-20:])
    trend_z = slope / sigma_daily

    # Short-term reversal: the last 2 sessions tend to partially give back.
    recent = log_closes[-1] - log_closes[-3]
    reversal_z = -recent / (sigma_daily * math.sqrt(2))

    # Displacement from the 20-day mean, a mean-reversion pressure term.
    sma20 = _mean(log_closes[-20:])
    ma_gap_z = -(log_closes[-1] - sma20) / (sigma_daily * math.sqrt(20))

    recent_vol = _mean(volumes[-5:]) if volumes else 0.0
    base_vol = _mean(volumes[-20:]) if volumes else 0.0
    volume_ratio = (recent_vol / base_vol) if base_vol > 0 else 1.0

    return {
        "momentum": round(_clip(momentum_z, -4, 4), 4),
        "trend": round(_clip(trend_z, -4, 4), 4),
        "reversal": round(_clip(reversal_z, -4, 4), 4),
        "ma_gap": round(_clip(ma_gap_z, -4, 4), 4),
        "volume_ratio": round(_clip(volume_ratio, 0.1, 5.0), 3),
    }


# Signal weights. Momentum and trend are the two effects with the most
# out-of-sample support at a daily horizon, so they carry the most weight;
# the two mean-reversion terms are correlated with each other and share the rest.
SIGNAL_WEIGHTS = {
    "momentum": 0.35,
    "trend": 0.30,
    "reversal": 0.20,
    "ma_gap": 0.15,
}


def _composite_z(signals: dict) -> float:
    raw = sum(signals.get(name, 0.0) * weight for name, weight in SIGNAL_WEIGHTS.items())
    return _clip(raw, -MAX_COMPOSITE_Z, MAX_COMPOSITE_Z)


def signal_agreement(signals: dict) -> float:
    """Fraction of directional signals that agree with the composite, 0.5-1.0."""
    values = [signals.get(name, 0.0) for name in SIGNAL_WEIGHTS]
    active = [v for v in values if abs(v) > 0.05]
    if not active:
        return 0.5
    composite_sign = 1.0 if _composite_z(signals) >= 0 else -1.0
    agreeing = sum(1 for v in active if (1.0 if v >= 0 else -1.0) == composite_sign)
    return agreeing / len(active)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def forecast_next_session(ticker: str, bars: list[dict]) -> QuantForecast | None:
    """Build the next-session distribution for ``ticker`` from OHLCV ``bars``.

    ``bars`` must be chronologically ordered dicts with ``date``, ``open``,
    ``high``, ``low``, ``close`` and ``volume`` keys — the shape returned by
    :func:`app.data_fetcher.fetch_analysis_data`.
    """
    clean = [
        b for b in bars
        if b.get("close") and b.get("open") and b.get("high") and b.get("low")
        and b["close"] > 0 and b["open"] > 0
    ]
    if len(clean) < MIN_BARS:
        return None

    closes = [b["close"] for b in clean]
    log_returns = [
        math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0
    ]
    if len(log_returns) < 30:
        return None

    sigma_yz = yang_zhang_volatility(clean, window=30)
    sigma_ewma = ewma_volatility(log_returns)
    if sigma_yz and sigma_ewma:
        sigma = YZ_WEIGHT * sigma_yz + (1.0 - YZ_WEIGHT) * sigma_ewma
    else:
        sigma = sigma_yz or sigma_ewma
    if not sigma or sigma <= 0:
        return None

    # Thin history means the volatility estimate is itself uncertain. Widen the
    # distribution rather than pretending to a precision we do not have.
    if len(clean) < 120:
        sigma *= 1.0 + 0.25 * (120 - len(clean)) / 120

    signals = directional_signals(clean, sigma)
    composite = _composite_z(signals)
    mu = DRIFT_SHRINK * sigma * composite

    scale = t_scale_for_sigma(sigma)
    p_up = student_t_cdf(mu / scale) if scale > 0 else 0.5

    # Expected move is the distribution mean, which for a symmetric t is mu.
    expected_move = mu
    band_68 = student_t_ppf(0.84) * scale
    band_95 = student_t_ppf(0.975) * scale

    direction = classify_direction(expected_move, sigma)

    realized = _rolling_realized_vol(log_returns, window=20)
    current_realized = realized[-1] if realized else sigma
    vol_pct = _percentile_rank(realized[-TRADING_DAYS:], current_realized) if realized else 0.5
    if vol_pct >= 0.8:
        regime = "stressed"
    elif vol_pct <= 0.25:
        regime = "calm"
    else:
        regime = "normal"

    conviction = conviction_score(
        p_up=p_up,
        agreement=signal_agreement(signals),
        bars=len(clean),
        volume_ratio=signals.get("volume_ratio", 1.0),
        direction=direction,
    )

    return QuantForecast(
        ticker=ticker,
        asof_date=clean[-1]["date"],
        ref_close=round(closes[-1], 4),
        p_up=round(p_up, 4),
        direction=direction,
        expected_move_pct=round(expected_move * 100, 3),
        sigma_pct=round(sigma * 100, 3),
        band_68_pct=round(band_68 * 100, 3),
        band_95_pct=round(band_95 * 100, 3),
        conviction=conviction,
        annualized_vol_pct=round(sigma * math.sqrt(TRADING_DAYS) * 100, 2),
        vol_regime=regime,
        vol_percentile=round(vol_pct, 3),
        signals=signals,
        bars_used=len(clean),
    )


def classify_direction(expected_move: float, sigma: float) -> str:
    """Call the candle, or admit there is no edge.

    Most next-session forecasts genuinely have no directional edge. Rather than
    round a 50.3% probability up to "bullish", anything inside the doji band is
    reported as exactly that: no call.
    """
    if sigma <= 0:
        return "doji"
    if abs(expected_move) / sigma < DOJI_ABS_RATIO:
        return "doji"
    return "bull" if expected_move > 0 else "bear"


def conviction_score(p_up: float, agreement: float, bars: int, volume_ratio: float,
                     direction: str) -> int:
    """Map the forecast onto a 1-100 conviction score.

    Conviction is *not* the probability. It answers "how much should you trust
    this row", so it folds in how far the probability sits from a coin flip, how
    much the underlying signals agree, how much history backed the estimate, and
    whether volume is confirming. A doji is capped low by construction — the
    call itself is an admission of no edge.
    """
    edge = abs(p_up - 0.5) / 0.10          # 10pp of edge is a full score here
    edge_component = min(edge, 1.0)

    agreement_component = (agreement - 0.5) * 2.0     # 0.5->0, 1.0->1
    history_component = min(bars / 250.0, 1.0)
    volume_component = min(max((volume_ratio - 0.7) / 0.8, 0.0), 1.0)

    score = (
        0.45 * edge_component
        + 0.25 * agreement_component
        + 0.20 * history_component
        + 0.10 * volume_component
    )
    conviction = int(round(5 + 95 * min(max(score, 0.0), 1.0)))
    if direction == "doji":
        conviction = min(conviction, 35)
    return max(1, min(100, conviction))
