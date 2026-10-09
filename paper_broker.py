"""Симулятор торговли (бумажный счёт). Настоящие деньги не используются.

Только покупка и продажа на споте (без шортов и плеча):
  - BUY открывает позицию, если её нет;
  - SELL закрывает позицию, если она есть;
  - стоп-лосс и тейк-профит закрывают позицию автоматически.
Комиссия берётся и при входе, и при выходе.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Position:
    entry_price: float
    amount: float          # сколько монет куплено
    cost: float            # сколько USDT потрачено (с комиссией)
    stop_loss: float
    take_profit: float
    opened_at: str


@dataclass
class PaperBroker:
    balance: float
    position_size: float
    sl_pct: float
    tp_pct: float
    fee_pct: float
    log_path: str | None = None
    position: Position | None = None
    trades: list = field(default_factory=list)

    def equity(self, price: float) -> float:
        if self.position:
            return self.balance + self.position.amount * price * (1 - self.fee_pct)
        return self.balance

    def buy(self, price: float, when: str | None = None) -> bool:
        if self.position:
            return False
        spend = min(self.position_size, self.balance)
        if spend < 1:
            return False
        amount = spend * (1 - self.fee_pct) / price
        self.balance -= spend
        self.position = Position(
            entry_price=price,
            amount=amount,
            cost=spend,
            stop_loss=price * (1 - self.sl_pct),
            take_profit=price * (1 + self.tp_pct),
            opened_at=when or _now(),
        )
        return True

    def sell(self, price: float, reason: str, when: str | None = None) -> dict | None:
        if not self.position:
            return None
        p = self.position
        proceeds = p.amount * price * (1 - self.fee_pct)
        self.balance += proceeds
        pnl = proceeds - p.cost
        trade = {
            "opened_at": p.opened_at,
            "closed_at": when or _now(),
            "entry": round(p.entry_price, 2),
            "exit": round(price, 2),
            "pnl_usdt": round(pnl, 4),
            "pnl_pct": round(pnl / p.cost * 100, 3),
            "reason": reason,
            "balance": round(self.balance, 4),
        }
        self.trades.append(trade)
        self.position = None
        self._log(trade)
        return trade

    def check_exits(self, low: float, high: float, when: str | None = None) -> dict | None:
        """Проверка стоп-лосса и тейк-профита по диапазону свечи.
        Если в одной свече задеты оба уровня — считаем, что сначала сработал стоп (осторожно)."""
        if not self.position:
            return None
        p = self.position
        if low <= p.stop_loss:
            return self.sell(p.stop_loss, "STOP_LOSS", when)
        if high >= p.take_profit:
            return self.sell(p.take_profit, "TAKE_PROFIT", when)
        return None

    def _log(self, trade: dict) -> None:
        if not self.log_path:
            return
        new = not os.path.exists(self.log_path)
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(trade.keys()))
            if new:
                w.writeheader()
            w.writerow(trade)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
