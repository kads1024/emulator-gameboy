# ADR 0002: Timing model

## Status summary

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

Four test resources can decide questions about timing empirically rather than by
argument:
- The **SM83 per-opcode test suite**, which supplies initial state, final state, and the ordered list of bus transactions with their cycle positions. It validates not only what an instruction does but which M-cycle of the instruction each access belongs to.
- **Blargg `mem_timing`** and **`mem_timing-2`**, which test when within an instruction memory is accessed.
- **Blargg `instr_timing`**, which tests total instruction durations.
- The **power-on-anchored boot-ROM handoff comparison**, which establishes absolute phase because its anchor is initialization rather than a CPU access.

The SM83 and Blargg suites can settle whether the emulator uses an M-cycle-interleaved timing model rather than instruction-stepped timing. The power-on-anchored boot-ROM observation can settle the tick/access ordering itself, because it establishes an absolute phase reference rather than anchoring timing solely to CPU accesses.

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

**6. The CPU is the sole caller of the timed entry points.** Nothing else in the core calls them. A component that appears to need bus access (notably the OAM DMA engine, which is driven by the clock rather than being a consumer of it) uses the untimed component access path. If a second caller advanced time, a single M-cycle would advance global time more than once.

**7. Interrupt dispatch is composed of the same primitives.** Its stack writes are timed writes through the CPU path; its idle cycles are `tick()`. Dispatch has no special timing implementation of its own.

**8. Instruction duration is emergent.** How long an instruction takes is the sum of the advances it triggers. No duration table is consulted at runtime, and no opcode implementation reports a cycle count.

**9. Components receive time in M-cycle quanta and subdivide internally.** A component whose hardware resolution is finer than an M-cycle (the PPU, which works in dots) receives four dots at once and advances itself through them internally. This defines the accuracy ceiling of the model: no component can be observed at a T-cycle boundary interior to an M-cycle.

### Deliberately deferred

The following are IMPLEMENTATION DETAIL and are not decided here. They are recorded so a future reader knows the silence is deliberate.
- **The order in which timed components are advanced within one tick.** The rule is that the order is fixed and documented; which order is correct cannot be determined until there are peripherals whose interaction can be observed. Decided when the second timed peripheral exists.
- **Where the OAM DMA engine sits in that order,** and the mechanism by which its byte moves are performed given that no component may reference another. Decided at the milestone that introduces DMA.

## Alternatives considered

### Alternative 1: Instruction-stepped ("catch-up")

Instruction-stepped timing executes an entire CPU instruction first and advances the peripherals afterward by the instruction's total elapsed time. All bus accesses performed during the instruction therefore occur before the peripheral catch-up for that instruction.

This approach is attractive because it is simple to implement, fast, and requires no restructuring of a straightforward instruction interpreter. It has broad compatibility with commercial software and is commonly recommended as a starting point for emulator development.

The analysis predicts that instruction-stepped timing fails Blargg's `mem_timing` and `mem_timing-2` tests. These tests align the timer relative to the instruction under test by resetting the divider and padding with a known number of cycles, then repeat the test with the alignment shifted. The observable is the alignment at which the value read from `TIMA` (`$FF05`) changes. Because TIMA's fastest rate increments once every four M-cycles, that boundary reveals the M-cycle at which the access occurred.

Under instruction-stepped timing, every access in an instruction occurs at the same emulated timestamp, `t0`. Relative to the model adopted in this ADR, the k-th access occurs at `t0 + k` M-cycles; therefore its timing error is exactly `k` M-cycles under that ordering. However, the rejection of instruction-stepped timing does not depend on whether the correct ordering is `t0 + k` or `t0 + (k−1)`: under either ordering, instruction-stepped timing performs every access at a single timestamp, so its error is `k` or `k−1` M-cycles and grows with the access's position within the instruction. The error affects every access after the first under either ordering, and under the ordering adopted here it displaces the opcode fetch as well.

It is also structurally incompatible with the SM83 per-opcode tests, which specify the exact bus transactions and which M-cycle of the instruction each transaction belongs to. Instruction-stepped execution has no representation of when within an instruction an access occurs: every access shares the instruction's timestamp. The required cycle positions could therefore only be reproduced by consulting a per-opcode timing/transaction table, which would validate the table rather than the machine and would violate rule 8 of the Decision section. The SM83 tests use flat memory, so the values returned by those transactions may still be correct; what is incorrect is the position of each transaction in time.

