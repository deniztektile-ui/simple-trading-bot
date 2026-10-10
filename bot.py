"""Главный файл: запускает бота в режиме симуляции.

Запуск:  python bot.py
Смотреть работу в браузере: http://localhost:8000 (откроется сама)
Остановка: Ctrl+C (бот напечатает итог).
"""
from __future__ import annotations

import html
import sys
import time
import webbrowser
from dataclasses import asdict
from datetime import datetime

from dotenv import load_dotenv

import config
import dashboard
import market_data
from council import Council
from paper_broker import PaperBroker
from strategy import add_indicators, market_snapshot, signal_at


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # местное время


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

    state = dashboard.BotState(symbol=config.SYMBOL, timeframe=config.TIMEFRAME,
                               start=config.STARTING_BALANCE, members=members)

    def log(text: str, kind: str = "info"):
        # текст от ИИ и ошибки экранируем, чтобы они не могли встроить HTML в страницу
        text = html.escape(text).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
        plain = html.unescape(text.replace("<b>", "").replace("</b>", ""))
        print(f"\n[{now()[11:19]}] {plain}")
        state.event(text, kind, now())

    print(f"Бот запущен: {config.SYMBOL} {config.TIMEFRAME}, симуляция, баланс {broker.balance} USDT")
    print(f"Совет ИИ: {', '.join(members) if members else 'выключен (нет ключей) — торгует только стратегия'}")
    try:
        url = dashboard.start(state, getattr(config, "DASHBOARD_PORT", 8000))
        print(f"\n>>> Смотреть работу бота в браузере: {url}\n")
        if getattr(config, "OPEN_BROWSER", True):
            webbrowser.open(url)
    except OSError as e:
        print(f"Страницу в браузере запустить не удалось ({e}). Поменяйте DASHBOARD_PORT в config.py.")
    state.event("Бот запущен", "info", now())

    last_candle = None
    price = None
    try:
        while True:
            try:
                df = add_indicators(market_data.fetch_candles(config.SYMBOL, config.TIMEFRAME, config.CANDLES_LIMIT),
                                    config.FAST_SMA, config.SLOW_SMA, config.RSI_PERIOD)
            except Exception as e:
                log(f"Ошибка получения цен: {e}. Повтор через {config.POLL_SECONDS} с.", "err")
                state.update(status="нет связи с биржей")
                time.sleep(config.POLL_SECONDS)
                continue

            price = float(df["close"].iloc[-1])  # текущая (незакрытая) свеча
            # Стоп/тейк проверяем по текущей цене каждый цикл
            closed = broker.check_exits(price, price)
            if closed:
                name = "Стоп-лосс" if closed["reason"] == "STOP_LOSS" else "Тейк-профит"
                log(f"<b>{name}</b>: продано по {closed['exit']}, прибыль {closed['pnl_usdt']} $", "sell")

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
                        state.update(status="совет ИИ голосует...")
                        res = council.decide(sig, market_snapshot(df, i))
                        res["when"] = now()[11:16]
                        state.update(council=res)
                        votes = ", ".join(f"{k}:{v['vote']}" for k, v in res["votes"].items())
                        log(f"Сигнал {sig}. Голоса: {votes or 'нет ответов'}")
                        for k, err in res["errors"].items():
                            log(f"{k} ошибка: {err}", "err")
                        go = res["approved"] if res["approved"] is not None else config.TRADE_IF_COUNCIL_UNAVAILABLE
                        if res["approved"] is None:
                            log("Ни один ИИ не ответил — " + ("торгую по стратегии" if go else "сделку пропускаю"), "err")
                        # голосование может занять до 30 с — берём свежую цену
                        try:
                            price = float(market_data.fetch_candles(config.SYMBOL, config.TIMEFRAME, 2)["close"].iloc[-1])
                        except Exception:
                            pass
                    if go and sig == "BUY":
                        if not broker.buy(price):
                            log(f"Покупка не удалась: на счету {broker.balance:.2f} $ — слишком мало", "err")
                        else:
                            log(f"<b>Куплено</b> по {price:.2f} (стоп {broker.position.stop_loss:.2f}, тейк {broker.position.take_profit:.2f})", "buy")
                    elif go and sig == "SELL":
                        t = broker.sell(price, "SIGNAL")
                        log(f"<b>Продано</b> по {price:.2f}, прибыль {t['pnl_usdt']} $", "sell")
                    elif not go:
                        log(f"Совет отклонил сигнал {sig}")

            tail = df.tail(120)
            state.update(
                price=price, equity=broker.equity(price), balance=broker.balance,
                position=asdict(broker.position) if broker.position else None,
                trades=list(broker.trades), updated=now(),
                status="в позиции" if broker.position else "ждёт сигнал",
                candles=[{"time": r.time, "close": float(r.close),
                          "f": None if r.sma_fast != r.sma_fast else round(float(r.sma_fast), 2),
                          "s": None if r.sma_slow != r.sma_slow else round(float(r.sma_slow), 2)}
                         for r in tail.itertuples()],
            )
            print(f"  цена {price:.2f} | капитал {broker.equity(price):.2f} USDT   ", end="\r")
            time.sleep(config.POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nОстановлено.")
        equity = broker.equity(price) if price else broker.balance
        print(f"Сделок: {len(broker.trades)}, итоговый капитал: {equity:.2f} USDT")


if __name__ == "__main__":
    main()
