# ADR 0001: Toolchain

## Status summary

- **Language standard, compilers, build system, and configurations:** BLOCKING ARCHITECTURAL DECISION: accepted.
- **Inclusion of the MSVC front end in the compiler matrix:** PROVISIONAL: adjudication recorded in the Status section.

## Context

### The problem

Most of this project's rules are enforceable only by the toolchain. The core's purity, the warning discipline, determinism, formatting, and the performance gate are all mechanisms rather than intentions, and each one exists only if some tool refuses to proceed without it. A decision here therefore determines which of the project's stated rules are real and which are merely remembered.

### What was measured

The following are observations from the development machine, not assumptions:

- clang 22.1.0 targets `x86_64-pc-windows-msvc` by default and links successfully using the MSVC Build Tools STL and the Windows SDK. The MSVC standard library is therefore already exercised without invoking `cl.exe`.
- `cl.exe` is present on disk but not on `PATH`.
- ASan builds on Windows and requires the LLVM runtime directory on `PATH` at run time.
- UBSan with its runtime library fails to link on Windows against this SDK. UBSan in trap mode builds, runs, and was verified to catch signed overflow, with a trap and no diagnostic text.
- WSL provides a Linux environment with GCC and CMake.
- Ninja is not installed on either environment.
- The twelve-pattern conversion survey established that neither clang nor GCC is uniformly stricter: which compiler warns depends on the expression, so code must satisfy both.

### Constraints from prior decisions

The core links only the standard library and the build fails otherwise. The debug configuration carries sanitizers. The performance gate requires a release build and CI. The error-handling mechanism is shaped by the C++20 standard and expects to be superseded if that changes.

### Out of scope

The repository layout, the CI provider's workflow mechanics, the test ROM acquisition mechanism, and the specific content of the clang-tidy check set, which is tuned against real code rather than chosen in advance.

## Decision, Part A: language, compilers, and build

**A1. The language standard is C++20, with no compiler extensions enabled.** A future move to a standard providing `std::expected` supersedes part of ADR 0005 and is that ADR's recorded review trigger; it is not undertaken as part of this one.

**A2. The enforcing compilers are clang and GCC.** They are the compilers that support the project's required warning set and its sanitizers, and the conversion survey shows both are necessary because neither subsumes the other. Code must compile clean under both.

**A3. MSVC standard-library coverage comes from clang targeting `x86_64-pc-windows-msvc`, not from `cl.exe`.** This exercises the Microsoft standard library and the Windows SDK without adding a front end that cannot enforce the project's central conversion rule.

**A4. The build system is CMake, driven by presets.** The minimum CMake version is pinned to the lowest version available across the CI images and the development machine, and recorded in the top-level build file rather than assumed.

**A5. The generator is Ninja, in every environment.** One build graph locally and in CI, identical across compilers. It is not currently installed and its installation is a prerequisite of the build step.

**A6. Two local development targets are supported:** Windows with clang as the primary, and WSL with GCC as the second, so that both enforcing compilers can be exercised before pushing rather than discovered in CI.

**A7. Configurations are debug and release.** Debug is unoptimised and carries sanitizers. Release is optimised, is what the performance gate measures, and is what ships. Sanitizer variants are separate presets rather than modes of the debug preset.

**A8. A configuration that cannot support a required flag fails to configure.** Silent degradation (a preset that quietly drops a sanitizer or a warning because the toolchain did not accept it) is forbidden, because a check that can silently disable itself is not a check.

## Decision, Part B: enforcement

### Warnings

**B1. The warning set is `-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion`, with warnings as errors.** It applies to this project's targets only. Dependencies brought in for testing are consumed as system includes so that their diagnostics are not this project's problem and cannot be silenced by weakening the project's own flags.

**B2. Warning configuration lives in exactly one place** (a single interface target that project targets consume) with the per-compiler spelling mapped there. No target sets its own warning flags, and no flag is applied globally.

**B3. Code must compile clean under both enforcing compilers.** The conversion survey established that neither clang nor GCC subsumes the other: which one warns depends on the expression. Satisfying one is not evidence about the other.

### Integer conversion convention

**B4. Interfaces return hardware-domain types.** Register accessors, memory accessors, and instruction decoders return `u8` or `u16`, never `int`. This keeps the common case warning-free by construction: both compilers exempt arithmetic in which every operand already has the destination type, so `u8 + u8` assigned to `u8` produces no diagnostic and needs no helper and no cast.

