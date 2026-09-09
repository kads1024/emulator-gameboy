# ADR 0003: Ownership and component communication

## Status summary

**Component ownership and communication model:** BLOCKING ARCHITECTURAL DECISION: accepted.

## Context

### The problem
The Game Boy is a set of cooperating parts. In code, "cooperating" is a word that invites objects to hold references to each other, and a machine of ten components with mutual references is a graph with no safe traversal order, no serialisable shape, and no way to reason about who changed what when.

This ADR decides who owns what, and by what mechanism one component's behaviour becomes visible to another.

### The hardware facts that constrain the answer
1. **Chips are wired to a bus, not to each other.** The PPU has no wire to the timer. Neither has a wire to the CPU. Every interaction between two parts of the machine passes through an address, a shared memory, an interrupt line, or the passage of time.
2. **An interrupt is a line, not a call.** A peripheral raises a level. It does not reach into the interrupt controller and set a bit, and it has no way to know whether anyone is listening.
3. **Shared memory is shared by address, not by reference.** The CPU and the PPU both touch VRAM, and neither holds a handle to the other. They are separated in time by access rules, not by ownership.
4. **The machine's state is finite, flat, and fully enumerable.** Everything that survives from one cycle to the next lives in a register or a memory cell. There is no hidden linkage.

### What makes this decision expensive to revisit
Ownership is threaded through every constructor, every access path, and every function that touches more than one component. It also determines whether the machine's state can be serialised field by field, which the save-state requirements demand. Changing the ownership model after peripherals exist means touching all of them at once.

### Interaction with ADR 0002
ADR 0002 rule 6 requires that exactly one caller may reach the timed bus entry points. That invariant is only enforceable if components cannot reach the bus at all. Ownership is therefore not an independent concern: it is what makes the timing model's central invariant mechanically true rather than a convention that has to be remembered.

### Out of scope for this ADR
The exact grouping of components beneath the bus, the mechanism by which OAM DMA moves its bytes (deferred by ADR 0002), and the save-state serialisation format.

## Decision
**1. Ownership is a two-level tree.** The root object owns the CPU and the bus. The bus owns the peripherals and the memories. Ownership lives in the root; no component allocates or owns another.
**2. No component stores a pointer or reference to another component, to the bus, or to the system root.** Not as a member, not as a cached handle, not indirectly through a callback holding one.
**3. Components communicate through values, explicit parameters, return values, and state exposed to their owner.** A component's public surface is what its owner can read and write, plus what it does when time advances.
**4. Interrupt requests are lines, not writes.** A peripheral exposes a line level as state. The interrupt controller samples lines, performs edge detection, and latches `IF`. No peripheral writes `IF`.
**5. Components are state, plus behaviour over that state and explicitly supplied dependencies.** A component never acquires a dependency by reaching for it.
**6. Ownership is by value.** `shared_ptr` is forbidden in the core. `unique_ptr` is used only where a demonstrated ownership or polymorphism requirement exists, and the requirement is written down where the type is introduced.
**7. Work spanning two components is performed by their nearest common owner.** When one component's output must reach another, the owner moves it. Neither component learns of the other's existence.
**8. No component may reach the timed bus entry points.** This is the ownership consequence that makes ADR 0002 rule 6 enforceable rather than aspirational.
**9. Test configurations use test-oriented component implementations, not interfaces introduced for mocking.** No abstraction exists in the production design solely so that a test can substitute something.

## Alternatives considered

### Alternative 1: Back-references
Each component holds a reference to the bus or to whichever sibling components it needs. This is attractive because the first few components can call each other directly: the CPU can ask the bus for memory, a peripheral can signal the interrupt controller, and there is little routing code.

The mechanical failure appears when the machine is serialised. The object graph is no longer a tree: the serialiser cannot simply walk ownership edges because a component may point back to an ancestor or sideways to a sibling. It must either track object identity and detect cycles or maintain special knowledge of which references are ownership and which are merely links. That is additional machinery around a state that is otherwise fully enumerable by value.

The obvious reply is that the back-references need not be serialised at all: they are structure rather than state, and can be rebuilt during construction when a state is loaded. That reply is correct, but reconstruction relocates the cost rather than removing it. Every component added from then on carries a fixup site that must be remembered at load time; a forgotten fixup produces a dangling reference or a silent alias rather than a compile error; and the correctness of save states becomes a property of a checklist maintained by hand rather than a property of the type system. Serialisation is therefore the supporting argument against this alternative, not the decisive one.

