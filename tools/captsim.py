#!/usr/bin/env python3
"""
captsim — Canon LBP3010 CAPT printer emulatori (CUPS backend)
=============================================================
Haqiqiy USB printer o'rniga turadi va captdriver (rastertocapt) bilan
CAPT protokoli bo'yicha "gaplashadi":
  * side-channel (fd 4): GET_DEVICE_ID → LBP3010 IEEE-1284 ID, DRAIN_OUTPUT → OK
  * back-channel (fd 3): har bir so'rov-buyruqqa printer javobi
  * stdin: drayver yuborgan CAPT kadrlar oqimi
Natija: /var/spool/capt-out/<job>.json (sahifalar, o'lcham, baytlar) va .capt (xom oqim)

Muhit: CAPTSIM_NOPAPER=1 — qog'oz tugagan holatni taqlid qiladi.
"""
import json
import os
import select
import struct
import sys
import time

OUT_DIR = os.environ.get("CAPTSIM_OUT", "/var/spool/capt-out")
DEVICE_ID = ("MFG:Canon;CMD:CAPT;SOJ:CAPT;MDL:LBP3010/LBP3018/LBP3050;"
             "CLS:PRINTER;DES:Canon LBP3010/LBP3018/LBP3050;CID:CA_CAPT_LBP3010;")

# Javob kutiladigan buyruqlar (capt_sendrecv)
REPLY_CMDS = {0xA1A1, 0xA3A2, 0xA2A0, 0xE1A2, 0xA0A8, 0xA0A1, 0xE0A0, 0xE1A1,
              0xE0A3, 0xE0A2, 0xE0A4, 0xE0A5, 0xE0A6, 0xE0A7, 0xE0A9, 0xE0BA}
NAMES = {0xA1A1: "IDENT", 0xA3A2: "START_0", 0xA2A0: "JOB_BEGIN", 0xE1A2: "GPIO",
         0xA0A8: "CHKXSTATUS", 0xE0A0: "CHKSTATUS", 0xE1A1: "JOB_SETUP", 0xE0A7: "FIRE",
         0xE0A9: "JOB_END", 0xD0A9: "SET_PARMS", 0xC0A0: "PRINT_DATA", 0xC0A4: "PRINT_DATA_END",
         0xE0A3: "START_1", 0xE0A2: "START_2", 0xE0A4: "START_3", 0xE0A5: "UPLOAD_2"}

SC_FD, BC_FD = 4, 3
SC_GET_DEVICE_ID, SC_DRAIN_OUTPUT = 4, 2


def log(msg):
    sys.stderr.write(f"DEBUG: captsim: {msg}\n")
    sys.stderr.flush()


class Printer:
    def __init__(self, job_id):
        self.job_id = job_id
        self.pages = []           # har sahifa: {"bytes":…, "bands":…, "params":…}
        self.cur = None
        self.completed = 0
        self.decoding = 0
        self.failed_attempts = 0
        self.nopaper_seen = False
        self.cmd_log = []
        self.raw = bytearray()

    def paper_missing(self):
        # Har so'rovda tekshiriladi: test davomida NOPAPER faylini o'chirish = qog'oz solish
        return (os.environ.get("CAPTSIM_NOPAPER") == "1"
                or os.path.exists(os.path.join(OUT_DIR, "NOPAPER")))

    def status_payload(self):
        nopaper = self.paper_missing()
        self.nopaper_seen = self.nopaper_seen or nopaper
        p = bytearray(40)
        s0 = (1 << 1) if nopaper else 0          # CAPT_FL_NOPAPER1
        struct.pack_into("<H", p, 0, s0)
        struct.pack_into("<H", p, 8, (1 << 14) if nopaper else 0)   # NOPAPER2
        struct.pack_into("<H", p, 10, 0 if nopaper else (1 << 7))   # nERROR (1 = xato yo'q)
        for off, val in ((14, self.decoding), (16, self.decoding), (18, self.completed),
                         (20, self.completed), (34, self.decoding)):
            struct.pack_into("<H", p, off, val & 0xFFFF)
        return bytes(p)

    def reply(self, cmd, data):
        if cmd in (0xA0A8, 0xE0A0):
            payload = self.status_payload()
        elif cmd == 0xA2A0:
            # Haqiqiy printer kabi jami 8 bayt: drayver javobni buf[8] ga ko'chiradi
            payload = struct.pack("<HH", 0, 0x0042)  # job id = 0x42
        else:
            payload = b"\x00\x00"
        frame = struct.pack("<HH", cmd, 4 + len(payload)) + payload
        os.write(BC_FD, frame)

    def handle(self, cmd, data):
        name = NAMES.get(cmd, hex(cmd))
        if not self.cmd_log or self.cmd_log[-1][0] != name:
            self.cmd_log.append([name, 1])
        else:
            self.cmd_log[-1][1] += 1
        if cmd == 0xD0A9:                         # SET_PARMS → yangi sahifa
            params = {}
            off = 0
            while off + 4 <= len(data):
                sc, sl = struct.unpack_from("<HH", data, off)
                sub = data[off + 4: off + sl]
                if sc == 0xD0A0 and len(sub) >= 34:
                    # pageparms: margin/qator o'lchamlari — eni/bo'yi baytlari
                    size_code = sub[4]
                    params["paper"] = {0x02: "A4", 0x03: "A5", 0x0D: "Letter",
                                       0x0C: "Legal"}.get(size_code, hex(size_code))
                    params["darkness"] = sub[8]
                    params["toner_save"] = sub[19]
                    params["line_bytes"] = struct.unpack_from("<H", sub, 26)[0]
                    params["lines"] = struct.unpack_from("<H", sub, 28)[0]
                    params["paper_w"] = struct.unpack_from("<H", sub, 30)[0]
                    params["paper_h"] = struct.unpack_from("<H", sub, 32)[0]
                off += max(sl, 4)
            self.cur = {"bytes": 0, "bands": 0, "params": params}
        elif cmd == 0xC0A0 and self.cur is not None:
            self.cur["bytes"] += len(data)
            self.cur["bands"] += 1
        elif cmd == 0xC0A4 and self.cur is not None:
            self.cur = dict(self.cur)
            if self.paper_missing():
                # sahifa qabul qilindi, lekin qog'oz yo'q — chiqmaydi, drayver qayta yuboradi
                self.failed_attempts += 1
                self.decoding = self.completed + 1
            else:
                self.pages.append(self.cur)
                self.completed += 1
                self.decoding = self.completed
            self.cur = None
        if cmd in REPLY_CMDS:
            self.reply(cmd, data)

    def save(self):
        os.makedirs(OUT_DIR, exist_ok=True)
        base = os.path.join(OUT_DIR, f"job{self.job_id}")
        with open(base + ".capt", "wb") as f:
            f.write(self.raw)
        with open(base + ".json", "w") as f:
            json.dump({"job": self.job_id, "pages_received": len(self.pages),
                       "pages_completed": self.completed, "pages": self.pages,
                       "commands": self.cmd_log, "raw_bytes": len(self.raw),
                       "nopaper_seen": self.nopaper_seen, "failed_attempts": self.failed_attempts, "time": time.time()}, f, indent=1)


