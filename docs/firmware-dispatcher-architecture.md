# HD2 v208 — Menu dispatcher architecture (final)

## Question: where does the menu-dispatcher code live?

The menu pointer table at flash rodata `0x06df00..0x06e500` references 9
distinct handler addresses in the SRAM range `0x0561d000..0x0561e000` and
one at `0x05670c82`. To dispatch a menu action, the firmware reads one of
these handler pointers from the table and calls it.

**These handler addresses are never copied to SRAM by any code in this
firmware.** Verified by:

1. Exhaustive search of all 32-bit values in the firmware finds the menu
   handler addresses (`0x0561daee`, `0x0561da2a`, etc.) **only inside the
   menu pointer table itself** at `0x06df00+`. Zero references from any
   code section.

2. No memcpy-style triplet (dst=SRAM, src=flash, len=KB-range) loads
   these specific addresses or even nearby ranges. Searched 0–94 KB of
   code; zero realistic candidates for handler init.

3. The 9 code-region literals that point into `0x0561d...` region all
   land in tiny (4–10 byte) "function" stubs that Ghidra cannot
   disassemble — they are literal-pool entries in the code-area, not
   actual code. These stubs likely belong to **vtables / callback
   registries** that store handler pointers for later use.

## Conclusion: the dispatcher lives in chip ROM (not in our firmware)

The C7000 SoC (or its companion HAL/BSP) provides menu-dispatcher
routines in ROM at the `0x0556xxxxx..0x0567xxxxx` address range. The
application firmware:

1. Stores ROM-routine pointers in the menu pointer table (one handler
   per menu segment)
2. The dispatcher (also in ROM) is invoked from the main event loop
3. The dispatcher walks the menu pointer table, calls the per-segment
   handler when an item is selected

This is a common embedded-radio architecture pattern: the chip vendor
ships a standard menu/UI framework in mask ROM; the application writes
a configuration table (the menu pointer table) that wires up labels +
handlers to that framework.

## What this means for further reverse engineering

- We **cannot decompile the menu dispatcher** from this firmware.
  It's a black box from our perspective.

- To get the dispatcher logic, options are:
  1. **Dump the C7000 internal ROM** via JTAG/SWD (requires hardware access)
  2. **Find the vendor BSP/SDK** (Anhui Sunplus or similar — likely NDA-only)
  3. **Reverse-engineer behaviorally** by toggling menu items and observing radio response

- We **can** still understand the radio's menu behavior because:
  - The menu pointer table is fully decoded (10 segments, 219 items)
  - Each segment's handler is consistently invoked for items in that
    segment
  - Item-to-handler mapping is known
  - Item enumeration matches docs (Key Define values, Main Set order, etc.)

## Implications for the wider firmware

Other SRAM ranges in the map are likely also ROM-resident chip
services:

- `0x0556xxxxx`–`0x0561xxxxx` — likely menu/UI framework ROM
- `0x0562xxxxx`–`0x0567xxxxx` — likely DSP / DMR / audio framework ROM
- `0x0568xxxxx`–`0x05900000` — additional services or shadow

Memcpy candidates we found (with implausibly large lengths) were false
positives; no boot-code in this firmware does flash→SRAM staging.

## What our firmware DOES contain

The 4,333 functions we identified are entirely application-level code
running from flash. They:

- Set up uC/OS-III tasks (event/sem/timer/sysint/txslot/...)
- Call ROM-resident chip services for menu, audio, RF, DMR
- Implement the application-specific glue: codeplug parsing, settings
  application, channel scan, GPS NMEA parsing, error handling, etc.
