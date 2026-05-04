#!/usr/bin/env python3
"""
HD2 firmware analysis using PyGhidra.

Usage:
    python3 fw_analyze.py [firmware.bin]

Loads the CK803S (CSKY_V2 LE) decrypted firmware at flash XIP base 0x03000000,
runs auto-analysis, then prints: vector table entries, strings, function
boundaries, and suspicious data regions.

Firmware must be pre-decrypted with the 922-word-period XOR key.
See firmware/decode_fw.py for the decryption script.
Decrypted files live in analysis/ relative to the firmware/ directory.

Requires GHIDRA_INSTALL_DIR to be set (done by home-manager ghidra.nix).
"""

import sys
import struct
from pathlib import Path

FW_PATH = Path(__file__).parent.parent / "analysis" / "HD-HD2PA-C7000-V2.0.7.dec.bin"
BASE_ADDR = 0x03000000   # flash XIP base (hw docs: LCSFC XIP at 0x03000000)
LANG_ID   = "CSKY_V2:LE:32:default"
CSPEC     = "default"

# ── helpers ──────────────────────────────────────────────────────────────────

def fmt_addr(addr):
    return f"0x{int(addr.getOffset()):08x}"

# ── analysis steps ────────────────────────────────────────────────────────────

def vec_to_ghidra(ptr, base):
    """Translate a 0x0377xxxx firmware pointer to Ghidra's loaded address space."""
    return base + (ptr - BASE_ADDR)


def dump_vectors(flat_api, base):
    """
    Print the interrupt vector table.
    Empirically the table starts at fw+0x7c (not 0x80 as originally assumed).
    fw+0x78-0x7b = 0xFFFFFFFF (sentinel before table).
    """
    print("\n=== Vector Table (fw+0x7c) ===")
    vector_start = base + 0x7c
    entries = []
    for i in range(64):
        addr = flat_api.toAddr(vector_start + i * 4)
        val  = flat_api.getInt(addr) & 0xffffffff
        if val != 0:
            ghidra_addr = vec_to_ghidra(val, base)
            in_range = 0 <= ghidra_addr < base + 0x200000
            tag = "" if in_range else "  [OUT OF RANGE]"
            print(f"  vec[{i:2d}]  @ file+0x{i*4+0x80:04x}  ->  0x{val:08x}  (ghidra 0x{ghidra_addr:08x}){tag}")
            entries.append((i, val, ghidra_addr, in_range))
    return entries


def find_infinite_loops(flat_api, monitor, base, size):
    """Scan for 0x07FE (br . = infinite loop = default ISR stubs)."""
    print("\n=== Infinite Loops (0x07FE) ===")
    found = []
    for off in range(0, size - 1, 2):
        addr = flat_api.toAddr(base + off)
        b0   = flat_api.getByte(addr) & 0xff
        b1   = flat_api.getByte(flat_api.toAddr(base + off + 1)) & 0xff
        if b0 == 0xfe and b1 == 0x07:        # LE: FE 07
            found.append(base + off)
            if len(found) <= 20:
                print(f"  0x{base + off:08x}")
    print(f"  ... total: {len(found)}")
    return found


def find_strings(flat_api, base, size, min_len=6, print_offset=0x60000):
    """
    Scan for null-terminated printable ASCII strings.
    Requiring a null terminator avoids false positives from code bytes.
    print_offset: only print strings at or above this file offset (skips code-section garbage).
    """
    print(f"\n=== Null-terminated Strings (min {min_len} chars, printed from file+0x{print_offset:x}) ===")
    strings = []
    printed = 0
    i = 0
    while i < size:
        addr = flat_api.toAddr(base + i)
        b    = flat_api.getByte(addr) & 0xff
        if 0x20 <= b < 0x7f:
            j = i
            s = []
            while j < size:
                c = flat_api.getByte(flat_api.toAddr(base + j)) & 0xff
                if 0x20 <= c < 0x7f:
                    s.append(chr(c))
                    j += 1
                else:
                    # require null terminator
                    if c == 0x00 and len(s) >= min_len:
                        text = "".join(s)
                        strings.append((base + i, text))
                        if i >= print_offset and printed < 500:
                            print(f"  file+0x{i:06x}  {text!r}")
                            printed += 1
                    break
            i = j + 1
        else:
            i += 1
    print(f"  ... total: {len(strings)}  (printed {printed} from data section)")
    return strings


