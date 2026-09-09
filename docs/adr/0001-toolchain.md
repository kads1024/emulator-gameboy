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

**B9. Host-boundary conversions are explicit, occur at the boundary, and contain no arithmetic in the cast operand.** A conversion from an emulated value (`u8`, `u16`) to a host indexing or sizing type (`std::size_t`, container `size_type`, span index, allocation size) appears only in the expression that crosses into the host facility, and its operand is a named emulated value, never an arithmetic expression.

Which domain arithmetic belongs to follows from the range of the result, not from the position of the cast:

- Arithmetic whose result is *defined* by the emulated domain's wrap (incrementing an address across a 16-bit read, `HL + e8`, stack pointer adjustment) is performed in the emulated domain, and the wrapped result is what gets converted.
- Arithmetic whose result legitimately exceeds the emulated domain's range (a bank offset resolved against a multi-megabyte ROM image (ADR 0006)) is performed in the host domain, *after* the conversion, on operands that are already host-domain values.

A reviewer applies this by checking that no operator appears inside the cast, which is the same check as B8.

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

## Alternatives considered

### Alternative 1: Conversion warnings not treated as errors

The alternative is to keep `-Wconversion` and `-Wsign-conversion` enabled but non-fatal, or to omit them entirely.

Treating them as warnings reduces friction in the short term but weakens the enforcement mechanism. The failure mode is not that developers consciously choose to ignore a specific warning. It is that the warning count ceases to be a useful signal. A new warning appears, the build still succeeds, and work continues. Additional warnings accumulate. Once the count is non-zero by default, determining whether a particular warning is new requires manual inspection rather than being answered by the build result. The signal is therefore mixed with historical noise, and the practical effect is that new warnings stop being reviewed consistently.

Dropping `-Wconversion` entirely would likely not cause immediate correctness failures in many cases. The SM83 core is validated against reference traces and test ROMs, and many unintended truncations would eventually surface as behavioural mismatches. The rule's primary justification is therefore not bug-catching. It is semantic visibility.

The conversion survey established that many operations performed by the hardware are represented in C++ through integer promotion followed by narrowing. Without a convention, a reader cannot distinguish between an intentional hardware-domain operation and an accidental truncation. B6 and B8 exist to make that distinction explicit. The value of the rule is that arithmetic which intentionally wraps, narrows, or crosses domains becomes visible in the source and reviewable as a design choice rather than merely accepted because a cast compiled.

This alternative was rejected because the project's conversion convention depends on warnings being enforceable. A warning that does not block progress eventually becomes documentation rather than policy.

### Alternative 2: Core purity by convention

The alternative is to rely on review discipline rather than mechanical enforcement.

The likely failure sequence is gradual. A deadline creates pressure to inspect state, write a quick diagnostic, or access a host facility. A translation unit gains a forbidden include. The change is reviewed in the context of the immediate task and merged. Nothing fails because the build system does not check for purity. Subsequent code begins using the newly available facility because it is already present. Additional dependencies accumulate around it. The architectural boundary has now moved, but no explicit decision recorded the move.

The delay before discovery may be substantial. The first visible symptom may occur weeks or months later when a new requirement depends on the core remaining pure and deterministic. By that point the dependency has become part of the design rather than a single line that can be removed.

Several other project decisions silently depend on core purity:

* ADR 0002 (timing model) assumes that advancing the machine state depends only on machine state and inputs, not on host facilities.
* ADR 0006 (cartridge representation) assumes real-world time enters the cartridge as an explicit parameter and is never read from the host. The RTC is the machine's only host-time input, and purity is what keeps it a parameter rather than a call.
* ADR 0007 (performance floor) assumes the measured workload is deterministic, which is why `<chrono>` and `<random>` sit on B13's denylist alongside the I/O headers. If purity erodes, run-to-run variation stops being host noise and the gate loses its meaning.
* Save-state requirements depend on the complete machine state being serialisable and restorable without hidden external dependencies.

A purity rule enforced only by convention therefore weakens multiple architectural decisions simultaneously. The mechanical checks in B12 exist because those downstream decisions depend on purity being a property of the build, not of reviewer diligence.

This alternative was rejected because the cost of enforcement is small and the consequences of accidental boundary erosion are delayed and difficult to localise.

### Alternative 3: A build system other than CMake

The alternative is to use another build system such as Meson, Premake, handwritten build scripts, or compiler-specific project files.

The project's requirements are modest: multiple compilers, multiple configurations, CI integration, test execution, and dependency acquisition. Several build systems can satisfy them. The choice is therefore largely operational rather than architectural.

This alternative was rejected because CMake is already available on both development environments, integrates naturally with CTest, supports the required compiler matrix, and is widely supported by tooling. The decision is reversible and does not materially affect the emulator architecture.

### Alternative 4: Windows-only development

