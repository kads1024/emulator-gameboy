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

## Alternatives considered

### Alternative 1: Exceptions
Exceptions make failure propagation concise and avoid requiring a result wrapper at every call site. They also have no normal-path performance cost when no exception is thrown.

The mechanical failure is that failure is not visible in a function's return type. A reader at the call site cannot tell from the signature whether the callee may produce a recoverable condition, which undermines the explicit condition/defect distinction required by rule 1. More importantly, an exception escaping from the middle of a sequence of operations can unwind through code after the machine has already been partially mutated, making the resulting state dependent on where the exception was caught rather than on an explicitly modelled failure boundary. The mechanism therefore does not provide the value-oriented failure contract this ADR requires.

### Alternative 2: Vendored `tl::expected`
A vendored `tl::expected` provides the desired value-or-error semantics immediately and is mature, familiar, and close to the eventual standard-library type.

The mechanical failure is the project's dependency boundary. The purity check currently requires the core to link against nothing but the standard library. Accommodating `tl::expected` would therefore require the purity check to maintain an allowlist or explicit exception for this header-only dependency. Once that exception exists, the same mechanism can be requested for every future header-only dependency, turning a binary architectural constraint into a growing policy list. The purity check would no longer enforce "standard library only"; it would enforce "standard library plus whatever dependencies have been approved."

A narrower version of the same request is to replace the allowlist with a rule: permit any vendored header-only library that itself depends only on the standard library. This is the same concession in a different shape. The property under enforcement stops being *the standard library* and becomes *a class of dependency we have decided to trust*, and membership in that class is a judgement the check cannot make on its own. It can verify the transitive includes; it cannot verify that the class is the one we meant.

This is the exact failure the contradiction in the Context exists to resolve.

### Alternative 3: Moving to C++23 for `std::expected`
C++23 provides `std::expected`, which is the natural standard-library solution and removes the need to maintain an in-house equivalent. It is therefore not rejected on technical merit.

The mechanical issue is scope: adopting it now changes the project's minimum language and standard-library requirements, which affects compiler versions and the CI matrix. That decision belongs to the toolchain ADR rather than this error-handling ADR.

The current `Result<T, E>` deliberately makes that future decision cheap. Because rule 3 restricts `Result` to a strict subset of the standard interface, moving to C++23 later can reduce to replacing the implementation with an alias to `std::expected` and deleting the in-house type. No bespoke API has to be migrated.

### Alternative 4: Error codes with out-parameters
A function returns a status code while writing its result through a pointer or reference. This is simple, requires no custom result type, and has a long history in systems programming.

The mechanical failure is that the status and the output are separate pieces of state. A caller can ignore the error code and read the output anyway, producing a read of a value that the callee never wrote. The compiler does not make the relationship between the status and the output mandatory. `Result<T, E>` instead makes the value's presence part of the returned object, so the caller cannot obtain a successful value without going through the result's success state.

### Alternative 5: One mechanism for both categories
Return `Result` from everything, including the failures this ADR classifies as defects. A violated invariant becomes an error value and propagates to a caller that decides what to do with it. There are no assertions and nothing aborts in a production build. The attraction is real: one mechanism, one calling convention, and no per-site judgement about which category a given failure belongs to. Rule 1 is not weakened by this alternative so much as made unnecessary, and with it goes the risk of classifying a failure wrongly.

The first mechanical failure is where this lands relative to rule 8. Bus accesses and instruction execution run on every emulated cycle. Giving them a `Result` return puts a discriminated union on the return path of the hottest functions in the machine and obliges every caller on that path either to branch on it or to propagate it, which moves the same obligation one frame up. The cost is not only the branch. It is a branch installed at sites where the failure it tests for cannot occur unless the emulator is already broken, per-cycle overhead bought entirely for cases that a correct build never reaches. Rule 8 keeps that path clear of error machinery because the machinery there is not paying for anything.

The second is what "handling" a defect would actually mean. Consider a caller that receives *the decoder found no region for this address*. Decoding is total by ADR 0004 rule 2, so every bit pattern maps to some instruction and this condition cannot have been produced by the emulated program's data. It can only have been produced by a defect in the decoder or in the table it consults. The caller cannot retry, because the same input yields the same result. It cannot substitute a default, because any substitution invents behaviour the hardware does not have. It cannot surface the failure to the guest, because the emulated machine has no corresponding failure to observe. Whatever it does next produces behaviour that is neither the hardware's nor the program's. Returning the condition relocates the defect; it does not handle it. An abort at the detection site at least stops while the state is still diagnostic.

