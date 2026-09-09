#!/usr/bin/env python3
"""Fetch external test artefacts named in scripts/test-roms.json.

Nothing this script downloads is committed. docs/scope.md section 7 keeps test ROMs out
of the repository and ADR 0008 (layout) rule 6 keeps fetched artefacts out of every
target's source directory; everything lands in roms/, which is gitignored.

Two verification modes, because the suites differ:

  * Artefacts with a recorded sha256 are verified against it. A mismatch is a hard
    failure and the bad file is not kept.
  * Suites marked "verify": "lock" are enumerated from a pinned git tree. The commit is
    immutable, so the first fetch records each file's hash in the lock file and every
    later fetch verifies against it. A lock entry is never silently rewritten.

Standard library only, so CI needs no package install to obtain its oracles.

Usage:
    fetch_test_roms.py --list
    fetch_test_roms.py --all-wired
    fetch_test_roms.py --suite sm83 --limit 8
    fetch_test_roms.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "scripts", "test-roms.json")
USER_AGENT = "emulator-gameboy-test-rom-fetcher"


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def http_get(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def quote_path(path):
    """Percent-encode a path while leaving separators alone. Blargg's filenames
    contain spaces and commas."""
    return "/".join(urllib.parse.quote(part) for part in path.split("/"))


def describe_licence(suite):
    licence = suite.get("license", {})
    status = licence.get("status", "unknown")
    holder = licence.get("holder", "unknown")
    return f"{status} | {holder}"


def cmd_list(manifest):
    print("Test artefact inventory. Licence fields were read from the named source on")
    print("the named date; none of it is recalled.\n")
    for suite in manifest["suites"]:
        state = "wired" if suite.get("wired") else "recorded only"
        print(f"{suite['id']}  [{state}]")
        print(f"    {suite['title']}")
        print(f"    licence : {describe_licence(suite)}")
        licence = suite.get("license", {})
        print(f"    read    : {licence.get('read_from', '?')} on {licence.get('read_on', '?')}")
        print(f"    redist  : {licence.get('redistribution', '?')}")
        print(f"    used at : {suite.get('milestone', '?')}")
        print()
    return 0


def enumerate_tree(suite):
    """List a pinned git tree. The commit is fixed, so the listing is immutable."""
    tree = suite["tree"]
    data = json.loads(http_get(tree["api_url"]).decode("utf-8"))
    if data.get("truncated"):
        raise RuntimeError(
            f"{suite['id']}: the git tree listing was truncated; the fetcher cannot "
            "enumerate the suite reliably"
        )
    prefix = tree["prefix"]
    paths = sorted(
        entry["path"] for entry in data["tree"]
        if entry["type"] == "blob" and entry["path"].startswith(prefix)
    )
    expected = tree.get("expected_count")
    if expected is not None and len(paths) != expected:
        raise RuntimeError(
            f"{suite['id']}: expected {expected} files under {prefix}, found {len(paths)}. "
            "The manifest and the pinned commit disagree."
        )
    return [{"path": path} for path in paths]


def artefacts_for(suite, limit):
    if "artifacts" in suite:
        items = list(suite["artifacts"])
    elif "tree" in suite:
        items = enumerate_tree(suite)
    else:
        raise RuntimeError(f"{suite['id']}: manifest entry has neither artifacts nor tree")
    return items[:limit] if limit else items


def fetch_suite(suite, roms_dir, lock, limit, verify_only):
    suite_id = suite["id"]
    if not suite.get("wired"):
        print(f"{suite_id}: recorded but not wired; nothing to fetch.")
        print(f"    reason: see notes in the manifest")
        return 0, 0

    base = suite["origin"]["base_url"]
    dest_root = os.path.join(roms_dir, suite_id)
    lock_entries = lock.setdefault(suite_id, {})

    fetched = present = missing = 0
    for artefact in artefacts_for(suite, limit):
        rel = artefact["path"]
        dest = os.path.join(dest_root, rel.replace("/", os.sep))
        expected = artefact.get("sha256") or lock_entries.get(rel)

        if os.path.exists(dest):
            with open(dest, "rb") as handle:
                actual = sha256_bytes(handle.read())
            if expected is None:
                lock_entries[rel] = actual
                present += 1
                continue
            if actual != expected:
                raise RuntimeError(
                    f"{suite_id}: {rel} is on disk but its hash does not match.\n"
                    f"    expected {expected}\n    actual   {actual}\n"
                    "    Delete it and re-fetch, or investigate why it changed."
                )
            present += 1
            continue

        if verify_only:
            missing += 1
            continue

        data = http_get(base + quote_path(rel))
        actual = sha256_bytes(data)

        if expected is not None and actual != expected:
            raise RuntimeError(
                f"{suite_id}: {rel} failed verification and was not kept.\n"
                f"    expected {expected}\n    actual   {actual}\n"
                "    The artefact served does not match the pinned revision."
            )

        size = artefact.get("size")
        if size is not None and len(data) != size:
            raise RuntimeError(
                f"{suite_id}: {rel} is {len(data)} bytes, manifest says {size}."
            )

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        partial = dest + ".part"
        with open(partial, "wb") as handle:
            handle.write(data)
        os.replace(partial, dest)

        if expected is None:
            lock_entries[rel] = actual
        fetched += 1

    if verify_only:
        state = "complete" if missing == 0 else f"INCOMPLETE, {missing} missing"
        print(f"{suite_id}: {present} verified on disk, {state}")
    else:
        print(f"{suite_id}: {fetched} fetched, {present} already present")
    return fetched, missing


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the licence inventory")
    parser.add_argument("--suite", action="append", default=[], help="suite id (repeatable)")
    parser.add_argument("--all-wired", action="store_true", help="every suite marked wired")
    parser.add_argument("--limit", type=int, default=0, help="fetch at most N artefacts per suite")
    parser.add_argument("--verify", action="store_true", help="check what is present, download nothing")
    args = parser.parse_args()

    manifest = load_json(MANIFEST)
    if args.list:
        return cmd_list(manifest)

    if not args.suite and not args.all_wired:
        parser.error("choose --list, --all-wired, or --suite ID")

    by_id = {suite["id"]: suite for suite in manifest["suites"]}
    if args.all_wired:
        selected = [s for s in manifest["suites"] if s.get("wired")]
    else:
        unknown = [name for name in args.suite if name not in by_id]
        if unknown:
            parser.error(f"unknown suite(s): {', '.join(unknown)}")
        selected = [by_id[name] for name in args.suite]

    roms_dir = os.path.join(REPO_ROOT, manifest["roms_dir"])
    lock_path = os.path.join(REPO_ROOT, manifest["lock_file"].replace("/", os.sep))
    lock = load_json(lock_path) if os.path.exists(lock_path) else {}
    before = json.dumps(lock, sort_keys=True)

    total = 0
    total_missing = 0
    try:
        for suite in selected:
            fetched, missing = fetch_suite(suite, roms_dir, lock, args.limit, args.verify)
            total += fetched
            total_missing += missing
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError) as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        if json.dumps(lock, sort_keys=True) != before:
            save_json(lock_path, lock)
        return 1

    if json.dumps(lock, sort_keys=True) != before:
        save_json(lock_path, lock)
        print(f"\nLock updated: {manifest['lock_file']}")
        print("Commit it. It is what makes a later fetch verifiable rather than trusting")
        print("the network twice.")

    if args.verify:
        if total_missing:
            # A verifier that reports success while artefacts are absent is exactly the
            # silent skip docs/scope.md section 7 forbids.
            print(
                f"\nINCOMPLETE: {total_missing} artefact(s) missing. Fetch them before "
                "relying on any test that consumes them.",
                file=sys.stderr,
            )
            return 1
        print("\nComplete. Every artefact named for the selected suites is present and verified.")
        return 0

    print(f"\nDone. {total} artefact(s) downloaded into {manifest['roms_dir']}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
