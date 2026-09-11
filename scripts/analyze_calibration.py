#!/usr/bin/env python3
"""Analyse collected calibration samples and produce the figures ADR 0007 asks for.

This is the analysis half of experiment E1. ADR 0007 (performance floor) names four
things the measurement must determine:

  1. the spread of individual runs within a job;
  2. the spread of per-job medians across jobs, which is the variation the calibrated
     ratio exists to divide out;
  3. the run count N at which the within-job median becomes stable enough to be useful;
  4. a tolerance band derived from the observed spread with a stated safety factor,
     rather than chosen by intuition.

It also enforces a discipline a script is better at than a person: it refuses to report
figures the data cannot support. The tolerance band is withheld unconditionally, because
the band applies to the calibrated ratio and a single-workload experiment measures only
the denominator. Sizing it from the raw across-job spread would derive the band from the
variation the ratio exists to cancel.

Standard library only.

Usage:
    analyze_calibration.py perf-results/
    analyze_calibration.py perf-results/ --min-jobs 8 --safety-factor 3
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys

# ADR 0007 wants samples "deliberately spread across different times of day". Fewer jobs
# than this describes one moment of the runner pool's load, not its variance.
DEFAULT_MIN_JOBS = 8

# Multiplied by the observed across-job spread to propose a tolerance band. Stated here
# rather than buried, because ADR 0007 rule 6 forbids choosing the band by intuition and
# a factor nobody can point at is a factor chosen by intuition.
DEFAULT_SAFETY_FACTOR = 3.0


def relative_spread(values):
    """(max - min) / median. A plain, unsmoothed measure: the question is how bad a
    sample can be, not how good the typical one is."""
    if not values:
        return 0.0
    median = statistics.median(values)
    return 0.0 if median == 0 else (max(values) - min(values)) / median


def load_samples(directory):
    samples = []
    for path in sorted(glob.glob(os.path.join(directory, "calibration-*.json"))):
        with open(path, "r", encoding="utf-8") as handle:
            record = json.load(handle)
        record["_path"] = os.path.basename(path)
        samples.append(record)
    return samples


def median_of_first(values, count):
    return statistics.median(values[:count])


def median_drift(values, count):
    """How far this job's median-of-first-N sits from its own median of every run.

    This is a within-job measure by construction, which is what ADR 0007 item 3 asks
    for: "the run count N at which the within-job median becomes stable enough to be
    useful". Comparing medians across jobs instead would be dominated by which
    processor each job landed on, and no run count can influence that.
    """
    full = statistics.median(values)
    if full == 0:
        return 0.0
    return abs(median_of_first(values, count) - full) / full


def coefficient_of_variation(values):
    """Relative standard deviation. Used only for the residual floor, because errors
    combine in quadrature as standard deviations; the range-based relative_spread
    reported elsewhere does not compose that way."""
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    return 0.0 if mean == 0 else statistics.stdev(values) / mean


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", help="directory of calibration-*.json samples")
    parser.add_argument("--min-jobs", type=int, default=DEFAULT_MIN_JOBS)
    parser.add_argument("--safety-factor", type=float, default=DEFAULT_SAFETY_FACTOR)
    args = parser.parse_args()

    samples = load_samples(args.directory)
    if not samples:
        print(f"no samples found in {args.directory}", file=sys.stderr)
        return 2

    # Workload equivalence first. Timings from jobs that did different work are not
    # comparable, and ADR 0007 Alternative 3 is explicit that the checksum is that
    # check and is not itself a performance measure.
    checksums = {s["measurement"]["checksum"] for s in samples}
    if len(checksums) != 1:
        print("ABORT: samples disagree about the workload checksum.", file=sys.stderr)
        for value in sorted(checksums):
            print(f"  {value}", file=sys.stderr)
        print("The calibration workload changed between samples, so these timings are "
              "not comparable and no baseline may be derived from them.", file=sys.stderr)
        return 1

    local = [s for s in samples if not s["host"]["ci"]["run_id"]]
    ci = [s for s in samples if s["host"]["ci"]["run_id"]]

    print(f"samples            : {len(samples)}  ({len(ci)} from CI, {len(local)} local)")
    print(f"workload checksum  : {checksums.pop()}  (consistent)")
    cpus = sorted({s["host"]["cpu_model"] for s in ci}) or sorted({s["host"]["cpu_model"] for s in samples})
    print(f"distinct CPU models: {len(cpus)}")
    for model in cpus:
        print(f"    {model}")
    print()

    # Only CI samples characterise the runner class. A developer laptop is a different
    # population and mixing it in would understate or overstate the spread.
    population = ci if ci else samples
    if not ci:
        print("NOTE: no CI samples present; analysing local samples only. These do not")
        print("      characterise a runner class and must not be used for the band.\n")

    within = []
    job_medians = []
    for sample in population:
        timings = sample["measurement"]["runs_ns"]
        within.append(relative_spread(timings))
        job_medians.append(statistics.median(timings))

    print("per-job detail")
    print(f"     {'recorded (UTC)':20} {'runs':>4} {'median':>9} {'min':>9} {'max':>9} "
          f"{'spread':>7}  cpu")
    for sample in sorted(population, key=lambda s: s["host"]["recorded_at_utc"]):
        timings = sample["measurement"]["runs_ns"]
        ms = [t / 1e6 for t in timings]
        print(f"     {sample['host']['recorded_at_utc'][:19]:20} {len(ms):4} "
              f"{statistics.median(ms):9.1f} {min(ms):9.1f} {max(ms):9.1f} "
              f"{relative_spread(ms) * 100:6.2f}%  {sample['host']['cpu_model']}")
    print()

    print("per-CPU grouping")
    by_cpu = {}
    for sample in population:
        by_cpu.setdefault(sample["host"]["cpu_model"], []).append(
            statistics.median(sample["measurement"]["runs_ns"]))
    for model in sorted(by_cpu):
        medians = sorted(m / 1e6 for m in by_cpu[model])
        rendered = ", ".join(f"{m:.1f}" for m in medians)
        note = ""
        if len(medians) > 1:
            note = f"  (spread within this model: {relative_spread(medians) * 100:.2f}%)"
        print(f"     {len(medians)} job(s) | {model}")
        print(f"         medians (ms): {rendered}{note}")
    print("     Repeated models differing from themselves indicate the processor does not")
    print("     fully explain the spread, so conditioning a baseline on CPU model would")
    print("     not remove it.")
    print()

    print("1. within-job spread of individual runs")
    print(f"     worst  : {max(within) * 100:.2f}%")
    print(f"     median : {statistics.median(within) * 100:.2f}%")
    print()

    across = relative_spread(job_medians)
    print("2. across-job spread of per-job medians")
    print(f"     spread : {across * 100:.2f}%")
    print(f"     fastest: {min(job_medians) / 1e6:.1f} ms")
    print(f"     slowest: {max(job_medians) / 1e6:.1f} ms")
    print()

    print("3. run count N at which the within-job median stabilises")
    run_counts = {len(s["measurement"]["runs_ns"]) for s in population}
    max_runs = min(run_counts) if run_counts else 0
    if max_runs < 3:
        print("     not determinable: jobs record fewer than 3 runs each")
    else:
        print(f"     Each job's median-of-first-N against that same job's median of all")
        print(f"     {max_runs} runs. Within-job by construction, so N can actually move it.")
        for n in range(1, max_runs + 1):
            drifts = [median_drift(s["measurement"]["runs_ns"], n) for s in population]
            print(f"     N={n}: worst drift {max(drifts) * 100:5.2f}%   "
                  f"median drift {statistics.median(drifts) * 100:5.2f}%")
        print(f"     N={max_runs} is 0.00% by construction (the full median compared with")
        print("     itself) and is not evidence.")
        print("     Descriptive only. No \"stable enough\" criterion has been defined, so")
        print("     this sweep reports observed behaviour and deliberately does not select")
        print("     N. Selecting one requires a stated adjudication rule, which is a")
        print("     decision rather than a measurement.")
    print()

    print("4. proposed tolerance band")
    if len(population) < args.min_jobs:
        print(f"     WITHHELD: {len(population)} job(s) collected, {args.min_jobs} required.")
        print("     ADR 0007 asks for samples spread across different times of day. A band")
        print("     derived from fewer describes one moment of the runner pool's load, and")
        print("     rule 6 forbids choosing it by intuition dressed up as arithmetic.")
    else:
        print("     WITHHELD: not derivable from this experiment, at any job count.")
        print()
        print("     The band applies to the calibrated ratio, and ADR 0007's failure")
        print("     clause is conditioned on the spread \"after calibration\". This")
        print("     experiment runs one workload, so it measures the denominator alone:")
        print("     figure 2 above is the variation the ratio exists to divide out, not")
        print("     what survives it. Multiplying it by a safety factor would size the")
        print("     band from the disease rather than from the residue.")
        print()
        print("     A ratio needs two timings from the same job. Producing the band")
        print("     therefore requires a second workload; the safety factor of")
        print(f"     {args.safety_factor:g} will apply to that residual when it exists.")
    print()

    print("5. conditional measurement-noise floor")
    print("   (NOT an unconditional lower bound on the calibrated ratio's variation)")
    cvs = [coefficient_of_variation(s["measurement"]["runs_ns"]) for s in population]
    epsilon = statistics.median(cvs)
    noise_term = (2 ** 0.5) * epsilon
    print(f"     median within-job relative standard deviation (CV): {epsilon * 100:.3f}%")
    print(f"     sqrt(2) x {epsilon * 100:.3f}% = {noise_term * 100:.3f}%")
    print()
    print("     What this is: the measurement-noise contribution to the spread of")
    print("     T_numerator / T_calibration, under two assumptions:")
    print("       (a) the two timings' measurement noise is INDEPENDENT;")
    print("       (b) both terms carry comparable relative noise.")
    print()
    print("     Why it is NOT an unconditional lower bound. The quotient's variance is")
    print()
    print("         (sigma_R / R)^2  =  eA^2 + eB^2 - 2 * rho * eA * eB")
    print()
    print("     so the correlation term matters. The two workloads would run on one host")
    print("     moments apart, which makes positive correlation likely; common-mode noise")
    print("     then cancels and this term falls below the figure above, toward zero as")
    print("     rho approaches 1. Negative correlation would raise it, to at most 2 x CV.")
    print("     The figure above is therefore the rho = 0 case, not a floor beneath all")
    print("     cases.")
    print()
    print("     Kept separate from it, and not included above: the DIFFERENTIAL-SCALING")
    print("     term, the extent to which two different workloads fail to scale together")
    print("     across processors. It is non-negative, entirely unmeasured, and additive")
    print("     on top of whatever the measurement-noise term turns out to be. Measuring")
    print("     it is the purpose of a two-workload experiment.")
    print()
    print("     Neither term alone predicts the calibrated ratio's behaviour, and this")
    print("     report contains only the first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
