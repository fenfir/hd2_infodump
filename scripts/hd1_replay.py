#!/usr/bin/env python3
"""
hd1_replay.py - Replay the exact host-to-radio bytes captured in a pcap.

Reads tshark-extracted serial bytes from a text file (one logical message per
line, with direction marker) and sends each OUT message to the radio, capturing
whatever comes back. Useful for sanity checks before generalizing the protocol.

Input format (extracted with):
    tshark -r input.pcapng -Y \\
      "usb.transfer_type == 0x03 && (ch340.bulk.data_in || ch340.bulk.data_out)" \\
      -T fields -e frame.number -e usb.src \\
      -e ch340.bulk.data_out -e ch340.bulk.data_in -E separator='|'
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import serial


def hexdump(data: bytes, n: int = 32) -> str:
    head = data[:n]
    return f"{' '.join(f'{b:02x}' for b in head)}{' ...' if len(data) > n else ''}"


def load_pcap_text(path: str):
    """Yield (direction, bytes) for each USB serial transfer."""
    msgs = []
    with open(path) as f:
        for line in f:
            parts = line.rstrip("\n").split("|")
            if len(parts) < 4:
                continue
            src = parts[1]
            hex_str = parts[2] if src == "host" else parts[3]
            if not hex_str:
                continue
            d = "OUT" if src == "host" else "IN"
            msgs.append((d, bytes.fromhex(hex_str)))
    return msgs


def reassemble(msgs):
    """Merge consecutive same-direction packets into logical messages."""
    out = []
    for d, b in msgs:
        if out and out[-1][0] == d:
            out[-1] = (d, out[-1][1] + b)
        else:
            out.append((d, b))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default=str(Path.home() / ".local/share/anytone-emu/anytoneport"))
    ap.add_argument("--input", required=True, help="pcap text extraction (see header)")
    ap.add_argument("--out", required=True, help="output prefix")
    ap.add_argument("--timeout", type=float, default=2.0,
                    help="per-message read timeout (seconds)")
    ap.add_argument("--idle", type=float, default=0.15,
                    help="quiet-idle threshold to detect end of response")
    ap.add_argument("--retries", type=int, default=3,
                    help="re-send command if response length doesn't match expected")
    ap.add_argument("--post-read-sleep", type=float, default=0.05,
                    help="pause after each read before next command")
    args = ap.parse_args()

    msgs = reassemble(load_pcap_text(args.input))
    print(f"Loaded {len(msgs)} logical messages from {args.input}")
    out_msgs = [m for m in msgs if m[0] == "OUT"]
    print(f"  OUT messages to replay: {len(out_msgs)}")

    out_path = Path(args.out)
    bin_path = out_path.with_suffix(".bin")
    raw_path = out_path.with_suffix(".raw")
    log_path = out_path.with_suffix(".log")
    bin_fp = open(bin_path, "wb")
    raw_fp = open(raw_path, "wb")
    log_fp = open(log_path, "w")

    ser = serial.Serial(
        port=args.port, baudrate=119200,
        bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
        rtscts=False, dsrdtr=False,
        timeout=args.timeout, write_timeout=args.timeout,
        exclusive=True,
    )
    try:
        ser.rts = True
        ser.dtr = True
    except Exception:
        pass  # PTYs don't support modem control lines
    time.sleep(0.2)  # let RTS/DTR settle before any I/O

    # Drain any boot-time debug log the radio is streaming. Read until the
    # port has been quiet for a sustained period.
    print("Draining boot log...", file=sys.stderr)
    drained = bytearray()
    quiet_needed = 1.0
    last_byte_time = time.monotonic()
    drain_deadline = time.monotonic() + 10.0
    while time.monotonic() < drain_deadline:
        ser.timeout = 0.1
        chunk = ser.read(4096)
        if chunk:
            drained.extend(chunk)
            last_byte_time = time.monotonic()
        elif time.monotonic() - last_byte_time >= quiet_needed:
            break
    if drained:
        print(f"  drained {len(drained)} bytes of boot data", file=sys.stderr)
    ser.reset_input_buffer()

    interrupted = {"flag": False}
    def handle_sigint(signum, frame):
        interrupted["flag"] = True
        print("\nInterrupted...", file=sys.stderr)
    signal.signal(signal.SIGINT, handle_sigint)

    ok = bad = 0
    try:
        for i, (d, b) in enumerate(msgs):
            if interrupted["flag"]:
                break
            if d != "OUT":
                continue  # skip captured IN messages; we'll read live response

            # END is terminal — no response expected from emulator.
            if b in (b"END", b"END\x00"):
                log_fp.write(f"TX[{i}.0] ({len(b)}B): {b.hex()} [END — skipping response]\n")
                ser.write(b)
                ser.flush()
                ok += 1
                continue

            # find what was expected to come back (next IN message in capture)
            expected_in = None
            for j in range(i + 1, len(msgs)):
                if msgs[j][0] == "IN":
                    expected_in = msgs[j][1]
                    break
                if msgs[j][0] == "OUT":
                    break

            target_len = len(expected_in) if expected_in else None
            buf = bytearray()
            attempt = 0
            while True:
                # Drain any stale bytes left over from prior reads.
                ser.reset_input_buffer()
                ser.write(b)
                ser.flush()
                log_fp.write(f"TX[{i}.{attempt}] ({len(b)}B): {b.hex()}\n")

                # Wait long enough for the radio to finish sending the response,
                # then read everything available at once. Estimate how long the
                # response takes to transmit at 119200 baud (~12 KB/s) and add
                # 100ms slack. For unknown-length responses, use post_read_sleep.
                if target_len:
                    transmit_time = (target_len * 10) / 119200.0
                    time.sleep(transmit_time + 0.1)
                else:
                    time.sleep(max(0.1, args.post_read_sleep))

                # Read everything that arrived. Try briefly for a few extra
                # bytes if we haven't reached target_len yet.
                buf = bytearray()
                deadline = time.monotonic() + args.timeout
                while True:
                    pending = ser.in_waiting
                    if pending:
                        buf.extend(ser.read(pending))
                    if target_len is None:
                        # quiet-idle exit
                        if buf:
                            time.sleep(args.idle)
                            if ser.in_waiting == 0:
                                break
                        else:
                            ser.timeout = 0.1
                            chunk = ser.read(1)
                            if chunk:
                                buf.extend(chunk)
                            elif time.monotonic() >= deadline:
                                break
                    else:
                        if len(buf) >= target_len:
                            break
                        if time.monotonic() >= deadline:
                            break
                        # Wait a bit longer for stragglers
                        time.sleep(0.05)

                log_fp.write(f"RX[{i}.{attempt}] ({len(buf)}B): {hexdump(bytes(buf), 64)}\n")
                log_fp.flush()

                if target_len is None or len(buf) == target_len or attempt >= args.retries:
                    break
                attempt += 1
                print(f"[{i:4d}] retry {attempt}/{args.retries} (got {len(buf)}/{target_len})", file=sys.stderr)

            raw_fp.write(b"OUT " + len(b).to_bytes(4,"little") + b)
            raw_fp.write(b"IN  " + len(buf).to_bytes(4,"little") + buf)
            raw_fp.flush()

            # Compare against expected (if available)
            match = "?"
            if expected_in is not None:
                if bytes(buf) == expected_in:
                    match = "MATCH"
                    ok += 1
                else:
                    match = f"DIFF (exp {len(expected_in)}, got {len(buf)})"
                    bad += 1

            print(f"[{i:4d}] TX={hexdump(b, 16)}  RX {len(buf)}B  {match}", file=sys.stderr)

            # If this looks like a 1035-byte read response, save the data payload to bin
            if len(buf) == 1035 and buf[0] == 0x68 and buf[-1] == 0x10:
                bin_fp.write(buf[10:-1])
                bin_fp.flush()
    finally:
        try:
            ser.close()
        except Exception:
            pass
        bin_fp.close()
        raw_fp.close()
        log_fp.close()

    print()
    print(f"  matched: {ok}")
    print(f"  diff:    {bad}")
    print(f"  bin:     {bin_path} ({bin_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
