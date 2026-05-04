#!/usr/bin/env python3
"""
cps_tree.py - Map the HD2 CPS tree view by walking it with keyboard navigation.

Requires: xdotool, tesseract, imagemagick (import), PIL
Run inside nix develop.

Workflow:
  1. Start emulator:  hd2-emu --launch
  2. Wait for CPS to fully load
  3. Run:  python3 cps_tree.py

The script finds the CPS window, clicks the tree view, then walks it
with arrow keys (Down/Right/Left), taking a screenshot and OCR-ing the
highlighted item at each step. Outputs a tree structure to stdout and
saves screenshots to output/cps_tree/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


def run(cmd: str, **kw) -> str:
    """Run a shell command, return stdout."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)
    return r.stdout.strip()


def find_cps_window() -> int | None:
    """Find the HD2 CPS window ID."""
    # Try various window name patterns
    for pattern in ["HD2", "HD1", "Ailunce"]:
        wids = run(f"xdotool search --name '{pattern}'").split()
        if wids:
            # Return the first visible/mapped window
            for wid in wids:
                return int(wid)
    return None


def activate_window(wid: int):
    """Bring window to front and focus it."""
    run(f"xdotool windowactivate --sync {wid}")
    time.sleep(0.1)


def screenshot_window(wid: int, path: str):
    """Take a screenshot of a specific X11 window."""
    # Use import (ImageMagick) targeting the window
    run(f"import -window {wid} '{path}'")


def screenshot_region(x: int, y: int, w: int, h: int, path: str):
    """Take a screenshot of a screen region."""
    run(f"import -window root -crop {w}x{h}+{x}+{y} '{path}'")


def get_window_geometry(wid: int) -> tuple[int, int, int, int]:
    """Return (x, y, width, height) of a window."""
    geo = run(f"xdotool getwindowgeometry --shell {wid}")
    vals = {}
    for line in geo.split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k] = int(v)
    return vals.get("X", 0), vals.get("Y", 0), vals.get("WIDTH", 800), vals.get("HEIGHT", 600)


def send_key(wid: int, key: str):
    """Send a key press to a window."""
    run(f"xdotool key --window {wid} {key}")
    time.sleep(0.15)


def click(wid: int, x: int, y: int):
    """Click at window-relative coordinates."""
    run(f"xdotool mousemove --window {wid} {x} {y}")
    time.sleep(0.05)
    run(f"xdotool click --window {wid} 1")
    time.sleep(0.2)


def ocr_image(path: str) -> str:
    """OCR a screenshot, return text."""
    if not HAS_OCR:
        return ""
    img = Image.open(path)
    text = pytesseract.image_to_string(img, config="--psm 6")
    return text.strip()


def ocr_region(wid: int, rx: int, ry: int, rw: int, rh: int, tmpdir: str) -> str:
    """Screenshot a small region relative to window and OCR it."""
    wx, wy, _, _ = get_window_geometry(wid)
    tmp = os.path.join(tmpdir, "_ocr_tmp.png")
    screenshot_region(wx + rx, wy + ry, rw, rh, tmp)
    return ocr_image(tmp)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", default="output/cps_tree",
                    help="directory for screenshots (default: output/cps_tree)")
    ap.add_argument("--max-items", type=int, default=200,
                    help="max tree items to walk before stopping")
    ap.add_argument("--screenshot-only", action="store_true",
                    help="just take one screenshot and exit")
    ap.add_argument("--tree-x", type=int, default=None,
                    help="x offset of tree view within window (auto-detected if omitted)")
    ap.add_argument("--tree-y", type=int, default=None,
                    help="y offset of tree view within window")
    ap.add_argument("--tree-w", type=int, default=None,
                    help="width of tree view area")
    ap.add_argument("--tree-h", type=int, default=None,
                    help="height of tree view area")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Find window
    wid = find_cps_window()
    if wid is None:
        print("ERROR: HD2 CPS window not found. Is it running?", file=sys.stderr)
        print("  Start with: hd2-emu --launch", file=sys.stderr)
        sys.exit(1)

    print(f"Found CPS window: {wid}")
    activate_window(wid)
    wx, wy, ww, wh = get_window_geometry(wid)
    print(f"  Geometry: {ww}x{wh} at ({wx},{wy})")

    # Full screenshot first
    full_path = str(outdir / "full_window.png")
    screenshot_window(wid, full_path)
    print(f"  Full screenshot: {full_path}")

    if args.screenshot_only:
        print("Done (--screenshot-only)")
        return

    if not HAS_OCR:
        print("WARNING: pytesseract not available, screenshots only (no text extraction)")

    # Tree view region — user can override, otherwise we guess left side
    tx = args.tree_x if args.tree_x is not None else 0
    ty = args.tree_y if args.tree_y is not None else 50   # skip menu bar
    tw = args.tree_w if args.tree_w is not None else min(250, ww // 3)
    th = args.tree_h if args.tree_h is not None else wh - ty
    print(f"  Tree region: ({tx},{ty}) {tw}x{th}")

    # Click inside tree to focus it
    click(wid, tx + tw // 2, ty + 20)
    time.sleep(0.3)

    # First, collapse everything by pressing Home then Left repeatedly
    send_key(wid, "Home")
    time.sleep(0.2)
    for _ in range(20):
        send_key(wid, "Left")

    # Now start at top
    send_key(wid, "Home")
    time.sleep(0.3)

    items = []
    prev_screenshot = None
    stale_count = 0

    for step in range(args.max_items):
        # Screenshot the tree area
        tree_path = str(outdir / f"tree_{step:03d}.png")
        tree_abs_path = str(outdir / f"tree_abs_{step:03d}.png")

        # Screenshot the full window to see what pane opened
        screenshot_window(wid, tree_abs_path)

        # OCR the tree region to get current item text
        text = ""
        if HAS_OCR:
            text = ocr_region(wid, tx, ty, tw, th, str(outdir))

        items.append({
            "step": step,
            "screenshot": tree_abs_path,
            "ocr_text": text,
        })
        print(f"  [{step:3d}] {text[:60] if text else '(no OCR)'}")

        # Try to expand current item
        send_key(wid, "Right")
        time.sleep(0.1)

        # Move to next item
        send_key(wid, "Down")
        time.sleep(0.3)

        # Check if we've looped back to start (screenshot unchanged)
        if prev_screenshot and os.path.exists(tree_abs_path) and os.path.exists(prev_screenshot):
            try:
                cur = Image.open(tree_abs_path)
                prev = Image.open(prev_screenshot)
                if list(cur.getdata()) == list(prev.getdata()):
                    stale_count += 1
                    if stale_count >= 3:
                        print(f"  Tree walk complete (no change for {stale_count} steps)")
                        break
                else:
                    stale_count = 0
            except Exception:
                pass

        prev_screenshot = tree_abs_path

    # Save results
    result_path = str(outdir / "tree_items.json")
    with open(result_path, "w") as f:
        json.dump(items, f, indent=2)
    print(f"\nSaved {len(items)} items to {result_path}")
    print(f"Screenshots in {outdir}/")


if __name__ == "__main__":
    main()
