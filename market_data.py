"""Загрузка свечей с Binance напрямую (публичные данные, ключи не нужны)."""
from __future__ import annotations

import time

import pandas as pd
import requests

URLS = [
    "https://api.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",  # запасной адрес Binance
]

TF_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
         "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "1d": 86_400_000}


def _get(params: dict) -> list:
    last_err = None
    for url in URLS:
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # пробуем следующий адрес
            last_err = e
    raise RuntimeError(f"Не удалось получить цены с Binance: {last_err}")


def _to_df(rows: list) -> pd.DataFrame:
    df = pd.DataFrame([r[:6] for r in rows], columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.astype({"ts": "int64", "open": float, "high": float, "low": float, "close": float, "volume": float})
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M")
    return df


def fetch_candles(symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    """Последние свечи. symbol вида 'BTC/USDT'."""
    return _to_df(_get({"symbol": symbol.replace("/", ""), "interval": timeframe, "limit": min(limit, 1000)}))


def fetch_history(symbol: str, timeframe: str, days: int) -> pd.DataFrame:
    """История за N дней (кусками по 1000 свечей)."""
    step = TF_MS[timeframe]
    now = int(time.time() * 1000)
    since = now - days * 86_400_000
    rows = []
    while since < now - step:
        batch = _get({"symbol": symbol.replace("/", ""), "interval": timeframe, "startTime": since, "limit": 1000})
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + step
    return _to_df(rows)
