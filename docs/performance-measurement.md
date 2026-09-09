# Performance measurement

How the performance gate in ADR 0007 (performance floor) is being built, and what is
deliberately not built yet.

## Current state: no gate exists

ADR 0007's consequence is explicit — a job that reports a pass while measuring nothing is
a lie told by the build system. There is therefore **no performance job in `ci.yml`**, and
there will not be one until there is an emulator, a headless runner, and the workload ROM
rule 3 requires.

What exists now is the *denominator* and the *experiment*.

## The calibration workload

`tools/calibration/` is the denominator of rule 4's calibrated ratio: the emulator's
measured time divided by this workload's measured time, in the same job on the same host,
so that a uniformly slower host cancels out.

Properties that matter, and why:

- **Deterministic.** The same iteration count always produces the same checksum. A
  changed checksum means the workload changed, not that the host was slow. This is the
  workload-equivalence check ADR 0007 Alternative 3 describes, and it is not a
  performance measure. The checksum is identical under clang and GCC.
- **Not linked against the core.** A denominator that executed the emulator's code would
  move when the emulator moved, which is the one thing it must not do.
- **Not elidable.** The result is consumed, and the timing was verified to scale linearly
  with the iteration count: halving the iterations halves the runtime, so nothing was
  optimised away.
- **Roughly half a second per run** on the development machine, which is long enough that
  scheduler noise does not dominate and short enough that seven runs cost a few seconds.

**It is frozen once a baseline is recorded against it.** Changing it invalidates every
historical baseline, so it is a re-baselining event with the same review requirement as
changing the baseline itself. The file says so at the top, where someone about to edit it
will read it.

The ratio is only meaningful **within one toolchain and preset**. The same workload takes
about 500 ms under clang on Windows and about 1.15 s under GCC in WSL on the same machine.
Comparing a ratio measured on one runner class against another is meaningless, which is
what rule 9 already says in different words.

## Experiment E1

E1 measures the runner class, not this project's code. `.github/workflows/perf-calibration.yml`
runs every three hours on `ubuntu-24.04`, takes seven timed runs, recovers every previous
sample, re-analyses the whole set, and writes the report to the job summary. The experiment
reports its own progress; nothing has to be collected by hand.

`scripts/analyze_calibration.py` produces the four figures ADR 0007's Status section asks
for: within-job spread, across-job spread of per-job medians, the run count `N` at which
the median stabilises, and a tolerance band derived from observed spread with a stated
safety factor.

Two disciplines are built into the analyser rather than left to good intentions:

- It **withholds the tolerance band** until at least eight CI jobs exist, because a band
  derived from fewer describes one moment of the runner pool's load. Rule 6 forbids
  choosing the band by intuition, and intuition dressed up as arithmetic is still
  intuition.
- It **reports an unusable verdict** when the band would exceed 20%, because a gate that
  only catches regressions larger than that catches nothing worth catching. ADR 0007
  records this outcome as an informative failure, not a problem to work around.

Local samples are kept separate from CI samples in the analysis. A developer machine is a
different population and mixing it in would misdescribe the runner class.

## Running it by hand

```
cmake --build --preset linux-gcc-release --target gb_calibration
python scripts/run_calibration.py \
    --binary build/linux-gcc-release/tools/calibration/gb_calibration \
    --runs 7 --out perf-results
python scripts/analyze_calibration.py perf-results
```

`perf-results/` is gitignored. The samples are CI artefacts; what gets committed is the
conclusion, recorded in ADR 0007 when the data supports it.

## What happens next

When enough samples exist, ADR 0007's PROVISIONAL figures — reference class, run count,
tolerance band — are filled in, or the experiment concludes that this runner class cannot
support the gate and the method is revisited. Neither outcome is written into the ADR
before the data supports it.