This prediction is to be verified when the Blargg timing suites are first fetched and run. If instruction-stepped timing were to pass `mem_timing` and `mem_timing-2`, the analysis in this section would be falsified and the rejection of Alternative 1 would need to be re-examined.

This decision would otherwise be reversed only if the project changed its goals and explicitly chose to trade M-cycle accuracy for performance because the chosen timing model could not meet the performance floor recorded in ADR 0007. No such trade is currently sanctioned.

### Alternative 2: Tick-after-access

Tick-after-access performs the bus access first and then advances the M-cycle. Under this ordering, the k-th access of an instruction occurs at `t0 + (k−1)` M-cycles rather than `t0 + k`.

This ordering is plausible because the CPU's bus operation can be viewed as occupying the current M-cycle, with peripheral advancement occurring after that access. In particular, the opcode fetch for the next instruction during the final cycle of the current instruction makes the boundary between the access and the following cycle naturally align with access-then-tick.

The two orderings differ by a uniform phase shift of the entire CPU access stream relative to the tick stream. They have the same instruction duration, the same sequence of accesses, and the same intervals between CPU accesses. Therefore, observations whose timing anchors are all CPU accesses are invariant under the shift. Only an anchor established outside the CPU access stream can observe the absolute phase convention.

Blargg's `instr_timing`, `mem_timing`, and `mem_timing-2` tests are expected to be blind to the tick/access ordering to the extent that their timing anchors are CPU accesses. They can distinguish instruction-stepped timing from M-cycle-interleaved timing, but when their observations are anchored by CPU accesses, the uniform phase shift cancels. A test that samples a free-running counter without first resetting or otherwise establishing its phase would be an exception. This assumption must be re-verified when the suites are actually fetched and run. The SM83 per-opcode transaction tests are similarly blind to the intra-M-cycle ordering: they specify which bus transaction belongs to each M-cycle, but do not establish whether the tick occurs immediately before or immediately after the transaction within that M-cycle. These suites therefore adjudicate Alternative 1, not the tick/access ordering itself.

The ordering is adjudicated by a power-on-anchored observation. Execute the real boot ROM from reset and compare the machine state at boot-ROM handoff, in particular `DIV` and the PPU's position, against documented post-boot values and the skip-boot state. A one-M-cycle phase error relative to the power-on initialization provides an absolute reference that can distinguish the two conventions. Mooneye boot-state tests may provide a second instance of this class of oracle once the suite is fetched. This makes boot-ROM validation and this ordering decision the same test: skipping boot-ROM validation leaves the phase convention permanently unadjudicated.

Tick-then-access is adopted as the provisional convention not because it is inherently more accurate, but because it is internally consistent with the other timing rules: an access consumes the M-cycle it occupies, instruction duration corresponds directly to its access and internal-cycle count, and a read observes peripheral state after the tick associated with the transaction. The convention is therefore chosen for consistency with rules 3, 5, and 8, pending the power-on-anchored evidence.

Reversing the ordering would require changing the ordering defined by rule 3, while rule 2 ensures that the change is localized to the single mechanism responsible for advancing time. The practical risk is broader because an incorrect phase could have been silently compensated elsewhere, such as by tuning an initial `DIV` or other peripheral state in the skip-boot state. Any such compensating offset must be documented in `docs/known-shortcuts.md` rather than silently introduced. The direct reversal is therefore localized to the rule-2 mechanism, but all phase-dependent initialization and timing tests must be revalidated.

## Consequences

### The CPU remains an ordinary interpreter
It is commonly claimed that M-cycle-accurate timing requires restructuring the CPU as a suspendable state machine. That claim assumes the host loop drives the CPU one M-cycle at a time, which forces the CPU to be resumable between cycles. This ADR inverts that control flow: time advances underneath the CPU because the bus operation advances it, so the CPU is written as a straightforward recursive interpreter and never suspends. The restructuring cost usually attributed to this model does not apply here.

