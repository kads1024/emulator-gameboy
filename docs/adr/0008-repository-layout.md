# ADR 0008: Repository layout and target boundaries

## Status summary

- **Target boundaries and the dependency direction between them:** BLOCKING ARCHITECTURAL DECISION: accepted.
- **Everything else about layout:** IMPLEMENTATION DETAIL, and explicitly not a review topic.

## Context

### The problem

Repository layout is usually a matter of taste, and treating it as an architectural question wastes time. One aspect of it is not: the core's dependency boundary is a rule the build enforces, and a rule the build enforces needs a boundary the build can see.

This ADR decides the target boundaries, the direction of dependency between them, and where a file may live. It deliberately decides nothing else.

### What constrains the answer

1. **The core links only the standard library, and the build fails otherwise.** The check in ADR 0001 (toolchain) B12 asserts that the core target resolves to no link dependencies. That assertion needs a target to make it about.
2. **The core performs no I/O.** It accepts bytes and input state and emits shade indices and audio samples. Reading files is the job of whatever sits above it.
3. **The project ships more than the core.** A headless runner, a debugger, and a frontend with video, audio, input and frame pacing are all in scope, and each has dependencies the core may not acquire.
4. **Tests link a framework the core must not.** ADR 0001 B18 requires the framework to reach the tests and never the core.
5. **Tests need the same visibility the core has.** ADR 0003 (ownership) rule 9 has tests constructing test-oriented components against concrete types rather than through interfaces introduced for mocking, which means the test target legitimately sees more of the core than a consumer would.
6. **Fetched artifacts are never committed.** `docs/scope.md` section 7 keeps test ROMs out of the repository, and ADR 0001 B17 fetches the test framework at configure time.

### Out of scope

Directory naming inside a target, file granularity, nesting depth, and the contents of the build files themselves.

## Decision

**1. Four build targets, with one-way dependency.**

| Target | May depend on | Purpose |
|---|---|---|
| core | the standard library, and nothing else | the emulated machine |
| tools | core, standard library, third-party as needed | headless runner, debugger, trace and ROM utilities |
| frontend | core, standard library, I/O libraries | video, audio, input, frame pacing |
| tests | core, tools, the test framework | every automated check |

Dependency runs one way. Nothing the core depends on may reference anything above it, and `tools` and `frontend` do not depend on each other.

**2. The core's dependency set is empty and is asserted, not assumed.** This is ADR 0001 B12; this ADR exists so that assertion has a well-defined subject.

**3. A file's target is determined by the directory it is in.** One top-level directory per target, named for it: `core/`, `tools/`, `frontend/`, `tests/`. No file belongs to two targets, and no target's build reaches into another target's directory for sources.

The purpose of this rule is visibility rather than tidiness: a file added to the wrong place is visible in the diff, before CI runs, without anyone needing to remember which rule it violates.

**4. Core headers live beside core sources. There is no public/private include split.** The consumable interface of the core is defined by its CMake target's usage requirements, not by which directory a header sits in.

The reason is constraint 5: the test target legitimately needs the visibility a public/private split would deny it. A split that the tests must bypass makes the "public" set a fiction, and a split that the tests honour makes the tests unable to construct the machine the way ADR 0003 rule 9 requires.

**5. Test-oriented components live in the test target, never in the core.** A component that exists so a test can drive something is test code, and its presence in the core would be the test-only architecture `docs/scope.md` and ADR 0003 rule 9 exclude.

**6. Fetched artifacts never land in a source directory.** The test framework is fetched into the build tree at configure time. Test ROMs land in a location that is gitignored and outside every target's source directory.

**7. Documentation lives in `docs/`, with decision records in `docs/adr/`.** Already true; recorded so it stays true.

**8. Everything else about layout is implementation detail.** How files are named, how deeply they nest, and how a target's sources are grouped internally are decided while implementing. They are not a review topic and they do not require an ADR to change.