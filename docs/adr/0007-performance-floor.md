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
- **Calibrated ratio** - the wall time the emulator takes to run the workload, divided by the wall time a fixed calibration workload takes in the same job on the same host. Both terms are times, so the ratio is dimensionless and a host that is uniformly slower cancels out of it. It answers "did this change make the emulator slower," which the absolute figure cannot answer on a shared runner. The calibration workload is committed to the repository.
**5. The regression gate is the calibrated ratio, compared against a baseline committed to the repository.** The absolute figure is the floor tripwire and is expected to sit far above 300%.
**6. Each measurement is repeated and aggregated by median**, with the run count and tolerance band set from the data named in the Status section, not chosen by intuition.
**7. The baseline is a reviewed file.** Changing it is a commit with a stated reason. Editing the baseline to turn a red build green, without that reason, is the specific failure this rule exists to prevent.
**8. When the gate fires, the response is to find the change that caused it.** Raising the baseline is the response only after the cause is identified and the cost accepted deliberately.
**9. The reference is a runner class plus a calibration workload, never a physical machine.** A tripwire that only one computer in the world can reproduce is not a tripwire.
**10. The measurement runs in CI on every change that touches the core**, so that the change which moved the number is the change being reviewed.

## Alternatives considered

### Alternative 1: Raw wall-clock threshold on a shared runner
This is the simplest automated design. The workload is fixed and deterministic, and the CI job fails only when absolute throughput falls below a deliberately wide threshold. The large margin means ordinary runner noise should not normally cross the boundary.

It does not eliminate run-to-run noise. A busy or slower runner can still produce a lower result, and a sufficiently unlucky run can still produce a false failure. The wide threshold merely makes that failure less likely. The resulting failure mode is therefore still present: if the gate fires often enough for developers to learn that re-running it usually makes the problem disappear, the gate becomes something to retry rather than trust.

Its advantage is proportionality. If the emulator normally operates far above the required 300% floor, this catches the catastrophic regressions the floor was originally intended to detect with very little machinery.

### Alternative 2: Dedicated physical reference machine
A dedicated machine removes the principal source of variation from other tenants and from changing hosts. Repeated measurements on that machine would therefore have substantially less run-to-run noise than measurements on a shared runner, and the gate would be less likely to fail because of unrelated CI load.

It does not satisfy Rule 9. The reference would be a particular physical machine rather than a runner class plus a calibration workload. That makes the baseline inseparable from the machine's exact hardware. When the machine is replaced or its CPU is upgraded, the existing baseline no longer represents the same reference. The project would then have to establish a new baseline, making historical comparisons discontinuous and creating another opportunity for a baseline change to conceal a regression.

The dedicated machine therefore eliminates more noise than Alternative 1, but at the cost of making the reference less portable and the baseline more fragile.

### Alternative 3: Deterministic counting instead of timing
Instead of measuring elapsed time, the project could count something deterministic. Two distinct proposals hide under that description, and they fail for entirely different reasons.

**Emulated cycles executed.** For a fixed workload this quantity is constant by construction. Determinism guarantees it: the same ROM driven by the same inputs retires the same number of emulated M-cycles no matter how fast or slow the host implementation happens to be. A change that halves the emulator's speed leaves the count bit-identical. It therefore reports nothing about performance at all. What it does report is workload equivalence, confirming that the benchmark ran the same program it ran last time. That is a genuinely useful thing to record alongside a timing measurement, and it is the only thing this count is good for.

**Host instructions retired.** This is the real competitor. It varies with the host implementation, so unlike the emulated cycle count it can in principle observe a regression. It is also very nearly noise-free: it is largely indifferent to other tenants, host frequency scaling, and CI load, so it eliminates the run-to-run variance that causes the trust failure in the first place rather than tolerating it behind a wide threshold. Two failure modes rule it out.

What it misses entirely is any change that leaves the instruction count unchanged but wrecks locality. Growing a hot structure so it no longer fits in cache, or scattering the data the hot path walks across separate allocations, executes exactly the same instructions in exactly the same order while stalling on memory. The emulator is materially slower and the counter reports no change whatsoever.

What it wrongly flags is the mirror case: a change that increases the instruction count while improving wall-clock time. Replacing an unpredictable branch with a short branchless computation executes more instructions and removes the mispredict penalty. Trading a lookup for arithmetic does the same. The program gets faster, the count goes up, and the gate fails a beneficial change.

Taken together those two cases give the honest verdict. Instruction counting measures work, and work is not time. The two correlate well in the ordinary case and diverge exactly where the interesting regressions and the interesting optimisations live.

### Alternative 4: No automated gate
The argument for this approach is legitimate: a tripwire that never fires is pure maintenance cost. For a solo project, manually benchmarking at milestones can appear sufficient, particularly when the emulator is expected to have substantial performance headroom.

The mechanical failure is attribution latency. A regression introduced today may not be measured until the next milestone, weeks or months later, after many unrelated changes have been made. At that point the benchmark can establish that performance has fallen but cannot reliably identify which change caused it. The cost of finding the regression therefore grows with the delay between introduction and detection.

An automated gate instead attaches the measurement to the change that introduced it. The purpose is not to eliminate benchmarking outside CI, but to make regression detection occur close enough to the responsible change that attribution remains practical.

