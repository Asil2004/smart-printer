#!/usr/bin/env python3
"""@CardXabarBot dagi oxirgi xabarlarni FAQAT O'QIYDI (format o'rganish uchun). Karta raqamlari yashiriladi.

  venv/bin/python tools/tg_peek_cardxabar.py [soni]
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tg_login import client  # noqa: E402

BOT = "CardXabarBot"


def mask(text: str) -> str:
    # 8600 **** **** 1234 / 860012******1234 kabi raqamlar → ****1234
    text = re.sub(r"\b\d{4}[\s*]*[\d*]{2,}[\s*]*[\d*]{2,}[\s*]*(\d{4})\b", r"****\1", text)
    return text


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    c = client()
    await c.connect()
    try:
        bot = await c.get_entity(BOT)
        async for m in c.iter_messages(bot, limit=n):
            who = "BOT" if m.sender_id == bot.id else "SIZ"
            print(f"--- {m.date:%Y-%m-%d %H:%M} [{who}] id={m.id}")
            print(mask(m.message or "<matnsiz xabar>"))
    finally:
        await c.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