### Emulation is not preemptible below the instruction boundary
Because the CPU never suspends, the host cannot stop it partway through an instruction. Save states, breakpoints, and any future rewind facility are instruction-boundary granular. A debugger cannot offer "break at M-cycle 3 of this `CALL`" without the state machine this ADR avoids. This is accepted: instruction-boundary snapshots are complete and deterministic, which is what `docs/scope.md` section 8 and the save-state requirements need.

### The timed path has exactly one caller, permanently
Rule 6 is not a stylistic preference; it is the invariant that keeps one M-cycle of emulated time equal to one advance. Every future bus master (OAM DMA first, anything else later) uses the untimed component path, and the component's owner performs the byte movement on its behalf, since no component may reference another. This is a constraint on the design of every peripheral added from here on.

### The accuracy ceiling is one M-cycle
Components receive time in M-cycle quanta and subdivide internally. A dot-accurate renderer remains possible, because the PPU subdivides its four dots itself. What is not representable is an interaction where the CPU and a peripheral must be interleaved *within* an M-cycle. Behaviour that depends on such interleaving cannot be reproduced without moving to T-cycle stepping, which is out of scope for this ADR and would be a separate decision with its own evidence.

### Every bus access pays for advancing every timed component
This is the principal cost of the model and the reason a performance floor exists at all. The advance mechanism is on the hottest path in the emulator: no allocation, no I/O, and no virtual dispatch may appear in it. ADR 0007 records the floor and its measurement.

### Absolute phase is unverified until boot-ROM validation
Per Alternative 2, the tick/access ordering is a phase convention that no interval-anchored test can settle. Until a real boot ROM is executed from reset and the handoff state compared against documented values, the convention is adopted but unverified. Any offset introduced anywhere outside the single advance mechanism to make a timing test pass is a compensation for a possible phase error, not a fix, and is recorded in `docs/known-shortcuts.md` as such.

### The CPU's primary oracle constrains the test harness
The SM83 per-opcode suite supplies arbitrary memory contents across the whole address space and expects reads and writes to behave uniformly. Exercising it therefore requires a bus configured with test-oriented components (flat memory in place of a mapper, and no rendering-mode locking) rather than an abstraction introduced for mocking. This is consistent with the project's decision to test the CPU against a concrete bus.

### Duration tests double as structure tests
Because instruction duration is emergent (rule 8), a wrong duration is evidence of a wrong access sequence rather than a wrong table entry. A failure in an instruction timing suite localises to the structure of the instruction, which is a more useful diagnostic than a mismatched constant.

### Deferred by this ADR
- The order in which timed components are advanced within one tick.
- The position of the OAM DMA engine in that order, and the mechanism by which its byte moves are performed.
- The exact point at which pending interrupts are sampled relative to the instruction boundary. This model determines that such a point exists and is expressible in M-cycles; it does not determine which cycle it is. Decided when the interrupt controller is implemented.

## Status

### Classification
- **Timing model (tick-on-bus-access):** BLOCKING ARCHITECTURAL DECISION: accepted.
- **Access ordering (tick-then-access):** PROVISIONAL: adopted as a phase convention, pending the evidence named below.

### Amendment to the originally specified adjudication mechanism
The project's original decision brief nominated Blargg `mem_timing`, `mem_timing-2`, and the SM83 per-opcode transaction tests as the adjudicators of the *ordering*. Analysis recorded under Alternative 2 establishes that those suites adjudicate the timing model (tick-on-bus-access versus instruction-stepped) but are blind to the tick/access ordering itself, because their timing anchors are CPU accesses and the two orderings differ by a uniform shift of the entire access stream.

The adjudicator for the ordering is therefore amended to the power-on-anchored observation described under Alternative 2. This is an amendment to the evidence, not to the decision.

### What would settle the ordering
Execution of a real boot ROM from reset, with the machine state at handoff (`DIV` and the PPU's position in particular) compared against documented post-boot values and against the skip-boot state table. Boot-ROM validation and this decision are the same test.

### What would reopen the model
Nothing about accuracy: instruction-stepped timing is a strict accuracy subset of this model. Only a change in project goals (an explicit decision to trade M-cycle accuracy for performance because the floor in ADR 0007 could not be met) would reopen it. No such trade is sanctioned.

### Review trigger
This ADR is revisited when boot-ROM execution is implemented and validated, at which point the ordering is either confirmed or corrected and its status changes from PROVISIONAL to accepted or superseded.