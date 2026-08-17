"""Version-tolerant parsing of yfinance responses.

yfinance's column layout has changed repeatedly across releases and also varies
with ``group_by``. Since 1.x, ``multi_level_index`` defaults to True, so even a
*single*-ticker download returns MultiIndex columns — which silently broke the
long-standing "flat frame when there's only one ticker" assumption throughout
this app and produced empty pages with no error anywhere.

Keeping the shape handling in one place means a future yfinance bump is a single
fix (and a failing unit test) rather than a hunt across every module that reads
market data.
"""

from __future__ import annotations

import pandas as pd

OHLC = ("Open", "High", "Low", "Close")


def extract_symbol_frame(raw, symbol: str):
    """Pull a flat OHLCV frame for ``symbol`` out of any yfinance response shape.

    Handles:

    * flat ``Open/High/Low/Close`` columns (older single-ticker responses)
    * MultiIndex with the ticker on level 0 (``group_by="ticker"``)
    * MultiIndex with the ticker on level 1 (``group_by="column"``)
    * single-ticker MultiIndex responses carrying only field names

    Returns a frame with plain OHLCV columns, or ``None`` when the symbol is not
    present or the response carries no recognizable price data.
    """
    if raw is None or getattr(raw, "empty", True):
        return None

    columns = raw.columns

    if not isinstance(columns, pd.MultiIndex):
        return raw if all(c in columns for c in OHLC) else None

    for level in range(columns.nlevels):
        if symbol in columns.get_level_values(level):
            frame = raw.xs(symbol, axis=1, level=level)
            if all(c in frame.columns for c in OHLC):
                return frame

    # A single-ticker MultiIndex whose remaining level is just the field names.
    if all(c in columns.get_level_values(0) for c in OHLC):
        frame = raw.copy()
        frame.columns = frame.columns.get_level_values(0)
        return frame

    return None
