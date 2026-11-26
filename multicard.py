"""
Rahmat Pro / Multicard to'lov shlyuzi (hosted checkout).

Hujjat: https://docs.multicard.uz  (Rahmat — Multicard Payment AJ mahsuloti)

Oqim:
  1. Server buyurtma summasi bilan invoys yaratadi   POST {base}/payment/invoice  (Bearer token)
  2. Mijozga checkout_url (QR yoki havola) ko'rsatiladi — Rahmat/Click/Payme/karta bilan to'laydi
  3. Multicard callback_url ga POST yuboradi, `sign` tekshiriladi → buyurtma PAID → chop etish
  4. Callback kelmay qolsa: GET {base}/payment/invoice/{uuid} bilan holat so'raladi (zaxira)

Sozlamalar (.env yoki Render → Environment):
  MULTICARD_APPLICATION_ID, MULTICARD_SECRET, MULTICARD_STORE_ID   — Rahmat Pro / Multicard beradi
  MULTICARD_BASE_URL       — standart https://mesh.multicard.uz  (sinov: https://dev-mesh.multicard.uz)
  MULTICARD_CALLBACK_URL   — serverning ochiq manzili + /api/payments/multicard/callback
  MULTICARD_RETURN_URL     — to'lovdan keyin mijoz qaytadigan sahifa (ixtiyoriy)
  MULTICARD_OFD_MXIK, MULTICARD_OFD_PACKAGE_CODE — fiskal chek uchun MXIK va o'lchov birligi kodi
  MULTICARD_OFD_NAME       — chekdagi xizmat nomi (standart: "Hujjat chop etish xizmati")
  MULTICARD_OFD_VAT        — QQS foizi (standart 0)
  MULTICARD_OFD_TIN        — kompaniya STIR/INN (ixtiyoriy)
  MULTICARD_CALLBACK_IPS   — vergul bilan IP ro'yxati; bo'sh bo'lsa IP tekshirilmaydi (sign baribir shart)
"""
import hashlib
import hmac
import logging
import os
import threading
import time

import requests

logger = logging.getLogger("smart_web_printchi.multicard")

APPLICATION_ID = os.environ.get("MULTICARD_APPLICATION_ID", "").strip()
SECRET         = os.environ.get("MULTICARD_SECRET", "").strip()
STORE_ID       = os.environ.get("MULTICARD_STORE_ID", "").strip()
BASE_URL       = os.environ.get("MULTICARD_BASE_URL", "https://mesh.multicard.uz").strip().rstrip("/")
CALLBACK_URL   = os.environ.get("MULTICARD_CALLBACK_URL", "").strip()
RETURN_URL     = os.environ.get("MULTICARD_RETURN_URL", "").strip()
OFD_MXIK       = os.environ.get("MULTICARD_OFD_MXIK", "").strip()
OFD_PACKAGE    = os.environ.get("MULTICARD_OFD_PACKAGE_CODE", "").strip()
OFD_NAME       = os.environ.get("MULTICARD_OFD_NAME", "Hujjat chop etish xizmati").strip()
OFD_VAT        = int(os.environ.get("MULTICARD_OFD_VAT", "0") or 0)
OFD_TIN        = os.environ.get("MULTICARD_OFD_TIN", "").strip()
CALLBACK_IPS   = {ip.strip() for ip in os.environ.get("MULTICARD_CALLBACK_IPS", "").split(",") if ip.strip()}

TIMEOUT = 15
_token = {"value": "", "until": 0.0}
_token_lock = threading.Lock()


class MulticardError(Exception):
    pass


def enabled() -> bool:
    return bool(APPLICATION_ID and SECRET and STORE_ID and OFD_MXIK and OFD_PACKAGE)


def missing_settings() -> list:
    names = {"MULTICARD_APPLICATION_ID": APPLICATION_ID, "MULTICARD_SECRET": SECRET,
             "MULTICARD_STORE_ID": STORE_ID, "MULTICARD_OFD_MXIK": OFD_MXIK,
             "MULTICARD_OFD_PACKAGE_CODE": OFD_PACKAGE}
    return [k for k, v in names.items() if not v]


