#!/usr/bin/env python3
"""
Pi'dan Telegram akkauntiga bir martalik kirish (karta xabarnomalarini o'qish uchun).

  venv/bin/python tools/tg_login.py send +998XXXXXXXXX   # Telegram ilovasiga kod yuboriladi
  venv/bin/python tools/tg_login.py code 12345 [2FA_parol]
  venv/bin/python tools/tg_login.py whoami

Kalitlar va seans: ~/.config/printchi-tg/ (faqat egasi o'qiy oladi, git'ga tushmaydi).
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

CFG = Path.home() / ".config" / "printchi-tg"
STATE = CFG / "login_state.json"


def load_env() -> tuple[int, str]:
    vals = {}
    for line in (CFG / "tg.env").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return int(vals["TG_API_ID"]), vals["TG_API_HASH"]


def client() -> TelegramClient:
    os.umask(0o077)
    api_id, api_hash = load_env()
    return TelegramClient(str(CFG / "printchi"), api_id, api_hash,
                          device_model="Printchi (Raspberry Pi)", app_version="1.0")


async def main(argv):
    cmd = argv[1] if len(argv) > 1 else "whoami"
    c = client()
    await c.connect()
    try:
        if cmd == "send":
            phone = argv[2]
            sent = await c.send_code_request(phone)
            STATE.write_text(json.dumps({"phone": phone, "hash": sent.phone_code_hash}))
            print("Kod Telegram ilovasiga yuborildi.")
        elif cmd == "code":
            st = json.loads(STATE.read_text())
            try:
                await c.sign_in(st["phone"], argv[2], phone_code_hash=st["hash"])
            except SessionPasswordNeededError:
                if len(argv) < 4:
                    print("2FA_PAROL_KERAK")
                    return
                await c.sign_in(password=argv[3])
            STATE.unlink(missing_ok=True)
            me = await c.get_me()
            print(f"Kirildi: {me.first_name or ''} (id {me.id})")
        elif cmd == "password":   # kod qabul qilingandan keyin 2FA paroli
            await c.sign_in(password=argv[2])
            STATE.unlink(missing_ok=True)
            me = await c.get_me()
            print(f"Kirildi: {me.first_name or ''} (id {me.id})")
        elif cmd == "whoami":
            if await c.is_user_authorized():
                me = await c.get_me()
                print(f"Kirilgan: {me.first_name or ''} (id {me.id})")
            else:
                print("Kirilmagan")
    finally:
        await c.disconnect()


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
