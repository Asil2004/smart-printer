"""
payments.py — Buyurtmalar, to'lov tasdig'i va xavfsizlik
=========================================================
Printer FAQAT to'lovi tasdiqlangan buyurtmani chop etadi. Tasdiq manbalari:
  1. Admin Telegram botda "✅ Tasdiqlash" tugmasini bosadi (P2P karta o'tkazmasi uchun)
  2. Admin API: POST /api/admin/orders/<id>/confirm  (X-Admin-Token sarlavhasi bilan)
  3. Click Merchant webhook (MD5 imzo tekshiriladi, CLICK_SECRET_KEY)
  4. Payme Merchant JSON-RPC (Basic auth tekshiriladi, PAYME_KEY)

Narx har doim SERVERDA hisoblanadi — mijoz yuborgan "amount" ga ishonilmaydi.

Buyurtma holatlari:
  PENDING  → yaratildi, to'lov kutilmoqda
  CLAIMED  → mijoz "To'ladim" dedi, admin tasdig'i kutilmoqda
  PAID     → to'lov tasdiqlandi, navbatda
  PRINTING → chop etilmoqda
  PRINTED  → tayyor
  FAILED   → to'langan, lekin chop etishda xato (admin qayta chop eta oladi)
  REJECTED → admin rad etdi
  EXPIRED  → to'lanmasdan muddati o'tdi
  CANCELLED→ to'lov tizimi bekor qildi
"""

import os
import json
import time
import hmac
import base64
import hashlib
import logging
import threading
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

logger = logging.getLogger("smart_web_printchi.payments")

# ── Sozlamalar (.env) ─────────────────────────────────────
def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")

REQUIRE_PAYMENT    = _env_bool("REQUIRE_PAYMENT_VERIFICATION", True)
ADMIN_TOKEN        = os.environ.get("ADMIN_TOKEN", "").strip()
# Admin panelga kirish: login + parol. ADMIN_PASSWORD bo'lmasa — parol sifatida ADMIN_TOKEN ishlatiladi.
ADMIN_LOGIN        = os.environ.get("ADMIN_LOGIN", "admin").strip()
ADMIN_PASSWORD     = os.environ.get("ADMIN_PASSWORD", "").strip() or ADMIN_TOKEN
ADMIN_SESSION_DAYS = int(os.environ.get("ADMIN_SESSION_DAYS", "30") or 30)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
CLICK_SERVICE_ID   = os.environ.get("CLICK_SERVICE_ID", "").strip()
CLICK_SECRET_KEY   = os.environ.get("CLICK_SECRET_KEY", "").strip()
PAYME_KEY          = os.environ.get("PAYME_KEY", "").strip()
# Avtomatik tasdiqlash: agar Telegram bot sozlanmagan bo'lsa yoki test rejimida bo'lsa,
# "To'lov qildim" bosilishi bilan avtomatik tasdiqlanadi va darhol chop etiladi!
DEMO_AUTO_CONFIRM  = _env_bool("DEMO_AUTO_CONFIRM", True)

PENDING_TTL_SECONDS = 30 * 60        # to'lanmagan buyurtma 30 daqiqada eskiradi
CLAIMED_TTL_SECONDS = 3 * 60 * 60    # "To'ladim" degan buyurtma 3 soat kutadi
ACTIVE_STATES = ("PENDING", "CLAIMED", "PAID", "PRINTING")

BASE_DIR    = Path(__file__).resolve().parent
ORDERS_FILE = BASE_DIR / "data" / "orders.json"

_lock = threading.RLock()
orders: dict = {}          # order_id -> order dict
payme_txns: dict = {}      # payme_transaction_id -> txn dict


# ══════════════════════════════════════════════════════════
# Saqlash (server qayta ishga tushsa ham to'langan buyurtmalar yo'qolmasin)
# ══════════════════════════════════════════════════════════
def load_state():
    global orders, payme_txns
    try:
        if ORDERS_FILE.exists():
            data = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))
            orders = data.get("orders", {})
            payme_txns = data.get("payme_txns", {})
            # PRINTING holatidagilarni app.start_background_workers() davom ettiradi
            # (CUPS ish raqami bo'lsa — kuzatadi, bo'lmasa qayta navbatga qo'yadi)
            logger.info(f"{len(orders)} ta buyurtma yuklandi")
    except Exception as e:
        logger.error(f"orders.json o'qishda xatolik: {e}")


