"""Стратегия: пересечение быстрой и медленной скользящих средних (SMA).

BUY  — быстрая SMA пересекла медленную снизу вверх.
SELL — быстрая SMA пересекла медленную сверху вниз.
HOLD — пересечения нет.
"""
import pandas as pd


def add_indicators(df: pd.DataFrame, fast: int, slow: int, rsi_period: int = 14) -> pd.DataFrame:
    df = df.copy()
    df["sma_fast"] = df["close"].rolling(fast).mean()
    df["sma_slow"] = df["close"].rolling(slow).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / rsi_period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    df["rsi"] = (100 - 100 / (1 + rs)).fillna(100)
    return df


def signal_at(df: pd.DataFrame, i: int) -> str:
    """Сигнал на закрытой свече с индексом i (по позиции)."""
    if i < 1:
        return "HOLD"
    f_now, s_now = df["sma_fast"].iloc[i], df["sma_slow"].iloc[i]
    f_prev, s_prev = df["sma_fast"].iloc[i - 1], df["sma_slow"].iloc[i - 1]
    if pd.isna(s_prev) or pd.isna(s_now):
        return "HOLD"
    if f_prev <= s_prev and f_now > s_now:
        return "BUY"
    if f_prev >= s_prev and f_now < s_now:
        return "SELL"
    return "HOLD"


def market_snapshot(df: pd.DataFrame, i: int, last_n: int = 20) -> dict:
    """Короткое описание рынка для совета ИИ."""
    window = df.iloc[max(0, i - last_n + 1): i + 1]
    row = df.iloc[i]
    return {
        "price": round(float(row["close"]), 2),
        "sma_fast": round(float(row["sma_fast"]), 2),
        "sma_slow": round(float(row["sma_slow"]), 2),
        "rsi": round(float(row["rsi"]), 1),
        "change_last_n_pct": round((float(window["close"].iloc[-1]) / float(window["close"].iloc[0]) - 1) * 100, 3),
        "last_closes": [round(float(x), 2) for x in window["close"].tolist()],
    }
