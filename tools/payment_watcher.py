#!/usr/bin/env python3
"""
Smart Printchi — to'lov kuzatuvchisi (Raspberry Pi)
====================================================
@CardXabarBot xabarlarini Pi'dagi Telegram seansi orqali FAQAT O'QIYDI. Kartaga kirim
("➕ 2 537.00 UZS") kelsa, summani Render serveriga yuboradi: server shu summadagi kutayotgan
buyurtmani topib tasdiqlaydi va Canon chop etadi.

Xabar namunasi (2026-11-26):
    🟢 Perevod na kartu
    ➕ 1 000.00 UZS
    💳 ***2570
    📍 UB VISA TO UZCARD, UZ
    🕓 26.11.26 13:55
    💵 1 000.00 UZS          ← balans, hisobga olinmaydi

Muhit: CLOUD_URL, AGENT_TOKEN (~/.config/printchi-agent.env), CARD_LAST4 (ixtiyoriy filtr).
Seans: ~/.config/printchi-tg/ (tools/tg_login.py bilan bir marta kiriladi).

  venv/bin/python tools/payment_watcher.py          # doimiy ishlaydi (systemd)
  venv/bin/python tools/payment_watcher.py --test   # parser sinovi
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] [Payments]: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("payment_watcher")

BOT = "CardXabarBot"
CLOUD_URL = os.environ.get("CLOUD_URL", "https://smart-printer-mo1g.onrender.com").rstrip("/")
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip()
CARD_LAST4 = os.environ.get("CARD_LAST4", "").strip()
STATE_FILE = Path.home() / ".config" / "printchi-tg" / "watcher_state.json"
CATCHUP_S = 45 * 60          # kuzatuvchi o'chiq bo'lgan paytdagi xabarlarni ham ko'rib chiqish

_AMOUNT_RE = re.compile(r"^\s*➕\s*([\d\s  ]+(?:[.,]\d{1,2})?)\s*(UZS|so['‘’`]?m|сум)?", re.M | re.I)
_CARD_RE = re.compile(r"💳\s*[*•.\s]*(\d{4})\b")


def parse_credit(text: str):
    """Kirim bo'lsa {'amount': int, 'card_last4': str}, aks holda None (chiqim, balans, menyu)."""
    if not text:
        return None
    m = _AMOUNT_RE.search(text)
    if not m:
        return None
    raw = re.sub(r"[\s  ]", "", m.group(1)).replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        return None
    if amount <= 0:
        return None
    c = _CARD_RE.search(text)
    return {"amount": int(round(amount)), "card_last4": c.group(1) if c else ""}


def _self_test():
    sample = "🟢 Perevod na kartu\n➕ 1 000.00 UZS\n💳 ***2570\n📍 UB VISA TO UZCARD, UZ\n🕓 26.11.26 13:55\n💵 1 000.00 UZS"
    cases = [
        (sample, {"amount": 1000, "card_last4": "2570"}),
        ("🔴 Oplata\n➖ 5 000.00 UZS\n💳 ***2570\n💵 1 000.00 UZS", None),       # chiqim
        ("💳 Umumiy balans:\n   💰 685.72 so'm", None),                             # balans
        ("Kerakli bo'limni tanlang👇", None),
        ("🟢 Popolnenie\n➕ 12 537.00 UZS\n💳 ***2570\n💵 13 537.00 UZS", {"amount": 12537, "card_last4": "2570"}),
        ("🟢 X\n➕ 2 537,00 UZS\n💳 **** 2570", {"amount": 2537, "card_last4": "2570"}),
    ]
    ok = True
    for text, want in cases:
        got = parse_credit(text)
        mark = "✅" if got == want else "❌"
        ok &= got == want
        print(mark, repr(text.splitlines()[0]), "→", got)
    sys.exit(0 if ok else 1)


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"last_id": 0, "pending": []}


def _save_state(st: dict):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st))
    tmp.replace(STATE_FILE)


