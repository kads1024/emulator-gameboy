# Test ROMs and external test artefacts

This is the audit record for every external artefact this project's oracles depend on.
`scripts/test-roms.json` is the machine-readable form and the source of truth; this
document is where the reasoning lives.

Every licence statement below was **read from the named source on the named date**. None
of it is recalled, and none of it is inferred from community practice.

## Policy

1. **Nothing is committed to this repository — including the permissively licensed
   suites.** `docs/scope.md` section 7 keeps test ROMs out of the tree, and ADR 0008
   (layout) rule 6 keeps fetched artefacts out of every target's source directory. The
   rule is uniform so that nobody has to reason about which suite is exempt at the moment
   they are tempted to vendor one.
2. **Artefacts are fetched by checksum from pinned revisions.** A suite is pinned to a
   commit or a release tag, never to a branch.
3. **Verification is mandatory and failure is loud.** A hash mismatch is an error, the
   offending file is not kept, and the fetcher exits non-zero. A verification pass that
   finds artefacts missing exits non-zero rather than reporting success, because a
   silently skipped oracle is the failure mode section 7 exists to prevent.
4. **Integrity and availability are different problems.** Pinning protects against an
   artefact changing underneath us. It does nothing about a host disappearing, which is a
   live risk for one suite below, so the manifest records a secondary origin where one
   exists.
5. **Licence status is recorded as found, including when it is absent.** "Everyone uses
   these" is not a licence.

## Inventory

| Suite | Licence as read | Distribution | Status |
|---|---|---|---|
| Blargg `cpu_instrs` (individual) | **None found** | Prebuilt `.gb`, third-party mirror | **wired** |
| SingleStepTests SM83 | MIT, © 2024 SingleStepTests | 500 JSON files, ~160 MB | **wired** |
| dmg-acid2 | MIT, © 2020 Matt Currie | Prebuilt release asset | recorded |
| Mooneye Test Suite | MIT, © 2014–2022 Joonas Javanainen | Source only, needs RGBDS | recorded |
| Mealybug Tearoom | MIT, © 2018 Matt Currie | Source + reference images | recorded |

### Blargg — no licence exists, and the project's position on it

`retrio/gb-test-roms` contains **no LICENSE file, no copyright notice, and no permission
grant.** The repository `readme.txt` records only the original and current hosting URLs.
`cpu_instrs/readme.txt` documents the test harness and ends with the author's signature,
`-- Shay Green <gblargg@gmail.com>`, and nothing else.

Default copyright therefore applies. These ROMs are not public domain and not
permissively licensed; they are simply distributed by their author for this purpose, and
have been for two decades without objection.

**The project's position, decided deliberately rather than by omission:** fetch at test
time, never redistribute, never include in a release artefact, and record the absence of a
licence explicitly wherever the suite is named. This is why the no-vendoring rule is
uniform — the one suite where vendoring would be legally questionable is also the one
whose ROMs are most convenient to vendor.

The mirror's last commit is from **2015-06-25**. Pinning the commit
(`c240dd7d700e5c0b00a7bbba52b53e4ee67b5f15`) protects integrity, not availability. The
manifest records `http://blargg.8bitalley.com/parodius/gb-tests/` as the secondary origin.

### Facts established by inspecting the artefacts

- **Each `cpu_instrs/individual/*.gb` is 32,768 bytes — no MBC.** They run before any
  mapper exists, so the CPU milestone is not blocked on cartridge work. The combined
  `cpu_instrs.gb` is 65,536 bytes and requires MBC1, which is why it is not in the
  manifest.
- **`dmg-acid2.gb` is also 32,768 bytes**, so the PPU milestone is likewise unblocked by
  mappers.
- **`02-interrupts` needs a working timer**, so the full `cpu_instrs` set passes at the
  milestone that implements the interrupt controller and timer, not at the CPU milestone.
- **The SM83 suite is 500 files and ~160 MB uncompressed** (244 base opcodes, 256
  CB-prefixed). Fetching all of it on every CI run is not free. How much CI fetches is
  decided by the milestone that consumes it, with measurement.

## gameboy-doctor: what it requires of this emulator

Read from its README rather than assumed, discharging the obligation in the project's
trace-format decision. Licence: MIT, © 2022 Rob Heaton.

- It supports **only the `cpu_instrs` individual ROMs**.
- It requires the CPU to start in **post-boot state**, including `F = 0xB0`.
- It requires **`LY` (`$FF44`) to return a hardcoded `0x90`**, because a constant prevents
  spurious divergences in a comparison against logs generated that way.
- Its canonical trace line is:
  ```
  A:00 F:11 B:22 C:33 D:44 E:55 H:66 L:77 SP:8888 PC:9999 PCMEM:AA,BB,CC,DD
  ```
  one line per executed instruction, with `PCMEM` being the four bytes at `PC`.
- For `02-interrupts`, a line must not be written while the CPU is halted.

**The `LY` hardcode is a deliberate inaccuracy.** When it is introduced it gets an entry
in `docs/known-shortcuts.md` on the same day, with removal at the PPU milestone. It is the
temporary testing hack the trace-format decision anticipated, and it is the first
`known-shortcuts.md` entry this project will have.

## Using the fetcher

```
python scripts/fetch_test_roms.py --list                    # licence inventory
python scripts/fetch_test_roms.py --all-wired               # fetch everything wired
python scripts/fetch_test_roms.py --suite sm83 --limit 8    # a subset
python scripts/fetch_test_roms.py --verify --all-wired      # check, download nothing
```

Artefacts land in `roms/`, which is gitignored. The fetcher uses the standard library
only, so CI needs no package install to obtain its oracles.

`scripts/test-roms.lock.json` records the hash of every file fetched from a
tree-enumerated suite, where per-file hashes are not practical to list by hand. It is
committed: it is what makes a later fetch verifiable instead of trusting the network a
second time.

## Deliberately not done yet

- **No CI job fetches anything.** Nothing consumes these artefacts, and a job that
  downloads 160 MB to test nothing is cost without signal — the same reasoning ADR 0007
  (performance floor) applies to its own gate. CI integration lands with the first test
  that consumes a ROM, together with the assertion that the expected number of
  ROM-dependent tests actually ran.
- **Mooneye is not wired.** It ships source only and requires RGBDS to assemble. Putting
  an assembler toolchain into CI before anything consumes its output is a seam the project
  declines to build early. It is wired at the milestone that first needs it, with a pinned
  RGBDS version.
- **The SM83 fetch strategy is unresolved.** Full fetch, cached fetch, or per-opcode lazy
  fetch is a decision for the CPU milestone, made against measured CI time rather than
  guessed now.
