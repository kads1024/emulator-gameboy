#!/usr/bin/env python3
"""Run the calibration workload once and record the result with its host context.

This is the data-collection half of experiment E1, defined in ADR 0007 (performance
floor). E1 characterises the *runner*, not this project's code: the workload is
deliberately not the emulator, which does not exist yet.

One invocation produces one job's worth of data: N timed runs of the frozen workload,
plus enough about the host to tell later whether two jobs are comparable. The analysis
half is scripts/analyze_calibration.py.

Standard library only, so CI needs no package install.

Usage:
    run_calibration.py --binary build/linux-gcc-release/tools/calibration/gb_calibration \\
                       --runs 7 --out perf-results/
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import subprocess
import sys


def cpu_model():
    """Best available description of the CPU. The runner class is a label, not a
    guarantee of hardware: two jobs on the same label can land on different silicon,
    which is one of the things E1 exists to observe."""
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
        # Present in CI, absent locally. Their absence marks a local sample, which
        # should not be mixed into a runner-class characterisation.
        "ci": {
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_image": os.environ.get("ImageOS"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "job": os.environ.get("GITHUB_JOB"),
            "sha": os.environ.get("GITHUB_SHA"),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--binary", required=True, help="path to gb_calibration")
    parser.add_argument("--runs", type=int, default=7, help="timed runs in this job")
    parser.add_argument("--out", required=True, help="directory to write the result into")
    args = parser.parse_args()

    # Resolved to an absolute path: on Windows a relative path with forward slashes is
    # accepted by os.path.exists and rejected by the process launcher, which produces a
    # confusing "file not found" for a file that demonstrably exists.
    binary = os.path.abspath(args.binary)
    if not os.path.isfile(binary):
        print(f"calibration binary not found: {binary}", file=sys.stderr)
        return 2

    completed = subprocess.run(
        [binary, "--runs", str(args.runs)],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0:
        # A non-zero exit means the workload reported that its runs did not do the same
        # work. Recording the timings anyway would put incomparable numbers into the
        # dataset, which is worse than having no sample from this job.
        print(f"calibration workload failed (exit {completed.returncode}):", file=sys.stderr)
        print(completed.stderr.strip(), file=sys.stderr)
        return 1

    try:
        measurement = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        print(f"could not parse workload output: {error}", file=sys.stderr)
        print(completed.stdout, file=sys.stderr)
        return 1

    record = {"host": host_context(), "measurement": measurement}

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    path = os.path.join(args.out, f"calibration-{stamp}-{run_id}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, indent=2, sort_keys=True)
        handle.write("\n")

    timings = measurement["runs_ns"]
    median_ms = sorted(timings)[len(timings) // 2] / 1e6
    print(f"wrote {path}")
    print(f"  cpu      : {record['host']['cpu_model']}")
    print(f"  runs     : {len(timings)}")
    print(f"  median   : {median_ms:.1f} ms")
    print(f"  checksum : {measurement['checksum']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