**B5. That exemption is binary only.** Measured behaviour: GCC warns on `u8 c = a + b + carry;` even when all three operands are `u8`, although modular arithmetic makes the truncation exact. Three-operand arithmetic (ADC, SBC, and multi-term address computation) therefore requires a named operation regardless of interface types. B4 shrinks the helper set; it does not eliminate it.

**B6. Named operations exist for arithmetic the hardware performs.** The initial set:

| Name | Operation |
|---|---|
| `wrap_add8` | 8-bit addition whose result wraps in the 8-bit hardware domain |
| `wrap_add16` | 16-bit addition whose result wraps in the 16-bit hardware domain |
| `rel_target` | a 16-bit address plus a signed 8-bit displacement |
| `pack_u16` | a 16-bit value constructed from a high and a low byte |
| `hi_byte` | the high byte of a 16-bit value |
| `lo_byte` | the low byte of a 16-bit value |

These are named here, not designed. Their signatures may later be subsumed by ALU operations returning a result together with its flags, since ADC requires a carry in and its callers require carry-out and half-carry, and a helper returning only the wrapped sum would duplicate flag computation at every call site. That shape is decided against real call sites at the CPU milestone.

**B7. A helper should represent a meaningful hardware operation, not just a warning workaround.**

**B8. A raw `static_cast` is permitted only where the converted expression contains no arithmetic and the target type is the hardware domain of the destination.** Narrowing that results from an operation the hardware performs goes through a named operation instead. A reviewer applies this by looking for an operator inside the cast, which makes it mechanical rather than a judgement about intent.

**B9. Host-boundary conversions are explicit and occur at the boundary.** Conversions from emulated values (`u8`, `u16`) to host indexing or sizing types (`std::size_t`, container `size_type`, span indices, allocation sizes) occur only in the expression that crosses into the host facility. Arithmetic is completed in the emulated domain before the conversion. A reviewer applies this by checking that the cast's operand is a named emulated value rather than an arithmetic expression.

A storage-indexing helper would eliminate most such conversions by centralising the boundary. This is recorded as a Milestone 2 observation rather than a commitment.

### Sanitizers

**B10. Linux is the authoritative sanitizer environment.** The debug configuration there (in CI and in WSL) carries ASan and UBSan with their runtime libraries and full diagnostics.

**B11. Windows sanitizer support is asymmetric, and the asymmetry is recorded rather than hidden.** ASan builds and runs, given the LLVM runtime directory on `PATH`. UBSan with its runtime library does not link against the installed SDK; UBSan in trap mode does work and was verified to catch signed overflow, but reports a trap rather than a diagnostic. A UB failure observed on Windows is therefore reproduced under Linux to be diagnosed.

### Core purity

**B12. The core's dependency boundary is enforced by two independent checks**, because
either alone is defeatable:
1. A build-system assertion that the core target resolves to no link dependencies.
2. A source scan of core translation units against a header denylist.

**B13. The denylist covers determinism as well as dependencies.** `<iostream>`, `<cstdio>`, `<filesystem>`, `<chrono>`, `<random>` and `<thread>` are all standard library headers and all are forbidden in the core: the first three because the core performs no I/O, the last three because principle P11 requires the core's next state to be a function of its current state and its inputs.

**B14. The purity check is itself tested.** A planted violation must fail the build, and that demonstration is repeated whenever the check's mechanism changes. An unverified guard is not a guard.

### Formatting and static analysis

**B15. clang-format configuration is committed and enforced in CI.** Formatting is not a review topic; a formatting discussion in a pull request is a defect in this rule, not in the code.

**B16. clang-tidy runs in CI.** Its check set is tuned against real code rather than chosen in advance. A suppressed check carries an inline justification naming why the code is correct, not merely that the check was noisy.

### Test framework

**B17. The test framework is Catch2 v3**, fetched at configure time, pinned to an exact release, and verified by hash.

The justification is brief because the choice is reversible: it integrates with CTest at per-test-case granularity, which matters for a per-opcode suite where a failure should name the opcode; it has matchers suitable for comparing structured values such as machine state and framebuffers; and it emits CI-consumable report formats without additional work. It also does not bring a mocking framework into the tree, which suits a project that tests against concrete types rather than interfaces. doctest is the runner-up on build time, and switching is mechanical.

**B18. The framework links to tests only, never to the core.** The purity checks in B12 enforce this; the framework's presence in the build is not an exception to them.