#!/usr/bin/env python3
"""
HD2 firmware analysis using PyGhidra — MCore (Motorola M•CORE) architecture.

Usage:
    python3 fw_analyze_mcore.py [firmware.bin]

Loads the MCore firmware at base 0x07700000, runs auto-analysis, then:
  - Dumps the MCore vector table (0x000–0x04c)
  - Dumps the ISR dispatch table at file offset 0x0670f0
  - Exports function list (address, name, size)
  - Disassembles the 3 hardware-variant init functions (file offsets given in task)
  - Decompiles selected functions

Architecture: MCORE:BE:32:default (big-endian, 16-bit fixed-width instructions)
Load base: 0x07700000 (derived from ISR table LE pointer analysis)
"""

import sys
import struct
from pathlib import Path

FW_PATH    = Path(__file__).parent.parent / "firmware" / "HD-HD2PA-C7000-V2.0.7.raw.bin"
BASE_ADDR  = 0x07700000          # likely base — try 0x77700000 if analysis looks wrong
LANG_ID    = "MCORE:BE:32:default"
CSPEC      = "default"

# Known offsets of interest (file offsets → virtual = BASE + offset)
ISR_DISPATCH_FILE_OFF = 0x0670f0  # app-level ISR dispatch table (79 entries)
ISR_DISPATCH_COUNT    = 79
STARTUP_FN_OFFSETS    = [0x077206, 0x037606, 0x067786]  # hardware-variant init routines

# ── helpers ──────────────────────────────────────────────────────────────────

_loaded_base = [0]   # filled in at run time; avoids global-mutation issues

def va(file_off):
    """File offset → virtual address (using actual loaded base)."""
    return _loaded_base[0] + file_off

def fo(virtual_addr):
    """Virtual address → file offset (using actual loaded base)."""
    return virtual_addr - _loaded_base[0]

def fmt_addr(addr):
    return f"0x{int(addr.getOffset()):08x}"

# ── analysis ─────────────────────────────────────────────────────────────────

def dump_vector_table(flat_api, base):
    """
    Dump the MCore hardware interrupt vector table.
    The pspec defines reset→0x000, missalign→0x004, …, trap3→0x04c.
    Each slot holds a 4-byte virtual address of the handler.
    """
    print("\n=== MCore Hardware Vector Table (base + 0x000) ===")
    labels = [
        (0x000, "reset"),    (0x004, "missalign"), (0x008, "access"),
        (0x00c, "divzero"),  (0x010, "illegal"),   (0x014, "privilege"),
        (0x018, "trace"),    (0x01c, "bkpt"),      (0x020, "unrecov"),
        (0x024, "softrst"),  (0x028, "intautovector"), (0x02c, "fintautovector"),
        (0x030, "hwaccel"),  (0x034, "reserved_0"),(0x038, "reserved_1"),
        (0x03c, "reserved_2"),(0x040, "trap0"),    (0x044, "trap1"),
        (0x048, "trap2"),    (0x04c, "trap3"),
    ]
    for off, name in labels:
        addr = flat_api.toAddr(base + off)
        val  = flat_api.getInt(addr) & 0xffffffff
        file_tgt = fo(val)
        in_range = 0 <= file_tgt < 0x200000
        tag = f" (file+0x{file_tgt:06x})" if in_range else " [OOB]"
        print(f"  [{name:20s}] @ 0x{base+off:08x}  ->  0x{val:08x}{tag}")


