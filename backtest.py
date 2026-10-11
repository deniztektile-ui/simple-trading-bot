"""Проверка стратегии на истории (бэктест). Совет ИИ здесь не вызывается —
это было бы дорого; проверяется только сама стратегия со стопами и комиссиями.

Примеры:
  python backtest.py                    # последние 30 дней с Binance, текущие настройки
  python backtest.py --days 90
  python backtest.py --compare          # сравнить старую версию (1 мин) и новую (15 мин)
  python backtest.py --csv data.csv     # свои данные: колонки time,open,high,low,close
"""
from __future__ import annotations

import argparse

import pandas as pd

import config
from paper_broker import PaperBroker
from strategy import add_indicators, signal_at


def current_params() -> dict:
    return {
        "timeframe": config.TIMEFRAME, "fast": config.FAST_SMA, "slow": config.SLOW_SMA,
        "sl": config.STOP_LOSS_PCT, "tp": config.TAKE_PROFIT_PCT, "fee": config.FEE_PCT,
        "min_gap": config.MIN_GAP_PCT, "adx_min": config.ADX_MIN, "trend": config.TREND_SMA,
    }


# Старая версия бота (до 11.10.2026): минутные свечи, без фильтров
OLD_PARAMS = {"timeframe": "1m", "fast": 5, "slow": 13, "sl": 0.008, "tp": 0.016, "fee": 0.001,
              "min_gap": 0.0, "adx_min": 0, "trend": 0}


def download(days: int, timeframe: str | None = None) -> pd.DataFrame:
    import market_data
    tf = timeframe or config.TIMEFRAME
    print(f"Загружаю свечи {tf} за {days} дн. с Binance...")
    return market_data.fetch_history(config.SYMBOL, tf, days)


def run(df: pd.DataFrame, params: dict | None = None, **overrides) -> dict:
    p = {**current_params(), **(params or {}), **overrides}
    df = add_indicators(df, p["fast"], p["slow"], config.RSI_PERIOD, p["trend"]).reset_index(drop=True)
    broker = PaperBroker(config.STARTING_BALANCE, config.POSITION_SIZE_USDT, p["sl"], p["tp"], p["fee"])
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
        sig = signal_at(df, j, p["min_gap"], p["adx_min"])
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
        "fees_paid_usdt_approx": round(len(trades) * config.POSITION_SIZE_USDT * p["fee"] * 2, 4),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "buy_and_hold_pct": round((last / float(df["open"].iloc[0]) - 1) * 100, 2),
        "exit_reasons": pd.Series([t["reason"] for t in trades]).value_counts().to_dict() if trades else {},
    }


def describe(p: dict) -> str:
    f = []
    if p["min_gap"]:
        f.append(f"запас {p['min_gap']}%")
    if p["adx_min"]:
        f.append(f"ADX≥{p['adx_min']}")
    if p["trend"]:
        f.append(f"тренд SMA{p['trend']}")
    return (f"свечи {p['timeframe']}, SMA {p['fast']}/{p['slow']}, стоп {p['sl']*100:g}% / тейк {p['tp']*100:g}%"
            + (", фильтры: " + ", ".join(f) if f else ", без фильтров"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--csv")
    ap.add_argument("--compare", action="store_true", help="сравнить старую и новую версию")
    args = ap.parse_args()

    if args.compare:
        new = current_params()
        rows = []
        for name, p in (("ДО (старая версия)", OLD_PARAMS), ("ПОСЛЕ (новая версия)", new)):
            df = download(args.days, p["timeframe"])
            r = run(df, p)
            rows.append((name, p, r))
        print(f"\n{config.SYMBOL}, {args.days} дней, старт {config.STARTING_BALANCE} $, комиссия {config.FEE_PCT*100:g}%\n")
        for name, p, r in rows:
            print(f"{name}: {describe(p)}")
            print(f"  сделок: {r['trades']}, прибыльных: {r['win_rate_pct']}%, комиссии ≈ {r['fees_paid_usdt_approx']} $")
            print(f"  ИТОГ: {r['pnl_usdt']:+.2f} $ ({r['return_pct']:+.2f}%), макс. просадка {r['max_drawdown_pct']}%")
        print(f"\nДля сравнения: просто купить BTC и держать = {rows[1][2]['buy_and_hold_pct']:+.2f}%")
        return

    df = pd.read_csv(args.csv) if args.csv else download(args.days)
    p = current_params()
    print(f"{config.SYMBOL}: {describe(p)}")
    for k, v in run(df, p).items():
        print(f"  {k}: {v}")
    print("\nДля сравнения — без комиссий:")
    print(f"  return_pct: {run(df, p, fee=0)['return_pct']}")


if __name__ == "__main__":
    main()
