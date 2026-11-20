"""
cups_jobs.py — CUPS ish (job) holatini kuzatish
================================================
`lp` buyrug'i faylni faqat NAVBATGA qo'yadi. Qog'oz tugasa yoki USB uzilsa,
Canon LBP3010 (captdriver) buni CUPS'ga xabar qilmaydi — ish navbatda kutib turadi.
Shuning uchun buyurtma "PRINTED" deb faqat CUPS ishni "completed" qilganda belgilanadi.

Qo'shimcha paket kerak emas: CUPS bilan to'g'ridan-to'g'ri IPP (HTTP, localhost:631) orqali gaplashadi.
"""
import re
import struct
import urllib.request

CUPS_URL = "http://localhost:631"

JOB_STATES = {3: "pending", 4: "held", 5: "processing", 6: "stopped",
              7: "canceled", 8: "aborted", 9: "completed"}
FINAL_OK = {"completed"}
FINAL_BAD = {"canceled", "aborted"}


def parse_lp_job_id(lp_stdout: str):
    """'request id is Canon-LBP3010-14 (1 file(s))' → 14"""
    m = re.search(r"request id is \S+-(\d+)", lp_stdout or "")
    return int(m.group(1)) if m else None


def _attr(tag: int, name: str, value: bytes) -> bytes:
    n = name.encode()
    return struct.pack(">BH", tag, len(n)) + n + struct.pack(">H", len(value)) + value


def _extra_value(tag: int, value: bytes) -> bytes:
    return struct.pack(">BHH", tag, 0, len(value)) + value


def _ipp_request(op: int, printer: str, extra: bytes) -> dict:
    uri = f"ipp://localhost/printers/{printer}".encode()
    body = struct.pack(">HHI", 0x0200, op, 1) + b"\x01"
    body += _attr(0x47, "attributes-charset", b"utf-8")
    body += _attr(0x48, "attributes-natural-language", b"en")
    body += _attr(0x45, "printer-uri", uri)
    body += extra + b"\x03"
    req = urllib.request.Request(f"{CUPS_URL}/printers/{printer}", data=body,
                                 headers={"Content-Type": "application/ipp"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return _parse(r.read())


def _parse(data: bytes) -> dict:
    """IPP javobidan job-attributes guruhini oddiy dict ga o'giradi."""
    out, pos, name = {}, 8, None
    status = struct.unpack(">H", data[2:4])[0]
    out["_status"] = status
    while pos < len(data):
        tag = data[pos]; pos += 1
        if tag == 0x03:
            break
        if tag < 0x10:      # guruh ajratgichi
            continue
        nlen = struct.unpack(">H", data[pos:pos + 2])[0]; pos += 2
        if nlen:
            name = data[pos:pos + nlen].decode(errors="replace")
        pos += nlen
        vlen = struct.unpack(">H", data[pos:pos + 2])[0]; pos += 2
        raw = data[pos:pos + vlen]; pos += vlen
        if tag in (0x21, 0x23) and vlen == 4:
            val = struct.unpack(">i", raw)[0]
        else:
            val = raw.decode(errors="replace")
        if name in out and nlen == 0:
            out[name] = (out[name] if isinstance(out[name], list) else [out[name]]) + [val]
        else:
            out[name] = val
    return out


def get_job(printer: str, job_id: int) -> dict:
    """{'state': 'processing'|'completed'|..., 'reasons': ..., 'message': ...} yoki {'state': 'unknown'}"""
    try:
        keys = [b"job-state", b"job-state-reasons", b"job-printer-state-message"]
        extra = _attr(0x21, "job-id", struct.pack(">i", job_id))
        extra += _attr(0x44, "requested-attributes", keys[0])
        for k in keys[1:]:
            extra += _extra_value(0x44, k)
        res = _ipp_request(0x0009, printer, extra)   # Get-Job-Attributes
        state = JOB_STATES.get(res.get("job-state"), "unknown")
        return {"state": state, "reasons": res.get("job-state-reasons", ""),
                "message": res.get("job-printer-state-message", "")}
    except Exception as e:
        return {"state": "unknown", "error": str(e)}


def cancel_job(printer: str, job_id: int) -> bool:
    try:
        extra = _attr(0x21, "job-id", struct.pack(">i", job_id))
        extra += _attr(0x42, "requesting-user-name", b"root")
        res = _ipp_request(0x0008, printer, extra)   # Cancel-Job
        return res.get("_status", 0xFFFF) < 0x0100
    except Exception:
        return False
