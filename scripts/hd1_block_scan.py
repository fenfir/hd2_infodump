#!/usr/bin/env python3
"""
hd1_block_scan.py - Scan the b1=0x31 (1024-byte block) address space.

Probes block addresses 0x0000..0xFFFF using the 0x31 read protocol to find
populated regions outside our known codeplug ranges. Uses sparse stepping
(default: every 16 blocks) to cover the full 64K address space quickly, then
you can re-run with --step 1 on interesting ranges.

A block is "populated" if the radio returns a valid 1035-byte response with
non-trivial data (not all 0xFF / 0x00). Blocks that return only an 11-byte
echo (no data) or timeout are marked as empty/invalid.
"""

from __future__ import annotations

import argparse
import signal
import struct
import sys
import time
from pathlib import Path

import serial

SYNC = 0x68
TERMINATOR = 0x10
BLOCK_SIZE = 1024


def csum_31(addr: int) -> int:
    return (0xFF - (0x15 + ((addr - 0x88) >> 8))) & 0xFF


def build_cmd(addr: int, *, percent: int = 0) -> bytes:
    return bytes([
        SYNC, 0x31, 0x00, 0x01,
        percent & 0xFF,
        csum_31(addr),
        0x00, 0x04,  # size = 0x0400 (1024); size_hi MUST be 0x04
        addr & 0xFF, (addr >> 8) & 0xFF,
        TERMINATOR,
    ])


class HD1:
    def __init__(self, port: str, *, timeout: float = 2.0):
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

    def read_block(self, addr: int, *, retries: int = 2) -> tuple[bytes, str]:
        """Read a 1024-byte block at the given block address.

        Returns (data, status) where status is one of:
          "OK"       - got full 1035-byte response, data is 1024 bytes
          "ECHO"     - got only 11-byte echo (no data payload)
          "TIMEOUT"  - no response
          "SHORT(n)" - partial response
        """
        cmd = build_cmd(addr)
        expected = 10 + BLOCK_SIZE + 1  # 1035
        transmit_time = (expected * 10) / 119200.0 + 0.1

        for attempt in range(retries + 1):
            self.ser.reset_input_buffer()
            self.ser.write(cmd)
            self.ser.flush()
            time.sleep(transmit_time)

            buf = bytearray()
            deadline = time.monotonic() + 1.5
            while True:
                pending = self.ser.in_waiting
                if pending:
                    buf.extend(self.ser.read(pending))
                if len(buf) >= expected:
                    break
                # If we got exactly 11 bytes (echo only), don't wait longer
                if len(buf) == 11 and time.monotonic() - (deadline - 1.5) > 0.3:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.03)

            if len(buf) == expected and buf[-1] == TERMINATOR:
                return bytes(buf[10:-1]), "OK"
            if len(buf) == 11:
                return b"", "ECHO"

        if not buf:
            return b"", "TIMEOUT"
        return bytes(buf), f"SHORT({len(buf)}/{expected})"

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True)
    ap.add_argument("--out", default="block_scan", help="Output prefix")
    ap.add_argument("--start", type=lambda x: int(x, 0), default=0x0000)
    ap.add_argument("--end", type=lambda x: int(x, 0), default=0xFFFF,
                    help="Inclusive end block address (default 0xFFFF)")
    ap.add_argument("--step", type=lambda x: int(x, 0), default=16,
                    help="Block step (default 16 for sparse scan)")
    ap.add_argument("--needle", action="append", default=[],
                    help="ASCII string to search for in block data (repeatable)")
    args = ap.parse_args()

    out_prefix = Path(args.out)
    scan_path = out_prefix.with_suffix(".bscan.bin")
    map_path = out_prefix.with_suffix(".bscan.map")

    needles = [n.encode() for n in args.needle]
    needles.extend([b"Address", b"Book", b"book", b"addr"])

    total_blocks = (args.end - args.start) // args.step + 1
    print(f"Block scan 0x{args.start:04x}..0x{args.end:04x} step {args.step}")
    print(f"  ~{total_blocks} probes, needles: {[n.decode(errors='replace') for n in needles]}")

    hd1 = HD1(port=args.port)
    interrupted = {"flag": False}

    def sigint(s, f):
        interrupted["flag"] = True
        print("\nInterrupted...", file=sys.stderr)
    signal.signal(signal.SIGINT, sigint)

    ver = hd1.get_version()
    if b"HD" not in ver:
        print(f"ERROR: GetVer failed: {ver!r}", file=sys.stderr)
        sys.exit(2)
    print(f"Radio: {ver[:48]!r}")

    scan_fp = open(scan_path, "wb")
    map_fp = open(map_path, "w")
    map_fp.write("# block_addr status non_trivial\n")

    ok = echo = bad = data_blocks = 0
    hits: list[tuple[int, bytes, int]] = []
    addr = args.start

    try:
        while addr <= args.end:
            if interrupted["flag"]:
                break
            data, status = hd1.read_block(addr)

            if status == "OK":
                ok += 1
                non_triv = sum(1 for b in data if b not in (0x00, 0xFF))
                map_fp.write(f"0x{addr:04x} OK {non_triv}\n")

                if non_triv > 0:
                    data_blocks += 1
                    # Save block data
                    scan_fp.write(b"BLK " + struct.pack("<HH", addr, len(data)) + data)
                    print(f"  0x{addr:04x}: OK  {non_triv:>4} non-trivial bytes  ***DATA***")

                    # Needle search
                    for needle in needles:
                        idx = data.find(needle)
                        if idx >= 0:
                            hits.append((addr, needle, idx))
                            print(f"    HIT @ blk 0x{addr:04x}+0x{idx:03x}: {needle!r}")
                elif addr % (args.step * 64) == 0:
                    # Periodic progress for blocks with no data
                    pass
            elif status == "ECHO":
                echo += 1
                map_fp.write(f"0x{addr:04x} ECHO 0\n")
            else:
                bad += 1
                map_fp.write(f"0x{addr:04x} {status} 0\n")
                print(f"  0x{addr:04x}: {status}")

            map_fp.flush()
            scan_fp.flush()

            if addr % 0x1000 == 0:
                pct = (addr - args.start) * 100 / max(1, args.end - args.start)
                print(f"  ... 0x{addr:04x} pct={pct:.0f}%  ok={ok} echo={echo} bad={bad} data={data_blocks}",
                      file=sys.stderr)

            addr += args.step
    finally:
        hd1.close()
        scan_fp.close()
        map_fp.close()

    print()
    print(f"  ok:     {ok}  (full 1035-byte response)")
    print(f"  echo:   {echo}  (11-byte echo only, no data)")
    print(f"  bad:    {bad}")
    print(f"  data:   {data_blocks}  (blocks with non-trivial content)")
    print(f"  hits:   {len(hits)}")
    for a, n, off in hits:
        print(f"    blk 0x{a:04x}+0x{off:03x}: {n!r}")
    print(f"  scan:   {scan_path}")
    print(f"  map:    {map_path}")


if __name__ == "__main__":
    main()