def _post(item: dict) -> bool:
    import requests
    try:
        r = requests.post(f"{CLOUD_URL}/api/agent/payment-seen", json=item, timeout=20,
                          headers={"X-Agent-Token": AGENT_TOKEN})
        if r.status_code == 401:
            log.error("Server agent kalitini rad etdi (AGENT_TOKEN)")
            return False
        if not r.ok:
            log.warning(f"Server javobi HTTP {r.status_code}")
            return False
        res = r.json()
        log.info(f"{item['amount']} so'm (…{item['card_last4']}) → {res.get('result')} {res.get('order_id', '')}")
        return True
    except Exception as e:
        log.warning(f"Serverga yuborib bo'lmadi: {e}")
        return False


def _heartbeat(pending: int):
    import requests
    try:
        requests.post(f"{CLOUD_URL}/api/agent/watcher-heartbeat", timeout=15,
                      json={"pending": pending, "card": CARD_LAST4},
                      headers={"X-Agent-Token": AGENT_TOKEN})
    except Exception as e:
        log.debug(f"Heartbeat yuborilmadi: {e}")


async def run():
    from telethon import events
    from tg_login import client

    if not AGENT_TOKEN:
        log.error("AGENT_TOKEN yo'q — ~/.config/printchi-agent.env ni tekshiring")
        sys.exit(1)
    st = _load_state()
    c = client()
    await c.connect()
    if not await c.is_user_authorized():
        log.error("Telegram seansi yo'q: avval tools/tg_login.py bilan kiring")
        sys.exit(1)
    bot = await c.get_entity(BOT)
    lock = asyncio.Lock()

    async def handle(m):
        async with lock:
            if m.id <= st["last_id"]:
                return
            st["last_id"] = m.id
            credit = parse_credit(m.message or "")
            if credit and (not CARD_LAST4 or credit["card_last4"] in ("", CARD_LAST4)):
                credit["msg_id"] = f"cx:{m.id}"
                credit["msg_time"] = m.date.timestamp()
                st["pending"].append(credit)
            _save_state(st)
            await flush()

    async def flush():
        left = []
        for item in st["pending"]:
            if time.time() - item.get("msg_time", time.time()) > 24 * 3600:
                continue  # bir kundan eski — tashlab yuboriladi
            ok = await asyncio.to_thread(_post, item)
            if not ok:
                left.append(item)
        st["pending"] = left
        _save_state(st)

    @c.on(events.NewMessage(chats=bot, incoming=True))
    async def on_new(ev):
        await handle(ev.message)

    # O'chiq paytda kelgan xabarlar (birinchi ishga tushishda faqat oxirgi id eslab qolinadi)
    if st["last_id"] == 0:
        async for m in c.iter_messages(bot, limit=1):
            st["last_id"] = m.id
        _save_state(st)
        log.info("Birinchi ishga tushish: eski xabarlar o'tkazib yuborildi")
    else:
        msgs = [m async for m in c.iter_messages(bot, min_id=st["last_id"], limit=50)]
        for m in reversed(msgs):
            if time.time() - m.date.timestamp() < CATCHUP_S:
                await handle(m)
            else:
                st["last_id"] = max(st["last_id"], m.id)
        _save_state(st)

    log.info(f"Kuzatuv boshlandi: @{BOT} → {CLOUD_URL} (karta: …{CARD_LAST4 or 'hammasi'})")
    last_beat = 0.0
    while True:
        if time.time() - last_beat >= 60:
            # Telegram aloqasi uzilgan bo'lsa "tirikman" yuborilmaydi — server 5 daqiqada adminni ogohlantiradi
            if c.is_connected():
                last_beat = time.time()
                await asyncio.to_thread(_heartbeat, len(st["pending"]))
        if st["pending"]:
            async with lock:
                await flush()
        await asyncio.sleep(30)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _self_test()
    asyncio.run(run())
