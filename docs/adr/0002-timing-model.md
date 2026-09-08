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

### Alternative 1: Instruction-stepped ("catch-up")

Instruction-stepped timing executes an entire CPU instruction first and advances the peripherals afterward by the instruction's total elapsed time. All bus accesses performed during the instruction therefore occur before the peripheral catch-up for that instruction.

This approach is attractive because it is simple to implement, fast, and requires no restructuring of a straightforward instruction interpreter. It has broad compatibility with commercial software and is commonly recommended as a starting point for emulator development.

It is rejected empirically by Blargg's `mem_timing` and `mem_timing-2` tests. These tests align the timer relative to the instruction under test by resetting the divider and padding with a known number of cycles, then repeat the test with the alignment shifted. The observable is the alignment at which the value read from `TIMA` (`$FF05`) changes. Because TIMA's fastest rate increments once every four M-cycles, that boundary reveals the M-cycle at which the access occurred. Under instruction-stepped timing, every access in an instruction occurs at the same emulated timestamp, `t0`. Relative to the model adopted in this ADR, the k-th access occurs at `t0 + k` M-cycles; therefore Option A's timing error is exactly `k` M-cycles under that ordering. However, the rejection of Option A does not depend on whether the correct ordering is `t0 + k` or `t0 + (k−1)`: under either ordering, Option A performs every access at a single timestamp, so its error is `k` or `k−1` M-cycles and grows with the access's position within the instruction. The error affects every access after the first under either ordering, and under the ordering adopted here it displaces the opcode fetch as well.

It is also rejected structurally by the SM83 per-opcode tests, which specify the exact bus transactions and their cycle positions. Instruction-stepped execution has no representation of when within an instruction an access occurs: every access shares the instruction's timestamp. The required cycle positions could therefore only be reproduced by consulting a per-opcode timing/transaction table, which would validate the table rather than the machine and would violate rule 8 of the Decision section. The SM83 tests use flat memory, so the values returned by those transactions may still be correct; what is incorrect is the position of each transaction in time.

This decision would be reversed only if the project changed its goals and explicitly chose to trade M-cycle accuracy for performance because the chosen timing model could not meet the performance floor recorded in ADR 0007. No such trade is currently sanctioned.

