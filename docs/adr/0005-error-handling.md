# ADR 0005: Error handling

## Status summary

**Error handling mechanism and the boundary between failures and defects:** BLOCKING ARCHITECTURAL DECISION: accepted.

## Context

### The problem

Two populations of failure exist in this project and they have almost nothing in common.

The first is **conditions**: a file that is not a Game Boy ROM, a header declaring a cartridge this emulator refuses, a save file whose size does not match the cartridge, a boot image of the wrong length. These are states of the world. They are expected, they are the user's to correct, and the program must survive them and say something useful.

The second is **defects**: an address that decoded to no region when rule 2 of ADR 0004 says decoding is total, a mapper offset outside the ROM it indexes. These are not conditions. They are proof that the program is wrong, and continuing past one produces behaviour that is neither the hardware's nor the program's.

Conflating the two produces the worst of both: defects returned as recoverable errors and ignored, or conditions treated as fatal.

### The contradiction this ADR resolves

The project's decision brief offered a vendored `tl::expected` as a candidate mechanism. It also requires that the core link nothing but the standard library, with the build failing if that is violated. A vendored header-only library is not the standard library, and a purity check that has to be taught exceptions on its first day is a purity check that will be disabled by its fourth month.

One of the two had to give. This ADR resolves it without weakening either.

### Constraints

1. **The core is closed.** No third-party dependency, no I/O, no filesystem, principle P11 and the purity check that enforces it.
2. **The hot path admits no overhead.** ADR 0002 makes the advance mechanism and bus access the most-executed code in the project. No allocation, no I/O, no virtual dispatch, and no error machinery there.
3. **`std::expected` is unavailable.** The project is C++20.
4. **Unknown hardware behaviour is not an error.** Principle P14 governs it, and it must not be routed through the error mechanism, which would turn a modelling gap into a condition the caller is invited to handle.

### Out of scope

The diagnostic and logging design, the debugger's error presentation, and the frontend's user-facing message text.

## Decision

**1. Failures are classified before they are handled.** A failure is either a *condition*(a possible state of the world outside the program's control ) or a *defect*(a violated invariant). Every failure site is one or the other, and the two use different mechanisms. A failure that is hard to classify is a signal that the invariant is unclear, not a reason to use both.

**2. Conditions are returned as values, using an in-house `Result<T, E>` defined in the core.** It depends on nothing but the standard library, which satisfies the purity requirement without an exception to it.

**3. `Result` implements a strict subset of `std::expected`'s interface.** Only members that exist in the standard type, with the same names and the same semantics, presence tests, value access, error access, `value_or`, and at most one monadic combinator, added only when a call site demonstrates the need. Nothing invented, nothing extended.

The purpose of the restriction is migration: when the project moves to a standard that provides `std::expected`, `Result` becomes an alias and then disappears. Any member without a standard counterpart makes that a refactor instead of a deletion.

**4. Errors are enumerated values, not text.** The core produces error values with structured payload where the caller needs detail. It does not produce sentences. Message text belongs to the tools and the frontend, which own presentation and are permitted to do I/O.

**5. No exceptions in the core.** Not for control flow and not for load failures. Allocation failure is the single exception to the rule and is deliberately unhandled: the core does not attempt to recover from it, and treats it as a condition outside its model.

**6. Defects are assertions.** A violated invariant aborts in debug builds with a diagnostic identifying the invariant. Release builds do not pay for checks that would
breach the performance floor. Where an invariant is too expensive to assert on the hot path, the design is expected to make its violation impossible by construction rather than to check for it, total decoding rather than a decode failure path is the model.

**7. Unimplemented hardware behaviour uses neither mechanism.** It is not a condition and not a defect in the caller: it is a gap in this emulator. Principle P14 governs it, loud in debug, counted in release, never a returned error and never a plausible value.

**8. `Result` never appears in the hot path.** Bus accesses, the advance mechanism, and instruction execution do not return `Result`, because there is no recoverable failure available to them: the hardware always does something, and what it does is this project's job to model.

**9. Failure is never signalled by a sentinel value.** No returned `$FF` meaning "no," no negative length, no null-as-error. Every one of those collides with a legitimate hardware value somewhere in this machine.

**10. Ignoring a returned `Result` is a compile error** wherever the language permits it to be made one.