# Architecture Principles

These principles derive from two sources: the hardware model of the DMG, and the scope committed in `docs/scope.md`. They are cited by number in code review. A principle that cannot be failed against is not a principle and does not belong in this file.

Each entry states:
- **Hardware fact**: the property of the machine the principle comes from.
- **Rule**: what the code must do.
- **Fails review**: concrete shapes that violate it.
- **Enforcement**: `CI` (a job fails), `grep` (mechanically findable by a reviewer), or `review` (requires human judgement).

Where a principle is not final, it carries a **Status** line naming what would change it.

---

## Part A: Time

### P1. One clock. One mechanism that advances it.

**Hardware fact.** A single crystal drives the whole machine at 4,194,304 Hz. CPU, PPU, timer, and APU are not merely each correct; they are correct *relative to each other* because they count the same ticks.

**Rule.** Exactly one function in the codebase advances global time, and it advances every timed component in a fixed, documented order.

**Fails review.**
- A component holding a cycle counter that some other code increments.
- Any `step(cycles)` or catch-up entry point in the core.
- Cycle arithmetic inside an opcode implementation.

**Enforcement.** grep, review.

### P2. Tick before access. Always, everywhere.

**Hardware fact.** A bus transaction occupies the machine cycle; the value is available at its end.

**Rule.** Every timed access advances the clock by one M-cycle and then performs the access. Internal CPU cycles consume their own explicit tick and are never batched at the start or end of an instruction.

**Fails review.**
- An instruction that performs several accesses and then ticks N times.
- An internal cycle absorbed into an adjacent access.
- A path that skips the tick because "nothing observes it."

**Status.** PROVISIONAL. Adjudicated by Blargg `mem_timing`, Blargg `mem_timing-2`, and the SM83 per-opcode bus transaction tests. Reopened only by concrete test evidence that this ordering cannot reproduce required behavior, never by a theoretical alternative.

**Enforcement.** CI (the named suites), review.

### P3. Instruction timing is emergent, never tabulated.

**Hardware fact.** An instruction's duration *is* its sequence of bus transactions plus its internal cycles. The published cycle counts are consequences, not definitions.

**Rule.** How long an instruction takes is a result of what it does. Nothing consults a duration table at runtime.

**Fails review.**
- A cycle-count table indexed by opcode, used by the interpreter.
- A taken/not-taken cycle table for conditional branches.
- An opcode handler that returns a cycle count.

A duration table in *test* code, asserting emergent behavior against documented values, is correct and encouraged. The distinction is which direction the information flows.

**Enforcement.** grep, review.

---

## Part B: The bus

### P4. The bus is the only address decoder.

**Hardware fact.** There is one shared bus. Whatever is wired to an address answers; the CPU cannot tell what kind of thing responded.

**Rule.** All routing from address to responder happens in one place. No component reaches into another's storage by direct indexing.

**Fails review.**
- A second place that decides what lives at an address range.
- A "fast path" that indexes a memory array directly to avoid routing.

**Enforcement.** review.

### P5. Three access paths. One caller each.

**Hardware fact.** Different bus masters have different rights. The CPU is subject to locking and consumes time; the PPU reading its own VRAM is not; a debugger is not part of the machine at all.

**Rule.** Three distinct paths exist:

| Path | Ticks | Locking | Side effects | Sole caller |
|---|---|---|---|---|
| CPU access | yes | yes | yes | the CPU |
| Component access | no | no | as required | owners, on behalf of components |
| Debug access | no | no | no | tooling |

The timed path has exactly one caller: the CPU. Anything else that appears to need it (including DMA, which is driven by the clock rather than a consumer of it) uses the component path, or global time advances twice per M-cycle.

**Fails review.**
- Any non-CPU call site of the timed path.
- A trace or debugger routine reading memory or instruction bytes through the timed path.
- A boolean flag threaded through one function in place of three paths.

**Enforcement.** grep, CI (call-site check once the paths exist).

### P6. I/O registers are behavior, not storage.

**Hardware fact.** An address in the I/O range is a control panel, not a byte. Reads can have side effects, writes can trigger events, and what reads back is often not what was written.

**Rule.** Every I/O address has explicit read and write logic, including read-only, write-only, and unused-bit behavior.

**Fails review.**
- A byte array backing the I/O range.
- A register read returning the last written value without a documented reason.
- Unused bits reading back as 0 where hardware returns 1.

**Enforcement.** review, CI (test ROMs).

### P7. The component that owns a resource enforces access to it.

**Hardware fact.** VRAM and OAM are inaccessible during certain PPU modes because the PPU is using them. The lock is a property of the user, not of the address.

**Rule.** Accessibility rules live with the owning component and are queried by the bus. They are not duplicated in routing logic.

**Fails review.**
- PPU mode comparisons inside the bus's routing code.
- Two places that both decide whether VRAM is currently readable.

**Enforcement.** grep, review.

---

## Part C: Components and ownership

### P8. No component knows another exists.

**Hardware fact.** Chips are wired to a bus, not to each other. Coordination happens through addresses and through time.

**Rule.** No component stores a pointer or reference to another component, to the bus, or to the system root. Components communicate through values, explicit parameters, return values, and state exposed to their owner. Ownership lives in the root object.

