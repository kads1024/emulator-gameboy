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