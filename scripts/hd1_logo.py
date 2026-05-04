#!/usr/bin/env python3
"""
hd1_logo.py - Read the boot logo from an Ailunce HD1/HD2 radio.

Replays the exact 40-command sequence captured from the official software
in ../pylunce/dump/hd2_read_logo.pcapng:

    Frame: 68 31 00 01 [pct] cd 00 04 [block_lo] [block_hi] 10
    Block range: 0x1dd0..0x1df7 (40 blocks * 1024 bytes = 40 KiB)
    pct: ramps 0x02..0x64 (display percentage)

Response (1035 bytes):
    [echo of first 10 bytes of cmd] [1024 bytes data] [0x10]
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

START_BLOCK = 0x1DD0
END_BLOCK = 0x1DF7  # inclusive
BLOCK_SIZE = 1024
RESP_LEN = 10 + BLOCK_SIZE + 1  # 1035

# Match the official software's percent ramp: 02, 05, 07, 0a, 0c, 0f, 11, 14, ...
PCT_STEP = 2.5


def build_cmd(block_addr: int, percent: int) -> bytes:
    return bytes([
        SYNC,
        0x31, 0x00, 0x01,
        percent & 0xFF,
        0xCD,                           # checksum (constant for this region)
        0x00, 0x04,                     # size = 0x0400 = 1024
        block_addr & 0xFF, (block_addr >> 8) & 0xFF,
        TERMINATOR,
    ])


def hexdump(data: bytes, n: int = 32) -> str:
    head = data[:n]
    return f"{' '.join(f'{b:02x}' for b in head)}{' ...' if len(data) > n else ''}"


class HD1:
    def __init__(self, port: str, *, timeout: float, trace_fp=None):
        self.trace_fp = trace_fp
        self.ser = serial.Serial(
            port=port,
            baudrate=119200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            rtscts=False, dsrdtr=False,
            timeout=timeout, write_timeout=timeout,
            exclusive=True,
        )
        self.ser.rts = True
        self.ser.dtr = True

    def trace(self, msg: str):
        if self.trace_fp:
            self.trace_fp.write(msg + "\n")
            self.trace_fp.flush()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def get_version(self) -> bytes:
        self.ser.reset_input_buffer()
        self.ser.write(b"GetVer")
        self.ser.flush()
        time.sleep(0.2)
        buf = bytearray()
        deadline = time.monotonic() + min(self.ser.timeout, 1.5)
        while time.monotonic() < deadline:
            chunk = self.ser.read(256)
            if not chunk:
                break
            buf.extend(chunk)
        self.trace(f"TX GetVer")
        self.trace(f"RX GetVer  {len(buf)} bytes  {hexdump(bytes(buf))}")
        return bytes(buf)

    def read_block(self, block_addr: int, percent: int) -> tuple[bytes, str]:
        cmd = build_cmd(block_addr, percent)
        self.ser.reset_input_buffer()
        self.ser.write(cmd)
        self.ser.flush()
        self.trace(f"TX block=0x{block_addr:04x} pct={percent:>3}  {hexdump(cmd)}")

        buf = bytearray()
        deadline = time.monotonic() + self.ser.timeout
        while len(buf) < RESP_LEN:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self.ser.timeout = max(0.05, remaining)
            chunk = self.ser.read(RESP_LEN - len(buf))
            if not chunk:
                break
            buf.extend(chunk)

        self.trace(f"RX block=0x{block_addr:04x}  got {len(buf)}/{RESP_LEN}  {hexdump(bytes(buf))}")

        if len(buf) == 0:
            return b"", "TIMEOUT"
        if len(buf) < RESP_LEN:
            return bytes(buf), f"SHORT({len(buf)}/{RESP_LEN})"
        if buf[-1] != TERMINATOR:
            return bytes(buf), f"BAD_TERM(0x{buf[-1]:02x})"
        # Response echoes request bytes 0-9, except byte 2 is 0x02 (response flag)
        # instead of 0x00. Validate everything else.
        echo = bytes(buf[:10])
        expected_echo = cmd[:2] + b"\x02" + cmd[3:10]
        if echo != expected_echo:
            return bytes(buf), f"BAD_ECHO({echo.hex()} != {expected_echo.hex()})"
        return bytes(buf), "OK"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True, help="Serial device, e.g. /dev/cu.usbserial-21330")
    ap.add_argument("--out", required=True, help="Output prefix")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()

    out_path = Path(args.out)
    log_path = out_path.with_suffix(".log")
    bin_path = out_path.with_suffix(".bin")
    raw_path = out_path.with_suffix(".raw")

    trace_fp = open(log_path, "w") if args.trace else None
    if trace_fp:
        print(f"Trace log: {log_path}")
    bin_fp = open(bin_path, "wb")
    raw_fp = open(raw_path, "wb")
    print(f"Logo bin:  {bin_path}")
    print(f"Raw:       {raw_path}")

    hd1 = HD1(port=args.port, timeout=args.timeout, trace_fp=trace_fp)

    interrupted = {"flag": False}

    def handle_sigint(signum, frame):
        interrupted["flag"] = True
        print("\nInterrupted...", file=sys.stderr)
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        ver = hd1.get_version()
        if not ver or b"HD" not in ver:
            print("ERROR: GetVer failed - radio not responding.", file=sys.stderr)
            sys.exit(2)
        printable = bytes(b if 32 <= b < 127 else 0x2e for b in ver).decode("ascii", errors="replace")
        print(f"Radio:     {printable.rstrip('.')}")

        ok = bad = 0
        pct_f = 0.0
        for n, addr in enumerate(range(START_BLOCK, END_BLOCK + 1)):
            if interrupted["flag"]:
                break
            pct_f += PCT_STEP
            pct_byte = min(100, round(pct_f))
            resp, status = hd1.read_block(addr, pct_byte)
            raw_fp.write(addr.to_bytes(4, "little") + len(resp).to_bytes(4, "little") + resp)
            raw_fp.flush()

            if status == "OK":
                bin_fp.write(resp[10:-1])
                bin_fp.flush()
                ok += 1
            else:
                bad += 1
                print(f"  block 0x{addr:04x} pct={pct_byte:>3}: {status}", file=sys.stderr)
                bin_fp.write(b"\x00" * BLOCK_SIZE)

            print(f"  block 0x{addr:04x} pct={pct_byte:>3}  ok={ok} bad={bad}", file=sys.stderr)
        print()
        print(f"  ok:  {ok}")
        print(f"  bad: {bad}")
        print(f"  bin: {bin_path} ({bin_path.stat().st_size} bytes)")
    finally:
        hd1.close()
        bin_fp.close()
        raw_fp.close()
        if trace_fp:
            trace_fp.close()


if __name__ == "__main__":
    main()