def _store_id():
    return int(STORE_ID) if STORE_ID.isdigit() else STORE_ID


# ── Token (24 soat amal qiladi — keshlanadi) ─────────────
def get_token(force: bool = False) -> str:
    with _token_lock:
        if not force and _token["value"] and time.time() < _token["until"]:
            return _token["value"]
        r = requests.post(f"{BASE_URL}/auth", json={"application_id": APPLICATION_ID, "secret": SECRET},
                          timeout=TIMEOUT)
        try:
            data = r.json()
        except ValueError:
            data = {}
        token = data.get("token")
        if not r.ok or not token:
            raise MulticardError(f"Multicard token olinmadi (HTTP {r.status_code})")
        _token["value"] = token
        _token["until"] = time.time() + 23 * 3600   # 24 soatdan biroz oldin yangilanadi
        return token


def _request(method: str, path: str, **kw) -> dict:
    for attempt in (1, 2):
        headers = {"Authorization": f"Bearer {get_token(force=attempt == 2)}"}
        r = requests.request(method, f"{BASE_URL}{path}", headers=headers, timeout=TIMEOUT, **kw)
        if r.status_code == 401 and attempt == 1:
            continue  # token eskirgan — yangisini olib qayta urinamiz
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not r.ok or not data.get("success"):
            err = data.get("error") or {}
            raise MulticardError(f"Multicard {method} {path}: HTTP {r.status_code} "
                                 f"{err.get('code', '')} {err.get('details', '')}".strip())
        return data.get("data") or {}
    raise MulticardError("Multicard: avtorizatsiya xatosi")


# ── Invoys ────────────────────────────────────────────────
def create_invoice(order_id: str, amount_sum: int, callback_url: str, ttl_seconds: int = 1800,
                   lang: str = "uz") -> dict:
    """Invoys yaratadi. amount_sum — so'mda (Multicard tiyinda qabul qiladi: ×100)."""
    tiyin = int(amount_sum) * 100
    item = {"qty": 1, "price": tiyin, "total": tiyin, "mxik": OFD_MXIK,
            "package_code": OFD_PACKAGE, "name": f"{OFD_NAME} #{order_id}"[:128], "vat": OFD_VAT}
    if OFD_TIN:
        item["tin"] = OFD_TIN
    body = {"store_id": _store_id(), "amount": tiyin, "invoice_id": order_id,
            "callback_url": callback_url, "lang": lang, "ttl": int(ttl_seconds), "ofd": [item]}
    if RETURN_URL:
        body["return_url"] = RETURN_URL
    data = _request("POST", "/payment/invoice", json=body)
    if not data.get("uuid") or not data.get("checkout_url"):
        raise MulticardError("Multicard javobida uuid/checkout_url yo'q")
    return data


def get_invoice(uuid: str) -> dict:
    return _request("GET", f"/payment/invoice/{uuid}")


def cancel_invoice(uuid: str) -> None:
    _request("DELETE", f"/payment/invoice/{uuid}")


def invoice_paid(inv: dict) -> bool:
    pay = inv.get("payment") or {}
    return str(pay.get("status", "")).lower() == "success"


# ── Callback tekshiruvi ───────────────────────────────────
def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def sign_ok(body: dict) -> bool:
    """
    Ikki xil callback formati qo'llab-quvvatlanadi:
      - success callback: md5({store_id}{invoice_id}{amount}{secret})
      - webhook (holat o'zgarishi): md5({uuid}{amount}{secret})
    """
    got = str(body.get("sign", "")).strip().lower()
    if not got or not SECRET:
        return False
    candidates = [
        _md5(f"{body.get('store_id', '')}{body.get('invoice_id', '')}{body.get('amount', '')}{SECRET}"),
        _md5(f"{body.get('uuid', '')}{body.get('amount', '')}{SECRET}"),
    ]
    return any(hmac.compare_digest(got, c) for c in candidates)


def ip_allowed(remote_ip: str) -> bool:
    return not CALLBACK_IPS or remote_ip in CALLBACK_IPS
