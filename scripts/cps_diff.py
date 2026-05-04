#!/usr/bin/env python3
"""
cps_diff.py - Automate settings diff mapping via CPS + anytone-emu.

Workflow per setting:
  1. Ctrl+R to read baseline from emulator
  2. Navigate to the right pane, toggle/change the setting
  3. Ctrl+W to write changed codeplug to emulator
  4. Emulator (running with --diff previous) logs which bytes changed

Requires: xdotool, imagemagick, anytone-emu running with --diff previous
Run:  nix-shell -p xdotool -p imagemagick -p python3 --run 'python3 pylunce/cps_diff.py'
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


# ── Coordinate system ──────────────────────────────────────────────────
# Display scaling (KDE Scale=1.35) causes XWayland window coords to differ
# from screenshot pixel coords (captured by `import -window` at native res).
#
# Calibrated from user cursor positions (xdotool getmouselocation):
#   Key Beep Tones: screenshot (638,220) → screen (824,319) → window (824,282)
#   Roger Beep:     screenshot (638,237) → screen (826,343) → window (826,306)
#   Double PTT:     screenshot (638,429) → screen (825,593) → window (825,556)
#
# Linear model: window = screenshot * SCALE + OFFSET
# Y: (220→282, 429→556) → scale=1.311, offset=-6.4
# X: (638→824) → using same scale: 638*1.311=836, offset=-12
COORD_SCALE = 1.3110
COORD_X_OFFSET = -12.2
COORD_Y_OFFSET = -6.4

# Tree params (tree is in the main window frame, different coordinate space)
TREE_Y_OFFSET = 30
TREE_ROW_H = 18
TREE_FIRST_Y = 83 + TREE_Y_OFFSET  # Freqset row in window coords
TREE_TEXT_X = 110
TREE_ICON_X = 55


def tree_y(row: int) -> int:
    return TREE_FIRST_Y + row * TREE_ROW_H


# ── Control types ──────────────────────────────────────────────────────
@dataclass
class Checkbox:
    """Click to toggle."""
    name: str
    x: int  # screenshot x
    y: int  # screenshot y (offset applied at click time)


@dataclass
class Dropdown:
    """Click to open, press Down to cycle to next value."""
    name: str
    x: int
    y: int
    steps: int = 1  # how many Down presses to change value


@dataclass
class Pane:
    """A CPS tree pane with its controls."""
    tree_item: str
    tree_row: int        # row index when parent is expanded (0=Freqset)
    parent_row: int | None  # row to expand first, or None if top-level
    controls: list = field(default_factory=list)


# ── Settings map ───────────────────────────────────────────────────────
# Coordinates measured from the Setting pane screenshot (05_key_setting.png)
# These are SCREENSHOT coords — Y_OFFSET is added at click time.

SETTING_PANE = Pane(
    tree_item="Setting",
    tree_row=3,       # row 3 when Basic Setting is expanded
    parent_row=1,     # Basic Setting
    controls=[
        # All coordinates are SCREENSHOT pixel coords.
        # click() applies ss_to_win() transform (scale 1.311 + offset).
        #
        # Measured from /tmp/setting_full.png (1425x1408, maximized Setting pane).
        # Left-col dropdowns: click the dropdown arrow at x≈460
        # Right-col checkboxes: click the checkbox square at x≈638
        # Right-col dropdowns: click the dropdown arrow at x≈750

        # ── Password Setting ──
        Checkbox("Enable Write Password",    350, 98),
        Checkbox("Enable Read Password",     638, 98),

        # ── Basic Attributes (left column — dropdowns) ──
        Dropdown("KeyPress Voice-assist",    460, 150),
        Dropdown("Keypress Voice Language",  460, 167),
        Dropdown("Squelch Level",            460, 184),
        Dropdown("Repeater Connect",         460, 201),
        Dropdown("A/B Scan Time Dual Band",  460, 220),
        Dropdown("Battery Powersave Mode",   460, 237),
        Dropdown("Wakeup Speed Powersave",   460, 254),
        Dropdown("Priv/Group Call Response",  460, 271),
        Dropdown("Lone Worker Response Time", 460, 289),
        Dropdown("Lone Worker Pre-Alarm",    460, 306),
        Dropdown("Default Zone Band A",      460, 324),
        Dropdown("Default Zone Band B",      460, 341),
        Dropdown("VFO Lock",                 460, 358),
        Dropdown("Keyboard Lock",            460, 375),
        Dropdown("Time Format Selection",    460, 392),

        # ── Basic Attributes (right column) ──
        Dropdown("Noise Tail Elimination Mode", 750, 150),
        Checkbox("Noise Tail Elimination",   638, 167),
        Checkbox("Keylock at Power-on",      638, 184),
        Checkbox("Auto Keylock After 15sec", 638, 201),
        Checkbox("Key Beep Tones",           638, 220),
        Checkbox("Roger Beep",               638, 237),
        Checkbox("Dual Watch Band A/B(BDR)", 638, 254),
        Checkbox("Accept Radio Kill Cmd",    638, 271),
        Checkbox("Accept Radio Wakeup Cmd",  638, 289),
        Checkbox("Talk Permit Tone Digital",  638, 306),
        Checkbox("Talk Permit Tone Analogue", 638, 324),
        Checkbox("No RX Info Operating Menu", 638, 341),
        Checkbox("RX Info Bright Screen",    638, 358),
        Checkbox("Missed Call Reminder",     638, 375),
        Dropdown("RX Info Display Time",     750, 392),
        Dropdown("Menu Exit Time",           750, 411),
        Checkbox("Double PTT",               638, 429),

        # ── Display ──
        Dropdown("Active Band At",           460, 467),
        Dropdown("BackLight Time",           460, 485),
        Dropdown("Backlight Brightness",     460, 503),
        Dropdown("Channel Dis A",            460, 527),
        Checkbox("Power-on Password",        638, 467),
        Checkbox("Night Mode Switch",        638, 503),
        Dropdown("Channel Dis B",            750, 527),

        # ── Mic Setting ──
        Dropdown("VOX Delay Time",           460, 561),
        Dropdown("Mic Gain",                 460, 580),
        Checkbox("Press PTT to cancel VOX",  638, 561),
        Checkbox("Insert Headset Activates VOX", 638, 580),

        # ── Emergency ──
        Dropdown("Emergency Mode",           460, 616),
        Dropdown("Alarm TX Time",            750, 616),
        Dropdown("Alarm Idle Time",          750, 633),
    ],
)

ALL_PANES = [SETTING_PANE]
# TODO: add Key Setting, DTMF, Radio, Freqset panes


# ── Helpers ────────────────────────────────────────────────────────────
WID = None


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


def ss_to_win(x: int, y: int) -> tuple[int, int]:
    """Convert screenshot pixel coords to xdotool --window coords."""
    return (int(x * COORD_SCALE + COORD_X_OFFSET),
            int(y * COORD_SCALE + COORD_Y_OFFSET))


def click(x: int, y: int):
    """Click at screenshot coords (applies coordinate transform for scaling)."""
    wx, wy = ss_to_win(x, y)
    run(f"xdotool mousemove --window {WID} {wx} {wy}")
    time.sleep(0.05)
    run(f"xdotool mousedown --window {WID} 1")
    time.sleep(0.05)
    run(f"xdotool mouseup --window {WID} 1")


def click_raw(x: int, y: int):
    """Click at raw window coords (no offset)."""
    run(f"xdotool mousemove --window {WID} {x} {y}")
    time.sleep(0.05)
    run(f"xdotool mousedown --window {WID} 1")
    time.sleep(0.05)
    run(f"xdotool mouseup --window {WID} 1")


def key(k: str):
    run(f"xdotool key --window {WID} {k}")


def screenshot(path: str):
    run(f"import -window {WID} '{path}'")


def tree_click(row: int):
    click_raw(TREE_TEXT_X, tree_y(row))


def tree_expand(row: int):
    click_raw(TREE_ICON_X, tree_y(row))


# ── Toolbar Read/Write ────────────────────────────────────────────────
# Toolbar icon positions (window coords, no Y offset needed):
#   Read from radio: x=135, y=27
#   Write to radio:  x=155, y=27
TOOLBAR_READ_X = 135
TOOLBAR_WRITE_X = 155
TOOLBAR_Y = 27



def _find_any_dialog() -> int | None:
    """Find any CPS popup dialog (not the main window, not tiny).
    Returns window ID or None."""
    for pattern in ["V1.14", "Read data", "Write data"]:
        wids = run(f"xdotool search --name '{pattern}'").split()
        for w in wids:
            if not w or w == str(WID):
                continue
            name = run(f"xdotool getwindowname {w}")
            if not name or "default-1" in name:
                continue
            geo = run(f"xdotool getwindowgeometry --shell {w}")
            width = 0
            for line in geo.split("\n"):
                if line.startswith("WIDTH="):
                    try:
                        width = int(line.split("=")[1])
                    except ValueError:
                        pass
            if width > 10:
                return int(w)
    return None


def _click_ok_on(wid: int):
    """Click OK on a dialog — OK button is always at approx x=68, y=62."""
    run(f"xdotool mousemove --window {wid} 68 62")
    time.sleep(0.05)
    run(f"xdotool mousedown --window {wid} 1")
    time.sleep(0.05)
    run(f"xdotool mouseup --window {wid} 1")


def _dismiss_all_dialogs():
    """Dismiss any open CPS dialogs and confirm they're gone."""
    for _ in range(10):
        dlg = _find_any_dialog()
        if not dlg:
            break
        _click_ok_on(dlg)
        time.sleep(0.5)
    # Verify all dialogs are gone
    for _ in range(10):
        if not _find_any_dialog():
            return
        time.sleep(0.5)
    print("  WARNING: could not dismiss all dialogs", file=sys.stderr)