def save_state():
    with _lock:
        try:
            ORDERS_FILE.parent.mkdir(exist_ok=True)
            tmp = ORDERS_FILE.with_suffix(".tmp")
            # Faqat oxirgi 300 ta buyurtma saqlanadi
            keep = dict(sorted(orders.items(), key=lambda kv: kv[1].get("created_at", 0))[-300:])
            tmp.write_text(json.dumps({"orders": keep, "payme_txns": payme_txns},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(ORDERS_FILE)
        except Exception as e:
            logger.error(f"orders.json yozishda xatolik: {e}")


def get_order(order_id: str):
    oid = (order_id or "").strip().upper()
    if not oid:
        return None
    with _lock:
        if oid in orders:
            return orders[oid]
    # Agar boshqa worker yozgan bo'lsa yoki server qayta yuklangan bo'lsa
    load_state()
    with _lock:
        return orders.get(oid)


def add_order(order: dict):
    with _lock:
        orders[order["id"]] = order
        save_state()


def set_status(order: dict, status: str, **extra):
    with _lock:
        order["status"] = status
        order["updated_at"] = time.time()
        order.update(extra)
        save_state()


def protected_paths() -> set:
    """Faol buyurtmalarning fayllari — tozalash oqimi ularni o'chirmasligi kerak."""
    with _lock:
        return {o.get("saved_path") for o in orders.values()
                if o.get("status") in ACTIVE_STATES + ("FAILED",)}


def expire_old_orders():
    now = time.time()
    changed = False
    with _lock:
        for o in orders.values():
            age = now - o.get("created_at", now)
            if o["status"] == "PENDING" and age > PENDING_TTL_SECONDS:
                o["status"] = "EXPIRED"; changed = True
            elif o["status"] == "CLAIMED" and age > CLAIMED_TTL_SECONDS:
                o["status"] = "EXPIRED"; changed = True
        if changed:
            save_state()


# ══════════════════════════════════════════════════════════
# Narx va sahifalar
# ══════════════════════════════════════════════════════════
def count_selected_pages(page_ranges: str, total_pages: int) -> int:
    """'1-3,5' kabi oraliqdan nechta sahifa chop etilishini hisoblaydi (frontend bilan bir xil)."""
    total_pages = max(1, int(total_pages or 1))
    if not page_ranges or page_ranges.strip().lower() in ("all", "barchasi"):
        return total_pages
    count = 0
    for part in page_ranges.split(","):
        part = part.strip()
        try:
            if "-" in part:
                a, b = [int(x) for x in part.split("-", 1)]
                count += max(0, min(b, total_pages) - max(1, a) + 1)
            elif part:
                n = int(part)
                if 1 <= n <= total_pages:
                    count += 1
        except ValueError:
            continue
    return count if count > 0 else total_pages


# ══════════════════════════════════════════════════════════
# Admin autentifikatsiyasi
# ══════════════════════════════════════════════════════════
def admin_login_configured() -> bool:
    return bool(ADMIN_LOGIN and ADMIN_PASSWORD)


def _session_key() -> bytes:
    # Parol yoki token almashsa — barcha eski sessiyalar o'z-o'zidan bekor bo'ladi
    return hashlib.sha256(f"printchi-admin|{ADMIN_LOGIN}|{ADMIN_PASSWORD}|{ADMIN_TOKEN}".encode()).digest()


def check_admin_credentials(login: str, password: str) -> bool:
    if not admin_login_configured():
        return False
    ok_login = hmac.compare_digest(str(login).strip().lower().encode(), ADMIN_LOGIN.lower().encode())
    ok_pass = hmac.compare_digest(str(password).encode(), ADMIN_PASSWORD.encode())
    return ok_login and ok_pass


def issue_admin_session() -> dict:
    exp = int(time.time()) + ADMIN_SESSION_DAYS * 86400
    sig = hmac.new(_session_key(), f"s1.{exp}".encode(), hashlib.sha256).hexdigest()
    return {"token": f"s1.{exp}.{sig}", "expires_at": exp}


def _session_valid(token: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "s1" or not parts[1].isdigit() or not admin_login_configured():
        return False
    if int(parts[1]) < time.time():
        return False
    sig = hmac.new(_session_key(), f"s1.{parts[1]}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig.encode(), parts[2].encode())


def is_admin(req) -> bool:
    """X-Admin-Token: login/parol bilan olingan sessiya kaliti yoki to'g'ridan-to'g'ri ADMIN_TOKEN."""
    token = req.headers.get("X-Admin-Token", "") or req.args.get("admin_token", "")
    if not token:
        return False
    if token.startswith("s1."):
        return _session_valid(token)
    return bool(ADMIN_TOKEN) and hmac.compare_digest(token.encode(), ADMIN_TOKEN.encode())


# ══════════════════════════════════════════════════════════
# Telegram: admin xabarlari va inline tasdiq tugmalari
# ══════════════════════════════════════════════════════════
def telegram_enabled() -> bool:
    # Demo rejimida haqiqiy adminga xabar yuborilmaydi
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) and not DEMO_AUTO_CONFIRM


def _tg(method: str, payload: dict, timeout: int = 8):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def tg_send(text: str, buttons: list | None = None):
    if not telegram_enabled():
        return None
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    try:
        return _tg("sendMessage", payload)
    except Exception as e:
        logger.warning(f"Telegram xabar xatosi: {e}")
        return None


def order_summary(o: dict) -> str:
    kind = {"file": "📄 Fayl", "template": "📋 Shablon"}.get(o.get("kind"), "📄")
    return (f"{kind}: <code>{o.get('filename', '')}</code>\n"
            f"Sahifa: {o.get('pages', 1)} × {o.get('copies', 1)} nusxa • "
            f"{'Rangli' if o.get('color_mode') == 'color' else 'Oq-qora'}\n"
            f"💰 <b>{int(o.get('amount', 0)):,} so'm</b>".replace(",", " "))


def notify_claim(o: dict):
    """Mijoz 'To'ladim' bosganda adminga xabar. Kartaga avtomatik tasdiq ishlasa — faqat ma'lumot."""
    auto = False
    try:
        import sys
        # app.py allaqachon yuklangan (gunicorn: "app", python app.py: "__main__") — qayta import qilinmaydi
        for name in ("app", "__main__"):
            fn = getattr(sys.modules.get(name), "auto_payment_alive", None)
            if fn:
                auto = bool(fn())
                break
    except Exception:
        pass
    if auto:
        text = (f"⏳ <b>#{o['id']}: mijoz \"To'ladim\" dedi</b>\n{order_summary(o)}\n\n"
                f"To'lov avtomatik tekshirilmoqda — pul tushsa o'zi tasdiqlanadi.\n"
                f"✅ ni faqat pul tushganini o'zingiz ko'rsangiz bosing.")
    else:
        text = (f"🧾 <b>To'lov tasdig'i kerak — #{o['id']}</b>\n{order_summary(o)}\n\n"
                f"Kartangizga shu summa tushganini tekshiring.")
    tg_send(
        text,
        buttons=[[{"text": "✅ Tasdiqlash", "callback_data": f"pay:{o['id']}"},
                  {"text": "❌ Rad etish", "callback_data": f"rej:{o['id']}"}]],
    )


class TelegramPoller(threading.Thread):
    """
    getUpdates long-polling — Raspberry Pi da tashqi webhook/port ochish shart emas.
    Faqat TELEGRAM_CHAT_ID dagi admin tugmalari qabul qilinadi.
    DIQQAT: shu bot tokenini boshqa dastur getUpdates bilan ishlatmasligi kerak (409 Conflict).
    """
    def __init__(self, on_confirm, on_reject, on_reprint):
        super().__init__(daemon=True, name="telegram-poller")
        self.on_confirm, self.on_reject, self.on_reprint = on_confirm, on_reject, on_reprint
        self.offset = 0

    def run(self):
        logger.info("Telegram tasdiq boti ishga tushdi")
        while True:
            try:
                res = _tg("getUpdates", {"offset": self.offset, "timeout": 25,
                                         "allowed_updates": ["callback_query"]}, timeout=35)
                for upd in res.get("result", []):
                    self.offset = upd["update_id"] + 1
                    cq = upd.get("callback_query")
                    if cq:
                        self.handle(cq)
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    logger.error("Telegram 409: bu bot tokeni boshqa joyda ishlatilmoqda. Alohida bot oching.")
                    time.sleep(60)
                else:
                    logger.warning(f"Telegram getUpdates HTTP {e.code}")
                    time.sleep(10)
            except Exception as e:
                logger.debug(f"Telegram polling: {e}")
                time.sleep(5)

    def handle(self, cq: dict):
        chat_id = str(cq.get("message", {}).get("chat", {}).get("id", ""))
        data = cq.get("data", "")
        answer = "Ruxsat yo'q"
        if chat_id == str(TELEGRAM_CHAT_ID) and ":" in data:
            action, oid = data.split(":", 1)
            handler = {"pay": self.on_confirm, "rej": self.on_reject, "rep": self.on_reprint}.get(action)
            answer = handler(oid, "TELEGRAM_ADMIN") if handler else "Noma'lum amal"
            try:
                msg = cq["message"]
                _tg("editMessageText", {
                    "chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                    "parse_mode": "HTML",
                    "text": (msg.get("text", "") + f"\n\n➡️ {answer}")[:4000],
                })
            except Exception:
                pass
        try:
            _tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": answer[:190]})
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
# Click Merchant (SHOP API) imzo tekshiruvi
# ══════════════════════════════════════════════════════════
def click_sign_ok(form, action: int) -> bool:
    if not CLICK_SECRET_KEY:
        return False
    parts = [form.get("click_trans_id", ""), form.get("service_id", ""), CLICK_SECRET_KEY,
             form.get("merchant_trans_id", "")]
    if action == 1:
        parts.append(form.get("merchant_prepare_id", ""))
    parts += [form.get("amount", ""), form.get("action", ""), form.get("sign_time", "")]
    expected = hashlib.md5("".join(parts).encode()).hexdigest()
    return hmac.compare_digest(expected, form.get("sign_string", "").lower())


# ══════════════════════════════════════════════════════════
# Payme Merchant API
# ══════════════════════════════════════════════════════════
def payme_auth_ok(req) -> bool:
    if not PAYME_KEY:
        return False
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode()
    except Exception:
        return False
    return hmac.compare_digest(decoded, f"Paycom:{PAYME_KEY}")


def payme_error(req_id, code: int, uz: str, data=None):
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": {"uz": uz, "ru": uz, "en": uz}, "data": data}}


# Modul import qilingan zahoti mavjud buyurtmalarni o'qiymiz
try:
    load_state()
except Exception:
    pass