def find_function_prologues(flat_api, base, size):
    """
    Scan for common CK803S function prologues.
    push r15 = 0xDC20 (16-bit) or push {r15, ...} 32-bit forms.
    Also look for 'subi sp, N' patterns.
    """
    print("\n=== Candidate Function Entries (push r15 / subi sp) ===")
    entries = []
    for off in range(0, size - 1, 2):
        addr = flat_api.toAddr(base + off)
        b0   = flat_api.getByte(addr) & 0xff
        b1   = flat_api.getByte(flat_api.toAddr(base + off + 1)) & 0xff
        hw   = b0 | (b1 << 8)

        # push r15 (16-bit): 0xDC20 -- bits[15:6]=0b1101110000, bits[5:0]=100000
        if hw == 0xDC20:
            entries.append(base + off)

        # push {r4-r11, r15} variants: upper byte 0xDE, lower varies
        if b1 == 0xDE:
            entries.append(base + off)

    # deduplicate and print first 40
    entries = sorted(set(entries))
    for e in entries[:40]:
        print(f"  0x{e:08x}")
    print(f"  ... total candidates: {len(entries)}")
    return entries


def disassemble_at(flat_api, program, addr_int, count=20):
    """Disassemble 'count' instructions starting at addr_int."""
    listing = program.getListing()
    addr    = flat_api.toAddr(addr_int)
    print(f"\n=== Disassembly @ 0x{addr_int:08x} ===")
    instr = listing.getInstructionAt(addr)
    if instr is None:
        flat_api.disassemble(addr)
        instr = listing.getInstructionAt(addr)
    if instr is None:
        print("  (no instruction - bad alignment or not analyzed yet)")
        return
    for _ in range(count):
        if instr is None:
            break
        print(f"  {fmt_addr(instr.getAddress())}  {instr}")
        instr = instr.getNext()


def decompile_at(program, monitor, addr_int, label=""):
    """Decompile the function containing addr_int."""
    from ghidra.app.decompiler import DecompInterface, DecompileOptions
    decomp = DecompInterface()
    decomp.setOptions(DecompileOptions())
    decomp.openProgram(program)
    fm   = program.getFunctionManager()
    addr = program.getAddressFactory().getDefaultAddressSpace().getAddress(addr_int)
    func = fm.getFunctionAt(addr)
    if func is None:
        func = fm.getFunctionContaining(addr)
    if func is None:
        print(f"\n=== Decompile @ 0x{addr_int:08x}: no function defined ===")
        decomp.dispose()
        return
    hdr = label or f"0x{addr_int:08x}"
    print(f"\n=== Decompile: {func.getName()} ({hdr}) ===")
    result = decomp.decompileFunction(func, 60, monitor)
    if result.decompileCompleted():
        print(result.getDecompiledFunction().getC())
    else:
        print(f"  FAILED: {result.getErrorMessage()}")
    decomp.dispose()


# ── main ──────────────────────────────────────────────────────────────────────

def dump_functions(flat_api, program):
    """Print all functions found by auto-analysis, sorted by address."""
    print("\n=== Function List ===")
    fm   = program.getFunctionManager()
    fns  = list(fm.getFunctions(True))
    fns.sort(key=lambda f: int(f.getEntryPoint().getOffset()))
    for f in fns[:100]:  # first 100
        ep   = int(f.getEntryPoint().getOffset())
        body = f.getBody()
        size = body.getMaxAddress().getOffset() - body.getMinAddress().getOffset() + 1
        print(f"  0x{ep:08x}  (file+0x{ep-BASE_ADDR:06x})  {int(size):6d} B  {f.getName()}")
    print(f"  ... total: {len(fns)} functions")
    return fns