def sc_read():
    hdr = os.read(SC_FD, 4)
    if len(hdr) < 4:
        return None, b""
    cmd, _st, ln = struct.unpack(">BBH", hdr)
    data = os.read(SC_FD, ln) if ln else b""
    return cmd, data


def sc_write(cmd, status, data=b""):
    os.write(SC_FD, struct.pack(">BBH", cmd, status, len(data)) + data)


def main():
    if len(sys.argv) == 1:
        print('direct captsim://lbp3010 "Canon LBP3010 (emulator)" "Canon LBP3010 CAPT emulator" '
              '"MFG:Canon;MDL:LBP3010/LBP3018/LBP3050;"')
        return 0
    job_id = sys.argv[1]
    infd = 0
    if len(sys.argv) >= 7:
        infd = os.open(sys.argv[6], os.O_RDONLY)
    pr = Printer(job_id)
    buf = bytearray()
    # USB uzilgan holat: haqiqiy usb backend kabi "printer kutilmoqda" deb turadi
    while os.path.exists(os.path.join(OUT_DIR, "NODEVICE")):
        sys.stderr.write("STATE: +connecting-to-device\nINFO: Waiting for printer to become available.\n")
        sys.stderr.flush()
        time.sleep(2)
    sys.stderr.write("STATE: -connecting-to-device\n")
    eof = False
    have_sc = True
    try:
        os.fstat(SC_FD)
    except OSError:
        have_sc = False
    while not eof:
        fds = [infd] + ([SC_FD] if have_sc else [])
        r, _, _ = select.select(fds, [], [], 30)
        if not r:
            log("30 s ma'lumot yo'q — tugatildi")
            break
        if have_sc and SC_FD in r:
            cmd, data = sc_read()
            if cmd is None:
                have_sc = False
            elif cmd == SC_GET_DEVICE_ID:
                sc_write(cmd, 1, DEVICE_ID.encode())  # 1 = CUPS_SC_STATUS_OK
            else:
                sc_write(cmd, 1, b"")  # DRAIN_OUTPUT va boshqalar → OK
        if infd in r:
            chunk = os.read(infd, 65536)
            if not chunk:
                eof = True
            else:
                pr.raw += chunk
                buf += chunk
            while len(buf) >= 4:
                cmd, ln = struct.unpack_from("<HH", buf, 0)
                if ln < 4:
                    log(f"noto'g'ri kadr uzunligi {ln}")
                    buf.clear()
                    break
                if len(buf) < ln:
                    break
                data = bytes(buf[4:ln])
                del buf[:ln]
                pr.handle(cmd, data)
    pr.save()
    log(f"qabul qilindi: {len(pr.pages)} sahifa, chiqdi: {pr.completed}")
    sys.stderr.write(f"INFO: LBP3010 emulator: {pr.completed} sahifa chop etildi\n")
    return 0 if (pr.completed == len(pr.pages) and pr.pages) else 1


if __name__ == "__main__":
    sys.exit(main())
