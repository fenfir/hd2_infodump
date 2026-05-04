#!/usr/bin/env python3
"""
hd1_codeplug_write.py - Write a codeplug .bin to the HD1/HD2.

By default writes only the regions that differ from a baseline .bin (much
faster, less flash wear). Use --all to write everything.

Two write protocols are used:

b1=0x0F (128-byte chunks, for 'header', 'vfo_config', 'settings' regions):
    TX: 68 0f 01 01 [pct] 00 80 00 [addr_lo] [addr_hi] [128B] 10
    ACK: 68 0f 01 01 [pct] 00 80 00 [addr_lo] [addr_hi] 10  (11B)

b1=0x31 (4096-byte blocks, for 'addr_book', 'channels', 'table_*' regions):
    Each 4096B write covers FOUR 1024B read-blocks. addr stride = 4.
    TX: 68 31 01 01 [pct] 31 00 10 [addr_lo] [addr_hi] [4096B] 10
    ACK: 68 31 02 01 [pct] 31 00 10 [addr_lo] [addr_hi] 10  (11B)

Examples:
    # Write only diffs (fast, default):
    mise exec -- python3 hd1_codeplug_write.py \\
        --port /dev/cu.usbserial-2140 \\
        --baseline output/cp_fmradio.bin \\
        output/cp_ai5qz.bin

    # Dry run (compute writes, don't talk to radio):
    mise exec -- python3 hd1_codeplug_write.py \\
        --port /dev/cu.usbserial-2140 \\
        --baseline output/cp_fmradio.bin \\
        --dry-run \\
        output/cp_ai5qz.bin
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import serial

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codeplug import REGIONS

SYNC = 0x68
TERMINATOR = 0x10
CHUNK_0F = 128
BLOCK_31 = 4096   # 4 x 1024 read-blocks per write
READ_BLOCK = 1024


def hexdump(data: bytes, n: int = 32) -> str:
    head = data[:n]
    return f"{' '.join(f'{b:02x}' for b in head)}{' ...' if len(data) > n else ''}"


def build_cmd_0f(pct: int, addr: int, data: bytes) -> bytes:
    """Build a b1=0x0F write command (128-byte chunk)."""
    assert len(data) == CHUNK_0F
    header = bytes([
        SYNC,
        0x0F,
        0x01,           # write
        0x01,
        pct & 0xFF,
        0x00,
        CHUNK_0F & 0xFF,        # size_lo
        (CHUNK_0F >> 8) & 0xFF, # size_hi
        addr & 0xFF,
        (addr >> 8) & 0xFF,
    ])
    return header + data + bytes([TERMINATOR])


def build_cmd_31(pct: int, addr: int, data: bytes) -> bytes:
    """Build a b1=0x31 write command (4096-byte block)."""
    assert len(data) == BLOCK_31
    header = bytes([
        SYNC,
        0x31,
        0x01,           # write
        0x01,
        pct & 0xFF,
        0x31,           # constant
        0x00,           # size_lo
        0x10,           # size_hi (0x1000 = 4096)
        addr & 0xFF,
        (addr >> 8) & 0xFF,
    ])
    return header + data + bytes([TERMINATOR])


class HD1Writer:
    def __init__(self, port: str, *, timeout: float = 3.0, trace_fp=None):
        self.trace_fp = trace_fp
        self.ser = serial.Serial(
            port=port,
            baudrate=120000,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            rtscts=False, dsrdtr=False,
            timeout=timeout, write_timeout=timeout,
            exclusive=True,
        )
        self.ser.rts = True
        self.ser.dtr = True
        time.sleep(0.2)
        self._drain_boot_log()

    def trace(self, msg: str):
        if self.trace_fp:
            self.trace_fp.write(msg + "\n")
            self.trace_fp.flush()

    def _drain_boot_log(self, quiet_for: float = 1.0, max_wait: float = 10.0):
        drained = bytearray()
        last = time.monotonic()
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            self.ser.timeout = 0.1
            chunk = self.ser.read(4096)
            if chunk:
                drained.extend(chunk)
                last = time.monotonic()
            elif time.monotonic() - last >= quiet_for:
                break
        if drained:
            self.trace(f"DRAIN {len(drained)} bytes")
        self.ser.reset_input_buffer()

    def get_version(self) -> bytes:
        self.ser.reset_input_buffer()
        self.ser.write(b"GetVer")
        self.ser.flush()
        time.sleep(0.3)
        self.ser.timeout = 0.5
        buf = bytes(self.ser.read(self.ser.in_waiting or 256))
        self.trace(f"RX GetVer {len(buf)}B {hexdump(buf)}")
        return buf

    def _send_and_ack(self, cmd: bytes, expected_ack_match: bytes,
                      ack_len: int = 11, settle: float = 0.3,
                      retries: int = 3) -> tuple[bytes, str]:
        """Send a command and wait for ack. expected_ack_match is the byte
        pattern the ack must start with (typically the first 10 bytes minus
        the size_lo difference for response variants)."""
        tx_time = (len(cmd) * 10) / 119200.0
        ack_time = (ack_len * 10) / 119200.0

        for attempt in range(retries + 1):
            self.ser.reset_input_buffer()
            self.ser.write(cmd)
            self.ser.flush()
            self.trace(f"TX[{attempt}] ({len(cmd)}B) hdr={cmd[:10].hex()}")

            time.sleep(tx_time + ack_time + settle)

            buf = bytearray()
            deadline = time.monotonic() + 2.0
            while True:
                pending = self.ser.in_waiting
                if pending:
                    buf.extend(self.ser.read(pending))
                if len(buf) >= ack_len:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)

            self.trace(f"RX[{attempt}] got {len(buf)}/{ack_len} {hexdump(bytes(buf))}")

            if len(buf) == ack_len:
                if (buf[0] == SYNC and buf[-1] == TERMINATOR
                        and buf[8] == expected_ack_match[8]
                        and buf[9] == expected_ack_match[9]):
                    return bytes(buf), "OK"
                return bytes(buf), f"BAD_ACK({bytes(buf).hex()})"

        if not buf:
            return b"", "TIMEOUT"
        return bytes(buf), f"SHORT({len(buf)}/{ack_len})"

    def write_chunk_0f(self, pct: int, addr: int, data: bytes) -> tuple[bytes, str]:
        cmd = build_cmd_0f(pct, addr, data)
        return self._send_and_ack(cmd, expected_ack_match=cmd[:10], ack_len=11,
                                  settle=0.05)

    def write_block_31(self, pct: int, addr: int, data: bytes) -> tuple[bytes, str]:
        cmd = build_cmd_31(pct, addr, data)
        return self._send_and_ack(cmd, expected_ack_match=cmd[:10], ack_len=11,
                                  settle=0.3)

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


def plan_writes(new_data: bytes, baseline_data: bytes | None,
                regions=REGIONS) -> list[dict]:
    """Plan write operations.

    Returns list of dicts: {kind: '0f'|'31', addr: int, data: bytes,
                             region: str, file_off: int}
    """
    writes = []
    for name, rbase, fbase, fsize, stride, blockwise in regions:
        rend = rbase + fsize // (READ_BLOCK if blockwise else stride)
        if blockwise:
            # 1024-byte read-blocks; group into 4-block (4096B) writes.
            # For regions shorter than 4 blocks (or not 4-aligned at the end),
            # pad with 0xFF (the radio's empty-flash byte).
            num_read_blocks = fsize // READ_BLOCK
            num_write_blocks = (num_read_blocks + 3) // 4
            for w in range(num_write_blocks):
                start = fbase + w * BLOCK_31
                avail = min(BLOCK_31, len(new_data) - start,
                            (fbase + fsize) - start)
                chunk_new = new_data[start:start + avail]
                if avail < BLOCK_31:
                    chunk_new = chunk_new + b"\xFF" * (BLOCK_31 - avail)
                if baseline_data is not None:
                    chunk_old = baseline_data[start:start + avail]
                    if avail < BLOCK_31:
                        chunk_old = chunk_old + b"\xFF" * (BLOCK_31 - avail)
                    if chunk_new == chunk_old:
                        continue
                addr = rbase + w * 4
                writes.append({
                    "kind": "31",
                    "addr": addr,
                    "data": chunk_new,
                    "region": name,
                    "file_off": start,
                })
        else:
            # 128-byte chunks
            num_chunks = fsize // CHUNK_0F
            for c in range(num_chunks):
                start = fbase + c * CHUNK_0F
                chunk_new = new_data[start:start + CHUNK_0F]
                if baseline_data is not None:
                    chunk_old = baseline_data[start:start + CHUNK_0F]
                    if chunk_new == chunk_old:
                        continue
                addr = rbase + c * CHUNK_0F
                writes.append({
                    "kind": "0f",
                    "addr": addr,
                    "data": chunk_new,
                    "region": name,
                    "file_off": start,
                })
    return writes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin_path", help="Codeplug .bin to write to the radio")
    ap.add_argument("--baseline", default=None,
                    help="Baseline .bin to diff against (writes only changed "
                         "blocks). Omit to write everything.")
    ap.add_argument("--port", help="Serial device (e.g. /dev/cu.usbserial-2140)")
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="Show plan without talking to radio.")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--log", default="codeplug_write.log")
    args = ap.parse_args()

    new_data = Path(args.bin_path).read_bytes()
    print(f"New codeplug:  {args.bin_path} ({len(new_data)} bytes)")

    baseline_data = None
    if args.baseline:
        baseline_data = Path(args.baseline).read_bytes()
        if len(baseline_data) != len(new_data):
            print(f"ERROR: baseline size {len(baseline_data)} != new {len(new_data)}",
                  file=sys.stderr)
            sys.exit(1)
        print(f"Baseline:      {args.baseline} ({len(baseline_data)} bytes)")
    else:
        print(f"Baseline:      <none>  (writing entire codeplug)")

    writes = plan_writes(new_data, baseline_data)
    n_0f = sum(1 for w in writes if w["kind"] == "0f")
    n_31 = sum(1 for w in writes if w["kind"] == "31")
    print(f"\nPlan: {len(writes)} writes total")
    print(f"  b1=0x0F (128B chunks):  {n_0f}")
    print(f"  b1=0x31 (4096B blocks): {n_31}")
    if writes:
        print(f"\nFirst 5 writes:")
        for w in writes[:5]:
            print(f"  {w['region']:<14} kind=0x{w['kind']} addr=0x{w['addr']:04X} "
                  f"@file 0x{w['file_off']:06X}")
        if len(writes) > 5:
            print(f"  ... and {len(writes) - 5} more")

    # Estimated time
    t_0f = n_0f * 0.1
    t_31 = n_31 * 0.7
    print(f"\nEstimated time: {t_0f + t_31:.1f}s")

    if args.dry_run:
        print("\n[dry-run] Not writing.")
        return

    if not args.port:
        print("ERROR: --port required for actual write", file=sys.stderr)
        sys.exit(2)

    if not writes:
        print("\nNothing to write.")
        return

    print(f"\n>>> Writing to {args.port} <<<")
    trace_fp = open(args.log, "w") if args.trace else None
    if trace_fp:
        print(f"Trace log: {args.log}")

    hd1 = HD1Writer(port=args.port, timeout=args.timeout, trace_fp=trace_fp)

    interrupted = {"flag": False}
    def sigint(signum, frame):
        interrupted["flag"] = True
        print("\nInterrupted...", file=sys.stderr)
    signal.signal(signal.SIGINT, sigint)

    try:
        ver = hd1.get_version()
        if not ver or b"HD" not in ver:
            print("ERROR: GetVer failed - radio not responding.", file=sys.stderr)
            sys.exit(2)
        printable = bytes(b if 32 <= b < 127 else 0x2e for b in ver).decode("ascii", errors="replace")
        print(f"Radio: {printable.rstrip('.')}")
        print()

        ok = bad = 0
        for i, w in enumerate(writes):
            if interrupted["flag"]:
                break
            pct = max(1, int((i + 1) * 100 / len(writes)))
            if w["kind"] == "0f":
                resp, status = hd1.write_chunk_0f(pct, w["addr"], w["data"])
            else:
                resp, status = hd1.write_block_31(pct, w["addr"], w["data"])
            tag = "OK " if status == "OK" else "ERR"
            print(f"  [{i+1:3d}/{len(writes)}] {w['region']:<14} "
                  f"kind=0x{w['kind']} addr=0x{w['addr']:04X}  {tag}  "
                  f"{status if status != 'OK' else ''}")
            if status == "OK":
                ok += 1
            else:
                bad += 1
                print(f"      resp={resp.hex()}", file=sys.stderr)
                if bad >= 3:
                    print("Too many errors, aborting.", file=sys.stderr)
                    break

        print()
        print(f"  ok:  {ok}/{len(writes)}")
        print(f"  bad: {bad}")
        if ok == len(writes):
            # Send END to terminate session (radio reboots and commits).
            # Without this, the radio kills the session and reverts.
            print("\nSending END to commit + reboot radio...")
            hd1.ser.reset_input_buffer()
            hd1.ser.write(b"END")
            hd1.ser.flush()
            time.sleep(0.5)
            print("Write complete.")
    finally:
        hd1.close()
        if trace_fp:
            trace_fp.close()


if __name__ == "__main__":
    main()
