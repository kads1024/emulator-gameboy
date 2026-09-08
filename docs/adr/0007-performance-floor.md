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
**10. The measurement runs in CI on every change that touches the core**, so that the change which moved the number is the change being reviewed.## Alternatives considered

### Alternative 1: Raw wall-clock threshold on a shared runner
This is the simplest automated design. The workload is fixed and deterministic, and the CI job fails only when absolute throughput falls below a deliberately wide threshold. The large margin means ordinary runner noise should not normally cross the boundary.

It does not eliminate run-to-run noise. A busy or slower runner can still produce a lower result, and a sufficiently unlucky run can still produce a false failure. The wide threshold merely makes that failure less likely. The resulting failure mode is therefore still present: if the gate fires often enough for developers to learn that re-running it usually makes the problem disappear, the gate becomes something to retry rather than trust.

Its advantage is proportionality. If the emulator normally operates far above the required 300% floor, this catches the catastrophic regressions the floor was originally intended to detect with very little machinery.

### Alternative 2: Dedicated physical reference machine
A dedicated machine removes the principal source of variation from other tenants and from changing hosts. Repeated measurements on that machine would therefore have substantially less run-to-run noise than measurements on a shared runner, and the gate would be less likely to fail because of unrelated CI load.

It does not satisfy Rule 9. The reference would be a particular physical machine rather than a runner class plus a calibration workload. That makes the baseline inseparable from the machine's exact hardware. When the machine is replaced or its CPU is upgraded, the existing baseline no longer represents the same reference. The project would then have to establish a new baseline, making historical comparisons discontinuous and creating another opportunity for a baseline change to conceal a regression.

The dedicated machine therefore eliminates more noise than Alternative 1, but at the cost of making the reference less portable and the baseline more fragile.

### Alternative 3: Deterministic host-work proxy
Instead of measuring elapsed time, the project could count a deterministic quantity such as instructions retired or simulated M-cycles. Because the workload is deterministic, the count would be effectively identical across hosts and repeated runs. This eliminates the run-to-run noise that causes the trust failure in the first place rather than merely tolerating it with a wide threshold.

The problem is that host-work is not the same thing as performance. A regression in the host implementation can make the emulator substantially slower without changing the number of emulated instructions. For example, replacing an efficient memory-access implementation with an expensive one could leave the emulated instruction count unchanged while increasing the actual execution time significantly. The proxy would miss that regression entirely.

It can also flag a beneficial change. An optimisation that legitimately reduces the amount of host work performed per emulated instruction may change the relationship between the proxy and actual runtime without changing the emulated workload. Depending on the chosen proxy, a refactoring that changes the number of host instructions required to perform the same emulated work could therefore look like a regression even when wall-clock performance improves.

The proxy is consequently excellent at measuring workload equivalence but cannot serve as a substitute for measuring actual performance.

### Alternative 4: No automated gate
The argument for this approach is legitimate: a tripwire that never fires is pure maintenance cost. For a solo project, manually benchmarking at milestones can appear sufficient, particularly when the emulator is expected to have substantial performance headroom.

The mechanical failure is attribution latency. A regression introduced today may not be measured until the next milestone, weeks or months later, after many unrelated changes have been made. At that point the benchmark can establish that performance has fallen but cannot reliably identify which change caused it. The cost of finding the regression therefore grows with the delay between introduction and detection.

An automated gate instead attaches the measurement to the change that introduced it. The purpose is not to eliminate benchmarking outside CI, but to make regression detection occur close enough to the responsible change that attribution remains practical.

A reasonable engineer building a solo emulator could therefore choose Alternative 1: it is cheap, simple, and a wide raw threshold is sufficient if the only goal is catching catastrophic slowdowns. The chosen design costs more: it requires a calibration workload, two reported measurements, a reviewed baseline, and enough repeated runs to establish a meaningful tolerance band. That cost is accepted because the project is deliberately making performance a trusted architectural tripwire rather than merely an occasional benchmark.

The calibrated ratio still cannot distinguish every cause of a performance change. It cannot reliably separate all forms of host-specific behaviour that affect both the emulator and calibration workload differently, and it cannot detect regressions that do not materially affect the measured workload. A regression confined to an unexercised subsystem, a workload-specific performance cliff, or a change whose cost appears only with a different ROM or input pattern can therefore pass this gate. The gate establishes evidence about this fixed workload on the reference runner class; it does not establish that every workload or every host will perform identically.
