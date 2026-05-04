#!/usr/bin/env python3
"""
hd1_probe_scan.py - Sweep the HD1/HD2 address space looking for readable
data outside the mapped CODEPLUG_REGIONS.

Walks one (b1, chunk-size) combination across an address range. Each chunk
is classified:

    ALL_FF   read OK, every byte is 0xFF (unprogrammed flash)
    DATA     read OK, contains non-0xFF bytes
    FAIL     TIMEOUT / SHORT / BAD_TERM / BAD_ECHO

Outputs:
    <out>.scanmap.txt   per-chunk classification + sparse DATA-run summary
    <out>.scan_<addr>.bin   each DATA chunk (only with --dump-data)

This is a read-only exploration tool. It does not send END or any write
frames. Reuses HD1 and CODEPLUG_REGIONS from hd1_dump.py.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

from hd1_dump import HD1, CODEPLUG_REGIONS, hexdump


def is_in_mapped_region(addr: int, b1: int) -> bool:
    for _, start, end, _, region_b1 in CODEPLUG_REGIONS:
        if region_b1 == b1 and start <= addr <= end:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--port", required=True)
    ap.add_argument("--out", required=True, help="Output prefix (no extension)")
    ap.add_argument("--b1", type=lambda s: int(s, 0), default=0x0F,
                    help="Command class. 0x0F (byte-addr, default), 0x31 (block-idx), 0x0D")
    ap.add_argument("--start", type=lambda s: int(s, 0), default=0x0000)
    ap.add_argument("--end", type=lambda s: int(s, 0), default=0xFFFF,
                    help="Inclusive end address")
    ap.add_argument("--chunk", type=lambda s: int(s, 0), default=None,
                    help="Bytes per read (default 0x80 for b1=0x0F/0x0D, 0x400 for b1=0x31)")
    ap.add_argument("--step", type=lambda s: int(s, 0), default=None,
                    help="Address step (default chunk for b1=0x0F/0x0D, 1 for b1=0x31)")
    ap.add_argument("--skip-mapped", action="store_true",
                    help="Skip addresses already covered by CODEPLUG_REGIONS")
    ap.add_argument("--dump-data", action="store_true",
                    help="Save each DATA chunk to <out>.scan_<addr>.bin")
    ap.add_argument("--retries", type=int, default=0,
                    help="read_chunk retries on FAIL (default 0 — fast scan)")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()

    chunk = args.chunk if args.chunk is not None else (0x400 if args.b1 == 0x31 else 0x80)
    step = args.step if args.step is not None else (1 if args.b1 == 0x31 else chunk)

    out_path = Path(args.out)
    map_path = out_path.parent / f"{out_path.stem}.scanmap.txt"
    log_path = out_path.parent / f"{out_path.stem}.scan.log"
    trace_fp = open(log_path, "w") if args.trace else None
    map_fp = open(map_path, "w")

    n_chunks = ((args.end - args.start) // step) + 1
    print(f"Scan b1=0x{args.b1:02x} 0x{args.start:04x}..0x{args.end:04x} "
          f"chunk=0x{chunk:x} step=0x{step:x} (~{n_chunks} reads)")
    print(f"Map:  {map_path}")
    if args.trace:
        print(f"Log:  {log_path}")

    hd1 = HD1(port=args.port, timeout=args.timeout, trace_fp=trace_fp)

    interrupted = {"flag": False}

    def handle_sigint(signum, frame):
        interrupted["flag"] = True
        print("\nInterrupted, flushing partial map...", file=sys.stderr)
    signal.signal(signal.SIGINT, handle_sigint)

    classifications: list[tuple[int, str]] = []
    n_all_ff = n_data = n_fail = n_skip = 0

    try:
        ver = hd1.get_version()
        if not ver or b"HD" not in ver:
            print("ERROR: GetVer failed - radio not responding.", file=sys.stderr)
            sys.exit(2)
        printable = bytes(b if 32 <= b < 127 else 0x2e for b in ver
                          ).decode("ascii", errors="replace")
        print(f"Radio: {printable.rstrip('.')}")

        map_fp.write(f"# scan b1=0x{args.b1:02x} 0x{args.start:04x}..0x{args.end:04x} "
                     f"chunk=0x{chunk:x} step=0x{step:x}\n")
        map_fp.write(f"# {'addr':>6}  {'class':<6}  preview\n")

        addr = args.start
        last_progress = time.monotonic()
        n_total = 0
        while addr <= args.end:
            if interrupted["flag"]:
                break
            if args.skip_mapped and is_in_mapped_region(addr, args.b1):
                map_fp.write(f"  0x{addr:04x}  SKIP    (in mapped region)\n")
                n_skip += 1
                addr += step
                continue
            resp, status = hd1.read_chunk(args.b1, addr, chunk,
                                          percent=0, retries=args.retries)
            n_total += 1
            if status != "OK":
                cls = "FAIL"
                preview = status
                n_fail += 1
            else:
                data = resp[10:-1]
                if all(b == 0xFF for b in data):
                    cls = "ALL_FF"
                    preview = "(unprogrammed)"
                    n_all_ff += 1
                else:
                    cls = "DATA"
                    preview = hexdump(data, 16)
                    n_data += 1
                    if args.dump_data:
                        bin_path = out_path.parent / f"{out_path.stem}.scan_{addr:04x}.bin"
                        bin_path.write_bytes(data)
            map_fp.write(f"  0x{addr:04x}  {cls:<6}  {preview}\n")
            map_fp.flush()
            classifications.append((addr, cls))

            now = time.monotonic()
            if now - last_progress >= 1.0:
                print(f"  0x{addr:04x}  data={n_data} ff={n_all_ff} "
                      f"fail={n_fail} skip={n_skip}", file=sys.stderr)
                last_progress = now
            addr += step

        # Sparse summary: contiguous DATA runs
        runs: list[tuple[int, int]] = []
        run_start: int | None = None
        run_end = 0
        for a, cls in classifications:
            if cls == "DATA":
                if run_start is None:
                    run_start = a
                run_end = a
            else:
                if run_start is not None:
                    runs.append((run_start, run_end))
                    run_start = None
        if run_start is not None:
            runs.append((run_start, run_end))

        map_fp.write("\n# DATA runs (contiguous chunks classified as DATA)\n")
        for s, e in runs:
            map_fp.write(f"  0x{s:04x}..0x{e:04x}\n")

        print()
        print(f"  total reads:  {n_total}")
        print(f"  ALL_FF:       {n_all_ff}")
        print(f"  DATA:         {n_data}")
        print(f"  FAIL:         {n_fail}")
        print(f"  SKIP:         {n_skip}")
        if runs:
            print("  Contiguous DATA runs:")
            for s, e in runs:
                print(f"    0x{s:04x}..0x{e:04x}")
    finally:
        hd1.close()
        map_fp.close()
        if trace_fp:
            trace_fp.close()


if __name__ == "__main__":
    main()
