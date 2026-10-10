"""Совет ИИ: Claude, ChatGPT, Grok и Gemini голосуют за сделку.

Как это работает:
  1. Стратегия даёт сигнал BUY или SELL.
  2. Каждый ИИ, для которого в .env есть ключ, получает описание рынка
     и отвечает одним словом: BUY, SELL или HOLD (+ короткая причина).
  3. Сделка проходит, если "за" сигнал проголосовало достаточно участников
     (настройка COUNCIL_QUORUM в config.py).

ИИ только советуют. Сделку исполняет симулятор, а стоп-лосс работает всегда.
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

SYSTEM_PROMPT = (
    "You are one member of a trading council for a small paper-trading bot (spot, long-only, "
    "no leverage). You get a market snapshot and the strategy's proposed action. "
    "Reply ONLY with JSON: {\"vote\": \"BUY\"|\"SELL\"|\"HOLD\", \"reason\": \"<max 20 words>\"}. "
    "Be skeptical: vote HOLD if the signal looks like noise."
)

# Какой ключ в .env нужен каждому участнику
KEY_NAMES = {
    "claude": "ANTHROPIC_API_KEY",
    "chatgpt": "OPENAI_API_KEY",
    "grok": "XAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _ask_claude(key, model, prompt, timeout):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 200, "system": SYSTEM_PROMPT,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


def _ask_openai_compatible(url, key, model, prompt, timeout):
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "max_tokens": 200,
              "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                           {"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _ask_chatgpt(key, model, prompt, timeout):
    return _ask_openai_compatible("https://api.openai.com/v1/chat/completions", key, model, prompt, timeout)


def _ask_grok(key, model, prompt, timeout):
    return _ask_openai_compatible("https://api.x.ai/v1/chat/completions", key, model, prompt, timeout)


def _ask_gemini(key, model, prompt, timeout):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
              "contents": [{"role": "user", "parts": [{"text": prompt}]}]},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


ASKERS = {"claude": _ask_claude, "chatgpt": _ask_chatgpt, "grok": _ask_grok, "gemini": _ask_gemini}


def parse_vote(text: str) -> tuple[str, str]:
    """Достаёт голос из ответа ИИ. Если не понять — HOLD."""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            vote = str(data.get("vote", "")).upper().strip()
            if vote in ("BUY", "SELL", "HOLD"):
                return vote, str(data.get("reason", ""))[:200]
        except json.JSONDecodeError:
            pass
    found = [w for w in ("BUY", "SELL", "HOLD") if re.search(rf"\b{w}\b", text.upper())]
    if len(found) == 1:  # только если ответ однозначный
        return found[0], text.strip()[:200]
    return "HOLD", "ответ неоднозначный или не разобран"


class Council:
    def __init__(self, models: dict, quorum="majority", timeout=30, log_path=None, askers=None):
        self.models = models
        self.quorum = quorum
        self.timeout = timeout
        self.log_path = log_path
        self.askers = askers or ASKERS
        self.members = {name: os.getenv(env) for name, env in KEY_NAMES.items()
                        if os.getenv(env) and name in self.askers}

    def active_members(self) -> list[str]:
        return list(self.members)

    def _ask_one(self, name, prompt):
        try:
            text = self.askers[name](self.members[name], self.models.get(name, ""), prompt, self.timeout)
            vote, reason = parse_vote(text)
            return name, vote, reason, None
        except Exception as e:  # сеть, неверный ключ, лимиты и т.п.
            return name, None, "", f"{type(e).__name__}: {e}"[:300]

    def decide(self, proposed: str, snapshot: dict) -> dict:
        """Возвращает {'approved': bool|None, 'votes': {...}, 'errors': {...}}.
        approved=None означает, что никто не ответил."""
        prompt = (
            f"Symbol snapshot: {json.dumps(snapshot)}\n"
            f"Strategy proposes: {proposed}. Do you agree?"
        )
        votes, errors = {}, {}
        if self.members:
            with ThreadPoolExecutor(max_workers=len(self.members)) as ex:
                for name, vote, reason, err in ex.map(lambda n: self._ask_one(n, prompt), self.members):
                    if err:
                        errors[name] = err
                    else:
                        votes[name] = {"vote": vote, "reason": reason}

        if not votes:
            approved = None
        else:
            yes = sum(1 for v in votes.values() if v["vote"] == proposed)
            need = len(votes) // 2 + 1 if self.quorum == "majority" else int(self.quorum)
            approved = yes >= need

        result = {"proposed": proposed, "approved": approved, "votes": votes, "errors": errors}
        self._log(result)
        return result

    def _log(self, result):
        if not self.log_path:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {json.dumps(result, ensure_ascii=False)}\n")