More importantly, a back-reference to the bus makes ADR 0002 rule 6 unenforceable. A component can directly invoke a timed bus entry point, so the compiler cannot prevent a second caller from advancing the clock and then performing the access. The resulting runtime symptom is that one instruction can advance the machine twice for a single logical access, causing later CPU, timer, PPU, or interrupt state to appear one M-cycle out of phase.

### Alternative 2: Shared ownership
Components are held through `shared_ptr`, allowing the object graph to retain whichever references are convenient. This is attractive because lifetime management appears automatic: a component can keep another component alive without deciding which object owns it.

The mechanical failure is that the resulting graph is not a serialization graph. `shared_ptr` represents lifetime relationships, not the machine's state, so a field-by-field serialiser cannot follow every pointer as state without either duplicating shared objects or maintaining an identity table to avoid writing the same state more than once. Cycles also require special handling. The lifetime mechanism therefore becomes part of the save-state traversal even though ownership itself is supposed to be a fixed property of the machine.

Shared ownership also does not prevent components from retaining a `shared_ptr` to the bus. Once they have that pointer, the timed bus entry points are reachable from multiple callers and ADR 0002 rule 6 cannot be mechanically enforced. The runtime failure is the same class of double-ticking: an access path advances time outside the single machine-level access sequence and the observable state drifts out of phase.

### Alternative 3: Callback registration
Components register callbacks with the components that need to react to them. This is genuinely pleasant for the first few components because the producer does not need to know the consumer's concrete type beyond the callback contract. An interrupt-producing peripheral, for example, can register a notification without carrying an explicit reference to the interrupt controller.

The mechanical failure is that the machine's communication topology moves into runtime registration state. A field-by-field serialiser cannot reconstruct the machine solely by walking component state because the callbacks are executable relationships rather than serialisable values. It must separately know which callbacks exist, in what order they were registered, and how to rebuild them after loading a state. This is the failure `docs/architecture.md` P12 names directly: state living only in a lambda capture is state that is not reachable from the machine root, and P12 already records it as a review failure.

Callbacks also provide an indirect path to the bus. A callback invoked by a component can perform a bus access or cause another callback to do so, so the compiler cannot establish that the timed bus entry points have exactly one caller. The runtime failure is an access occurring from inside a notification path, potentially advancing the clock in the middle of another component's operation rather than at the machine's defined access boundary.

### Alternative 4: Global state
The machine's components are globals or singletons, allowing any component to reach any other component without carrying references. This is the simplest model for the first few components: there is no construction graph and no routing code, and a component can immediately access whatever machine state it needs.

The mechanical failure is that there is no machine instance to traverse independently. A field-by-field serialiser cannot represent two machines' states separately because the state being serialised is process-global. Running two independent Game Boy instances in the same process therefore requires duplicating or virtualising the globals, defeating the model.

Global state also makes ADR 0002 rule 6 unenforceable because any component can reach the global bus and its timed entry points. The runtime failure is that unrelated execution paths can perform timed accesses without passing through the machine's single sequencing point, producing nondeterministic or incorrectly phased state changes.

All four alternatives make communication relationships separate from ownership: components can retain, register, or globally discover paths to things they do not own. That turns the machine from a tree of state into a graph of state plus links, callbacks, or global access. The chosen model keeps ownership as the only structural relationship, which is `docs/architecture.md` P8, and makes component-to-component work explicit at their nearest common owner, leaving the machine state directly enumerable and the timed bus entry points unreachable from components.

## Consequences

### Ownership is the only structural relationship, so the machine is a tree of values
Serialising the machine means walking ownership edges and writing fields. There is no identity table, no cycle detection, no pointer fixup, and no reconstruction step on load. This is the payoff for which the four alternatives were rejected, and it is what makes the save-state requirements achievable without machinery.

### A component receives dependencies as parameters, never as members
Rule 2 forbids a component from *storing* a reference to another. It does not forbid one from *receiving* one for the duration of a call. The CPU is stepped with the bus supplied as an explicit parameter; it holds nothing between calls. This distinction is the whole of rule 3 and it is what keeps the design usable.

