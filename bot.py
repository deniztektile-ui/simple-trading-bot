"""Главный файл: запускает бота в режиме симуляции.

Запуск:  python bot.py
Остановка: Ctrl+C (бот напечатает итог).
"""
import sys
import time

from dotenv import load_dotenv

import config
import market_data
from council import Council
from paper_broker import PaperBroker
from strategy import add_indicators, market_snapshot, signal_at


def main():
    if not config.PAPER_TRADING:
        sys.exit("Реальная торговля в этой версии отключена. Оставьте PAPER_TRADING = True.")

    load_dotenv()
    # Для симуляции ключи биржи не нужны — цены публичные.
    broker = PaperBroker(config.STARTING_BALANCE, config.POSITION_SIZE_USDT, config.STOP_LOSS_PCT,
                         config.TAKE_PROFIT_PCT, config.FEE_PCT, log_path=config.TRADES_LOG)
    council = Council(config.AI_MODELS, config.COUNCIL_QUORUM, config.AI_TIMEOUT_SECONDS,
                      log_path=config.COUNCIL_LOG) if config.USE_AI_COUNCIL else None

    members = council.active_members() if council else []
    print(f"Бот запущен: {config.SYMBOL} {config.TIMEFRAME}, симуляция, баланс {broker.balance} USDT")
    print(f"Совет ИИ: {', '.join(members) if members else 'выключен (нет ключей) — торгует только стратегия'}")

    last_candle = None
    price = None
    try:
        while True:
            try:
                df = add_indicators(market_data.fetch_candles(config.SYMBOL, config.TIMEFRAME, config.CANDLES_LIMIT), config.FAST_SMA, config.SLOW_SMA, config.RSI_PERIOD)
            except Exception as e:
                print(f"Ошибка получения цен: {e}. Повтор через {config.POLL_SECONDS} с.")
                time.sleep(config.POLL_SECONDS)
                continue

            price = float(df["close"].iloc[-1])  # текущая (незакрытая) свеча
            # Стоп/тейк проверяем по текущей цене каждый цикл
            closed = broker.check_exits(price, price)
            if closed:
                print(f"[{closed['closed_at']}] {closed['reason']} по {closed['exit']}  PnL {closed['pnl_usdt']} USDT")

            # Сигналы — только по закрытой свече (предпоследняя), один раз на свечу
            i = len(df) - 2
            candle_time = df["time"].iloc[i]
            if candle_time != last_candle:
                last_candle = candle_time
                sig = signal_at(df, i)
                actionable = (sig == "BUY" and not broker.position) or (sig == "SELL" and broker.position)
                if actionable:
                    go = True
                    if council and members:
                        res = council.decide(sig, market_snapshot(df, i))
                        votes = ", ".join(f"{k}:{v['vote']}" for k, v in res["votes"].items())
                        print(f"[{candle_time}] Сигнал {sig}. Голоса: {votes or 'нет ответов'}")
                        for k, err in res["errors"].items():
                            print(f"   {k} ошибка: {err}")
                        go = res["approved"] if res["approved"] is not None else config.TRADE_IF_COUNCIL_UNAVAILABLE
                    if go and sig == "BUY":
                        broker.buy(price)
                        print(f"[{candle_time}] КУПЛЕНО по {price:.2f}  SL {broker.position.stop_loss:.2f}  TP {broker.position.take_profit:.2f}")
                    elif go and sig == "SELL":
                        t = broker.sell(price, "SIGNAL")
                        print(f"[{candle_time}] ПРОДАНО по {price:.2f}  PnL {t['pnl_usdt']} USDT")
                    elif not go:
                        print(f"[{candle_time}] Совет отклонил {sig}")

            print(f"  цена {price:.2f} | капитал {broker.equity(price):.2f} USDT", end="\r")
            time.sleep(config.POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nОстановлено.")
        equity = broker.equity(price) if price else broker.balance
        print(f"Сделок: {len(broker.trades)}, итоговый капитал: {equity:.2f} USDT")


if __name__ == "__main__":
    main()
