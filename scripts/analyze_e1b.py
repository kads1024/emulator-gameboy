#!/usr/bin/env python3
"""Analyse E1b job records: does the calibrated ratio separate a target-side regression?

Every derived quantity is RECOMPUTED here from the raw invocation records and
cross-checked against the values the driver stored. The raw records are the source of
truth; a disagreement is reported as an error rather than silently preferred.

WHAT THIS REPORTS

  per variant, never pooling b_near with b_far:
    - R_null and R_reg distributions across jobs (mean, cv, relative spread)
    - Q_j = R_reg,j / R_null,j            paired effect, median with a distribution-free
                                         interval from the order statistics
    - probability of superiority          across-job separation, defined exactly below
    - separation at the pre-registered experimental boundary
  plus:
    - D (same-workload reference and within-round drift diagnostic)
    - S (realised injection scaling) with a position breakdown
    - paired vs aggregate ratio comparison

WHAT THIS IS NOT

  It does not set, propose, or imply a production gate threshold. The pre-registered
  2.5% boundary below is an EXPERIMENTAL effect-separation criterion, fixed before
  collection so it cannot be tuned afterwards. The eventual ADR 0007 gate policy is a
  separate, post-E1b decision that additionally requires an accepted false-positive
  tolerance, the uncertainty of an estimated baseline, and re-validation against the
  real emulator.

Standard library only.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import statistics
import sys

# Midpoint between no regression and the 5% design input. Pre-registered, experimental.
EXPERIMENTAL_BOUNDARY = 0.025

# Initial sample size from the approved design. NOT a stopping rule: results below it
# are reported in full and labelled interim. The interim look is descriptive by design,
# because a rigorous futility boundary cannot be justified before the data exist.
TARGET_JOBS = 16

# Smallest job count at which the order-statistic interval for Q has any non-trivial
# coverage. Below this, median_ci returns None.
MIN_JOBS_FOR_Q_INTERVAL = 6

# Nominal injected effect: 1.05x ITERATION COUNT. The realised runtime effect is S.
NOMINAL_INJECTION = 1.05

FAMILIES = ("near", "far")
VARIANTS = ("near_null", "near_reg", "far_null", "far_reg")


def relative_spread(values):
    if not values:
        return 0.0
    median = statistics.median(values)
    return 0.0 if median == 0 else (max(values) - min(values)) / median


def cv(values):
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    return 0.0 if mean == 0 else statistics.stdev(values) / mean


def recompute(job):
    """Rebuild every derived quantity from raw invocations alone."""
    timed = [i for i in job["invocations"] if not i["warmup"]]
    by_round = {}
    for entry in timed:
        by_round.setdefault(entry["round"], {})[entry["variant"]] = entry["timing_ns"]

    rounds = []
    for round_index in sorted(by_round):
        slots = by_round[round_index]
        a_mid = (slots["A1"] + slots["A2"]) / 2.0
        rounds.append({
            "round": round_index,
            "A_mid_ns": a_mid,
            "D": slots["A2"] / slots["A1"],
            "R": {v: slots[v] / a_mid for v in VARIANTS},
            "S": {f: slots[f"{f}_reg"] / slots[f"{f}_null"] for f in FAMILIES},
        })

    return {
        "rounds": rounds,
        "D_j": statistics.median([r["D"] for r in rounds]),
        "R_paired": {v: statistics.median([r["R"][v] for r in rounds]) for v in VARIANTS},
        "R_aggregate": {
            v: statistics.median([by_round[r["round"]][v] for r in rounds])
            / statistics.median([r["A_mid_ns"] for r in rounds])
            for v in VARIANTS
        },
        "S": {f: statistics.median([r["S"][f] for r in rounds]) for f in FAMILIES},
    }


def median_ci(values, confidence=0.95):
    """Distribution-free interval for the median from the order statistics.

    Coverage comes from the binomial: the interval spanned by the k-th smallest and
    k-th largest values covers the median with probability 1 - 2*P(X < k), X ~ Bin(n, 1/2).
    Returns (low, high, achieved_coverage) or None when n is too small for any
    non-trivial interval.
    """
    n = len(values)
    if n < 6:
        return None
    ordered = sorted(values)
    alpha = 1.0 - confidence
    best = None
    for k in range(1, n // 2 + 1):
        tail = sum(math.comb(n, i) for i in range(0, k)) / (2.0 ** n)
        coverage = 1.0 - 2.0 * tail
        if coverage >= confidence - 1e-12:
            best = (ordered[k - 1], ordered[n - k], coverage)
        else:
            break
    if best is None:
        return None
    return best


def probability_of_superiority(reg_values, null_values, exclude_same_job=False):
    """Fraction of ordered (reg, null) job pairs in which the reg value is larger.

    EXACT DEFINITION. Every reg job is compared against every null job: all
    len(reg) * len(null) ordered pairs are formed, including the pair drawn from the
    same job unless exclude_same_job is set. Each pair contributes 1.0 when the reg
    value exceeds the null value, 0.0 when it is smaller, and 0.5 on an exact tie. The
    statistic is the mean contribution, so 0.5 means no separation and 1.0 means every
    reg job reads higher than every null job.

    Values are assumed index-aligned by job, which is how the caller builds them.
    """
    total = 0.0
    count = 0
    for i, reg in enumerate(reg_values):
        for j, null in enumerate(null_values):
            if exclude_same_job and i == j:
                continue
            count += 1
            if reg > null:
                total += 1.0
            elif reg == null:
                total += 0.5
    return total / count if count else float("nan")


def load_jobs(directory):
    jobs = []
    for path in sorted(glob.glob(os.path.join(directory, "e1b-*.json"))):
        with open(path, "r", encoding="utf-8") as handle:
            job = json.load(handle)
        job["_path"] = os.path.basename(path)
        jobs.append(job)
    return jobs


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", help="directory of e1b-*.json job records")
    args = parser.parse_args()

    jobs = load_jobs(args.directory)
    if not jobs:
        print(f"no E1b job records found in {args.directory}", file=sys.stderr)
        return 2

    versions = {j["protocol_version"] for j in jobs}
    if len(versions) != 1:
        print(f"ABORT: job records span protocol versions {sorted(versions)}.", file=sys.stderr)
        print("Records from different protocols are not comparable.", file=sys.stderr)
        return 1

    # Workload equivalence, per variant. Null and reg deliberately differ, so the check
    # is applied within each variant rather than across all invocations.
    for variant in VARIANTS + ("A1", "A2", "A"):
        seen = {i["checksum"] for j in jobs for i in j["invocations"] if i["variant"] == variant}
        if len(seen) > 1:
            print(f"ABORT: variant {variant} has inconsistent checksums {sorted(seen)}.",
                  file=sys.stderr)
            return 1

    # Recompute from raw and cross-check the stored values.
    mismatches = []
    for job in jobs:
        fresh = recompute(job)
        job["_recomputed"] = fresh
        stored = job.get("derived", {})
        for key in ("D_j",):
            if key in stored and abs(stored[key] - fresh[key]) > 1e-9:
                mismatches.append(f"{job['_path']}:{key}")
        for group in ("R_paired", "R_aggregate", "S"):
            for name, value in fresh[group].items():
                if group in stored and name in stored[group]:
                    if abs(stored[group][name] - value) > 1e-9:
                        mismatches.append(f"{job['_path']}:{group}.{name}")
    if mismatches:
        print("ABORT: stored derived values disagree with recomputation from raw records:",
              file=sys.stderr)
        for item in mismatches[:10]:
            print(f"  {item}", file=sys.stderr)
        return 1

    ci_jobs = [j for j in jobs if j["host"]["ci"]["run_id"]]
    local_jobs = [j for j in jobs if not j["host"]["ci"]["run_id"]]
    population = ci_jobs if ci_jobs else jobs

    print(f"jobs               : {len(jobs)}  ({len(ci_jobs)} from CI, {len(local_jobs)} local)")
    n_population = len(ci_jobs) if ci_jobs else len(jobs)
    if n_population < TARGET_JOBS:
        print(f"STATUS             : INTERIM / DESCRIPTIVE")
        print(f"     {n_population} of the {TARGET_JOBS}-job initial target collected.")
        print("     Everything below is reported in full, but it is an interim read, not a")
        print("     result. There is no stopping rule here: the interim look is descriptive")
        print("     by design, because a rigorous futility boundary cannot be justified")
        print("     before the data exist.")
        if n_population < MIN_JOBS_FOR_Q_INTERVAL:
            print(f"     The distribution-free interval for Q is NOT available at "
                  f"n={n_population};")
            print(f"     it needs at least {MIN_JOBS_FOR_Q_INTERVAL} jobs for any non-trivial "
                  "coverage.")
        else:
            print(f"     The distribution-free interval for Q is available at "
                  f"n={n_population}, with")
            print("     the coverage reported alongside it below.")
    else:
        print(f"STATUS             : {n_population} jobs, at or above the "
              f"{TARGET_JOBS}-job initial target")
    print(f"protocol_version   : {versions.pop()}")
    print("derived values     : recomputed from raw invocations and cross-checked, agree")
    if not ci_jobs:
        print("NOTE: no CI jobs present; local records do not characterise a runner class.")
    models = sorted({j["host"]["cpu_model"] for j in population})
    print(f"distinct CPU models: {len(models)}")
    for model in models:
        print(f"    {model}")
    print()

    r = {v: [j["_recomputed"]["R_paired"][v] for j in population] for v in VARIANTS}
    r_agg = {v: [j["_recomputed"]["R_aggregate"][v] for j in population] for v in VARIANTS}
    d = [j["_recomputed"]["D_j"] for j in population]
    s = {f: [j["_recomputed"]["S"][f] for j in population] for f in FAMILIES}

    print("D: same-workload reference and within-round drift")
    print(f"     median {statistics.median(d):.5f}   cv {cv(d) * 100:.3f}%   "
          f"spread {relative_spread(d) * 100:.3f}%")
    print("     A same-workload reference under this protocol's bracket separation. It is")
    print("     context for interpreting magnitudes, NOT a decomposition: the residual of")
    print("     R minus this is not a measurement of differential scaling.")
    print()

    print("S: realised injection scaling (nominal injected work = 1.05x iteration count)")
    for family in FAMILIES:
        values = s[family]
        print(f"     {family:5}: median {statistics.median(values):.5f}   "
              f"min {min(values):.5f}   max {max(values):.5f}   cv {cv(values) * 100:.3f}%")
    print("     S is a PAIRED diagnostic, not a pure regression multiplier: within a round")
    print("     the null and reg variants sit in different positions, so residual position")
    print("     effects can contribute. Counterbalancing makes that testable, not absent.")
    print("     If the realised scaling departs materially from 1.05, E1b demonstrates")
    print("     sensitivity to the MEASURED effect, not to a 5% runtime regression.")
    print()

    print("S by B position (post-hoc position diagnostic)")
    for family in FAMILIES:
        by_position = {}
        for job in population:
            positions = {}
            for entry in job["invocations"]:
                if entry["warmup"] or entry["b_position"] is None:
                    continue
                positions.setdefault((entry["round"], entry["variant"]), entry["b_position"])
            for round_entry in job["_recomputed"]["rounds"]:
                rnd = round_entry["round"]
                key = positions.get((rnd, f"{family}_reg"))
                if key is not None:
                    by_position.setdefault(key, []).append(round_entry["S"][family])
        rendered = "  ".join(
            f"pos{p}: {statistics.median(v):.4f} (n={len(v)})" for p, v in sorted(by_position.items()))
        print(f"     {family:5}: {rendered}")
    print("     A position gradient here would indicate S is partly a position artefact.")
    print()

    for family in FAMILIES:
        null_key, reg_key = f"{family}_null", f"{family}_reg"
        print(f"=== B_{family} ===")
        for key in (null_key, reg_key):
            print(f"  R[{key:9}] mean {statistics.fmean(r[key]):.5f}   "
                  f"cv {cv(r[key]) * 100:.3f}%   spread {relative_spread(r[key]) * 100:.3f}%")
        print(f"  aggregate cv for comparison: null {cv(r_agg[null_key]) * 100:.3f}%   "
              f"reg {cv(r_agg[reg_key]) * 100:.3f}%")
        print("     Paired markedly tighter than aggregate would indicate temporal")
        print("     correlation is doing the cancelling.")
        print()

        q = [reg / null for reg, null in zip(r[reg_key], r[null_key])]
        print(f"  Q = R_reg / R_null   (paired effect, primary)")
        print(f"     median {statistics.median(q):.5f}   min {min(q):.5f}   max {max(q):.5f}")
        interval = median_ci(q)
        if interval is None:
            print(f"     distribution-free interval: not available at n={len(q)}")
        else:
            low, high, coverage = interval
            print(f"     distribution-free interval [{low:.5f}, {high:.5f}] "
                  f"(order statistics, coverage {coverage * 100:.1f}%)")
        print()

        ps_all = probability_of_superiority(r[reg_key], r[null_key])
        ps_excl = probability_of_superiority(r[reg_key], r[null_key], exclude_same_job=True)
        print("  probability of superiority (across-job separation)")
        print(f"     all pairs                 : {ps_all:.4f}   "
              f"({len(r[reg_key])} x {len(r[null_key])} ordered pairs, ties count 0.5)")
        print(f"     excluding same-job pairs  : {ps_excl:.4f}")
        print("     0.5 means no separation; 1.0 means every reg job reads above every")
        print("     null job. The excluding variant is closer to the gate's situation,")
        print("     where a job is compared against a baseline built from other jobs.")
        print()

        boundary = statistics.fmean(r[null_key]) * (1.0 + EXPERIMENTAL_BOUNDARY)
        null_above = sum(1 for v in r[null_key] if v >= boundary)
        reg_below = sum(1 for v in r[reg_key] if v < boundary)
        print(f"  at the pre-registered EXPERIMENTAL boundary "
              f"(mean_null x {1 + EXPERIMENTAL_BOUNDARY})")
        print(f"     boundary {boundary:.5f}")
        print(f"     null jobs at or above it : {null_above} / {len(r[null_key])}")
        print(f"     reg jobs below it        : {reg_below} / {len(r[reg_key])}")
        print("     Experimental criterion only. This is NOT a production gate threshold,")
        print("     and these counts are not production error rates: they treat the")
        print("     baseline mean as known when it is estimated, assume nothing about the")
        print("     distribution's shape, and rest on the realised effect size S above.")
        print()

    print("NOT PRODUCED BY THIS ANALYSIS")
    print("  - a production gate threshold, which remains a post-E1b decision;")
    print("  - a decomposition of residual variation into measurement noise versus")
    print("    differential scaling;")
    print("  - any claim about the real emulator, which does not exist yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