def dump_isr_dispatch(flat_api, base, fw_data):
    """
    Dump the application-level ISR dispatch table at file offset ISR_DISPATCH_FILE_OFF.
    Each 4-byte entry is a pair of lrw instructions or 0xFFFFFFFF (unused).
    Decoded: lrw rZ, disp8 → pool = inst_file_off + 2 + disp8*4 (base-independent).
    """
    print(f"\n=== ISR Dispatch Table (file+0x{ISR_DISPATCH_FILE_OFF:06x}) ===")
    base_off = ISR_DISPATCH_FILE_OFF
    used = 0
    for i in range(ISR_DISPATCH_COUNT):
        off = base_off + i * 4
        b = fw_data[off:off + 4]
        if b == b'\xff\xff\xff\xff':
            continue
        used += 1
        hw1 = struct.unpack_from('>H', fw_data, off)[0]
        hw2 = struct.unpack_from('>H', fw_data, off + 2)[0]
        # Decode lrw: op12_15=0b0111, rZ=bits[11:8], disp8=bits[7:0]
        def decode_lrw(hw, hw_off):
            if (hw >> 12) == 0b0111:
                rz    = (hw >> 8) & 0xf
                disp8 = hw & 0xff
                pool_off = hw_off + 2 + (disp8 << 2)
                if pool_off + 4 <= len(fw_data):
                    pool_val = struct.unpack_from('>I', fw_data, pool_off)[0]
                    return f"lrw r{rz}, [pool@file+0x{pool_off:06x}]=0x{pool_val:08x}"
                return f"lrw r{rz}, disp8=0x{disp8:02x} [OOB pool]"
            return f"??? 0x{hw:04x}"
        d1 = decode_lrw(hw1, off)
        d2 = decode_lrw(hw2, off + 2)
        print(f"  [{i:2d}] file+0x{off:06x}: {b.hex()}  |  {d1}  /  {d2}")
    print(f"  ({used} active entries out of {ISR_DISPATCH_COUNT})")


def dump_functions(flat_api, program):
    """Print all functions found by auto-analysis, sorted by address."""
    print("\n=== Function List ===")
    fm   = program.getFunctionManager()
    fns  = list(fm.getFunctions(True))   # True = forward iterator
    fns.sort(key=lambda f: int(f.getEntryPoint().getOffset()))
    for f in fns:
        ep   = int(f.getEntryPoint().getOffset())
        body = f.getBody()
        size = body.getMaxAddress().getOffset() - body.getMinAddress().getOffset() + 1
        print(f"  0x{ep:08x}  (file+0x{fo(ep):06x})  {int(size):6d} B  {f.getName()}")
    print(f"  Total: {len(fns)} functions")
    return fns


def disassemble_at(flat_api, program, addr_int, count=24, label=""):
    """Disassemble 'count' instructions starting at addr_int (virtual)."""
    listing = program.getListing()
    addr    = flat_api.toAddr(addr_int)
    hdr     = label or f"0x{addr_int:08x} (file+0x{fo(addr_int):06x})"
    print(f"\n=== Disassembly @ {hdr} ===")
    instr = listing.getInstructionAt(addr)
    if instr is None:
        flat_api.disassemble(addr)
        instr = listing.getInstructionAt(addr)
    if instr is None:
        print("  (no instruction decoded)")
        return
    for _ in range(count):
        if instr is None:
            break
        print(f"  {fmt_addr(instr.getAddress())}  {instr}")
        instr = instr.getNext()


def decompile_at(program, monitor, addr_int, label=""):
    """Decompile the function at or containing addr_int."""
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
        print(f"\n=== Decompile {label or hex(addr_int)}: no function ===")
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


def ensure_func(flat_api, program, addr_int, name):
    """Disassemble and create a named function at addr_int if not already present."""
    a  = flat_api.toAddr(addr_int)
    flat_api.disassemble(a)
    fm = program.getFunctionManager()
    f  = fm.getFunctionAt(a)
    if f is None:
        f = flat_api.createFunction(a, name)
    return f


# ── main ─────────────────────────────────────────────────────────────────────

