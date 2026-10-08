"""Наблюдаемый прототип совета из статьи alpha404.

Реальные данные Hyperliquid. Реальные вызовы моделей, если ключ задан.
Ни одного ордера: MODE=LIVE отвергается на старте.

Лог events.jsonl — единственный источник правды.
Теневые правила (shadow_*) — не модели. Они нужны, чтобы машина
крутилась до появления ключей, и в кворум не входят.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Literal

import websockets
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

ROOT = Path(__file__).resolve().parent
INFO = "https://api.hyperliquid.xyz/info"
WS = "wss://api.hyperliquid.xyz/ws"
MAX_SNAPSHOT_AGE_MS = 1500
MIN_CONF = 0.55
QUORUM = 3
SEATS = ("CLAUDE", "GROK", "GEMINI", "GPT")

BASE = """
You are one model on a four-model BTC perpetual trading council.
You receive a compact JSON market snapshot based on 1-minute market data.
Return exactly one JSON object and nothing else.

Allowed votes: LONG, SHORT, WAIT
WAIT is a respected decision. Do not invent a trade when the setup is unclear.
Confidence: 0.0 to 1.0. Confidence above 0.80 should be rare.
Keep the reason under 12 words.
Schema: {"vote":"LONG|SHORT|WAIT","conf":0.5,"why":"short reason"}
""".strip()

ROLES = {
    "CLAUDE": """
RISK MANAGER. You may additionally vote VETO.
Look for reasons not to trade:
- efficiency ratio showing chop
- extreme volatility
- price trapped directly against a major wall
- move already extended
- poor reward relative to nearby liquidity
A veto should be exceptional and explainable.
""".strip(),
    "GROK": """
MOMENTUM SPECIALIST.
Prioritize: ret_5m_pct, ret_15m_pct, ema9_vs_ema21_pct, er20.
Favor aligned directional movement. WAIT when timeframes conflict.
""".strip(),
    "GEMINI": """
LIQUIDITY SPECIALIST.
Prioritize: bid_wall, ask_wall, book_imbalance, px_vs_vwap_pct, spread_bps.
Avoid entering directly into nearby opposing liquidity.
""".strip(),
    "GPT": """
