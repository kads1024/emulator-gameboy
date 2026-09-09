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

It also enforces the discipline ADR 0007 implies but a script is better at than a
person: it refuses to propose figures from too little data, and it reports when the
answer is "this runner class cannot support a trustworthy gate", which ADR 0007 records
as an informative failure rather than a problem to work around.

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
        for n in range(1, max_runs + 1):
            medians = [median_of_first(s["measurement"]["runs_ns"], n) for s in population]
            print(f"     N={n}: across-job spread of the median-of-first-N = "
                  f"{relative_spread(medians) * 100:.2f}%")
        print("     Choose the smallest N past which the spread stops improving; more")
        print("     runs after that buy job time rather than stability.")
    print()

    print("4. proposed tolerance band")
    if len(population) < args.min_jobs:
        print(f"     WITHHELD: {len(population)} job(s) collected, {args.min_jobs} required.")
        print("     ADR 0007 asks for samples spread across different times of day. A band")
        print("     derived from fewer describes one moment of the runner pool's load, and")
        print("     rule 6 forbids choosing it by intuition dressed up as arithmetic.")
        return 0

    band = across * args.safety_factor
    print(f"     across-job spread {across * 100:.2f}% x safety factor "
          f"{args.safety_factor:g} = {band * 100:.2f}%")
    print()
    if band >= 0.20:
        print("     VERDICT: this runner class cannot support a trustworthy gate.")
        print("     A band this wide only catches regressions larger than it, which is")
        print("     larger than a regression worth catching. ADR 0007 records this as an")
        print("     informative failure: revisit the method, reconsider the dedicated")
        print("     machine against rule 9, and consider host-instruction counting as a")
        print("     supplementary signal rather than a replacement for measuring time.")
    else:
        print("     VERDICT: usable. This band is the figure ADR 0007's Status section")
        print("     leaves PROVISIONAL, together with the reference class and N above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
