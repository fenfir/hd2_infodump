#!/usr/bin/env python3
"""
hd1_scan.py - Walk the HD1/HD2 address space looking for populated regions.

Sends b1=0x0F, size=0x80 reads from 0x0000 through 0xFFFF and reports:
  - Which 128-byte blocks return a valid response (all reads should, on this
    radio firmware - we want to confirm)
  - Which blocks contain non-0xff, non-0x00 data
  - Where any needle strings (e.g. the known channel name) are found

Writes the full raw scan to <out>.scan.bin so you can re-parse offline.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import serial

SYNC = 0x68
TERMINATOR = 0x10
CHUNK = 0x80


def csum(addr: int, size: int) -> int:
    addr_lo = addr & 0xFF
    addr_hi = (addr >> 8) & 0xFF
    return (0xFF - (0x10 + addr_hi + ((addr_lo + size - 1) >> 7))) & 0xFF


def build_cmd(addr: int, size: int = CHUNK, *, b1: int = 0x0F, percent: int = 0) -> bytes:
    return bytes([
        SYNC, b1, 0x00, 0x01,
        percent & 0xFF,
        csum(addr, size),
        size & 0xFF, 0x00,
        addr & 0xFF, (addr >> 8) & 0xFF,
        TERMINATOR,
    ])


class HD1:
    def __init__(self, port: str, *, timeout: float = 1.5):
        self.ser = serial.Serial(
            port=port, baudrate=119200,
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            rtscts=False, dsrdtr=False,
            timeout=timeout, write_timeout=timeout,
            exclusive=True,
        )
        self.ser.rts = True
        self.ser.dtr = True
        time.sleep(0.2)
        self._drain()

    def _drain(self, quiet_for: float = 1.0, max_wait: float = 10.0):
        last = time.monotonic()
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            self.ser.timeout = 0.1
            chunk = self.ser.read(4096)
            if chunk:
                last = time.monotonic()
            elif time.monotonic() - last >= quiet_for:
                break
        self.ser.reset_input_buffer()

    def get_version(self) -> bytes:
        self.ser.reset_input_buffer()
        self.ser.write(b"GetVer")
        self.ser.flush()
        time.sleep(0.3)
        return bytes(self.ser.read(self.ser.in_waiting or 256))

    def read_chunk(self, addr: int, *, retries: int = 2) -> tuple[bytes, str]:
        cmd = build_cmd(addr, CHUNK)
        expected = 10 + CHUNK + 1  # 139
        transmit_time = (expected * 10) / 119200.0 + 0.1
        for attempt in range(retries + 1):
            self.ser.reset_input_buffer()
            self.ser.write(cmd)
            self.ser.flush()
            time.sleep(transmit_time)
            buf = bytearray()
            deadline = time.monotonic() + 1.0
            while True:
                pending = self.ser.in_waiting
                if pending:
                    buf.extend(self.ser.read(pending))
                if len(buf) >= expected:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.03)
            if len(buf) == expected and buf[-1] == TERMINATOR:
                return bytes(buf[10:-1]), "OK"
        if not buf:
            return b"", "TIMEOUT"
        return bytes(buf), f"SHORT({len(buf)}/{expected})"

    def close(self):
        try: self.ser.close()
        except: pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--out", default="scan", help="Output prefix")
    ap.add_argument("--start", type=lambda x: int(x, 0), default=0x0000)
    ap.add_argument("--end", type=lambda x: int(x, 0), default=0xFFFF,
                    help="Inclusive end address (default 0xFFFF)")
    ap.add_argument("--step", type=lambda x: int(x, 0), default=CHUNK,
                    help="Step size; set > 0x80 for sparse probing")
    ap.add_argument("--needle", action="append", default=[],
                    help="ASCII string to flag matches on (repeatable)")
    args = ap.parse_args()

    out_prefix = Path(args.out)
    scan_path = out_prefix.with_suffix(".scan.bin")
    map_path = out_prefix.with_suffix(".scan.map")

    needles = [n.encode() for n in args.needle]
    # Also always scan for 'KC' 'N1' 'W1' 'AA' style callsign prefixes
    # The user specified:  446.19250 MHz, 435.32500 MHz, "shitPostin"
    # Hunt for these too.
    always = [b"shitPostin", b"shit", b"Postin"]
    needles.extend(always)

    print(f"Scanning 0x{args.start:04x}..0x{args.end:04x} step 0x{args.step:x}")
    print(f"Needles: {[n.decode(errors='replace') for n in needles]}")

    hd1 = HD1(port=args.port)
    interrupted = {"flag": False}
    def sigint(s, f):
        interrupted["flag"] = True
        print("\nInterrupted...", file=sys.stderr)
    signal.signal(signal.SIGINT, sigint)

    ver = hd1.get_version()
    if b"HD" not in ver:
        print("ERROR: GetVer failed", file=sys.stderr)
        sys.exit(2)
    print(f"Radio: {ver[:48]!r}")

    scan_fp = open(scan_path, "wb")
    map_fp = open(map_path, "w")
    map_fp.write("# addr size status non_trivial first_hit\n")

    ok = bad = 0
    hits: list[tuple[int, bytes, int]] = []
    addr = args.start
    try:
        while addr <= args.end:
            if interrupted["flag"]:
                break
            data, status = hd1.read_chunk(addr)
            if status == "OK":
                ok += 1
                # Count non-trivial bytes (not 0xff and not 0x00)
                non_triv = sum(1 for b in data if b not in (0x00, 0xFF))
                # Record in map
                map_fp.write(f"0x{addr:04x} {CHUNK} OK {non_triv}\n")
                # Record raw data for offline parsing (just the payload)
                scan_fp.write(b"DATA" + addr.to_bytes(4,"little") + len(data).to_bytes(4,"little") + data)
                # Needle search
                for needle in needles:
                    idx = data.find(needle)
                    if idx >= 0:
                        hits.append((addr + idx, needle, idx))
                        print(f"  HIT @ 0x{addr + idx:04x}: {needle!r} (block 0x{addr:04x})")
                if non_triv > 0 and addr % 0x400 == 0:
                    print(f"  0x{addr:04x}: {non_triv} bytes of data")
            else:
                bad += 1
                map_fp.write(f"0x{addr:04x} {CHUNK} {status} 0\n")
                print(f"  0x{addr:04x}: {status}")
            map_fp.flush()
            scan_fp.flush()
            if addr % 0x1000 == 0:
                pct = (addr - args.start) * 100 / max(1, args.end - args.start)
                print(f"  ... 0x{addr:04x} pct={pct:.0f}% ok={ok} bad={bad}", file=sys.stderr)
            addr += args.step
    finally:
        hd1.close()
        scan_fp.close()
        map_fp.close()

    print()
    print(f"  ok:   {ok}")
    print(f"  bad:  {bad}")
    print(f"  hits: {len(hits)}")
    for a, n, off in hits:
        print(f"    0x{a:04x}: {n!r}")
    print(f"  scan: {scan_path}")
    print(f"  map:  {map_path}")


if __name__ == "__main__":
    main()
