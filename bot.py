#!/usr/bin/env python3
"""
Simple Educational Trading Bot
Strategy: SMA Crossover
Default: Paper Trading (simulation)
"""

import time
import pandas as pd
from datetime import datetime
import ccxt

from config import *


def create_exchange():
    params = {
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "spot"},
    }
    if PAPER_TRADING:
        print("[PAPER] Running in Paper Trading mode (simulation)")
        exchange = ccxt.binance(params)
    else:
        if not API_KEY or not API_SECRET:
            raise ValueError("API_KEY and API_SECRET required for real trading")
        print("[LIVE] REAL TRADING MODE - BE CAREFUL!")
        params["apiKey"] = API_KEY
        params["secret"] = API_SECRET
        exchange = ccxt.binance(params)
    return exchange


def fetch_ohlcv(exchange, symbol, timeframe, limit=100, retries=3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not ohlcv:
                raise ccxt.NetworkError("empty klines response")
            df = pd.DataFrame(
                ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
        except Exception as e:
            last_error = e
            wait = 2 * attempt
            print(f"  [WARN] klines attempt {attempt}/{retries} failed: {type(e).__name__}. retry in {wait}s")
            time.sleep(wait)
    raise last_error


def fetch_last_price(exchange, symbol):
    ticker = exchange.fetch_ticker(symbol)
    price = ticker.get("last") or ticker.get("close")
    if price is None:
        raise ValueError("ticker has no last price")
    return float(price)


def add_indicators(df):
    df = df.copy()
    df["sma_fast"] = df["close"].rolling(window=FAST_SMA).mean()
    df["sma_slow"] = df["close"].rolling(window=SLOW_SMA).mean()
    return df


def generate_signal(df):
    if len(df) < SLOW_SMA + 2:
        return None

    prev_fast = df["sma_fast"].iloc[-2]
    prev_slow = df["sma_slow"].iloc[-2]
    curr_fast = df["sma_fast"].iloc[-1]
    curr_slow = df["sma_slow"].iloc[-1]

    if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
        return None

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "BUY"
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "SELL"
    return None


def main():
    print("=" * 60)
    print("  Simple Educational Trading Bot")
    print("  Strategy: SMA Crossover")
    print("=" * 60)
    print(f"Symbol:      {SYMBOL}")
    print(f"Timeframe:   {TIMEFRAME}")
    print(f"Fast SMA:    {FAST_SMA}")
    print(f"Slow SMA:    {SLOW_SMA}")
    print(f"Paper mode:  {PAPER_TRADING}")
    print("=" * 60)
    print("Press Ctrl+C to stop\n")

    exchange = create_exchange()
    position = None
    entry_price = 0.0
    last_df = None

    while True:
        try:
            time_str = datetime.now().strftime("%H:%M:%S")
            signal = None

            try:
                df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME)
                df = add_indicators(df)
                last_df = df
                signal = generate_signal(df)
                price = float(df["close"].iloc[-1])
                fast = df["sma_fast"].iloc[-1]
                slow = df["sma_slow"].iloc[-1]
                fast_s = f"{fast:.2f}" if pd.notna(fast) else "n/a"
                slow_s = f"{slow:.2f}" if pd.notna(slow) else "n/a"
                print(f"[{time_str}] Price: {price:.2f} | FastSMA: {fast_s} | SlowSMA: {slow_s}")
            except Exception as e:
                print(f"[{time_str}] klines fail ({type(e).__name__}), trying ticker...")
                price = fetch_last_price(exchange, SYMBOL)
                if last_df is not None:
                    signal = generate_signal(last_df)
                print(f"[{time_str}] Price (ticker): {price:.2f} | SMA: last known")

            if signal == "BUY" and position is None:
                print(f"  >>> BUY SIGNAL at {price:.2f}")
                position = "long"
                entry_price = price
                mode = "PAPER" if PAPER_TRADING else "LIVE"
                print(f"  [{mode}] Opened LONG at {entry_price:.2f}")

            elif signal == "SELL" and position == "long":
                print(f"  >>> SELL SIGNAL at {price:.2f}")
                pnl_pct = (price - entry_price) / entry_price * 100
                print(f"  [PAPER] Closed LONG | PnL: {pnl_pct:+.2f}%")
                position = None
                entry_price = 0.0

            if position == "long" and entry_price > 0:
                change = (price - entry_price) / entry_price
                if change <= -STOP_LOSS_PCT:
                    print(f"  !!! STOP-LOSS triggered at {price:.2f} ({change*100:.2f}%)")
                    position = None
                    entry_price = 0.0
                elif change >= TAKE_PROFIT_PCT:
                    print(f"  $$$ TAKE-PROFIT triggered at {price:.2f} ({change*100:.2f}%)")
                    position = None
                    entry_price = 0.0

            time.sleep(30)

        except KeyboardInterrupt:
            print("\nBot stopped by user.")
            break
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
            print("  Check VPN / internet. Binance API must be reachable.")
            time.sleep(15)


if __name__ == "__main__":
    main()
