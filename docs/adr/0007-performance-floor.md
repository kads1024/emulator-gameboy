# ADR 0007: Performance floor

## Status summary

- **The floor's purpose, workload definition, and measurement method:** BLOCKING ARCHITECTURAL DECISION: accepted.
- **The reference class, run count, and tolerance band:** PROVISIONAL: pending the measurement defined in the Status section.

## Context
### The problem
The project requires the core to sustain at least 300% of real time (roughly 180 frames per second) in a headless release build using the scanline renderer.

A performance requirement with no reproducible measurement is a slogan. Worse, a requirement measured badly is actively harmful: a gate that fires spuriously teaches everyone to re-run the job until it passes, and once that habit exists the gate detects nothing while appearing to.

This ADR decides what is measured, how, and what happens when the measurement moves.

### What the floor is for
It is a **tripwire**, not a target. Its purpose is to detect regressions, a change that makes the emulator several times slower, which usually means an accident rather than a design choice. It is never optimised against, and there is no work item to make the number larger. Being far above the floor is the expected state.

### The facts that make this measurable at all
1. **The core is deterministic.** Same ROM, same initial state, same input, same number of frames means the same instructions executed and the same work performed. Any variation between runs is host noise, not workload variation. Most software cannot say this about its benchmarks.
2. **The core is headless and has no I/O.** There is no display, no audio device, no frame pacing and no filesystem in the measured path, so the measurement contains no waiting.
3. **The hot path is known in advance.** ADR 0002 places the advance mechanism and the bus access on the most-executed path in the program, and ADR 0004 puts a permission query alongside them. A regression will almost always be there.

### The constraint that shapes the method
Shared CI runners vary substantially between runs and between physical hosts, for reasons having nothing to do with the code: different CPU models behind one label, other tenants on the machine, and thermal behaviour. A raw wall-clock threshold measured on such a runner conflates "the emulator got slower" with "the runner was busier," which is the failure mode described above.

### Out of scope
Optimisation policy, the choice of profiling tools, per-subsystem performance budgets, and frontend performance. This ADR measures the core.

## Decision
**1. The floor is a tripwire and is never optimised against.** No work is undertaken to increase the measured figure. Work is undertaken only when the figure falls.
**2. The measured quantity is emulated machine time per unit of wall time**, produced by a headless release build with the scanline renderer, no frontend, no audio output, and no frame pacing.
**3. The workload is fixed, named, and version-controlled.** It is defined by: one specific ROM, a fixed initial machine state, a fixed frame count, and no input. The ROM must be deterministic, require no input, exercise the CPU, PPU, and timer together, and be freely redistributable or fetchable by checksum, a commercial ROM is excluded by `docs/scope.md`. The specific ROM is selected when the test ROM acquisition mechanism is settled.
**4. Two figures are reported, and they have different jobs.**
- **Absolute throughput** - the human-meaningful number that the 300% floor is stated against. It is compared against the floor with a wide margin, and it answers "is this emulator fast enough to be worth using."
- **Calibrated ratio** - the same measurement divided by the time taken, in the same job on the same host, by a fixed calibration workload committed to the repository. It answers "did this change make the emulator slower," with most host-to-host variation divided out.
**5. The regression gate is the calibrated ratio, compared against a baseline committed to the repository.** The absolute figure is the floor tripwire and is expected to sit far above 300%.
**6. Each measurement is repeated and aggregated by median**, with the run count and tolerance band set from the data named in the Status section, not chosen by intuition.
**7. The baseline is a reviewed file.** Changing it is a commit with a stated reason. Editing the baseline to turn a red build green, without that reason, is the specific failure this rule exists to prevent.
**8. When the gate fires, the response is to find the change that caused it.** Raising the baseline is the response only after the cause is identified and the cost accepted deliberately.
**9. The reference is a runner class plus a calibration workload, never a physical machine.** A tripwire that only one computer in the world can reproduce is not a tripwire.
**10. The measurement runs in CI on every change that touches the core**, so that the change which moved the number is the change being reviewed.