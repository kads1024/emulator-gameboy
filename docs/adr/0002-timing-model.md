# ADR 0002: Timing model

## Status

This ADR records two decisions with different classifications.

- **Timing model (tick-on-bus-access):** BLOCKING ARCHITECTURAL DECISION: accepted.
- **Access ordering (tick-then-access):** PROVISIONAL: adjudication mechanism recorded in the Status section at the end of this document.

## Context

### The problem

On real hardware, the CPU, PPU, timer, and APU run simultaneously, driven by a single 4,194,304 Hz clock. In an emulator they run sequentially. Every emulator therefore approximates simultaneity by interleaving its components, and the granularity of that interleaving is the accuracy of the machine.

This ADR decides that granularity and, equally important, decides *where in the code the advance of time is triggered from*.

### The hardware facts that constrain the answer

1. **There is one clock, and every component counts the same ticks.** Components do not merely need to be individually correct; they need to be correct relative to each other. A PPU that runs one percent fast relative to the CPU produces a register write that lands a scanline late.

2. **The CPU's smallest real step is the M-cycle (four T-cycles) and an M-cycle is one bus transaction.** Instruction durations are not arbitrary numbers; they are the count of bus accesses plus internal operations, multiplied by four.

3. **Peripherals observe and are observed at instants, not over intervals.** A read of a status register returns what that peripheral's state is at that exact cycle. A write to a control register takes effect from that exact cycle. Both the value read and the effect of the value written depend on precisely when within an instruction the access occurs.

4. **Peripherals run continuously and are not driven by the CPU.** The PPU is drawing whether or not the CPU is looking. Time passing is the only thing that advances them.

### What makes this decision expensive to revisit

The timing model determines the shape of the CPU's execution path, the signature of every bus operation, and whether components can observe intermediate states within an instruction. Changing it later is not a local edit; it is a rewrite of the CPU and of every call site that touches memory. `docs/scope.md` section 8 names the timing model as one of two things that must never be rewritten under force. This ADR is where that commitment is spent.

### Available oracles

Three test resources can decide questions about timing empirically rather than by
argument:
- The **SM83 per-opcode test suite**, which supplies initial state, final state, and the ordered list of bus transactions with their cycle positions. It validates not only what an instruction does but when each access happens.
- **Blargg `mem_timing`** and **`mem_timing-2`**, which test when within an instruction memory is accessed.
- **Blargg `instr_timing`**, which tests total instruction durations.

Their existence is the reason the ordering sub-decision can be marked provisional rather than argued indefinitely: there is a mechanism that can settle it.

### Out of scope for this ADR

This ADR does not decide the PPU's rendering strategy, the save-state format, or the frontend's frame pacing. It decides only how time advances inside the core and what triggers that advance.