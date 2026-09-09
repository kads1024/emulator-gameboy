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

## Alternatives considered

### Alternative 1: A single target

A single target would simplify the initial project setup, but it would destroy the architectural boundary that ADR 0001 B12 is intended to enforce. The first check (that the core resolves to no link dependencies) would no longer have a distinct target to inspect, so the core could silently acquire third-party or platform dependencies while still producing a successful build.

That loss propagates downstream. The dependency direction between core and the rest of the system would no longer be mechanically enforceable; the frontend could become a dependency of code that should remain platform-independent; and the test framework could become transitively available to the core. The purity checks described in ADR 0001 Alternative 2 therefore stop being meaningful, because there is no longer a separately identifiable core boundary to check.

Those checks are what several later decisions rest on:

* ADR 0002 (timing model) assumes that advancing the machine depends only on machine state and inputs. A core that can reach platform code can advance on something else.
* ADR 0006 (cartridge) assumes real-world time enters as a parameter rather than as a call, the RTC being the machine's only host-time input. An unchecked core makes a direct clock call available anywhere.
* ADR 0007 (performance floor) assumes the measured workload is deterministic. Without that, run-to-run variation can no longer be attributed to host noise, and the gate stops separating regressions from scheduling.
* The save-state requirements assume complete machine state with no hidden external dependencies. Any acquired dependency that holds state is state the save file does not contain.

None of these fail at the moment the boundary is lost. They fail later, as a timing bug, a benchmark that will not settle, or a save state that does not restore, with no build failure to connect any of them back to the layout. That is what makes target structure an architectural question rather than a cosmetic one.

### Alternative 2: A public/private include split

A conventional `include/<project>/` and `src/` split would make the intended external API visually obvious and protect consumers from depending on implementation details. It was rejected because this repository has no external consumer boundary: tools and frontend are in-repository consumers, while tests intentionally require visibility of concrete core types under ADR 0003 rule 9.

The decision would flip if the core becomes a separately consumed library with external consumers whose dependency on internal headers needs to be prevented.

### Alternative 3: Separate repositories

Separate repositories would weaken the atomicity of changes that cross the core, tools, frontend, and tests. A bus-contract change and its corresponding tests could no longer be reviewed as one repository diff or validated by one CI invocation against one commit. When a regression appears months later, `git bisect` would also lose its ability to identify the offending cross-component change as a single repository history event; the investigation would require correlating histories across repositories.

This is a mechanical cost, not merely a workflow preference.

A reasonable solo engineer starting this repository would pick the single target, since it is the lowest-friction start and nothing in an empty repository is yet leaning on the boundary it removes. The chosen four-target layout therefore costs more initial structure than a solo project strictly needs: four targets must be configured before the emulator exists, and genuinely shared code that belongs to neither a target nor the core has no automatic home. That cost is accepted because the targets make the architectural dependency boundaries explicit and mechanically enforceable. Internal file organization remains implementation detail and can be changed without revisiting this ADR.

## Consequences

### The purity assertion has a subject

ADR 0001 (toolchain) B12's first check asserts that a target resolves to no link dependencies. This layout is what makes "a target" well defined. The check and this ADR are two halves of one mechanism, and neither is useful alone.

### A misplaced file is visible before CI runs

Rule 3 ties a file's target to its directory, so a source file that has drifted across a boundary appears in the diff as a path, not as a build failure ten minutes later. This is the cheapest form of enforcement available and it costs nothing to maintain.

### The tests see everything, so the discipline moves to the test target

Rule 4 gives the test target full visibility of the core, which is what ADR 0003 (ownership) rule 9 requires. The risk that comes with it is core code shaped by test convenience rather than by hardware. The tripwire: a type or accessor in the core that exists only because a test needed it. Rule 5 is the answer, and the fix is to move the thing into the test target rather than to justify its presence in the core.

### Code shared by two targets and belonging to neither has no home, deliberately

If the tools and the frontend both need something that is not part of the machine, this layout offers nowhere obvious to put it. That is intentional. The answer is to leave it duplicated until a third user justifies a target of its own, rather than to create a utility target on first contact. A shared-utility target added early accumulates everything that is awkward to place, and its dependency set is the one nobody watches.

### The frontend can grow without touching the core's dependency set

Because dependency runs one way, adding a graphics or audio library to the frontend cannot alter what the core links. The purity assertion stays trivially true as the frontend acquires whatever it needs, which is what makes the frontend's dependencies a non-issue rather than a standing risk.

### Four targets exist before any emulator code does

The configuration cost is paid up front, before there is anything to run. This is accepted for the same reason the CI guards are built before the code they guard: a boundary introduced after the code exists is a boundary that already has violations.

## Status

### Classification
- **Target boundaries and the dependency direction between them:** BLOCKING ARCHITECTURAL DECISION: accepted.
- **Everything else about layout:** IMPLEMENTATION DETAIL. Changing it requires no ADR and is not a review topic.

### What would reopen the include-split decision

The core acquiring a consumer outside this repository. Rule 4 rests on there being no external boundary to protect and on the test target needing full visibility; an external consumer changes the first of those and the tradeoff flips. Until that happens, the split is not designed for preemptively.

### What would reopen the target set

A product-level change that introduces a second machine-level artefact, not a new tool or a second frontend, both of which fit the existing set, but something that is neither the machine nor a consumer of it.

### Review triggers

- The build setup step, when the targets are created and the purity assertion is wired to the core target for the first time.
- The first time code appears that plausibly belongs to two targets and to neither, which tests whether the duplication rule survives contact