### Why the chosen design costs more
A reasonable engineer building a solo emulator could choose Alternative 1: it is cheap, simple, and a wide raw threshold is sufficient if the only goal is catching catastrophic slowdowns. The chosen design costs more. It requires a calibration workload, two reported measurements, a reviewed baseline, and enough repeated runs to establish a meaningful tolerance band. That cost is accepted because the project is deliberately making performance a trusted architectural tripwire rather than merely an occasional benchmark.

### Residual limits of the chosen design
The calibrated ratio cannot distinguish every cause of a performance change, and four classes of regression can pass it.

It cannot reliably separate all forms of host-specific behaviour that affect the emulator and the calibration workload differently. It cannot detect a regression confined to a subsystem the benchmark does not exercise. It cannot detect a workload-specific performance cliff, or a change whose cost appears only under a different ROM or input pattern.

The fourth is the most likely to occur in practice: ratchet drift. Each individual change can land just inside the tolerance band and pass, and if the baseline is re-committed as each change is accepted, the band moves along with it. Ten such changes can sum to a large regression without any single run ever failing the gate. The gate is working exactly as specified on every one of those runs, and the emulator ends up substantially slower.

The countermeasure is a policy that Rule 7 implies but does not state. The baseline is a long-lived reference, not a rolling one. It is not re-committed after every accepted change; updating it is a deliberate, reviewed decision. The history of previous baselines is retained, so a slow slide across many changes remains visible even though no individual step tripped the gate.

The gate establishes evidence about this fixed workload on the reference runner class. It does not establish that every workload or every host will perform identically.

## Consequences

### The gate is inert until several things exist, and must say so
This measurement requires CI, a release build, a headless runner, and the workload ROM. Until all four exist there is nothing to measure. A performance job that reports success while measuring nothing is a lie told by the build system, so until the gate is real it reports explicitly that it is not yet measurable, never a pass.

### The baseline is long-lived, not rolling
Per the ratchet-drift limit recorded in the alternatives, the baseline is not re-committed after every accepted change. It is a fixed reference that changes deliberately, with a stated reason, and previous baselines are retained so that a slow slide across many changes is visible even though no single change tripped the band.

### The calibration workload is frozen
Because the ratio is meaningful only against a stable denominator, any change to the calibration workload invalidates every historical baseline. It is committed, versioned, and treated as immutable; changing it is a re-baselining event with the same review requirement as changing the baseline itself.

### The job's output must be readable by a human
Two numbers, a floor, and a tolerance band are enough to be uninterpretable at a glance. The job reports both figures, the floor, the band, and the baseline it compared against, so that a failure can be understood without reading the workflow definition.

### This ADR depends on the ROM acquisition decision
The workload ROM is fetched rather than committed. The performance job therefore depends on that mechanism, and a failure to obtain the ROM fails the job loudly rather than skipping it, a silently skipped performance job is the inert-gate failure in a different costume.

### The floor does not license rejecting designs on theory
The constraints the floor imposes are the ones ADR 0002 and ADR 0004 already state: no allocation, no I/O, and no virtual dispatch on the hot path. Beyond those, an abstraction is not rejected because it might be slow. It is measured, and the measurement is brought to the review. The floor is evidence for arguments, not a substitute for them.

### Determinism is a prerequisite, not merely a principle
The workload is fixed only because the core is deterministic. If determinism were ever lost, run-to-run variation would stop being host noise and this measurement would lose its meaning. Principle P11 is therefore load-bearing for this ADR, and a change that compromises determinism breaks the performance gate as a side effect.

## Status

### Classification
- **Purpose, workload definition, and measurement method:** BLOCKING ARCHITECTURAL DECISION: accepted.
- **Reference class, run count, and tolerance band:** PROVISIONAL: resolved by the measurement defined below.

### The measurement that resolves the provisional part
Run a fixed, CPU-bound, single-threaded workload (not the emulator, which does not yet exist) on the candidate runner class. For each job, execute it N times and record every timing. Repeat across at least M separate jobs, deliberately spread across different times of day. Record the CPU model each job reports.

From the data, determine:
1. The spread of individual runs within a job.
2. The spread of per-job medians across jobs, which is the variation the calibration ratio exists to divide out.
3. The run count N at which the within-job median becomes stable enough to be useful.
4. The tolerance band, derived from the observed spread with a stated safety factor, rather than chosen by intuition.

**The experiment fails informatively.** If the spread across jobs remains large after calibration, the conclusion is that this runner class cannot support a trustworthy gate, and the method is revisited, with the dedicated machine reconsidered against rule 9, and host-instruction counting reconsidered as a *supplementary* regression signal rather than as a replacement for measuring time.

Emulated-cycle counting is recorded alongside whichever method is used, as the workload-equivalence check Alternative 3 describes: it confirms the benchmark ran the same program, and it is not a performance measure. The two counts are not interchangeable and the distinction is the substance of Alternative 3.

### What would reopen the method
Evidence that the smallest regression this gate can reliably detect is large enough to be useless, that is, that the tolerance band demanded by observed variance exceeds the size of a regression worth catching.

### Review triggers
- When CI exists: run the measurement above and fill in the provisional figures.
- When the first headless release build exists: take the first real measurement and commit the initial baseline.
- When the workload ROM is selected: record it here by name and checksum.