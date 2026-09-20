#!/usr/bin/env python3
"""
Simple Educational Trading Bot
Strategy: SMA Crossover
Default: Paper Trading (simulation)
"""

import time
import pandas as pd
import numpy as np
from datetime import datetime
import ccxt

from config import *

def create_exchange():
    if PAPER_TRADING:
        print("[PAPER] Running in Paper Trading mode (simulation)")
        exchange = ccxt.binance({
            "enableRateLimit": True,
        })
    else:
        if not API_KEY or not API_SECRET:
            raise ValueError("API_KEY and API_SECRET required for real trading")
        print("[LIVE] REAL TRADING MODE - BE CAREFUL!")
        exchange = ccxt.binance({
            "apiKey": API_KEY,
            "secret": API_SECRET,
            "enableRateLimit": True,
        })
    return exchange

def fetch_ohlcv(exchange, symbol, timeframe, limit=100):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df

def add_indicators(df):
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

    # Golden cross - Buy
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "BUY"
    # Death cross - Sell
    elif prev_fast >= prev_slow and curr_fast < curr_slow:
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
    position = None          # None / "long"
    entry_price = 0.0

    while True:
        try:
            df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME)
            df = add_indicators(df)
            signal = generate_signal(df)
            price = df["close"].iloc[-1]
            time_str = datetime.now().strftime("%H:%M:%S")

            print(f"[{time_str}] Price: {price:.2f} | FastSMA: {df['sma_fast'].iloc[-1]:.2f} | SlowSMA: {df['sma_slow'].iloc[-1]:.2f}")

            if signal == "BUY" and position is None:
                print(f"  >>> BUY SIGNAL at {price:.2f}")
                if PAPER_TRADING:
                    position = "long"
                    entry_price = price
                    print(f"  [PAPER] Opened LONG at {entry_price:.2f}")
                else:
                    # Real order would go here
                    print("  [LIVE] Would place market buy order")
                    position = "long"
                    entry_price = price

            elif signal == "SELL" and position == "long":
                print(f"  >>> SELL SIGNAL at {price:.2f}")
                pnl_pct = (price - entry_price) / entry_price * 100
                print(f"  [PAPER] Closed LONG | PnL: {pnl_pct:+.2f}%")
                position = None
                entry_price = 0.0

            # Simple stop-loss / take-profit in paper mode
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

            time.sleep(30)  # проверять каждые 30 секунд

        except KeyboardInterrupt:
            print("\nBot stopped by user.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