### Worked example: OAM DMA writing into OAM
DMA and the PPU are siblings under the bus, and OAM belongs to the PPU. Under rule 7 the DMA engine cannot write into OAM, and under rule 2 it cannot hold a handle to the PPU.

The mechanism is deferred by ADR 0002, but this ADR fixes its shape: the DMA component owns only the schedule (whether a transfer is active, its source page, and its current index) and the byte movement is performed by the nearest common owner, which reads the source through the component access path and writes the destination through the PPU's component access path. Neither component learns the other exists.

This also matches the hardware: the DMA controller is a bus master, and OAM is a device at the other end of the transfer. Nothing on the real machine gives the DMA unit a private channel to the PPU either.

### Worked example: the APU's frame sequencer and the timer's counter
The APU's frame sequencer is clocked by a bit of the same internal counter the timer exposes as `DIV`. Two siblings, one genuinely dependent on the other's internal state, with a coupling that is documented hardware behaviour rather than an implementation artefact.

Rule 7 says the owner mediates. But the first tool is not mediation, it is to ask whether the ownership assignment is right. The counter that drives both the timer's increments and the sequencer's steps is one counter in hardware; if it is modelled as state owned by whichever component the owner can feed to both, the coupling stops being a sibling interaction at all. The same reasoning that showed VRAM belongs to the PPU applies here.

This is recorded as the first real test of rule 7, to be settled at the milestone that implements the APU, with ownership reassignment tried before mediation and mediation tried before amending this ADR.

### Worked example: interrupt dispatch reading pending state
The CPU must know whether `IE & IF` is non-zero in order to decide whether to dispatch, and that decision is not itself a memory access performed by the program. The CPU therefore asks the bus it was handed as a parameter, through a named untimed query the bus exposes for exactly this question. The bus answers it by reading the interrupt controller it owns, which is rule 7: the owner mediates. It is not a timed read, it does not advance the clock, and it does not require the CPU to hold anything.

The distinction is worth stating because `docs/architecture.md` P5 and ADR 0004 (bus contract) rule 5 both reserve the generic component access path for owners acting on behalf of components they own, and the CPU owns nothing. The CPU calls a query; the bus uses the component path internally to answer it.

The `IE` and `IF` registers remain readable and writable by the program through the ordinary timed path at their addresses. The two paths coexist because they are different kinds of access, which is the distinction principle P5 exists to preserve.

### The owner accumulates code, and that is the cost
Work that "belongs" to a component sometimes lives in its owner. The bus in particular becomes a substantial object: it owns the peripherals, routes accesses, applies access rules, and mediates cross-component work. This is accepted.

The tripwire that distinguishes an acceptable owner from a broken design: **the owner may contain routing, sequencing, and mediation. It may not contain peripheral behaviour.** If logic describing what a peripheral *does* migrates into the owner, the ownership assignment is wrong and the fix is to move the state, not to relax rule 7.

### Independent machine instances are free
No global state and no singletons means a process can hold many machines at once. The test harness can construct one machine per test case and run the suite in parallel without contention, which matters for a per-opcode suite of the size the CPU milestone depends on.

### Value ownership makes an in-process snapshot trivial, which is not the save-state format
Because components are owned by value, copying the root object copies the machine. This is useful for rewind and for test harnesses that need a checkpoint. It is not the save-state format: the on-disk format remains explicit, field-by-field, and versioned, and never a raw object representation.

### No virtual dispatch in the ownership tree
Components are concrete members of their owner. Calls through the tree are direct and inlinable, which matters because the advance mechanism named in ADR 0002 is the hottest path in the emulator.

## Status

### Classification
**Component ownership and communication model:** BLOCKING ARCHITECTURAL DECISION: accepted.

### What would reopen this

Not taste, and not local awkwardness. This model is reopened by the discovery of a hardware behaviour requiring two sibling components to observe each other *within* a single advance, in a manner their common owner cannot mediate, a genuine mutual dependency rather than a one-directional one.

Before any such finding amends this ADR, two cheaper remedies are tried in order: reassign the ownership so the interacting state has a single owner, then mediate at the nearest common owner.

### Review triggers
- The milestone that implements OAM DMA, which exercises owner-mediated byte movement for the first time.
- The milestone that implements the APU, which is the first genuine sibling coupling in the machine.

At each, this ADR is either confirmed or amended with the specific behaviour that defeated it.