def run(flat_api, program, monitor, loaded_base, fw_data):
    _loaded_base[0] = loaded_base
    fw_size = int(program.getMemory().getSize())
    print(f"Firmware size: 0x{fw_size:x} ({fw_size} bytes)")
    print(f"Loaded at:     0x{loaded_base:08x}")

    # 1. Hardware vector table
    dump_vector_table(flat_api, loaded_base)

    # 2. ISR dispatch table (pure file-byte decode, no Ghidra needed)
    dump_isr_dispatch(flat_api, loaded_base, fw_data)

    # 3. Ensure the 3 startup/init functions are created
    print("\n=== Creating startup/init function entries ===")
    for i, file_off in enumerate(STARTUP_FN_OFFSETS):
        vaddr = loaded_base + file_off
        if file_off + 2 >= len(fw_data):
            print(f"  startup_{i}: file+0x{file_off:06x} out of file range")
            continue
        b = fw_data[file_off:file_off + 2]
        if b == b'\xff\xff':
            print(f"  startup_{i}: file+0x{file_off:06x} = 0xFFFF (empty/unused slot)")
            continue
        ensure_func(flat_api, program, vaddr, f"hw_init_{i}")
        print(f"  startup_{i}: file+0x{file_off:06x}  vaddr=0x{vaddr:08x}  first_hw={b.hex()}")

    # 4. Function list after auto-analysis
    fns = dump_functions(flat_api, program)

    # 5. Disassemble + decompile the 3 startup functions
    print("\n=== Hardware-variant init functions (disassembly + decompile) ===")
    for i, file_off in enumerate(STARTUP_FN_OFFSETS):
        vaddr = loaded_base + file_off
        b = fw_data[file_off:file_off + 2]
        if b == b'\xff\xff':
            print(f"\nhw_init_{i} (file+0x{file_off:06x}): empty slot")
            continue
        disassemble_at(flat_api, program, vaddr, count=32, label=f"hw_init_{i} (file+0x{file_off:06x})")
        decompile_at(program, monitor, vaddr, label=f"hw_init_{i}")

    # 6. Disassemble the reset entry point (start of file)
    print("\n=== Reset entry (file+0x000000) ===")
    disassemble_at(flat_api, program, loaded_base, count=32, label="reset_entry")

    # 7. Check ISR dispatch table region in Ghidra's view
    print("\n=== ISR dispatch table as Ghidra sees it (first 8 entries) ===")
    listing = program.getListing()
    isr_va = loaded_base + ISR_DISPATCH_FILE_OFF
    it = listing.getCodeUnits(flat_api.toAddr(isr_va), True)
    shown = 0
    while it.hasNext() and shown < 32:
        cu = it.next()
        if int(cu.getMinAddress().getOffset()) >= isr_va + 8 * 4:
            break
        print(f"  {cu.getAddress()}  {cu}")
        shown += 1


def main():
    fw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else FW_PATH
    if not fw_path.exists():
        print(f"ERROR: firmware not found: {fw_path}", file=sys.stderr)
        sys.exit(1)

    fw_data = fw_path.read_bytes()
    print(f"Firmware: {fw_path.name}  ({len(fw_data)} bytes)")

    import pyghidra
    print(f"Loading with PyGhidra (MCORE:BE:32:default, base 0x{BASE_ADDR:08x}) …")

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pyghidra.open_program(
            fw_path,
            language=LANG_ID,
            compiler=CSPEC,
            analyze=False,   # don't analyze yet — rebase first
        ) as flat_api:
            program = flat_api.getCurrentProgram()
            monitor  = flat_api.getMonitor()

            mem   = program.getMemory()
            block = mem.getBlocks()[0]
            loaded_base = int(block.getStart().getOffset())
            print(f"Ghidra initial base: 0x{loaded_base:08x}")

            # Rebase to BASE_ADDR (BSR targets need correct virtual addresses)
            if loaded_base != BASE_ADDR:
                print(f"Rebasing to 0x{BASE_ADDR:08x} …")
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

            # Disassemble the reset entry point before analysis so Ghidra
            # can propagate through the startup code
            print("Pre-disassembling reset entry …")
            flat_api.disassemble(flat_api.toAddr(loaded_base + 0))
            flat_api.disassemble(flat_api.toAddr(loaded_base + 0x008))

            # Now run auto-analysis
            print("Running auto-analysis …")
            flat_api.analyzeAll(program)

            run(flat_api, program, monitor, loaded_base, fw_data)


if __name__ == "__main__":
    main()