The alternative is to perform all development and validation on Windows and remove the Linux leg.

This is attractive because it is the path of least resistance on the development machine. It removes WSL setup, eliminates a second compiler invocation, and keeps all work in a single environment.

However, two measured limitations exist.

First, the conversion survey established that clang and GCC do not diagnose the same expressions. Several patterns warned only under GCC, while others warned only under clang. A Windows-only workflow would therefore remove one of the enforcing compilers and weaken B3.

Second, full UBSan diagnostics are not currently available on the measured Windows environment. UBSan runtime mode fails to link against the installed SDK, while Linux provides working runtime diagnostics. A Windows-only workflow therefore loses the project's authoritative undefined-behaviour diagnosis path.

This alternative was rejected because it removes two independently useful validation mechanisms that have already been shown to catch different classes of problems.

The chosen path carries real daily friction. Every change must compile under two enforcing compilers, developers must occasionally switch environments to diagnose undefined behaviour, and the conversion policy requires deliberate handling of arithmetic that would otherwise compile silently. A solo developer could reasonably choose Alternative 1 or Alternative 4 to reduce that friction.

The benefit of the chosen path is not that it finds every bug earlier. The benefit is that it turns architectural rules into mechanically enforced constraints. The project pays a small cost on every change so that violations are discovered immediately rather than after they have become part of the design.

## Consequences

### Both enforcing compilers are part of the local workflow
WSL is not optional tooling. A change is not finished when it compiles under clang; the conversion survey established that clang and GCC disagree by expression, so the second compiler is part of the definition of done rather than a CI formality. In practice this means a way to invoke both from one command, so the discipline does not depend on remembering.

### Ninja must be installed before any build work
It is absent from both environments today. This is a concrete prerequisite of the build step, not a detail to be discovered when the first preset fails to configure.

### Helper proliferation is a diagnostic, not a nuisance
B4 confines the named operations to mixed-width and multi-operand arithmetic. If helpers begin appearing in ordinary binary 8-bit arithmetic, the cause is almost certainly an interface returning `int` somewhere upstream, because that is precisely what removes the compilers' same-type exemption. The helper count is therefore a canary for B4 drift, and the response is to fix the interface rather than to add helpers.

### The core cannot print, so its diagnostics are data
Principle P14 requires unimplemented behaviour to be loud, and B13 forbids the core from using any facility that could print. These are compatible, and the resolution follows from the constraint: the core records what it encountered as state its owner can read, and the tools and frontend do the reporting. This closes the mechanism ADR 0005 deferred, what P14's loudness consists of in a core that cannot perform I/O.

### A compiler upgrade can break the build, deliberately
Warnings as errors under two compilers means a new release of either can fail a build that passed yesterday, because new diagnostics appear in new versions. Compiler versions are therefore pinned in CI, and upgrading one is a deliberate change reviewed on its own rather than an ambient event.

### The first configure requires network access

The test framework is fetched at configure time and verified by hash. CI caches it; a developer working offline needs a populated cache. This is a small operational cost of not vendoring, accepted because a pinned, hash-verified fetch keeps the dependency out of the repository and its provenance checkable.

### Undefined behaviour on Windows arrives without a message

Trap-mode UBSan produces a trap and a debugger stop, not a diagnostic. Reproducing under Linux is therefore a documented step in the debugging workflow rather than folklore, and belongs in the contributor documentation when it is written.

### clang-tidy initially enforces little

Its check set is tuned against real code, so at the outset it contributes less than the warning set does. This is accepted: a check set chosen before the code exists would be either uselessly permissive or an obstacle course, and neither is worth the time it costs to configure now.

## Status

### Classification

- **Language standard, compilers, build system, and configurations:** BLOCKING ARCHITECTURAL DECISION: accepted.
- **Inclusion of the MSVC front end in the compiler matrix:** PROVISIONAL.

### Adjudication of the MSVC question

The MSVC front end is added to the matrix if a defect reaches CI or a released branch that the MSVC front end would have detected and that both enforcing compilers accepted. Absent such a defect, front-end diversity is not purchased at the cost of a compiler that cannot enforce this project's conversion rule.

### What would reopen the other decisions

- **The language standard** is reopened by ADR 0005's recorded trigger, a standard providing `std::expected` becoming available across the whole matrix.
- **The test framework** is reopened if build time becomes a routine obstacle, measured rather than felt. Switching is mechanical and the choice was made on that basis.
- **The Windows UBSan link failure** may be revisited if the runtime mismatch is resolved upstream. The current behaviour is recorded as measured, and the decision does not depend on it changing.

### Review triggers

- The build setup step: Ninja installed, presets written, both compilers invocable locally.
- The first CI pipeline: the compiler matrix running, and the purity check demonstrated failing on a planted violation before it is trusted.
- The CPU milestone: the helper signatures, and whether they are subsumed by ALU operations returning flags. 