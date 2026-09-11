# Game Boy emulator

A cycle-accurate emulator for the original Game Boy: the Sharp DMG, and nothing else.

**There is no emulator yet.** What exists is the foundation it will be built on: the
build, the guards that enforce the architecture, and the decision record that explains
why the architecture is what it is. This README says so plainly because a repository that
overstates its state wastes the reader's time.

## Status

Milestone 1: foundation and contracts.

| Exists | Does not exist |
|---|---|
| Four-target build with one-way dependency | CPU, bus, PPU, timer, APU, any emulation at all |
| CI on clang and GCC, debug and release | A performance gate (there is nothing to measure) |
| Core dependency-purity checks, with a test proving they reject a violation | Test ROM integration in CI |
| Test artefact manifest with an audited licence for every suite | |
| Calibration workload and the experiment that will size the performance gate | |
| Fourteen documents recording every architectural decision | |

## What it will be

The scope is deliberately narrow and closed. In: the SM83 CPU with M-cycle-accurate
memory timing, the bus, the interrupt controller, the PPU, the timer, the APU, joypad,
OAM DMA, serial, and the No-MBC, MBC1, MBC3 and MBC5 cartridges. Out: Game Boy Color,
Super Game Boy, link-cable emulation, exotic mappers, and anything that is not this
machine.

`docs/scope.md` is the document every scope question is settled against. If a feature
cannot be classified as in or out by reading it, that is a defect in the document.

## Documents

| Document | What it is for |
|---|---|
| [`docs/scope.md`](docs/scope.md) | What this project emulates and what it refuses to |
| [`docs/architecture.md`](docs/architecture.md) | Seventeen principles, each with what fails review |
| [`docs/adr/`](docs/adr/) | Eight decision records, each with a falsifier and a review trigger |
| [`docs/review-checklist.md`](docs/review-checklist.md) | What a human checks, given what CI already enforces |
| [`docs/known-shortcuts.md`](docs/known-shortcuts.md) | Every deliberate inaccuracy, with a removal condition |
| [`docs/test-roms.md`](docs/test-roms.md) | The licence audit for every external test artefact |
| [`docs/performance-measurement.md`](docs/performance-measurement.md) | How the performance gate is being built, and what is not built yet |

The decision records are the interesting part. Each one states what would falsify it, so a
future disagreement is settled by evidence rather than by re-arguing it.

## Building

Requires CMake 3.25 or newer, Ninja, and clang or GCC with C++20. Both compilers are
enforcing: code must compile clean under each, because neither subsumes the other's
diagnostics.

```
cmake --preset linux-gcc-debug        # or windows-clang-debug
cmake --build --preset linux-gcc-debug
ctest --preset linux-gcc-debug
```

Release presets exist for both toolchains. Debug carries sanitizers: ASan and UBSan with
full diagnostics on Linux, and ASan plus UBSan in trap mode on Windows, where UBSan's
runtime does not link against the installed SDK.

## What the build refuses to do

The architecture is enforced mechanically rather than remembered:

- The core links **only** the standard library. The build asserts it declares no link
  dependencies, and scans its sources for headers that would perform I/O or make its
  behaviour depend on anything but its own state and inputs.
- The core may not include from `tools`, `frontend`, or `tests`. Dependency runs one way.
- Warnings are errors, under both compilers, including `-Wconversion` and
  `-Wsign-conversion`.
- Every guard has a test that plants a violation and passes only when the build rejects
  it. A guard nobody has watched fail is not a guard.

## Test ROMs

None are distributed with this project, and none are committed to it, including the
permissively licensed ones, because a uniform rule needs no per-suite reasoning at the
moment somebody is tempted.

`scripts/fetch_test_roms.py` obtains them from pinned revisions and verifies every one by
SHA-256. `docs/test-roms.md` records each suite's licence as read from its file, on the
date it was read, including the one suite that has no licence at all.

No commercial game ROM appears in this repository, its history, its fixtures, its CI, or
any release artefact.

## Licence

MIT: see [`LICENSE`](LICENSE).

That covers this project's own code and documentation. It does **not** cover the external
test artefacts the fetch script downloads: those carry their own terms, one of them
carries none, and `docs/test-roms.md` records the position on each.