The third is what this does to rule 1's visibility. The classification earns its place by being readable at the call site: a `Result` return states that the callee has a failure mode the caller is expected to model, and the absence of one states that any failure here is a bug in this program. Carrying both categories on the same channel makes every signature say the same thing, and "this may fail in a way you must handle" becomes indistinguishable from "this may fail in a way no caller can handle." The distinction survives only in the author's head, which is the one place this ADR cannot enforce it. Rule 1 degrades from a mechanism into a convention.

The judgement call this alternative promises to remove is therefore not removed. It is deferred to every site that receives a value, each of which has less information than the site that produced it about whether the failure was modelled or a broken invariant.

### Steel-man: what I would use for a two-week project
For a two-week emulator or prototype, I would probably use exceptions or an existing `expected` implementation, and I would not separate conditions from defects at all, every failure would go out through whichever channel was closest to hand. The priority would be reaching a working machine quickly, and both the error contract and the classification behind it would cost more to establish than the project would live to recover.

That does not apply here because this project is deliberately establishing an architecture intended to survive incremental accuracy work. The dependency boundary, the explicit failure classification, and the migration path to a future `std::expected` are therefore part of the design rather than incidental implementation details.

The alternatives either hide recoverable failure at the call site, weaken the dependency boundary, defer a toolchain decision that this ADR does not own, separate the validity of a result from the result itself, or dissolve the condition/defect distinction by carrying both on one channel. The chosen `Result<T, E>` keeps the failure contract explicit, standard-library-only, and mechanically difficult to misuse while preserving a cheap path to `std::expected` when the toolchain permits it.

## Consequences

### The hot path is made of total functions
Rule 8 keeps `Result` out of bus accesses and instruction execution, and rule 9 forbids in-band failure sentinels. Together they say something stronger than either alone: the functions on the hot path do not fail. They are total, because the hardware they model is total, a read of any address produces something, always. Any pressure to add a failure channel there is evidence that a hardware behaviour has not been modelled, not evidence that the rule is wrong.

### Every failure site requires a classification, and the ADR supplies no default
Rule 1 provides no fallback for "unclear." A failure that resists classification is a signal that the surrounding invariant is not stated precisely enough, and the resolution is to state the invariant, not to pick the more convenient mechanism. This is a standing review question: for any new failure path, which of the two is it, and why.

### Release builds may proceed past a violated invariant
Rule 6 compiles assertions out where they would breach the performance floor, so a defect that would abort in a debug build can continue in a release build. This is accepted, and its mitigation is structural rather than defensive: where an invariant matters and cannot be asserted cheaply, the design makes its violation unrepresentable, total decoding rather than a decode failure path being the model case.

### There are two "something is wrong" mechanisms, and they must not merge
`Result` reports conditions. Principle P14 reports gaps in this emulator's model of the hardware. They are different things with different audiences, and the temptation to funnel P14's cases into an error enumeration will arrive the first time an unimplemented register is read. Rule 7 forbids it: an unimplemented behaviour surfacing as a returned error tells the caller a condition occurred, when what actually happened is that this program does not yet know what the machine does.

### `Result` is code the project owns, tests, and expects to delete
A hand-written vocabulary type carries its own unit tests, construction in both states, value and error access, correct behaviour with move-only and non-trivial payloads, and the discard diagnostic required by rule 10. That cost is accepted deliberately, and it is bounded: the type is designed to be deleted rather than maintained indefinitely.

### The error enumeration and its presentation live in different targets
Rule 4 puts message text outside the core, so an error value and the sentence describing it are maintained in separate places and can drift. The intended countermeasure is an exhaustive mapping over the enumeration, which turns an omission into a compile error rather than an empty message. Until that exists, drift is possible and is a known cost of rule 4.

### Deferred by this ADR
The diagnostic mechanism P14 relies on (how a debug build reports a modelling gap, and how a release build counts one without flooding output or breaching the performance floor) is not decided here. It is a logging and diagnostics decision that depends on the toolchain.

## Status

### Classification

**Error handling mechanism and the boundary between failures and defects:** BLOCKING ARCHITECTURAL DECISION: accepted.

### What would reopen this
- A call site demonstrating a genuine need for a `Result` member that `std::expected` does not have. That forces a choice between extending the type and abandoning the migration path, and the choice should be made deliberately rather than by adding the member.
- The toolchain ADR adopting a standard that provides `std::expected`. That supersedes the implementation named in rule 2 and the restriction in rule 3; rules 1 and 4 through 10 are unaffected and continue to govern.

### Review triggers
- The toolchain ADR, which owns the language-standard decision this ADR defers.
- The first implemented load path, which is the first real test of rule 1's classification and rule 4's enumerated errors.
- The first point at which the CI matrix can support `std::expected` across every compiler, at which point rule 2's implementation is revisited on schedule rather than under pressure.