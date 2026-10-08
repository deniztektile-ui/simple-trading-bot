"""Проверка стратегии на истории (бэктест). Совет ИИ здесь не вызывается —
это было бы дорого; проверяется только сама стратегия со стопами и комиссиями.

Примеры:
  python backtest.py                    # последние 3 дня с Binance
  python backtest.py --days 7
  python backtest.py --csv data.csv     # свои данные: колонки time,open,high,low,close
"""
import argparse

import pandas as pd

import config
from paper_broker import PaperBroker
from strategy import add_indicators, signal_at


def download(days: int) -> pd.DataFrame:
    import ccxt
    ex = getattr(ccxt, config.EXCHANGE)({"enableRateLimit": True})
    ms = ex.parse_timeframe(config.TIMEFRAME) * 1000
    since = ex.milliseconds() - days * 24 * 3600 * 1000
    rows = []
    while since < ex.milliseconds() - ms:
        batch = ex.fetch_ohlcv(config.SYMBOL, config.TIMEFRAME, since=since, limit=1000)
        if not batch:
            break
        rows += batch
        since = batch[-1][0] + ms
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M")
    return df.reset_index(drop=True)


def run(df: pd.DataFrame, fast=None, slow=None, sl=None, tp=None, fee=None) -> dict:
    fast, slow = fast or config.FAST_SMA, slow or config.SLOW_SMA
    sl = config.STOP_LOSS_PCT if sl is None else sl
    tp = config.TAKE_PROFIT_PCT if tp is None else tp
    fee = config.FEE_PCT if fee is None else fee

    df = add_indicators(df, fast, slow, config.RSI_PERIOD).reset_index(drop=True)
    broker = PaperBroker(config.STARTING_BALANCE, config.POSITION_SIZE_USDT, sl, tp, fee)
    pending = None
    peak, max_dd = config.STARTING_BALANCE, 0.0

    for j in range(len(df)):
        row = df.iloc[j]
        # 1) Сигнал прошлой свечи исполняем по цене открытия текущей
        if pending == "BUY" and not broker.position:
            broker.buy(float(row["open"]), row["time"])
        elif pending == "SELL" and broker.position:
            broker.sell(float(row["open"]), "SIGNAL", row["time"])
        pending = None
        # 2) Стоп-лосс / тейк-профит внутри свечи
        broker.check_exits(float(row["low"]), float(row["high"]), row["time"])
        # 3) Новый сигнал по закрытию свечи
        sig = signal_at(df, j)
        if sig != "HOLD":
            pending = sig
        eq = broker.equity(float(row["close"]))
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak)

    last = float(df["close"].iloc[-1])
    if broker.position:
        broker.sell(last, "END", df["time"].iloc[-1])

    trades = broker.trades
    wins = [t for t in trades if t["pnl_usdt"] > 0]
    return {
        "period": f"{df['time'].iloc[0]} → {df['time'].iloc[-1]}",
        "candles": len(df),
        "trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "pnl_usdt": round(broker.balance - config.STARTING_BALANCE, 4),
        "return_pct": round((broker.balance / config.STARTING_BALANCE - 1) * 100, 2),
        "fees_paid_usdt_approx": round(sum(config.POSITION_SIZE_USDT * fee * 2 for _ in trades), 4),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "buy_and_hold_pct": round((last / float(df["open"].iloc[0]) - 1) * 100, 2),
        "exit_reasons": pd.Series([t["reason"] for t in trades]).value_counts().to_dict() if trades else {},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--csv")
    args = ap.parse_args()
    df = pd.read_csv(args.csv) if args.csv else download(args.days)

    print(f"{config.SYMBOL} {config.TIMEFRAME}, SMA {config.FAST_SMA}/{config.SLOW_SMA}")
    for k, v in run(df).items():
        print(f"  {k}: {v}")
    print("\nДля сравнения — без комиссий:")
    r = run(df, fee=0)
    print(f"  return_pct: {r['return_pct']}")


if __name__ == "__main__":
    main()
