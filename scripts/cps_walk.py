#!/usr/bin/env python3
"""
cps_walk.py - Walk every CPS tree item and screenshot its settings pane.

Requires: xdotool, imagemagick (import)
Run:  nix-shell -p xdotool -p imagemagick -p python3 --run 'python3 pylunce/cps_walk.py'

The script expands parent nodes itself via double-click, then single-clicks
each leaf to capture its pane. All tree items are at x=110 (text), with the
folder icon at x=55 for expand/collapse.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def run(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip()


def find_window() -> int:
    wids = run("xdotool search --name 'RETEVIS Ailunce HD2'").split()
    for w in wids:
        name = run(f"xdotool getwindowname {w}")
        if "V1.14" in name:
            return int(w)
    print("ERROR: CPS window not found", file=sys.stderr)
    sys.exit(1)


def click(wid: int, x: int, y: int):
    run(f"xdotool mousemove --window {wid} {x} {y}")
    time.sleep(0.05)
    run(f"xdotool click --window {wid} 1")


def double_click(wid: int, x: int, y: int):
    run(f"xdotool mousemove --window {wid} {x} {y}")
    time.sleep(0.05)
    run(f"xdotool click --window {wid} --repeat 2 --delay 80 1")


def screenshot(wid: int, path: str):
    run(f"import -window {wid} '{path}'")


# Row spacing in window coords (measured empirically)
ROW_H = 18
# First tree item (Freqset) y in window coords
# Screenshot y for Freqset ≈ 83, but there's a +30 offset between
# screenshot coords and actual click coords (Wayland decoration gap).
FIRST_ROW_Y = 83 + 30  # = 113
# x for clicking text
TEXT_X = 110
# x for clicking folder icon (expand/collapse)
ICON_X = 55


def row_y(row: int) -> int:
    """Window y coordinate for tree row index (0 = Freqset)."""
    return FIRST_ROW_Y + row * ROW_H


def main():
    outdir = Path("output/cps_panes")
    outdir.mkdir(parents=True, exist_ok=True)

    wid = find_window()
    print(f"CPS window: {wid}")

    # The tree when fully collapsed (no children visible):
    # Row 0: Freqset
    # Row 1: Basic Setting [+]
    # Row 2: Channel
    # Row 3: Zone Information
    # Row 4: VFO Scan / Priority CH
    # Row 5: DTMF
    # Row 6: Radio
    # Row 7: Contacts [+]
    # Row 8: RX Group Lists  (visible only when Contacts collapsed; shifts when expanded)
    # Row 9: DMR Service [+]
    #
    # Strategy: work top-down. When we hit an expandable node, expand it,
    # capture its children, then collapse it before moving on.

    step = 0

    def capture(name: str, row: int):
        nonlocal step
        step += 1
        safe = name.lower().replace(" ", "_").replace("/", "_")
        fname = f"{step:02d}_{safe}.png"
        click(wid, TEXT_X, row_y(row))
        time.sleep(0.6)
        screenshot(wid, str(outdir / fname))
        print(f"[{step:2d}] {name:30s} -> {fname}")

    def expand(row: int):
        """Click folder icon to expand a tree node."""
        click(wid, ICON_X, row_y(row))
        time.sleep(0.5)

    def collapse(row: int):
        """Click folder icon to collapse a tree node."""
        click(wid, ICON_X, row_y(row))
        time.sleep(0.5)

    # Take initial screenshot
    screenshot(wid, str(outdir / "00_initial.png"))
    print("Saved initial screenshot")

    # --- Walk the tree ---

    # Freqset (row 0)
    capture("Freqset", 0)

    # Basic Setting (row 1) — expand, capture children, collapse
    capture("Basic Setting", 1)
    expand(1)  # now children appear at rows 2-6, pushing everything down by 5
    capture("Basic Information", 2)
    capture("Setting", 3)
    capture("Key Setting", 4)
    capture("One Key Call", 5)
    capture("ID Setting", 6)
    collapse(1)  # collapse Basic Setting, children disappear

    # Channel (row 2 after collapse)
    capture("Channel", 2)

    # Zone Information (row 3)
    capture("Zone Information", 3)

    # VFO Scan / Priority CH (row 4)
    capture("VFO Scan / Priority CH", 4)

    # DTMF (row 5)
    capture("DTMF", 5)

    # Radio (row 6)
    capture("Radio", 6)

    # Contacts (row 7) — expand, capture children, collapse
    capture("Contacts", 7)
    expand(7)  # children at rows 8-9, pushing down by 2
    capture("Priority Contacts", 8)
    capture("Address Book Contacts", 9)
    collapse(7)

    # RX Group Lists (row 8 after collapse)
    capture("RX Group Lists", 8)

    # DMR Service (row 9) — expand, capture children, collapse
    capture("DMR Service", 9)
    expand(9)  # child at row 10
    capture("Encryption", 10)
    collapse(9)

    print(f"\nDone. {step} screenshots in {outdir}/")


if __name__ == "__main__":
    main()
