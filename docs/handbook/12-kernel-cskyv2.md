---
title: "12. The CK803S / C-SKY V2 kernel port (Miosix)"
---

# 12. The CK803S / C-SKY V2 kernel port (Miosix)

## What it is / how it works

The HD2's SoC (HR_C7000) runs a **CK803S core** — a single-core, in-order C-SKY V2
CPU with *no* Cortex-M-style hardware exception frame. On any exception the core
saves **only** PC→EPC (`cr<4,0>`) and PSR→EPSR (`cr<2,0>`), clears `PSR.IE`, and
pushes **nothing** to the stack. Vectoring is table-driven through the **VBR**
(`cr<1,0>`): the core loads the word at `VBR + vec*4` and jumps to that address.
`rte` reverses entry: PC←EPC, PSR←EPSR (re-enabling `IE`). There is **no PendSV,
no SVCall, no NVIC** — the whole preemption model the stock Miosix Cortex-M ports
assume is absent and must be re-created.

The port (`vendor/miosix-kernel/miosix/arch/cpu/cskyv2/`) reconstructs it with
three ingredients. (1) A **manual full-register context frame** — CK803S only
implements the 16-register base file (r0–r15), so a preemption frame is r0–r13
(`stm`) + r15/lr + EPC + EPSR + pad = **72 bytes** (`FRAME_SIZE 0x48`), pushed
full-descending onto the *interrupted thread's own stack*. `sp`(r14) is not in
the frame — it *is* the frame pointer, published to `ctxsave[0]`. (2) A
**software PendSV substitute**: a `volatile bool s_schedPending` flag plus the
synchronous `trap 0` instruction (which fires regardless of `PSR.IE`). (3) A
**custom two-channel os_timer** on the DesignWare timer block, because that
block has neither a match register nor a software-pend IRQ (the two things
Miosix's `TimerAdapter` requires).

Mental model: every PIC source (incl. the OS tick) autovectors to a single
`generic_irq_entry` stub that does *save → dispatch → restore*; the context
switch is taken at that stub's restore — deferred-PendSV, hand-rolled.

## How to implement it

**Exception vectoring** (`interrupts.cpp` `IRQinitIrqTable`): build a 128-entry
VBR table (`CK803S_VBR_NVEC=128`, 1 KiB aligned). Point every slot at `fault_entry`, then override:
- `g_vbrTable[16]` (`CK803S_YIELD_VEC`) → `yield_isr_entry` — `trap 0` = cooperative yield.
- `g_vbrTable[32..95]` (`HRC7000_PIC_VECTOR0=32` + PIC source) → `generic_irq_entry`.

Install with `csky_set_vbr()` (`mtcr rX, cr<1,0>`). PIC @ `0x17000000`: level,
active-high, all sources masked (`PIC_MASK=0xFFFFFFFF`, bit=0 *enables*);
`IRQregisterIrqOnCore` unmasks per source. Timer1 = PIC src1 → vec33, Timer2 =
PIC src2 → vec34.

**Context save/restore** (`cskyv2_context.S`). Frame offsets: r0–r13 at
`+0x00..+0x34`, r15 at `+0x38`, EPC at `+0x3c`, EPSR at `+0x40`, pad `+0x44`.
`CTX_SAVE` snapshots EPC/EPSR from `cr<4,0>`/`cr<2,0>` into the frame and
publishes `sp` to `ctxsave[0]`; `CTX_RESTORE` re-reads `ctxsave[0]` (the
scheduler may have repointed it at a different thread), writes EPC/EPSR back and
`rte`s. Carrying EPC/EPSR *in the frame* makes new-thread and resumed-thread
restore identical. Constants that must agree: `CTXSAVE_SIZE=2`,
`CTXSAVE_ON_STACK=72`, `STACK_OFFSET_IN_CTXSAVE=0`, `CTXSAVE_STACK_ALIGNMENT=8`
(`cpu_const_impl.h`).

**New-thread seeding** (`cpu.cpp` `initKernelThreadCtxsave`): lay down the same
72-byte frame 18 words below the stack top — `r0=arg0`, `r1=arg1`,
`r15=0xffffffff` (lr sentinel), `EPC=threadLauncher`, **`EPSR=0x80000140`** =
`S(bit31, supervisor) | EE(bit8) | IE(bit6)`. The supervisor bit is essential —
without it the thread runs unprivileged and its first MMIO access faults.

**First switch** (`cpu.cpp` `IRQportableStartKernel`): `Scheduler::IRQrunScheduler()`
to select the first thread, then `csky_first_switch()` — a bare `CTX_RESTORE`
that `rte`s into it. Do **not** use a trap for the first switch.

**The scheduler-invoke decision** (`cpu_impl.h` `IRQinvokeScheduler`):
```
if (areInterruptsEnabled() && !s_inIrq)  csky_yield_switch();   // thread ctx: switch now
else                                     s_schedPending = true; // IRQ/lock: defer
```
`csky_yield_switch` saves the current thread with the resume PC set to a
`.Lyield_resume` trampoline, executes **`psrclr ie`** (run the scheduler with
IRQs off), repoints `ctxsave`, and `rte`s into the next thread. The
`csky_isr_dispatch` C body services fired PIC sources, EOIs, then — as it leaves
IRQ context — honours `s_schedPending` by calling `IRQrunScheduler()` so the
enclosing stub's `CTX_RESTORE` performs the switch.

**os_timer** (`hr_c7000_os_timer.cpp`, `OS_TIMER_MODEL_UNIFIED`): DW timers @
`0x14000000`, stride `0x14`, regs `+0x00 LoadCount / +0x04 CurrentValue /
+0x08 Control (b0 en, b1 user-def-reload, b2 intmask) / +0x0c EOI (read-clear) /
+0x10 IntStatus`. TIME_CH (ch0) free-runs down from `0xFFFFFFFF`; virtual
up-counter = `0xFFFFFFFF - CurrentValue`, overflow IRQ bumps the upper 32 bits
(TimerAdapter pending-bit trick). WAKE_CH (ch1) is a one-shot match armed by
`IRQosTimerSetInterrupt` with the relative tick count; if past-due it loads `1`
to fire ASAP (this replaces `IRQforcePendingIrq`). `HRC7000_TIMER_HZ = 42 MHz`,
verified on silicon; `TimeConversion` 32.32 fixed-point.

**Boot** (`interrupts.cpp` `Reset_Handler` → `boot.cpp` `IRQmemoryAndClockInit`
→ `IRQkernelBootEntryPoint`): `Reset_Handler` is naked in `.isr_vector`, the
first code at flash base `0x0300d000` (the Dahua IAP jumps there and executes).
It sets `PSR=0x80000000` (supervisor, IE/EE off), clears `cr<31,0>` bit3 (random
prefetch enable), sets `sp=_irq_stack_top`, calls `IRQmemoryAndClockInit`, then
resets `sp=_heap_end` and calls the kernel boot. (For how the IAP reaches this
entry, see the [boot & IAP chapter](02-boot-flash-pipeline).) `IRQmemoryAndClockInit`
**disables the IAP watchdog first** (`0x14010000 = 0x5ada7200` unlock,
`0x14010010 = 0` WDG_EN) then brings up APLL/BPLL via SOCSYS @ `0x11000000`.
`IRQbspInit` (`bsp.cpp`) sets LEDs PTB0(green)/PTB1(red) as outputs, holds the
PTB13 power self-latch, and inits the UART0 debug console (`0x14030000`, 57600
8N1, `DLL=46` at the post-PLL 42 MHz ref).

## Gotchas & cautions

- ⚠️ **The no-PendSV contract is the #1 killer.** Any blocking path that
  re-enables IRQs with a bare `fastEnableIrq()` (no drain) silently breaks it:
  the thread keeps running while marked WAITING until the next IRQ, racing the
  wake path → ~1/40k windows corrupt scheduler state → permanent "drain into
  eternal sleep" (the old stochastic 10–30 s hard lock). **Fix pattern
  (`d4ef8cf6`):** claim `s_schedPending` *before* IE-on, `Thread::yield()`
  *after*. Audit every new blocking primitive for this.
- The `psrclr ie` in `csky_yield_switch` is **required, not optional** — without
  it a timer/WAKE IRQ landing mid-`IRQrunScheduler` re-enters the scheduler on
  the same ready-lists (the fast-keypress hang).
- ⚠️ **PIC EOI does not clear the record.** `PIC_COW1=eoi` only pops the single
  highest-priority in-service entry. You must write-1-clear `PIC_INT_ST` /
  `PIC_INT_ST1` for every serviced source, *after* the handlers run. Skipping
  this looks fine until a **2nd** source fires (the TIME_CH overflow at ~102 s)
  → un-popped record re-dispatches on every IRQ → spurious storm collapses all
  sleeps into a busy-loop.
- ⚠️ **Clamp the wake horizon before `nsToTicks`.** The scheduler arms
  `IRQosTimerSetInterrupt(numeric_limits::max())` when idle; converting that
  absolute "infinity" overflows 64-bit → `rel<1` → the timer fires ASAP forever
  (thread starvation). Compute a *relative* delay and clamp to
  `WAKE_MAX_HORIZON_NS` (~102 s) first. This was THE `Thread::sleep` blocker.
- **Frame width is load-bearing.** Don't shrink below r0–r13+r15 — a preemption
  can interrupt a thread holding live t-regs; a narrow frame = silent
  cross-thread corruption. (CK803 never allocates above r15, so r16+ need not be
  saved; there is no GBR/r28 on this core.)
- Don't seed a thread's EPSR without bit31 (supervisor) — it will fault on its
  first privileged/MMIO access.
- **shutdown must reset the modem blocks** (`0x11000000 = 0xfffffe00`, bits 0–8),
  not just CPU+system: live modem blocks leave the clock tree in a state where
  the post-reset `clk_init` hangs (the "won't power up until the cable is
  pulled" wedge). Do the QUAD_ENABLE poke (`0x1100005c = 0x01000000`) first.
- WDT reset does **not** reset the clock tree — call the clock-restore path
  before any deliberate jump/reset to the IAP or its UART runs at the wrong baud.

## Where the code lives

- CPU (C-SKY V2): `vendor/miosix-kernel/miosix/arch/cpu/cskyv2/`
  - `cskyv2_context.S` — the frame, `CTX_SAVE`/`CTX_RESTORE`, `csky_first_switch`,
    `csky_yield_switch`, `yield_isr_entry`, `generic_irq_entry`, `fault_entry`.
  - `interrupts.cpp` — VBR table, PIC dispatch (`csky_isr_dispatch`),
    `Reset_Handler`, fault reporter, `s_schedPending`/`s_inIrq`.
  - `interfaces-impl/cpu_impl.h` — `IRQinvokeScheduler` (the PendSV substitute).
  - `interfaces-impl/cpu.cpp` — `initKernelThreadCtxsave`, `IRQportableStartKernel`, `sleepCpu`.
  - `interfaces-impl/cpu_const_impl.h`, `interrupts_impl.h`, `arch_registers_impl.h`.
- CHIP (HR_C7000): `vendor/miosix-kernel/miosix/arch/chip/hr_c7000/`
  - `hr_c7000_os_timer.cpp` — the two-channel tickless timer.
  - `interfaces-impl/delays.cpp`, `poweroff.cpp`, `gpio_impl.h`.
- BOARD (HD2): `vendor/miosix-kernel/miosix/arch/board/hrc7000_hd2/`
  - `boot.cpp` — `IRQmemoryAndClockInit` (WDT-off + PLL).
  - `interfaces-impl/bsp.cpp` — LEDs/power-latch/UART0 console, `shutdown`, `reboot`.

## Status & deeper reading

**Status: 🟡 in-progress — core proven on silicon.** HW-verified pieces:
context save/restore + first switch, PIC autovector + the write-1-clear storm
fix, the 42 MHz timebase and `TimeConversion` round-trip, WDT-off/PLL boot, the
fault reporter, LED/UART bring-up. **Known gap:** `IRQinvokeScheduler`'s deferred
switch under the global lock is currently taken only at the next IRQ (no true
PendSV-equivalent), so a thread that unblocks a higher-priority thread *under the
lock* keeps running until the next tick — `Thread::sleep` is not yet fully
prompt. The full fix needs the global-lock release path to honour
`s_schedPending` (or a real deferred-switch interrupt, e.g. the core-VIC
TSPEND/vec22). ⚠️ The earlier "old vendored Miosix in-repo" route is **superseded**
— it structurally requires the Miosix-patched newlib (pthread-struct + `__getreent`)
and cannot build on the stock Xuantie toolchain; the modern arch/cpu+chip+board
port above + a patched `csky-miosix-elf` toolchain is the live path.

Deeper reading:
- `tmp/miosix_modern_port_spec.md` — the modern-port file layout + context-switch mapping.
- `tmp/miosix_port_plan.md` — phased bring-up, risk map, the newlib strategic wall.
- `docs/threading_redesign.md` — event-driven redesign, PIC source table, scheduler guardrails.
- memory `hd2-hard-lock-solved-pendsv-drain` — the no-PendSV drain rule + forensics recipe.
- Skill `hd2-kernel-dev` — reference ports (Linux arch/csky, RT-Thread ck803, FreeRTOS ck802).
