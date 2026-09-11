#!/usr/bin/env python3
"""E1b driver: one job of the two-workload calibrated-ratio experiment.

E1b measures whether the calibrated ratio R = T_target / T_calibration removes enough
cross-host variation for a target-side regression to be separable. Nothing here assumes
it does.

PROTOCOL (one job)

  warm-up : one invocation of each of the five workload configurations, recorded,
            flagged, and excluded from every statistic.
  rounds  : five rounds, each  A1 | four B variants | A2 .
            Each invocation is a separate process with one timed run.

ROUND PERMUTATIONS -- explicit, not "a Latin square"

  Rounds 1-4 are a cyclic 4x4 Latin square: each variant occupies each B position
  exactly once. Round 5 repeats round 1. With five rounds and four variants perfect
  balance is impossible; this choice gives each variant its doubled exposure in a
  DIFFERENT position, and keeps the mean-position difference within each (null, reg)
  pair at 0.2, the minimum attainable. Position is recorded per invocation so residual
  order effects remain testable rather than assumed absent.

DERIVED QUANTITIES

  A_r    = (T_A1,r + T_A2,r) / 2      estimates A at the round's temporal midpoint,
                                      under an approximately linear drift assumption;
                                      D_r is the diagnostic for violations.
  R_X,r  = T_X,r / A_r
  D_r    = T_A2,r / T_A1,r
  R_X,j  = median_r(R_X,r)            primary, paired
  R'_X,j = median_r(T_X,r) / median_r(A_r)    secondary, aggregate
  S_X,j  = median_r(T_X_reg,r / T_X_null,r)   paired injection-scaling diagnostic

  S is NOT a pure estimate of the regression multiplier. Within a round the null and reg
  variants occupy different positions, so residual position effects can contribute to it.
  Counterbalancing across rounds is what makes that confounding testable and mitigable,
  not what removes it. S measures the REALISED runtime effect of a 1.05x iteration-count
  injection; the nominal injected effect is +5% work, and the two are not assumed equal.

INJECTION INTERFACE

  The B workloads expose --condition null|reg, a closed two-valued flag, rather than the
  arbitrary --scale multiplier the approved plan named. The experimental semantics are
  identical -- null is the base iteration count and reg is exactly 1.05x of it -- but a
  caller cannot request any other value. A free multiplier would let an edited or
  mistyped invocation run the experiment at an unintended injected effect with nothing
  downstream noticing, since the iteration count would be recorded faithfully either
  way. The 1.05 constant lives in the workload sources, where changing it is a
  reviewable diff.

Everything derived is recomputable from the raw invocation records, which are all
retained. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import statistics
import subprocess
import sys

PROTOCOL_VERSION = 1

# variant label -> (binary key, --condition value)
VARIANTS = {
    "near_null": ("b_near", "null"),
    "near_reg": ("b_near", "reg"),
    "far_null": ("b_far", "null"),
    "far_reg": ("b_far", "reg"),
}

# Rounds 1-4: cyclic Latin square. Round 5: repeats round 1. See module docstring.
ROUND_PERMUTATIONS = [
    ("near_null", "near_reg", "far_null", "far_reg"),
    ("near_reg", "far_null", "far_reg", "near_null"),
    ("far_null", "far_reg", "near_null", "near_reg"),
    ("far_reg", "near_null", "near_reg", "far_null"),
    ("near_null", "near_reg", "far_null", "far_reg"),
]

ROUNDS = len(ROUND_PERMUTATIONS)


def cpu_model():
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine() or "unknown"


def host_context():
    return {
        "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": cpu_model(),
        "cpu_count": os.cpu_count(),
        "ci": {
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_image": os.environ.get("ImageOS"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "job": os.environ.get("GITHUB_JOB"),
            "sha": os.environ.get("GITHUB_SHA"),
        },
    }


def verify_identity(payload, binary, expected_workload, expected_condition):
    """Check what the executable SAYS it is against what the driver asked for.

    Without this, swapping two binary paths on the command line would mislabel every
    record in the job, the checksums would stay self-consistent within each (wrong)
    label, and no downstream check would notice. The payload is the executable's own
    account of its identity, so it is what gets validated - not the driver's
    expectation copied into the record.

    The calibration workload is frozen and emits no identity fields, so for it the
    check is inverted: the absence of those fields is what distinguishes it from a B
    workload. That covers a swap in either direction.
    """
    if expected_workload == "calibration":
        if "workload" in payload or "condition" in payload:
            raise RuntimeError(
                f"identity mismatch for {os.path.basename(binary)}: expected the "
                f"calibration workload, which emits no identity fields, but the payload "
                f"reports workload={payload.get('workload')!r} "
                f"condition={payload.get('condition')!r}"
            )
        return

    actual_workload = payload.get("workload")
    actual_condition = payload.get("condition")
    if actual_workload != expected_workload or actual_condition != expected_condition:
        raise RuntimeError(
            f"identity mismatch for {os.path.basename(binary)}: expected "
            f"workload={expected_workload!r} condition={expected_condition!r}, "
            f"payload reports workload={actual_workload!r} condition={actual_condition!r}"
        )


def invoke(binary, expected_workload, expected_condition):
    """One process, one timed run. Returns the workload's parsed JSON.

    The payload's self-reported identity is validated before it is returned, so a
    mismatched invocation raises and the job aborts before any record is written.
    """
    command = [binary, "--runs", "1"]
    if expected_condition is not None:
        command += ["--condition", expected_condition]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"{os.path.basename(binary)} exited {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    payload = json.loads(completed.stdout)
    verify_identity(payload, binary, expected_workload, expected_condition)
    return payload


def record(index, variant, workload, condition, round_index, slot, b_position, warmup, payload):
    return {
        "invocation_index": index,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "variant": variant,
        "workload": workload,
        "condition": condition,
        "round": round_index,
        "round_slot": slot,
        "b_position": b_position,
        "warmup": warmup,
        "iterations": payload["iterations"],
        "checksum": payload["checksum"],
        "checksum_stable": payload["checksum_stable"],
        "timing_ns": payload["runs_ns"][0],
    }


def derive(invocations):
    """Recompute every derived quantity from the raw invocations.

    The analyser performs this same computation independently and cross-checks; storing
    it here is a convenience, never the source of truth.
    """
    timed = [i for i in invocations if not i["warmup"]]
    by_round = {}
    for entry in timed:
        by_round.setdefault(entry["round"], {})[entry["variant"]] = entry["timing_ns"]

    rounds = []
    for round_index in sorted(by_round):
        slots = by_round[round_index]
        a1 = slots["A1"]
        a2 = slots["A2"]
        a_mid = (a1 + a2) / 2.0
        rounds.append({
            "round": round_index,
            "A1_ns": a1,
            "A2_ns": a2,
            "A_mid_ns": a_mid,
            "D": a2 / a1,
            "R": {v: slots[v] / a_mid for v in VARIANTS},
        })

    def med(values):
        return statistics.median(values)

    derived = {
        "rounds": rounds,
        "D_j": med([r["D"] for r in rounds]),
        "R_paired": {v: med([r["R"][v] for r in rounds]) for v in VARIANTS},
        "R_aggregate": {
            v: med([by_round[r["round"]][v] for r in rounds]) / med([r["A_mid_ns"] for r in rounds])
            for v in VARIANTS
        },
        "S": {
            family: med([
                by_round[r["round"]][f"{family}_reg"] / by_round[r["round"]][f"{family}_null"]
                for r in rounds
            ])
            for family in ("near", "far")
        },
    }
    return derived


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--calibration", required=True, help="path to gb_calibration")
    parser.add_argument("--b-near", required=True, help="path to gb_b_near")
    parser.add_argument("--b-far", required=True, help="path to gb_b_far")
    parser.add_argument("--out", required=True, help="directory to write the job record into")
    args = parser.parse_args()

    # Absolute paths: on Windows a relative path with forward slashes passes
    # os.path.exists and is then rejected by the process launcher.
    binaries = {
        "calibration": os.path.abspath(args.calibration),
        "b_near": os.path.abspath(args.b_near),
        "b_far": os.path.abspath(args.b_far),
    }
    for name, path in binaries.items():
        if not os.path.isfile(path):
            print(f"{name} binary not found: {path}", file=sys.stderr)
            return 2

    invocations = []
    index = 0

    try:
        # Warm-up: recorded, flagged, excluded from every statistic.
        payload = invoke(binaries["calibration"], "calibration", None)
        invocations.append(record(index, "A", "calibration", "calibration", 0, 0, None, True, payload))
        index += 1
        for variant, (binary_key, condition) in VARIANTS.items():
            payload = invoke(binaries[binary_key], binary_key, condition)
            invocations.append(
                record(index, variant, binary_key, condition, 0, 0, None, True, payload))
            index += 1

        # Five bracketed rounds.
        for round_number, permutation in enumerate(ROUND_PERMUTATIONS, start=1):
            payload = invoke(binaries["calibration"], "calibration", None)
            invocations.append(
                record(index, "A1", "calibration", "calibration", round_number, 1, None, False,
                       payload))
            index += 1

            for b_position, variant in enumerate(permutation, start=1):
                binary_key, condition = VARIANTS[variant]
                payload = invoke(binaries[binary_key], binary_key, condition)
                invocations.append(
                    record(index, variant, binary_key, condition, round_number,
                           1 + b_position, b_position, False, payload))
                index += 1

            payload = invoke(binaries["calibration"], "calibration", None)
            invocations.append(
                record(index, "A2", "calibration", "calibration", round_number, 6, None, False,
                       payload))
            index += 1
    except (RuntimeError, json.JSONDecodeError) as error:
        print(f"E1b job aborted: {error}", file=sys.stderr)
        return 1

    job = {
        "protocol_version": PROTOCOL_VERSION,
        "rounds": ROUNDS,
        "permutations": [list(p) for p in ROUND_PERMUTATIONS],
        "host": host_context(),
        "invocations": invocations,
        "derived": derive(invocations),
    }

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    path = os.path.join(args.out, f"e1b-{stamp}-{run_id}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(job, handle, indent=2, sort_keys=True)
        handle.write("\n")

    derived = job["derived"]
    print(f"wrote {path}")
    print(f"  cpu        : {job['host']['cpu_model']}")
    print(f"  invocations: {len(invocations)} "
          f"({sum(1 for i in invocations if i['warmup'])} warm-up, excluded)")
    print(f"  D_j        : {derived['D_j']:.5f}")
    for variant in VARIANTS:
        print(f"  R[{variant:9}]: {derived['R_paired'][variant]:.5f}")
    for family in ("near", "far"):
        print(f"  S[{family:9}]: {derived['S'][family]:.5f}   "
              f"(realised; nominal injected work is 1.05)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
