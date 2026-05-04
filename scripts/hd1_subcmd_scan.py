#!/usr/bin/env python3
"""
hd1_subcmd_scan.py - Sweep the subcommand byte (frame[2]) of an HD1/HD2
command class to discover undocumented operations.

11-byte frame layout:
    [0]=SYNC(0x68) [1]=b1 [2]=SUB [3]=0x01 [4]=pct [5]=csum
    [6]=size_lo   [7]=size_hi [8]=addr_lo [9]=addr_hi [10]=TERM(0x10)

Known SUB values for b1=0x0F:
    0x00  read request (normal codeplug read)
    0x02  read response echo (server-sent — not normally used as a request)
    0x05  set clock (real frame is 16 B, not 11 — but we still probe)

This holds b1/addr/size/csum constant and varies SUB across the requested
range. For each probe it captures whatever the radio replies (or doesn't),
classifies it, and writes one line per subcmd to <out>.subcmd_scan.txt.

After the sweep it re-runs GetVer to confirm the radio is still responsive.

Read-only — does not send write frames or END.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from hd1_dump import HD1, csum as compute_csum


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--port", required=True)
    ap.add_argument("--out", required=True, help="Output prefix (no extension)")
    ap.add_argument("--b1", type=lambda s: int(s, 0), default=0x0F)
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x0000)
    ap.add_argument("--size", type=lambda s: int(s, 0), default=0x80)
    ap.add_argument("--probe-timeout", type=float, default=0.3,
                    help="Per-probe wait window in seconds (default 0.3)")
    ap.add_argument("--start-sub", type=lambda s: int(s, 0), default=0x00)
    ap.add_argument("--end-sub", type=lambda s: int(s, 0), default=0xFF,
                    help="Inclusive end of subcmd sweep")
    args = ap.parse_args()

    out_path = Path(args.out)
    txt_path = out_path.parent / f"{out_path.stem}.subcmd_scan.txt"

    print(f"Subcmd sweep b1=0x{args.b1:02x} addr=0x{args.addr:04x} "
          f"size=0x{args.size:x} sub=0x{args.start_sub:02x}..0x{args.end_sub:02x}")
    print(f"Output: {txt_path}")

    hd1 = HD1(port=args.port, timeout=2.0)

    SYNC = 0x68
    TERM = 0x10
    addr_lo = args.addr & 0xFF
    addr_hi = (args.addr >> 8) & 0xFF
    cs = compute_csum(args.addr, args.size, args.b1)
    expected_full = 10 + args.size + 1  # echo(10) + payload + terminator(1)

    txt_fp = open(txt_path, "w")
    txt_fp.write(f"# Subcmd sweep b1=0x{args.b1:02x} addr=0x{args.addr:04x} "
                 f"size=0x{args.size:x}\n")
    txt_fp.write(f"# expected FULL response length = {expected_full}\n")
    txt_fp.write(f"# {'sub':>4}  {'len':>4}  {'class':<10}  preview\n")

    try:
        ver = hd1.get_version()
        if not ver or b"HD" not in ver:
            print("ERROR: GetVer failed - radio not responding.", file=sys.stderr)
            sys.exit(2)
        printable = bytes(b if 32 <= b < 127 else 0x2e for b in ver
                          ).decode("ascii", errors="replace")
        print(f"Radio: {printable.rstrip('.')}")

        ser = hd1.ser
        n_no_reply = n_echo = n_full = n_partial = n_over = 0

        for sub in range(args.start_sub, args.end_sub + 1):
            cmd = bytes([
                SYNC, args.b1, sub, 0x01, 0x00, cs,
                args.size & 0xFF, (args.size >> 8) & 0xFF,
                addr_lo, addr_hi, TERM,
            ])
            ser.reset_input_buffer()
            ser.write(cmd)
            ser.flush()

            deadline = time.monotonic() + args.probe_timeout
            while time.monotonic() < deadline:
                if ser.in_waiting >= expected_full:
                    break
                time.sleep(0.005)
            time.sleep(0.02)  # let any trailing bytes arrive
            n = ser.in_waiting
            data = ser.read(n) if n else b""

            if len(data) == 0:
                cls = "NO_REPLY"
                n_no_reply += 1
            elif len(data) <= 10:
                cls = "ECHO_ONLY"
                n_echo += 1
            elif len(data) < expected_full:
                cls = "PARTIAL"
                n_partial += 1
            elif len(data) == expected_full:
                cls = "FULL"
                n_full += 1
            else:
                cls = "OVER"
                n_over += 1

            preview = data[:32].hex(' ')
            line = f"  0x{sub:02x}  {len(data):>4}  {cls:<10}  {preview}"
            txt_fp.write(line + "\n")
            txt_fp.flush()
            # Print every non-NO_REPLY result + a heartbeat every 32 subs
            if cls != "NO_REPLY" or sub % 32 == 0:
                print(line)

        print()
        print("  Tally:")
        print(f"    NO_REPLY:  {n_no_reply}")
        print(f"    ECHO_ONLY: {n_echo}")
        print(f"    PARTIAL:   {n_partial}")
        print(f"    FULL:      {n_full}")
        print(f"    OVER:      {n_over}")

        print()
        print("Post-sweep GetVer check...")
        ver2 = hd1.get_version()
        if ver2 and b"HD" in ver2:
            printable2 = bytes(b if 32 <= b < 127 else 0x2e for b in ver2
                               ).decode("ascii", errors="replace")
            print(f"  Radio still responsive: {printable2.rstrip('.')!r}")
        else:
            print(f"  WARNING: post-sweep GetVer failed (got {len(ver2)} bytes)",
                  file=sys.stderr)
            print(f"  Hex: {ver2.hex(' ') if ver2 else '<none>'}", file=sys.stderr)
    finally:
        hd1.close()
        txt_fp.close()


if __name__ == "__main__":
    main()
