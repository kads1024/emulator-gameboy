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

## Decision

Time advances in M-cycle quanta, triggered by the CPU's bus operations. Concretely:

**1. The unit of advance is one M-cycle.** Every advance moves global time forward by exactly four T-cycles. There is no partial advance and no variable-size advance.

**2. Exactly one mechanism performs the advance.** A single function moves time forward and advances every timed component. Timing semantics are never duplicated across opcode implementations, peripherals, or call sites.

**3. Time advances before the access it pays for.** A bus operation advances the clock by one M-cycle and then performs the read or write. Reads and writes follow the same ordering.

**4. The bus exposes exactly three timed entry points, and each advances exactly one M-cycle:**
| Entry point | Effect |
|---|---|
| `read(addr)` | advance one M-cycle, then perform the routed read, return the value |
| `write(addr, value)` | advance one M-cycle, then perform the routed write |
| `tick()` | advance one M-cycle, perform no access |

**5. Internal CPU cycles are explicit and unbatched.** Any cycle an instruction consumes without a bus access consumes `tick()` at the point in the instruction where the hardware consumes it. Internal cycles are never collected at the start or end of an instruction, and never folded into an adjacent access.

**6. The CPU is the sole caller of the timed entry points.** Nothing else in the core calls them. A component that appears to need bus access — notably the OAM DMA engine, which is driven by the clock rather than being a consumer of it — uses the untimed component access path. If a second caller advanced time, a single M-cycle would advance global time more than once.

**7. Interrupt dispatch is composed of the same primitives.** Its stack writes are timed writes through the CPU path; its idle cycles are `tick()`. Dispatch has no special timing implementation of its own.

**8. Instruction duration is emergent.** How long an instruction takes is the sum of the advances it triggers. No duration table is consulted at runtime, and no opcode implementation reports a cycle count.

**9. Components receive time in M-cycle quanta and subdivide internally.** A component whose hardware resolution is finer than an M-cycle — the PPU, which works in dots — receives four dots at once and advances itself through them internally. This defines the accuracy ceiling of the model: no component can be observed at a T-cycle boundary interior to an M-cycle.

### Deliberately deferred

The following are IMPLEMENTATION DETAIL and are not decided here. They are recorded so a future reader knows the silence is deliberate.
- **The order in which timed components are advanced within one tick.** The rule is that the order is fixed and documented; which order is correct cannot be determined until there are peripherals whose interaction can be observed. Decided when the second timed peripheral exists.
- **Where the OAM DMA engine sits in that order,** and the mechanism by which its byte moves are performed given that no component may reference another. Decided at the milestone that introduces DMA.

## Alternative 1: Instruction-stepped timing

Under an instruction-stepped model, the CPU executes the entire instruction first and peripherals are advanced afterward based on the instruction's total cycle count.

**Q1:** I think that under instruction-stepped execution, the peripherals have experienced 0 M-cycles when the M3 access happens, because they only advance after the instruction finishes.

**Q2:** The timer and PPU seem like the obvious candidates because they change continuously and their state can be observed by the CPU.

**Q3:** A CPU write to a peripheral control register should affect the peripheral at that point in the instruction, so the remaining M-cycles should run with the new state. Instruction-stepped execution delays the peripheral's progression until after the instruction.

**Q4:** The SM83 per-opcode tests seem to be the structural oracle because they specify the exact bus transactions and their cycle positions. An instruction-stepped model can't naturally expose the intermediate timing/state at those positions.

