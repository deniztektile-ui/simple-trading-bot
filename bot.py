#!/usr/bin/env python3
"""
Simple Educational Trading Bot
SMA crossover on CLOSED candles only + trend filter.
Paper trading by default. No profit guarantee.
"""

import time
import pandas as pd
from datetime import datetime
import ccxt

from config import *

START_BAL = float(globals().get("STARTING_BALANCE", POSITION_SIZE_USDT))
SIZE_USDT = float(POSITION_SIZE_USDT)


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


def fetch_ohlcv(exchange, symbol, timeframe, limit=120, retries=3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if not ohlcv or len(ohlcv) < 10:
                raise ccxt.NetworkError("empty/short klines response")
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


def closed_bars(df):
    """Drop the still-forming last candle so SMA does not flicker every 30s."""
    if len(df) < 3:
        return df
    return df.iloc[:-1].copy()


def generate_signal(df):
    if len(df) < SLOW_SMA + 3:
        return None

    prev_fast = df["sma_fast"].iloc[-2]
    prev_slow = df["sma_slow"].iloc[-2]
    curr_fast = df["sma_fast"].iloc[-1]
    curr_slow = df["sma_slow"].iloc[-1]
    close = df["close"].iloc[-1]

    if any(pd.isna(x) for x in (prev_fast, prev_slow, curr_fast, curr_slow, close)):
        return None

    # Golden cross AND price above slow SMA (uptrend filter)
    if prev_fast <= prev_slow and curr_fast > curr_slow and close > curr_slow:
        return "BUY"
    # Death cross
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "SELL"
    return None


def equity(balance, position, entry_price, price):
    if position == "long" and entry_price > 0 and price:
        return balance + SIZE_USDT * ((price - entry_price) / entry_price)
    return balance


def print_summary(start, balance, position, entry_price, price, trades):
    eq = equity(balance, position, entry_price, price) if price else balance
    pnl = eq - start
    print("\n" + "=" * 60)
    print("  ITOG")
    print("=" * 60)
    print(f"  Bylo:     {start:.2f} USDT")
    print(f"  Stalo:    {eq:.2f} USDT")
    print(f"  PnL:      {pnl:+.2f} USDT ({(pnl / start * 100) if start else 0:+.2f}%)")
    print(f"  Sdelok:   {trades}")
    if position == "long":
        print(f"  Open LONG entry={entry_price:.2f} (ne zakryt)")
    print("=" * 60)


def main():
    print("=" * 60)
    print("  Simple Educational Trading Bot")
    print("  Closed-candle SMA + trend filter")
    print("  Profit NOT guaranteed")
    print("=" * 60)
    print(f"Symbol:      {SYMBOL}")
    print(f"Timeframe:   {TIMEFRAME}")
    print(f"Fast SMA:    {FAST_SMA}")
    print(f"Slow SMA:    {SLOW_SMA}")
    print(f"Paper mode:  {PAPER_TRADING}")
    print(f"Start:       {START_BAL:.2f} USDT")
    print(f"Size/trade:  {SIZE_USDT:.2f} USDT")
    print("=" * 60)
    print("Press Ctrl+C to stop\n")

    exchange = create_exchange()
    position = None
    entry_price = 0.0
    last_df = None
    balance = START_BAL
    trades = 0
    last_price = None
    last_signal_ts = None

    while True:
        try:
            time_str = datetime.now().strftime("%H:%M:%S")
            signal = None
            price = None
            bar_ts = None
            fast_s, slow_s = "n/a", "n/a"

            try:
                raw = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME)
                raw = add_indicators(raw)
                df = closed_bars(raw)
                last_df = df
                signal = generate_signal(df)
                price = float(raw["close"].iloc[-1])  # live price for SL/TP
                last_price = price
                fast = df["sma_fast"].iloc[-1]
                slow = df["sma_slow"].iloc[-1]
                bar_ts = df["timestamp"].iloc[-1]
                fast_s = f"{fast:.2f}" if pd.notna(fast) else "n/a"
                slow_s = f"{slow:.2f}" if pd.notna(slow) else "n/a"
            except Exception as e:
                print(f"[{time_str}] klines fail ({type(e).__name__}), trying ticker...")
                price = fetch_last_price(exchange, SYMBOL)
                last_price = price
                if last_df is not None:
                    signal = generate_signal(last_df)
                    bar_ts = last_df["timestamp"].iloc[-1]
                fast_s, slow_s = "last", "last"

            eq = equity(balance, position, entry_price, price)
            pos = "LONG" if position == "long" else "FLAT"
            print(
                f"[{time_str}] Price: {price:.2f} | FastSMA: {fast_s} | SlowSMA: {slow_s} "
                f"| {pos} | Bal: {eq:.2f} USDT ({eq - START_BAL:+.2f})"
            )

            same_bar = bar_ts is not None and last_signal_ts is not None and bar_ts == last_signal_ts

            if signal == "BUY" and position is None and not same_bar:
                print(f"  >>> BUY (closed bar) at {price:.2f}")
                position = "long"
                entry_price = price
                last_signal_ts = bar_ts
                mode = "PAPER" if PAPER_TRADING else "LIVE"
                print(f"  [{mode}] Opened LONG {SIZE_USDT:.2f} USDT at {entry_price:.2f}")

            elif signal == "SELL" and position == "long" and not same_bar:
                pnl_pct = (price - entry_price) / entry_price
                pnl_usdt = SIZE_USDT * pnl_pct
                balance += pnl_usdt
                trades += 1
                last_signal_ts = bar_ts
                print(f"  >>> SELL (closed bar) at {price:.2f}")
                print(f"  Closed LONG | PnL: {pnl_usdt:+.2f} USDT ({pnl_pct*100:+.2f}%) | Bal: {balance:.2f}")
                position = None
                entry_price = 0.0

            if position == "long" and entry_price > 0 and price:
                change = (price - entry_price) / entry_price
                if change <= -STOP_LOSS_PCT:
                    pnl_usdt = SIZE_USDT * change
                    balance += pnl_usdt
                    trades += 1
                    print(f"  !!! STOP-LOSS at {price:.2f} ({change*100:.2f}%) | {pnl_usdt:+.2f} USDT | Bal: {balance:.2f}")
                    position = None
                    entry_price = 0.0
                elif change >= TAKE_PROFIT_PCT:
                    pnl_usdt = SIZE_USDT * change
                    balance += pnl_usdt
                    trades += 1
                    print(f"  $$$ TAKE-PROFIT at {price:.2f} ({change*100:.2f}%) | {pnl_usdt:+.2f} USDT | Bal: {balance:.2f}")
                    position = None
                    entry_price = 0.0

            time.sleep(30)

        except KeyboardInterrupt:
            print_summary(START_BAL, balance, position, entry_price, last_price, trades)
            print("Bot stopped by user.")
            break
        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")
            print("  Check VPN / internet. Binance API must be reachable.")
            time.sleep(15)


if __name__ == "__main__":
    main()
