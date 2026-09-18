"""
tunnel_sync.py — Avtomatik Tunnel Sync xizmati
Raspberry Pi-dagi faol Cloudflare / Ngrok tunnel manzilini aniqlaydi va
GitHub Pages uchun dinamik relay (ntfy) ga yuklaydi.
"""

import time
import subprocess
import urllib.request
import re
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [TUNNEL_SYNC]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tunnel_sync")

NTFY_TOPIC = "smart_printer_asil2004_tunnel_url"
LOG_FILE = Path("/home/cail/smart-printchi/cloudflared.log")


def get_current_tunnel_url() -> str:
    if not LOG_FILE.exists():
        return ""
    try:
        content = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
        matches = re.findall(r"https://[a-zA-Z0-9-]+.trycloudflare.com", content)
        if matches:
            return matches[-1]
    except Exception as e:
        logger.warning(f"Log oqishda xatolik: {e}")
    return ""


def publish_url(url: str):
    if not url:
        return
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=url.encode("utf-8"),
            headers={"Title": "Smart Printer Live URL"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                logger.info(f"URL muvaffaqiyatli sinxronlandi: {url}")
    except Exception as e:
        logger.warning(f"URL yuborishda xatolik: {e}")


def main():
    logger.info("Tunnel Sync daemon ishga tushdi...")
    last_url = ""
    while True:
        try:
            url = get_current_tunnel_url()
            if not url:
                try:
                    res = subprocess.run(
                        ["journalctl", "-u", "smart-cloudflared", "-n", "30", "--no-pager"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
                    )
                    matches = re.findall(r"https://[a-zA-Z0-9-]+.trycloudflare.com", res.stdout)
                    if matches:
                        url = matches[-1]
                except Exception:
                    pass

            if url and url != last_url:
                publish_url(url)
                last_url = url
        except Exception as err:
            logger.error(f"Kutilmagan xatolik: {err}")
        time.sleep(20)


if __name__ == "__main__":
    main()