ORDER FLOW SPECIALIST.
Prioritize: cvd_5m, cvd_z, book_imbalance, price response.
Follow aggressive flow when price confirms it.
Treat strong flow without price response as possible absorption.
""".strip(),
}

SEAT_FIELDS = {
    "CLAUDE": None,
    "GROK": ("px", "ret_5m_pct", "ret_15m_pct", "ema9_vs_ema21_pct", "er20", "atr_vs_avg"),
    "GEMINI": ("px", "bid_wall", "ask_wall", "book_imbalance", "px_vs_vwap_pct", "spread_bps"),
    "GPT": ("px", "cvd_5m", "cvd_z", "book_imbalance", "ret_5m_pct"),
}


class Vote(BaseModel):
    vote: Literal["LONG", "SHORT", "WAIT", "VETO"]
    conf: float = Field(ge=0.0, le=1.0)
    why: str


def load_cfg() -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    mode = os.getenv("MODE", "OBSERVE").upper()
    if mode != "OBSERVE":
        raise SystemExit(f"Отказ: MODE={mode}. Этот прототип не маршрутизирует ордера.")
    return {
        "coin": os.getenv("COIN", "BTC"),
        "equity": float(os.getenv("EQUITY", "400")),
        "risk": float(os.getenv("RISK_PER_TRADE", "0.0075")),
        "max_lev": float(os.getenv("MAX_LEVERAGE", "5")),
        "taker_fee": float(os.getenv("TAKER_FEE", "0.00045")),
        "max_closes": int(os.getenv("MAX_CLOSES", "3")),
        "keys": {
            "CLAUDE": os.getenv("ANTHROPIC_API_KEY", ""),
            "GROK": os.getenv("XAI_API_KEY", ""),
            "GEMINI": os.getenv("GEMINI_API_KEY", ""),
            "GPT": os.getenv("OPENAI_API_KEY", ""),
        },
        "models": {
            "CLAUDE": os.getenv("CLAUDE_MODEL", ""),
            "GROK": os.getenv("GROK_MODEL", ""),
            "GEMINI": os.getenv("GEMINI_MODEL", ""),
            "GPT": os.getenv("OPENAI_MODEL", ""),
        },
    }


def post_info(payload: dict) -> Any:
    req = urllib.request.Request(
        INFO,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def log_event(path: Path, event: dict) -> None:
    event.setdefault("ts", int(time.time() * 1000))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def ema(values: list[float], n: int) -> float:
    if not values:
        return 0.0
    k = 2 / (n + 1)
    acc = values[0]
    for v in values[1:]:
        acc = v * k + acc * (1 - k)
    return acc


def efficiency_ratio(closes: list[float], n: int = 20) -> float:
    if len(closes) < n + 1:
        return 0.0
    change = abs(closes[-1] - closes[-n - 1])
    path = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - n, len(closes)))
    return change / path if path else 0.0


def atr(candles: list[dict], n: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        prev_c = candles[i - 1]["c"]
        trs.append(max(
            candles[i]["h"] - candles[i]["l"],
            abs(candles[i]["h"] - prev_c),
            abs(candles[i]["l"] - prev_c),
        ))
    window = trs[-n:]
    return sum(window) / len(window) if window else 0.0


class MarketFeed:
    def __init__(self, coin: str):
        self.coin = coin
        self.book = None
        self.book_ts = 0
        self.trades: deque[dict] = deque(maxlen=5000)
        self.trade_ts = 0
        self.candles: dict[int, dict] = {}
        self.candle_ts = 0
        self.cvd_hist: deque[float] = deque(maxlen=60)

    def seed(self) -> None:
        now = int(time.time() * 1000)
        rows = post_info({
            "type": "candleSnapshot",
            "req": {"coin": self.coin, "interval": "1m", "startTime": now - 120 * 60_000, "endTime": now},
        })
        for row in rows:
            self.candles[int(row["t"])] = {
                "o": float(row["o"]), "h": float(row["h"]), "l": float(row["l"]),
                "c": float(row["c"]), "v": float(row["v"]),
            }
        self.candle_ts = now
        book = post_info({"type": "l2Book", "coin": self.coin})
        self.book = book
        self.book_ts = int(book.get("time") or now)

    def closed(self) -> list[tuple[int, dict]]:
        now_ms = int(time.time() * 1000)
        rows = [(t, c) for t, c in self.candles.items() if t + 60_000 <= now_ms]
        return sorted(rows)

    def apply(self, msg: dict) -> None:
        ch, data = msg.get("channel"), msg.get("data")
        now = time.time() * 1000
        if ch == "l2Book" and data and data.get("coin") == self.coin:
            self.book, self.book_ts = data, now
        elif ch == "trades" and isinstance(data, list):
            for t in data:
                if t.get("coin") != self.coin:
                    continue
                self.trades.append({
                    "time": int(t["time"]),
                    "px": float(t["px"]),
                    "sz": float(t["sz"]),
                    "side": t["side"],
                })
            self.trade_ts = now
        elif ch == "candle" and data and data.get("s") == self.coin and data.get("i") == "1m":
            self.candles[int(data["t"])] = {
                "o": float(data["o"]), "h": float(data["h"]), "l": float(data["l"]),
                "c": float(data["c"]), "v": float(data["v"]),
            }
            self.candle_ts = now

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                async with websockets.connect(WS, ping_interval=20) as ws:
                    for sub in (
                        {"type": "l2Book", "coin": self.coin},
                        {"type": "trades", "coin": self.coin},
                        {"type": "candle", "coin": self.coin, "interval": "1m"},
                    ):
                        await ws.send(json.dumps({"method": "subscribe", "subscription": sub}))
                    while not stop.is_set():
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        self.apply(json.loads(raw))
            except Exception:
                self.book = None
                await asyncio.sleep(2)


def snapshot(feed: MarketFeed) -> dict | None:
    closed = feed.closed()
    if len(closed) < 22 or not feed.book:
        return None
    closes = [c["c"] for _, c in closed]
    px = closes[-1]
    bids, asks = feed.book["levels"]
    if not bids or not asks:
        return None
    best_bid, best_ask = float(bids[0]["px"]), float(asks[0]["px"])
    mid = (best_bid + best_ask) / 2
    spread_bps = (best_ask - best_bid) / mid * 10_000 if mid else 0.0

    def ret(n: int) -> float:
        if len(closes) <= n or closes[-n - 1] == 0:
            return 0.0
        return (closes[-1] / closes[-n - 1] - 1) * 100

    e9, e21 = ema(closes, 9), ema(closes, 21)
    ema_gap = (e9 / e21 - 1) * 100 if e21 else 0.0
    window = closed[-60:]
    notion = sum((c["h"] + c["l"] + c["c"]) / 3 * c["v"] for _, c in window)
    vol = sum(c["v"] for _, c in window)
    vwap = notion / vol if vol else px
    atr_now = atr([c for _, c in closed])
    atr_hist = [atr([c for _, c in closed[:i]]) for i in range(max(16, len(closed) - 20), len(closed) + 1)]
    atr_hist = [x for x in atr_hist if x > 0]
    atr_avg = sum(atr_hist) / len(atr_hist) if atr_hist else atr_now

    band = mid * 0.0015
    bid_wall = max((float(l["sz"]) for l in bids if mid - float(l["px"]) <= band), default=0.0)
    ask_wall = max((float(l["sz"]) for l in asks if float(l["px"]) - mid <= band), default=0.0)
    bid_sz = sum(float(l["sz"]) for l in bids[:10])
    ask_sz = sum(float(l["sz"]) for l in asks[:10])
    imbalance = bid_sz / (bid_sz + ask_sz) if bid_sz + ask_sz else 0.5

    cutoff = int(time.time() * 1000) - 5 * 60_000
    cvd = 0.0
    for t in feed.trades:
        if t["time"] < cutoff:
            continue
        # Hyperliquid: B = агрессивная покупка, A = агрессивная продажа.
        cvd += t["sz"] if t["side"] == "B" else -t["sz"]
    feed.cvd_hist.append(cvd)
    hist = list(feed.cvd_hist)
    mean = sum(hist) / len(hist)
    var = sum((x - mean) ** 2 for x in hist) / len(hist)
    cvd_z = (cvd - mean) / math.sqrt(var) if var else 0.0

    now = int(time.time() * 1000)
    return {
        "ts": now,
        "coin": feed.coin,
        "px": round(px, 2),
        "mid": round(mid, 2),
        "ret_5m_pct": round(ret(5), 4),
        "ret_15m_pct": round(ret(15), 4),
        "ema9_vs_ema21_pct": round(ema_gap, 4),
        "px_vs_vwap_pct": round((px / vwap - 1) * 100, 4) if vwap else 0.0,
        "vwap": round(vwap, 2),
        "atr": round(atr_now, 2),
        "atr_vs_avg": round(atr_now / atr_avg, 3) if atr_avg else 0.0,
        "er20": round(efficiency_ratio(closes), 3),
        "book_imbalance": round(imbalance, 3),
        "bid_wall": round(bid_wall, 4),
        "ask_wall": round(ask_wall, 4),
        "cvd_5m": round(cvd, 4),
        "cvd_z": round(cvd_z, 3),
        "spread_bps": round(spread_bps, 3),
        "book_ready": feed.book_ts > 0 and now - feed.book_ts < 5_000,
        "candle_ready": len(closed) >= 22,
        "book_exchange_ts": int(feed.book.get("time") or 0),
    }


def validate_snapshot(s: dict) -> tuple[bool, str | None]:
    age = int(time.time() * 1000) - s["ts"]
    if age > MAX_SNAPSHOT_AGE_MS:
        return False, "STALE_DATA"
    if not s.get("book_ready"):
        return False, "NO_BOOK"
    if not s.get("candle_ready"):
        return False, "NO_CANDLE"
    return True, None


def hard_gate(s: dict) -> str | None:
    if s["spread_bps"] > 3:
        return "SPREAD"
    if s["er20"] < 0.25:
        return "CHOP"
    if s["atr_vs_avg"] > 2.5:
        return "VOL_SPIKE"
    return None


def worth_asking(s: dict, prev: dict | None) -> bool:
    crossed = False
    if prev is not None:
        crossed = (prev["px"] - prev["vwap"]) * (s["px"] - s["vwap"]) < 0
    unusual = abs(s["cvd_z"]) > 2
    skew = not (0.35 < s["book_imbalance"] < 0.65)
    return unusual or skew or crossed


def position_size(equity: float, entry: float, atr_value: float, risk: float, max_lev: float) -> dict:
    stop_dist = 1.2 * atr_value
    if stop_dist <= 0 or entry <= 0:
        return {"qty": 0.0, "stop_dist": stop_dist, "notional": 0.0, "binding": "NONE"}
    qty_risk = equity * risk / stop_dist
    qty_lev = equity * max_lev / entry
    qty = min(qty_risk, qty_lev)
    return {
        "qty": round(qty, 6),
        "stop_dist": round(stop_dist, 2),
        "notional": round(qty * entry, 2),
        "risk_usd": round(qty * stop_dist, 2),
        "binding": "LEVERAGE" if qty_lev < qty_risk else "RISK",
    }


def decide(votes: dict[str, dict]) -> tuple[str | None, str]:
    if votes.get("CLAUDE", {}).get("vote") == "VETO":
        return None, "CLAUDE_VETO"
    sides = {"LONG": [], "SHORT": []}
    for name, v in votes.items():
        if v.get("vote") in sides and float(v.get("conf") or 0) >= MIN_CONF:
            sides[v["vote"]].append(name)
    if len(sides["LONG"]) >= QUORUM and not sides["SHORT"]:
        return "LONG", ",".join(sides["LONG"])
    if len(sides["SHORT"]) >= QUORUM and not sides["LONG"]:
        return "SHORT", ",".join(sides["SHORT"])
    return None, "NO_QUORUM"


def shadow_votes(s: dict) -> dict[str, dict]:
    """Детерминированные заглушки. Не модели и не голос совета."""
    aligned_up = s["ret_5m_pct"] > 0 and s["ret_15m_pct"] > 0 and s["ema9_vs_ema21_pct"] > 0 and s["er20"] >= 0.5
    aligned_dn = s["ret_5m_pct"] < 0 and s["ret_15m_pct"] < 0 and s["ema9_vs_ema21_pct"] < 0 and s["er20"] >= 0.5
    grok = "LONG" if aligned_up else "SHORT" if aligned_dn else "WAIT"
    into_ask = s["ask_wall"] > s["bid_wall"] * 1.5 and s["px_vs_vwap_pct"] > 0
    into_bid = s["bid_wall"] > s["ask_wall"] * 1.5 and s["px_vs_vwap_pct"] < 0
    if into_ask or into_bid or s["spread_bps"] > 2:
        gemini = "WAIT"
    elif s["book_imbalance"] >= 0.62:
        gemini = "LONG"
    elif s["book_imbalance"] <= 0.38:
        gemini = "SHORT"
    else:
        gemini = "WAIT"
    if s["cvd_z"] > 1.5 and s["ret_5m_pct"] > 0:
        gpt = "LONG"
    elif s["cvd_z"] < -1.5 and s["ret_5m_pct"] < 0:
        gpt = "SHORT"
    else:
        gpt = "WAIT"
    veto = s["er20"] < 0.30 or s["atr_vs_avg"] > 2 or s["spread_bps"] > 2
    claude = "VETO" if veto else "WAIT"
    return {
        "CLAUDE": {"vote": claude, "conf": 0.6, "why": "shadow risk rule"},
        "GROK": {"vote": grok, "conf": 0.6, "why": "shadow momentum rule"},
        "GEMINI": {"vote": gemini, "conf": 0.6, "why": "shadow liquidity rule"},
        "GPT": {"vote": gpt, "conf": 0.6, "why": "shadow flow rule"},
    }


def _http_json(url: str, payload: dict, headers: dict, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no json")
    return json.loads(text[start:end + 1])


def call_model(seat: str, snap: dict, cfg: dict) -> dict:
    key, model = cfg["keys"][seat], cfg["models"][seat]
    if not key or not model:
        return {"vote": "WAIT", "conf": 0.0, "why": "provider unavailable"}
    fields = SEAT_FIELDS[seat]
    view = snap if fields is None else {k: snap[k] for k in fields}
    prompt = BASE + "\n" + ROLES[seat] + "\nSNAPSHOT:\n" + json.dumps(view)
    try:
        if seat == "GPT":
            data = _http_json(
                "https://api.openai.com/v1/chat/completions",
                {"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]},
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            text = data["choices"][0]["message"]["content"]
        elif seat == "GROK":
            data = _http_json(
                "https://api.x.ai/v1/chat/completions",
                {"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]},
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            text = data["choices"][0]["message"]["content"]
        elif seat == "CLAUDE":
            data = _http_json(
                "https://api.anthropic.com/v1/messages",
                {"model": model, "max_tokens": 120, "messages": [{"role": "user", "content": prompt}]},
                {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            )
            text = data["content"][0]["text"]
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            data = _http_json(url, {"contents": [{"parts": [{"text": prompt}]}]}, {"Content-Type": "application/json"})
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        vote = Vote.model_validate(_extract_json(text))
        if seat != "CLAUDE" and vote.vote == "VETO":
            return {"vote": "WAIT", "conf": 0.0, "why": "veto not allowed"}
        return vote.model_dump()
    except (urllib.error.URLError, TimeoutError, ValidationError, KeyError, ValueError, json.JSONDecodeError):
        return {"vote": "WAIT", "conf": 0.0, "why": "provider unavailable"}


async def council(snap: dict, cfg: dict) -> dict[str, dict]:
    async def one(seat: str) -> tuple[str, dict]:
        try:
            result = await asyncio.wait_for(asyncio.to_thread(call_model, seat, snap, cfg), timeout=8)
        except Exception:
            result = {"vote": "WAIT", "conf": 0.0, "why": "provider unavailable"}
        return seat, result

    pairs = await asyncio.gather(*(one(seat) for seat in SEATS))
    return dict(pairs)


def fee_preview(size: dict, fee: float) -> dict:
    notional = size["notional"]
    round_trip = notional * fee * 2
    gross_2r = size["risk_usd"] * 2
    return {
        "gross_2r": round(gross_2r, 2),
        "fees_2r": round(round_trip, 2),
        "net_2r": round(gross_2r - round_trip, 2),
    }


async def on_close(feed: MarketFeed, cfg: dict, path: Path, prev: dict | None, pending: list) -> dict | None:
    snap = snapshot(feed)
    if snap is None:
        log_event(path, {"type": "skip", "reason": "SNAPSHOT_NOT_READY"})
        return prev
    log_event(path, {"type": "snapshot", **snap})
    ok, reason = validate_snapshot(snap)
    if not ok:
        log_event(path, {"type": "skip", "reason": reason, "px": snap["px"]})
        return snap
    gate = hard_gate(snap)
    if gate:
        log_event(path, {"type": "skip", "reason": gate, "px": snap["px"], "er20": snap["er20"]})
        return snap
    if not worth_asking(snap, prev):
        log_event(path, {"type": "skip", "reason": "NO_TRIGGER", "px": snap["px"]})
        return snap

    started = time.time()
    votes = await council(snap, cfg)
    for seat, vote in votes.items():
        log_event(path, {"type": "vote", "model": seat, "source": "model", **vote})
    ok_after, reason_after = validate_snapshot(snap)
    mid_now = snap["px"]
    if feed.book and feed.book.get("levels"):
        bids, asks = feed.book["levels"]
        if bids and asks:
            mid_now = (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
    drift = abs(mid_now - snap["px"]) > 0.25 * snap["atr"] if snap["atr"] else False
    if not ok_after or drift:
        log_event(path, {"type": "decision", "result": reason_after or "STALE_AFTER_VOTE", "drift": drift, "mid_now": round(mid_now, 2)})
        return snap
    side, detail = decide(votes)
    size = position_size(cfg["equity"], snap["px"], snap["atr"], cfg["risk"], cfg["max_lev"])
    event = {
        "type": "decision",
        "result": side or detail,
        "detail": detail,
        "latency_s": round(time.time() - started, 3),
        "would_enter": side,
        "size_preview": size,
        "fee_preview": fee_preview(size, cfg["taker_fee"]),
        "order_sent": False,
    }
    log_event(path, event)
    shadows = shadow_votes(snap)
    for seat, vote in shadows.items():
        log_event(path, {"type": "shadow_vote", "model": seat, "source": "shadow", **vote})
    if side:
        pending.append({
            "due": {"5m": int(time.time()) + 300, "15m": int(time.time()) + 900, "30m": int(time.time()) + 1800},
            "side": 1 if side == "LONG" else -1,
            "entry": snap["px"],
            "stop_dist": size["stop_dist"],
            "opened_ms": snap["ts"],
        })
    print(
        f"совет {event['result']} за {event['latency_s']}с | px {snap['px']} | "
        f"er {snap['er20']} | спред {snap['spread_bps']} bps | ордер не отправлен"
    )
    return snap


def settle(feed: MarketFeed, path: Path, pending: list) -> None:
    now = int(time.time())
    still = []
    last = feed.closed()[-1][1]["c"] if feed.closed() else None
    for item in pending:
        done = True
        for label, due in item["due"].items():
            if item.get(label):
                continue
            if now >= due and last is not None:
                move = (last - item["entry"]) * item["side"]
                item[label] = {"px": last, "r": round(move / item["stop_dist"], 3) if item["stop_dist"] else None}
                log_event(path, {"type": "counterfactual", "horizon": label, "side": item["side"], **item[label]})
            else:
                done = False
        if not done:
            still.append(item)
    pending[:] = still


async def once(cfg: dict, path: Path) -> None:
    feed = MarketFeed(cfg["coin"])
    feed.seed()
    book = post_info({"type": "l2Book", "coin": cfg["coin"]})
    feed.book = book
    feed.book_ts = time.time() * 1000
    await on_close(feed, cfg, path, None, [])


async def observe(cfg: dict, path: Path) -> None:
    feed = MarketFeed(cfg["coin"])
    print("гружу свечи и стакан...")
    feed.seed()
    print(f"свечей {len(feed.closed())}, стакан {feed.book_ts}")
    stop = asyncio.Event()
    asyncio.create_task(feed.run(stop))
    seen = {t for t, _ in feed.closed()}
    prev = None
    pending: list = []
    closes = 0
    target = cfg["max_closes"]
    try:
        while target == 0 or closes < target:
            await asyncio.sleep(1)
            settle(feed, path, pending)
            closed_now = {t for t, _ in feed.closed()}
            fresh = sorted(closed_now - seen)
            if not fresh:
                continue
            seen.update(fresh)
            prev = await on_close(feed, cfg, path, prev, pending)
            closes += 1
            print(f"закрытых свечей разобрано: {closes}")
    finally:
        stop.set()


def self_test() -> None:
    cases = [
        ("все LONG", {"CLAUDE": ("LONG", 0.64), "GROK": ("LONG", 0.81), "GEMINI": ("LONG", 0.62), "GPT": ("LONG", 0.74)}, "LONG"),
        ("трое, один WAIT", {"CLAUDE": ("WAIT", 0.61), "GROK": ("LONG", 0.83), "GEMINI": ("LONG", 0.68), "GPT": ("LONG", 0.72)}, "LONG"),
        ("трое против одного", {"CLAUDE": ("LONG", 0.62), "GROK": ("LONG", 0.81), "GEMINI": ("LONG", 0.67), "GPT": ("SHORT", 0.73)}, None),
        ("вето", {"CLAUDE": ("VETO", 0.9), "GROK": ("LONG", 0.8), "GEMINI": ("LONG", 0.8), "GPT": ("LONG", 0.8)}, None),
        ("битый ответ уже WAIT", {"CLAUDE": ("WAIT", 0.0), "GROK": ("LONG", 0.9), "GEMINI": ("LONG", 0.9), "GPT": ("WAIT", 0.0)}, None),
    ]
    failed = 0
    for name, raw, expect in cases:
        votes = {k: {"vote": v, "conf": c, "why": "t"} for k, (v, c) in raw.items()}
        side, detail = decide(votes)
        ok = side == expect
        failed += not ok
        print(f"{'ok' if ok else 'FAIL'} {name}: {side} ({detail})")
    size = position_size(400, 83150, 52.8, 0.0075, 5)
    print("размер на $400 / ATR 52.8:", size)
    if size["binding"] != "LEVERAGE" or abs(size["notional"] - 2000) > 1:
        failed += 1
        print("FAIL потолок плеча")
    raise SystemExit(failed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hyperliquid observe council")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--once", action="store_true", help="один снимок по уже закрытым свечам, без ожидания новой")
    parser.add_argument("--log", default=str(ROOT / "events.jsonl"))
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    cfg = load_cfg()
    path = Path(args.log)
    armed = [s for s in SEATS if cfg["keys"][s] and cfg["models"][s]]
    print("MODE=OBSERVE. Ордера выключены.")
    print("стулья с ключом:", ", ".join(armed) if armed else "нет — модели будут WAIT")
    log_event(path, {"type": "start", "mode": "OBSERVE", "armed": armed, "coin": cfg["coin"]})
    if args.once:
        asyncio.run(once(cfg, path))
        return
    asyncio.run(observe(cfg, path))


if __name__ == "__main__":
    main()