def _wait_for_dialog(timeout: float = 10.0) -> int | None:
    """Wait for a CPS dialog to appear."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dlg = _find_any_dialog()
        if dlg:
            return dlg
        time.sleep(0.3)
    return None


def _do_radio_op(toolbar_x: int, op_name: str):
    """Click a toolbar button, handle confirmation + progress + completion dialogs."""
    _dismiss_all_dialogs()
    _refocus_main()
    click_raw(toolbar_x, TOOLBAR_Y)
    time.sleep(1)

    # Step 1: Find and click OK on confirmation dialog
    dlg = _wait_for_dialog(timeout=5)
    if not dlg:
        print(f"  WARNING: {op_name} confirmation dialog not found", file=sys.stderr)
        return
    print(f"    {op_name} confirmed...", end="", flush=True)
    _click_ok_on(dlg)
    time.sleep(0.5)

    # Step 2: Poll until the operation completes (OK dialog appears after progress)
    # The progress window stays open, then a small OK dialog appears on top.
    # We keep polling for any new dialog and clicking OK until we find the
    # completion (small ~114px) dialog.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        time.sleep(0.5)
        dlg = _find_any_dialog()
        if not dlg:
            # No dialog at all — maybe everything dismissed already
            continue
        name = run(f"xdotool getwindowname {dlg}")
        geo = run(f"xdotool getwindowgeometry --shell {dlg}")
        width = 0
        for line in geo.split("\n"):
            if line.startswith("WIDTH="):
                try:
                    width = int(line.split("=")[1])
                except ValueError:
                    pass
        if "V1.14" in name and width < 200:
            # This is the completion dialog (ReadOK/WriteOK)
            _click_ok_on(dlg)
            print(" done")
            return
        # Otherwise it's the progress window — keep waiting

    print(" TIMEOUT", file=sys.stderr)


def _refocus_main():
    """Click into the main CPS window to ensure it has focus."""
    click_raw(400, 400)
    time.sleep(0.3)


def read_codeplug():
    """Click Read toolbar button, handle all dialogs."""
    _do_radio_op(TOOLBAR_READ_X, "Read")
    _dismiss_all_dialogs()
    _refocus_main()
    time.sleep(0.5)


def write_codeplug():
    """Click Write toolbar button, handle all dialogs."""
    _do_radio_op(TOOLBAR_WRITE_X, "Write")
    _dismiss_all_dialogs()
    _refocus_main()
    time.sleep(0.5)


def toggle_checkbox(ctrl: Checkbox):
    click(ctrl.x, ctrl.y)
    time.sleep(0.2)


def scroll_at(x: int, y: int, button: int = 5):
    """Send a scroll event at screenshot coords. button 5=down, 4=up."""
    wx, wy = ss_to_win(x, y)
    run(f"xdotool mousemove --window {WID} {wx} {wy}")
    time.sleep(0.05)
    run(f"xdotool mousedown --window {WID} {button}")
    time.sleep(0.05)
    run(f"xdotool mouseup --window {WID} {button}")


def _click_neutral():
    """Click a neutral grey area to deselect any focused widget."""
    click_raw(800, 700)
    time.sleep(0.2)


def cycle_dropdown(ctrl: Dropdown):
    """Click dropdown to focus, arrow down to change value, enter to commit."""
    click(ctrl.x, ctrl.y)
    time.sleep(0.3)
    for _ in range(ctrl.steps):
        run(f"xdotool key --window {WID} Down")
        time.sleep(0.1)
    run(f"xdotool key --window {WID} Return")
    time.sleep(0.2)
    _click_neutral()


def restore_dropdown(ctrl: Dropdown):
    """Click dropdown to focus, arrow up to restore value, enter to commit."""
    click(ctrl.x, ctrl.y)
    time.sleep(0.3)
    for _ in range(ctrl.steps):
        run(f"xdotool key --window {WID} Up")
        time.sleep(0.1)
    run(f"xdotool key --window {WID} Return")
    time.sleep(0.2)
    _click_neutral()


# ── Main ───────────────────────────────────────────────────────────────
def main():
    global WID

    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outdir", default="output/cps_diffs",
                    help="output directory for screenshots and results")
    ap.add_argument("--pane", default=None,
                    help="only run controls from this pane (e.g. 'Setting')")
    ap.add_argument("--control", default=None,
                    help="only run a single control by name")
    ap.add_argument("--dry-run", action="store_true",
                    help="just show what would be done, no clicks")
    ap.add_argument("--skip-nav", action="store_true",
                    help="skip tree navigation (pane already open and maximized)")
    ap.add_argument("--emu-log", default=None,
                    help="path to emulator diff log to parse after each write")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    WID = find_window()
    print(f"CPS window: {WID}")

    panes = ALL_PANES
    if args.pane:
        panes = [p for p in panes if p.tree_item == args.pane]

    results = []

    for pane in panes:
        if not args.skip_nav:
            # Expand parent if needed
            if pane.parent_row is not None:
                print(f"Expanding parent row {pane.parent_row}")
                if not args.dry_run:
                    tree_expand(pane.parent_row)
                    time.sleep(0.5)

            # Navigate to pane
            print(f"Opening pane: {pane.tree_item}")
            if not args.dry_run:
                tree_click(pane.tree_row)
                time.sleep(0.8)

        # Read baseline
        print("Reading baseline...")
        if not args.dry_run:
            read_codeplug()
            time.sleep(1)

        controls = pane.controls
        if args.control:
            controls = [c for c in controls if c.name == args.control]

        for i, ctrl in enumerate(controls):
            safe = ctrl.name.lower().replace(" ", "_").replace("/", "_")
            kind = "checkbox" if isinstance(ctrl, Checkbox) else "dropdown"
            print(f"  [{i+1:2d}/{len(controls)}] {kind:8s} {ctrl.name}")

            if args.dry_run:
                results.append({"name": ctrl.name, "type": kind, "status": "dry-run"})
                continue

            # Screenshot before
            before_path = str(outdir / f"{safe}_before.png")
            screenshot(before_path)

            # Toggle the setting
            if isinstance(ctrl, Checkbox):
                toggle_checkbox(ctrl)
            else:
                cycle_dropdown(ctrl)
            time.sleep(0.3)

            # Screenshot after toggle
            after_path = str(outdir / f"{safe}_after.png")
            screenshot(after_path)

            # Write to emulator
            write_codeplug()

            # Record result
            results.append({
                "name": ctrl.name,
                "type": kind,
                "before_screenshot": before_path,
                "after_screenshot": after_path,
                "status": "written",
            })

            # Restore the setting to baseline
            if isinstance(ctrl, Checkbox):
                toggle_checkbox(ctrl)  # toggle back
            else:
                restore_dropdown(ctrl)  # cycle back
            time.sleep(0.3)

            # Write restored state
            write_codeplug()

        # Collapse parent
        if not args.skip_nav and pane.parent_row is not None and not args.dry_run:
            tree_expand(pane.parent_row)  # toggle collapse
            time.sleep(0.3)

    # Save results
    result_path = str(outdir / "results.json")
    with open(result_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDone. {len(results)} settings tested. Results in {result_path}")


if __name__ == "__main__":
    main()
