"""Тесты без интернета: python -m pytest -q"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest  # noqa: E402
from council import Council, parse_vote  # noqa: E402
from paper_broker import PaperBroker  # noqa: E402
from strategy import add_indicators, signal_at  # noqa: E402


def make_df(closes):
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "time": [f"t{i}" for i in range(len(closes))],
        "open": closes, "high": closes * 1.001, "low": closes * 0.999, "close": closes,
    })


def test_crossover_signals():
    closes = [100] * 15 + [101, 102, 103, 104, 105] + [104, 102, 100, 98, 96, 94]
    df = add_indicators(make_df(closes), 5, 13)
    sigs = [signal_at(df, i) for i in range(len(df))]
    assert "BUY" in sigs and "SELL" in sigs
    assert sigs.index("BUY") < sigs.index("SELL")


def test_broker_fees_and_stop():
    b = PaperBroker(50, 50, 0.01, 0.02, 0.001)
    assert b.buy(100)
    assert not b.buy(100)  # уже в позиции
    t = b.check_exits(low=98.9, high=100.5)
    assert t["reason"] == "STOP_LOSS"
    # убыток ~1% + 2 комиссии
    assert -0.62 < t["pnl_usdt"] < -0.58
    assert b.position is None


def test_broker_take_profit():
    b = PaperBroker(50, 50, 0.01, 0.02, 0.0)
    b.buy(100)
    t = b.check_exits(low=99.5, high=102.5)
    assert t["reason"] == "TAKE_PROFIT" and abs(t["pnl_usdt"] - 1.0) < 1e-9


def test_parse_vote():
    assert parse_vote('{"vote": "buy", "reason": "trend"}') == ("BUY", "trend")
    assert parse_vote("I think HOLD here")[0] == "HOLD"
    assert parse_vote("???")[0] == "HOLD"


def test_council_majority(monkeypatch):
    for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY"]:
        monkeypatch.setenv(k, "test")
    answers = {"claude": "BUY", "chatgpt": "BUY", "grok": "HOLD", "gemini": None}

    def fake(name):
        def ask(key, model, prompt, timeout):
            if answers[name] is None:
                raise TimeoutError("no answer")
            return f'{{"vote": "{answers[name]}", "reason": "x"}}'
        return ask

    c = Council({}, askers={n: fake(n) for n in answers})
    res = c.decide("BUY", {"price": 1})
    assert res["approved"] is True          # 2 из 3 ответивших
    assert "gemini" in res["errors"]

    answers["chatgpt"] = "HOLD"
    assert c.decide("BUY", {"price": 1})["approved"] is False


def test_council_no_keys(monkeypatch):
    for k in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY"]:
        monkeypatch.delenv(k, raising=False)
    c = Council({})
    assert c.active_members() == []
    assert c.decide("BUY", {})["approved"] is None


def test_backtest_runs():
    rng = np.random.default_rng(0)
    closes = 60000 * np.exp(np.cumsum(rng.normal(0, 0.001, 3000)))
    r = backtest.run(make_df(closes))
    assert r["trades"] > 0
    assert r["candles"] == 3000


def test_market_data_parsing(monkeypatch):
    import market_data
    rows = [[1700000000000 + i * 60000, "100", "101", "99", str(100 + i), "5", 0] for i in range(5)]
    monkeypatch.setattr(market_data, "_get", lambda params: rows)
    df = market_data.fetch_candles("BTC/USDT", "1m", 5)
    assert list(df["close"]) == [100.0, 101.0, 102.0, 103.0, 104.0]
    assert df["time"].iloc[0].startswith("2023-11-14")