**Fails review.**
- A member pointer or reference to another component, to `Bus`, or to `System`.
- `shared_ptr` anywhere in the core.
- `unique_ptr` without a written ownership or polymorphism justification.
- A constructor taking a peripheral it does not own.

**Enforcement.** grep, review.

### P9. Peripherals raise lines. The controller detects edges.

**Hardware fact.** A peripheral has control registers, status registers, and an interrupt *line*. STAT interrupt blocking is a property of how those lines combine, not of any single source.

**Rule.** Peripherals expose line state as data. The interrupt controller samples lines, performs edge detection, and latches `IF`.

**Fails review.**
- Any peripheral writing `IF`.
- Edge detection implemented inside the PPU or the timer.
- A peripheral that "fires" an interrupt as a call rather than exposing a level.

**Enforcement.** grep, review.

### P10. No interface with a single implementation.

**Hardware fact.** There is one PPU, one timer, one CPU. There are several cartridge mappers, and even those are a closed set fixed at load time.

**Rule.** Virtual dispatch and abstract interfaces appear only where the hardware itself is polymorphic. Abstractions are not introduced for testability; tests use test-oriented component implementations against concrete types.

**Fails review.**
- An abstract base class with one implementation.
- An interface introduced so something can be mocked.
- A plugin system, an accuracy-level configuration, or a scheduler with nothing to schedule.

**Enforcement.** review.

---

## Part D: State and determinism

### P11. The core is a closed, deterministic system.

**Hardware fact.** The machine's next state is a function of its current state and its inputs. Nothing else. The console does not read files, open windows, or consult a clock.

**Rule.** The core links only the standard library, performs no I/O, reads no host clock, and contains no randomness. Real-world time enters only as an explicit parameter, for the MBC3 RTC. The core accepts bytes and input state; it emits shade indices and audio samples. Filesystem access belongs to the tools and the frontend.

**Fails review.**
- `<iostream>`, `<cstdio>`, `<filesystem>`, `<chrono>`, `<random>`, or `<thread>` in a core translation unit.
- Any link dependency of the core target.
- A host handle stored in core state.

**Enforcement.** CI (purity check).

### P12. All machine state is reachable from the root, as plain data.

**Hardware fact.** The machine has no hidden state surviving a power cycle except battery-backed cartridge RAM.

**Rule.** Every byte of emulation state is reachable by walking from the root object and is expressible as plain data. No statics, no function-local statics, no state held in closures, no emulation state in the frontend.

**Fails review.**
- A `static` variable inside a core function.
- State living only in a lambda capture.
- A field that cannot be named by a field-by-field serializer.

**Enforcement.** grep, review.

### P13. The framebuffer holds post-palette shade indices.

**Hardware fact.** Palette lookup is a stage of the pixel pipeline inside the PPU, and games rewrite palette registers mid-frame.

**Rule.** The PPU applies `BGP`, `OBP0`, and `OBP1` at the moment each pixel is produced. The core emits shade indices 0–3. The frontend owns the mapping from shade index to displayed color.

**Fails review.**
- RGB values anywhere in the core.
- Palette application performed by the frontend.
- A palette type representing more than four shades.

**Enforcement.** grep, review.

---

## Part E: Honesty

### P14. Unknown behavior is loud.

**Hardware fact.** The machine has definite behavior everywhere, including the prohibited region and open bus. Where *we* do not know that behavior, the gap is ours, not the machine's.

**Rule.** Unimplemented or unknown behavior produces a debug assertion or a counted, rate-limited diagnostic. It never returns a plausible value. Debug builds make it easy to detect; release builds neither flood output nor break the performance floor.

**Fails review.**
- `default: return 0;`
- A returned constant with a comment expressing uncertainty.
- A silently swallowed write to an unimplemented register.

**Enforcement.** grep, review.

### P15. Every deliberate inaccuracy is tracked debt.

**Rule.** Any known deviation from hardware behavior has an entry in `docs/known-shortcuts.md` with an assigned removal milestone. An undocumented deviation is a defect. The review question is always: which entry covers this?

Behavior that is correct for the hardware being emulated is not debt; it belongs in `docs/scope.md` section 5 under the admission rule stated there.

**Fails review.**
- A comment noting an inaccuracy with no corresponding entry.
- An entry with no removal milestone.

**Enforcement.** review, CI (once the file has entries to cross-check).

### P16. Every subsystem ships with an automatable oracle.

**Hardware fact.** The behaviors that matter are the ones the ecosystem's test ROMs encode; they cannot be derived by reading alone.

**Rule.** A subsystem is not done when it looks right. It is done when a machine decides it is right, in CI, without a human looking at a screen.

**Fails review.**
- A milestone exit criterion phrased as a visual judgement.
- A rendering change merged without a framebuffer hash or a test ROM result.

**Enforcement.** CI, review.

---

## Part F: Scope

### P17. No abstraction whose only justification is Game Boy Color.

**Rule.** `docs/scope.md` section 4, in full. CGB imposes no requirements on this project. Only the three named accommodations are permitted.

**Fails review.**
- A bank index parameter on VRAM or WRAM access.
- Speed-multiplier plumbing through the clock or peripherals.
- Attribute-map fields in tile-map handling.
- The phrase "so CGB can slot in" in a commit message or pull request description.

**Enforcement.** review.