def run(flat_api, program, monitor, base):
    """base = the address Ghidra actually loaded the binary at."""
    fw_size = int(program.getMemory().getSize())
    print(f"Firmware size: 0x{fw_size:x} ({fw_size} bytes)")
    print(f"Loaded at:     0x{base:08x}  (target: 0x{BASE_ADDR:08x})")

    # 1. Strings
    find_strings(flat_api, base, fw_size)

    # 2. Function prologues
    find_function_prologues(flat_api, base, fw_size)

    # 3. Vector table
    vectors = dump_vectors(flat_api, base)

    # 4. Function list from auto-analysis
    fns = dump_functions(flat_api, program)

    # 5. Disassemble + decompile the reset entry (start of file)
    print("\n=== Reset entry (file+0x0000) ===")
    flat_api.disassemble(flat_api.toAddr(base))
    disassemble_at(flat_api, program, base, count=40)

    # 6. Create functions at key entry points and decompile
    fm = program.getFunctionManager()
    def ensure_func(addr_int, name):
        a = flat_api.toAddr(addr_int)
        flat_api.disassemble(a)
        f = fm.getFunctionAt(a)
        if f is None:
            f = flat_api.createFunction(a, name)
        return f

    # 7. Decompile first 5 unique vector handlers
    print("\n=== Vector Targets (decompile) ===")
    seen = set()
    count = 0
    for idx, ptr, ghidra_addr, in_range in vectors[:64]:
        if not in_range or ptr in seen:
            continue
        seen.add(ptr)
        code_addr = ghidra_addr & ~1  # mask C-SKY Thumb-style mode bit
        print(f"\nvec[{idx}] -> 0x{ptr:08x}  (code@0x{code_addr:08x})")
        ensure_func(code_addr, f"vec_{idx}")
        disassemble_at(flat_api, program, code_addr, count=12)
        decompile_at(program, monitor, code_addr)
        count += 1
        if count >= 5:
            break

    # 8. Decompile a few functions from prologue scan
    print("\n=== Sample functions from prologue scan ===")
    prologue_offsets = [0x001f44, 0x00259c, 0x002842, 0x002a3a, 0x002ff0]
    for off in prologue_offsets:
        addr_int = base + off
        ensure_func(addr_int, f"func_{off:06x}")
        disassemble_at(flat_api, program, addr_int, count=15)
        decompile_at(program, monitor, addr_int, f"file+0x{off:06x}")


def main():
    fw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else FW_PATH
    if not fw_path.exists():
        print(f"ERROR: firmware not found at {fw_path}", file=sys.stderr)
        sys.exit(1)

    import pyghidra
    print(f"Loading {fw_path} with PyGhidra ...")

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pyghidra.open_program(
            fw_path,
            language=LANG_ID,
            compiler=CSPEC,
            analyze=False,
        ) as flat_api:
            program = flat_api.getCurrentProgram()
            monitor  = flat_api.getMonitor()

            # Find where Ghidra initially loaded the binary, then rebase
            mem   = program.getMemory()
            block = mem.getBlocks()[0]
            loaded_base = int(block.getStart().getOffset())
            print(f"Ghidra initial base: 0x{loaded_base:08x}")

            if loaded_base != BASE_ADDR:
                print(f"Rebasing to 0x{BASE_ADDR:08x} ...")
                tid = program.startTransaction("rebase")
                try:
                    program.setImageBase(flat_api.toAddr(BASE_ADDR), True)
                    program.endTransaction(tid, True)
                    block = mem.getBlocks()[0]
                    loaded_base = int(block.getStart().getOffset())
                    print(f"Rebased to: 0x{loaded_base:08x}")
                except Exception as e:
                    program.endTransaction(tid, False)
                    print(f"  Rebase failed ({e}), using 0x{loaded_base:08x}")

            # Pre-disassemble the reset vector so auto-analysis propagates
            print("Pre-disassembling reset entry ...")
            flat_api.disassemble(flat_api.toAddr(loaded_base))

            print("Running auto-analysis ...")
            flat_api.analyzeAll(program)

            run(flat_api, program, monitor, loaded_base)


if __name__ == "__main__":
    main()
