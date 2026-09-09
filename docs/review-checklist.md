# Review checklist
## How to use this
- It is a checklist, not a rubric. Skip the sections the diff does not touch.
- It omits everything CI enforces: purity, the warning set, formatting, clang-tidy. If a machine can decide it, a human reading a diff should not spend attention on it. Finding yourself checking something here that CI could check is a signal to move it into CI.
- Cite by number *and* subject: "ADR 0003 (ownership) rule 6", "P8". A wrong number is visible the moment the subject does not match it.
- "Looks good" is not a review.

## Every diff
1. Does this introduce a deviation from hardware behaviour? If so, which `docs/known-shortcuts.md` entry covers it, and does that entry have a removal condition? (P15)
2. Does it add a failure path? Is it a *condition* or a *defect*, and does the mechanism match the classification? (ADR 0005 (error handling) rule 1)
3. Does it encounter behaviour this emulator does not model? Is that loud rather than plausible? (P14)
4. Does it add behaviour a machine cannot check? A subsystem is done when a test decides it is, not when it looks right. (P16)
5. Is anything here justified by "we might need it later" or by Game Boy Color? (P17, `docs/scope.md` section 4)

## Time and the bus
6. Cycle arithmetic inside an opcode, or a second place that advances time? (P1, P3)
7. Tick before access, with internal cycles explicit and unbatched? (P2, ADR 0002 (timing model) rules 3 and 5)
8. A duration table consulted at runtime, or an opcode reporting a cycle count? (P3, ADR 0002 rule 8)
9. Any non-CPU call site of a timed entry point? (P5, ADR 0002 rule 6)
10. A debug, trace, or disassembly path performing a timed or side-effecting access? (P5, ADR 0004 (bus contract) rule 10)
11. New address behaviour: is it in the region map, or is this a second decoder? (P4, ADR 0004 rules 1 and 2)
12. An I/O register backed by plain storage, or read-back behaviour not modelled? (P6)
13. Permission logic in the bus rather than in the component that owns the resource? (P7, ADR 0004 rule 6)
14. A denied or unanswered read returning a convenient value rather than a sourced one? (ADR 0004 rule 7)

## Components and ownership
15. A member pointer or reference to another component, to the bus, or to the root? (P8, ADR 0003 (ownership) rule 2)
16. `shared_ptr` anywhere, or `unique_ptr` without a written justification at the point it is introduced? (ADR 0003 rule 6)
17. A peripheral writing `IF`, or performing its own edge detection? (P9, ADR 0003 rule 4)
18. Cross-component work performed by the components rather than by their owner? (ADR 0003 rule 7)
19. A new abstract base or virtual call: is the hardware polymorphic here, or is this for testing? (P10, ADR 0003 rule 9)
20. New state: reachable from the root, expressible as plain data, nameable by a field-by-field serializer? Any `static`, or state living in a capture? (P12)

## Targets and layout
21. Is every added file in the target directory its content belongs to? A boundary crossing is visible as a path in the diff. (ADR 0008 (layout) rule 3)
22. Does the core gain a type, accessor, or component that exists because a test needed it? It belongs in the test target. (ADR 0008 rule 5, P10)

## Integers
23. A cast with an operator inside it? (ADR 0001 (toolchain) B8, B9)
24. Narrowing that models hardware arithmetic, written as a cast instead of a named operation? (ADR 0001 B6, B7)
25. A new accessor or decoder returning `int` rather than `u8` or `u16`? (ADR 0001 B4)

## Cartridge
26. Anything on the read path that branches on mapper type or re-derives the mapping? (ADR 0006 (cartridge) rules 4 and 5)
27. Mapper-specific behaviour outside the functions operating on that mapper's own variant alternative? (ADR 0006 rule 5)
28. Derived state written into a save state rather than recomputed on load? (ADR 0006 rule 9)

## Rendering
29. RGB values in the core, or palette application outside the PPU? (P13, `docs/scope.md` section 6)

## Performance
30. Is the performance baseline edited? Has the cause been identified and stated? (ADR 0007 (performance floor) rules 7 and 8)
31. Allocation, I/O, or virtual dispatch introduced on the hot path? (ADR 0002 consequences)
32. Is an abstraction being rejected on speculation rather than on a measurement brought to the review? (ADR 0007)

## Drift tripwires
These are not violations. They are signals that something upstream is wrong, and the fix is upstream rather than in the diff that surfaced them.
- **Named helpers appearing in ordinary binary 8-bit arithmetic.** An interface is returning `int` somewhere. Fix the interface, do not add helpers. (ADR 0001 B4)
- **The bus acquiring peripheral behaviour.** The ownership assignment is wrong. Move the state, do not relax the rule. (ADR 0003, the owner-accumulates-code tripwire)
- **Mapper logic drifting toward the shared write path.** Same shape, same answer. (ADR 0006)
- **A `known-shortcuts.md` entry whose removal milestone slips twice.** It is becoming permanent by default. Either schedule it deliberately or promote it to `docs/scope.md` section 5 with the ADR that section's admission rule requires.

## Not review topics

- Formatting. (ADR 0001 B15)
- Whether a design would be convenient for Game Boy Color. (P17)
- Anything CI already fails the build on.