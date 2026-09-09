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