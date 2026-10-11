"""Стратегия: пересечение быстрой и медленной скользящих средних (SMA) с фильтрами.

BUY  — быстрая SMA поднялась выше медленной с запасом (MIN_GAP_PCT), и при этом:
         * тренд достаточно сильный (ADX не ниже ADX_MIN) — не торгуем в «боковике»;
         * цена выше длинной средней (TREND_SMA) — покупаем только по общему росту.
SELL — быстрая SMA опустилась ниже медленной (выход из позиции, без фильтров).
HOLD — ничего не делаем.

Фильтры можно выключить: MIN_GAP_PCT = 0, ADX_MIN = 0, TREND_SMA = 0.
"""
from __future__ import annotations

import pandas as pd


def add_indicators(df: pd.DataFrame, fast: int, slow: int, rsi_period: int = 14,
                   trend: int = 0, adx_period: int = 14) -> pd.DataFrame:
    df = df.copy()
    close, high, low = df["close"], df["high"], df["low"]
    df["sma_fast"] = close.rolling(fast).mean()
    df["sma_slow"] = close.rolling(slow).mean()
    df["gap_pct"] = (df["sma_fast"] / df["sma_slow"] - 1) * 100
    df["sma_trend"] = close.rolling(trend).mean() if trend else float("nan")

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / rsi_period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    df["rsi"] = (100 - 100 / (1 + rs)).fillna(100)

    # ADX — сила тренда (0–100). Ниже ~20 обычно «боковик».
    up, down = high.diff(), -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    a = 1 / adx_period
    atr = tr.ewm(alpha=a, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=a, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    df["adx"] = dx.ewm(alpha=a, adjust=False).mean()
    df["atr_pct"] = atr / close * 100
    return df


def signal_at(df: pd.DataFrame, i: int, min_gap_pct: float = 0.0, adx_min: float = 0.0) -> str:
    """Сигнал на закрытой свече с индексом i (по позиции)."""
    if i < 1:
        return "HOLD"
    g_now, g_prev = df["gap_pct"].iloc[i], df["gap_pct"].iloc[i - 1]
    if pd.isna(g_now) or pd.isna(g_prev):
        return "HOLD"

    # Выход: быстрая средняя ушла под медленную
    if g_prev >= 0 and g_now < 0:
        return "SELL"

    # Вход: быстрая поднялась над медленной с запасом min_gap_pct
    crossed = (g_prev < min_gap_pct) if min_gap_pct > 0 else (g_prev <= 0)
    if crossed and g_now >= min_gap_pct and g_now > 0:
        row = df.iloc[i]
        if adx_min and not (row["adx"] >= adx_min):
            return "HOLD"          # слабый тренд / боковик
        if not pd.isna(row["sma_trend"]) and row["close"] < row["sma_trend"]:
            return "HOLD"          # общий тренд вниз — не покупаем
        return "BUY"
    return "HOLD"


def market_snapshot(df: pd.DataFrame, i: int, last_n: int = 20) -> dict:
    """Короткое описание рынка для совета ИИ."""
    window = df.iloc[max(0, i - last_n + 1): i + 1]
    row = df.iloc[i]

    def r(x, n=2):
        return None if pd.isna(x) else round(float(x), n)

    return {
        "price": r(row["close"]),
        "sma_fast": r(row["sma_fast"]),
        "sma_slow": r(row["sma_slow"]),
        "sma_trend": r(row["sma_trend"]),
        "rsi": r(row["rsi"], 1),
        "adx_trend_strength": r(row["adx"], 1),
        "atr_pct": r(row["atr_pct"], 3),
        "change_last_n_pct": round((float(window["close"].iloc[-1]) / float(window["close"].iloc[0]) - 1) * 100, 3),
        "last_closes": [round(float(x), 2) for x in window["close"].tolist()],
    }
