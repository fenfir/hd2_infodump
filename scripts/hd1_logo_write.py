#!/usr/bin/env python3
"""
hd1_logo_write.py - Generate a boot logo and write it to the HD1/HD2.

Logo format: 160x128 RGB565 little-endian, 40960 bytes total.

Write protocol (host -> radio, 4107 bytes per block):
    68 31 01 01 [pct] 31 00 10 [addr_lo] [addr_hi] [4096 bytes data] 10

Ack (radio -> host, 11 bytes):
    68 31 02 01 [pct] 31 00 10 [addr_lo] [addr_hi] 10

10 blocks total, addresses 0x1dd0, 0x1dd4, ... 0x1df4 (+4 each).
pct values are 10, 20, 30, ..., 100.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

import serial
from PIL import Image, ImageDraw, ImageFont

SYNC = 0x68
TERMINATOR = 0x10
LOGO_W, LOGO_H = 160, 128
BLOCK_SIZE = 4096
BLOCK_COUNT = 10  # 10 * 4096 = 40960 = 160 * 128 * 2
BASE_ADDR = 0x1DD0
ADDR_STEP = 4


def rgb565_le(img: Image.Image) -> bytes:
    """Convert a 160x128 RGB image to RGB565 little-endian bytes."""
    assert img.size == (LOGO_W, LOGO_H)
    px = img.convert("RGB").load()
    out = bytearray(LOGO_W * LOGO_H * 2)
    i = 0
    for y in range(LOGO_H):
        for x in range(LOGO_W):
            r, g, b = px[x, y]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            out[i] = v & 0xFF
            out[i + 1] = (v >> 8) & 0xFF
            i += 2
    return bytes(out)


def make_logo() -> Image.Image:
    """Create a 160x128 'Claude did it!' logo with a stylized asterisk."""
    img = Image.new("RGB", (LOGO_W, LOGO_H), (0, 0, 0))
    d = ImageDraw.Draw(img)

    # Claude orange (the current brand color is a warm terra).
    ORANGE = (213, 119, 75)
    WHITE = (255, 255, 255)

    # Draw a stylized 'claude asterisk' / sparkle in the upper area.
    # Eight-pointed star made of two crossed elongated diamonds.
    cx, cy = LOGO_W // 2, 40
    def diamond(pts):
        d.polygon(pts, fill=ORANGE)

    # Vertical petal
    diamond([(cx, cy - 26), (cx + 8, cy), (cx, cy + 26), (cx - 8, cy)])
    # Horizontal petal
    diamond([(cx - 30, cy), (cx, cy - 6), (cx + 30, cy), (cx, cy + 6)])
    # Diagonal petals (shorter)
    diamond([(cx - 16, cy - 16), (cx, cy - 4), (cx + 16, cy + 16), (cx, cy + 4)])
    diamond([(cx + 16, cy - 16), (cx + 4, cy), (cx - 16, cy + 16), (cx - 4, cy)])

    # Try to load a decent font; fall back to default bitmap font.
    font = None
    font_small = None
    for path in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
    ]:
        try:
            font = ImageFont.truetype(path, 20)
            font_small = ImageFont.truetype(path, 14)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Text lines, centered.
    def centered(text, y, f, fill):
        bbox = d.textbbox((0, 0), text, font=f)
        w = bbox[2] - bbox[0]
        d.text(((LOGO_W - w) // 2 - bbox[0], y), text, font=f, fill=fill)

    centered("Claude", 76, font, WHITE)
    centered("did it!", 100, font_small, ORANGE)

    return img


def build_cmd(pct: int, block_idx: int, data: bytes) -> bytes:
    assert len(data) == BLOCK_SIZE
    addr = BASE_ADDR + block_idx * ADDR_STEP
    header = bytes([
        SYNC,
        0x31,              # b1 (same as logo read)
        0x01,              # write request
        0x01,              # constant
        pct & 0xFF,
        0x31,              # constant (observed)
        0x00,              # size_lo
        0x10,              # size_hi (0x1000 = 4096)
        addr & 0xFF,
        (addr >> 8) & 0xFF,
    ])
    return header + data + bytes([TERMINATOR])


def hexdump(data: bytes, n: int = 32) -> str:
    head = data[:n]
    return f"{' '.join(f'{b:02x}' for b in head)}{' ...' if len(data) > n else ''}"


class HD1Writer:
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

    def write_block(self, pct: int, block_idx: int, data: bytes, *,
                    retries: int = 3) -> tuple[bytes, str]:
        cmd = build_cmd(pct, block_idx, data)
        expected_ack = 11
        addr = BASE_ADDR + block_idx * ADDR_STEP

        # At 119200 baud, 4107 bytes takes ~0.34s to send + 11B ack takes ~1ms.
        # Give the radio time to process the write.
        tx_time = (len(cmd) * 10) / 119200.0
        ack_time = (expected_ack * 10) / 119200.0

        for attempt in range(retries + 1):
            self.ser.reset_input_buffer()
            self.ser.write(cmd)
            self.ser.flush()
            self.trace(f"TX[{attempt}] blk={block_idx} pct={pct} addr=0x{addr:04x} "
                       f"({len(cmd)}B) hdr={cmd[:10].hex()}")

            # Wait for TX to complete + radio flash write + ack transmission.
            # Flash writes can be slow; give it generous time.
            time.sleep(tx_time + ack_time + 0.3)

            buf = bytearray()
            deadline = time.monotonic() + 2.0
            while True:
                pending = self.ser.in_waiting
                if pending:
                    buf.extend(self.ser.read(pending))
                if len(buf) >= expected_ack:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)

            self.trace(f"RX[{attempt}] blk={block_idx} got {len(buf)}/{expected_ack} "
                       f"{hexdump(bytes(buf))}")

            if len(buf) == expected_ack:
                # Validate ack: 68 31 02 01 pct 31 00 10 addr_lo addr_hi 10
                if (buf[0] == SYNC and buf[1] == 0x31 and buf[2] == 0x02
                        and buf[-1] == TERMINATOR
                        and buf[8] == (addr & 0xFF)
                        and buf[9] == ((addr >> 8) & 0xFF)):
                    return bytes(buf), "OK"
                return bytes(buf), f"BAD_ACK({bytes(buf).hex()})"

        if not buf:
            return b"", "TIMEOUT"
        return bytes(buf), f"SHORT({len(buf)}/{expected_ack})"

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True, help="Serial device")
    ap.add_argument("--out", default="logo_write",
                    help="Output prefix for preview BMP / trace log")
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="Generate image and print plan, but don't write radio")
    ap.add_argument("--image", default=None,
                    help="Path to a 160x128 image to upload (skip generator)")
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()

    out_prefix = Path(args.out)
    preview_path = out_prefix.with_suffix(".preview.png")
    rgb565_path = out_prefix.with_suffix(".rgb565")
    log_path = out_prefix.with_suffix(".log")

    if args.image:
        img = Image.open(args.image).convert("RGB")
        if img.size != (LOGO_W, LOGO_H):
            img = img.resize((LOGO_W, LOGO_H))
    else:
        img = make_logo()

    img.save(preview_path)
    rgb = rgb565_le(img)
    rgb565_path.write_bytes(rgb)
    print(f"Preview image:  {preview_path}")
    print(f"RGB565 payload: {rgb565_path} ({len(rgb)} bytes)")
    assert len(rgb) == LOGO_W * LOGO_H * 2

    if args.dry_run:
        print(f"Would write {BLOCK_COUNT} blocks of {BLOCK_SIZE}B starting at "
              f"0x{BASE_ADDR:04x}")
        return

    trace_fp = open(log_path, "w") if args.trace else None
    if trace_fp:
        print(f"Trace log:      {log_path}")

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
        print(f"Radio:          {printable.rstrip('.')}")

        print(f"Writing {BLOCK_COUNT} blocks ({len(rgb)} bytes)...")
        ok = bad = 0
        for i in range(BLOCK_COUNT):
            if interrupted["flag"]:
                break
            block = rgb[i * BLOCK_SIZE : (i + 1) * BLOCK_SIZE]
            pct = (i + 1) * 10
            addr = BASE_ADDR + i * ADDR_STEP
            resp, status = hd1.write_block(pct, i, block)
            tag = "OK " if status == "OK" else "ERR"
            print(f"  [{i+1:2d}/{BLOCK_COUNT}] 0x{addr:04x} pct={pct:>3}  {tag}  {status if status != 'OK' else ''}")
            if status == "OK":
                ok += 1
            else:
                bad += 1
                print(f"      resp={resp.hex()}", file=sys.stderr)

        print()
        print(f"  ok:  {ok}/{BLOCK_COUNT}")
        print(f"  bad: {bad}")
        if ok == BLOCK_COUNT:
            print("Logo written. Reboot the radio to see it.")
    finally:
        hd1.close()
        if trace_fp:
            trace_fp.close()


if __name__ == "__main__":
    main()
