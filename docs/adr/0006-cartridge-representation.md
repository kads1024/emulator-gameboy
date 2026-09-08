# ADR 0006: Cartridge representation

## Status summary 
- **Cartridge structure and the cached-offset read path:** BLOCKING ARCHITECTURAL DECISION: accepted.
- **Closed variant as the mapper representation:** PROVISIONAL: adjudication mechanism recorded in the Status section.

## Context

### The problem
A cartridge holds up to 8 MB of ROM. The CPU can name 32 KB of it at a time. Between them sits a chip whose entire job is to decide which bytes are currently visible.

How that chip is represented determines the shape of the most frequently executed read in the emulator: while a program runs from ROM, every instruction fetch and every immediate operand passes through it.

### The hardware facts that constrain the answer
1. **The mapper is a latch, not a computation.** Writes into the ROM address range do not store data; they set registers inside the cartridge. Those registers drive the ROM chip's upper address lines continuously. When the CPU reads, no decision is made by the mapper, the decision was made at the moment of the last register write, and the wires have been holding it ever since.
2. **The read is an address computation, not a dispatch.** With the bank latched, the byte the CPU receives is determined by concatenating the latched bank bits with the address bits the CPU supplied. Multiply and add, in the primer's phrasing.
3. **The mapper set is closed and fixed at load time.** A cartridge's type byte is read once from the header. No cartridge changes its mapper while running, and the set of mappers this project supports is enumerated in `docs/scope.md`.
4. **MBC3 contains a clock.** The cartridge has an input the console does not: real-world time. It is the only part of the machine that does.
5. **ROM and cartridge RAM have different lifetimes.** ROM is fixed and comes from outside the machine. Battery-backed RAM survives power-off and is part of what the player owns.

### Constraints from prior decisions
The read path is hot, per ADR 0002's consequences. The cartridge is a component owned by the bus and holds no references, per ADR 0003. Virtual dispatch requires hardware polymorphism to justify it, per principle P10. Time may not be read from the host inside the core, per principle P11. The save-state requirements distinguish what is reloaded from a file from what is captured.

### What makes this decision expensive to revisit
The shape of the read path appears in every fetch, and the split between cartridge data and mapper state determines what a save state contains and what it reconstructs.

### Out of scope
The register semantics of each individual mapper (MBC1's banking modes, RAM enable values, MBC3's latch sequence) which are implementation detail documented per mapper. The on-disk formats for battery RAM and for RTC persistence. The save-state format.

## Decision
**1. A cartridge is one component with four distinguishable parts:** a parsed header, immutable after load; the ROM bytes; the RAM bytes; and the mapper's state.
**2. Mapper state is a closed `std::variant` of small, trivially copyable structs** - one alternative per supported mapper. No inheritance, no virtual functions, no heap.
**3. The mapper's output is cached as resolved offsets.** The current ROM offsets for both windows, the current RAM offset, and whether RAM is currently accessible are stored, and are recomputed only when a mapper register changes.
**4. The read path is a masked array index using those cached offsets.** It contains no `visit`, no branch on mapper type, and no per-access recomputation. This mirrors fact 1: on hardware, a read consults latched wires, and the latching happened earlier.
**5. Writes into the mapper's register ranges dispatch through the variant once,** update that mapper's registers, and recompute the cached offsets. All mapper-specific behaviour lives on this path.
**6. Masking for undersized ROM and RAM happens when offsets are recomputed,** not on each access. A cartridge with fewer banks than its bank register can express resolves to a wrapped offset once, at write time.
**7. The cartridge consumes time through an explicit parameter,** from the first implementation, even though only MBC3 uses it and every other mapper ignores it. Time is never read from the host inside the core.
**8. Access to disabled cartridge RAM follows ADR 0004 rule 7.** The observed value is documented and sourced, not chosen for convenience.
**9. ROM bytes are supplied from outside and are not part of the save state. RAM bytes are.** The header is derived from the ROM and is reconstructed on load rather than captured.
**10. The mapper alternative is selected once, at load, from the header type byte,** and does not change for the life of the cartridge.

## Alternatives considered

This ADR departs from the primer's explicit recommendation of a polymorphic mapper. That departure is justified by the hardware model: the cartridge really does contain physically different mapper hardware, but the polymorphism is concentrated in the mapper's **state transition and address-resolution rules**, not in the representation of the cartridge's externally visible address space.

### Alternative 1: Polymorphic mapper

A base `Mapper` interface with virtual `read` and `write` operations, with one derived implementation per MBC, is a reasonable and conventional design. It accurately represents the fact that different cartridges contain different mapper hardware, and it keeps MBC-specific behaviour encapsulated behind the cartridge boundary. Adding another mapper does not require changing the cartridge's callers; it only requires another implementation.

This is also the strongest argument for the primer's recommendation. The mapper is genuine hardware polymorphism: MBC1 and MBC3 do not merely contain different data; they implement different register semantics and therefore different state transitions.

However, the polymorphism does not need to occur at every cartridge memory access. The CPU-visible address map is the same, while the mapper's state determines which physical storage an address resolves to. The selected offsets can therefore be derived when mapper state changes and then used by the ordinary cartridge access path. The hardware polymorphism remains encapsulated in the mapper while the steady-state read/write path operates on the resolved representation.

The structural cost is more significant. A polymorphic mapper normally requires the cartridge to own the mapper through indirection, such as a base-class pointer. That introduces separate mapper allocation/ownership and means the cartridge's state is no longer necessarily contained entirely within the root machine object. This conflicts with **ADR 0003's Rule 1: copying the root machine object must copy the entire machine state**. A shallow copy of the root object would copy the pointer rather than the mapper object, producing shared mapper state rather than an independent machine.

A function-pointer table has essentially the same structural tradeoff: it preserves runtime polymorphism but still introduces indirect ownership/state outside the value-contained machine object.

**Rejected:** although this is a sound design and the primer's recommendation, its runtime-polymorphic ownership model conflicts with the project's value-semantics requirement for the machine root. The hardware polymorphism can instead be represented by a closed value-owned variant.

### Alternative 2: Per-access variant visit

The cartridge can store the mapper as a closed variant and visit it on every `read` and `write`. This preserves value semantics and avoids heap ownership, while making the mapper implementations explicit and exhaustive.

The weakness is not that `visit` must be slower than a virtual call. For a small closed set, the generated dispatch can be comparable. The problem is **when the work occurs**. Every access must redispatch into the mapper and perform the address-resolution logic, even though the relevant mapping only changes when mapper state changes.

That repeats work that can instead be performed once when the authoritative mapper register changes. The steady-state operation should be "use the mapping already derived from the current mapper state", not "re-derive which mapper behaviour applies for every access."

**Rejected:** it preserves the desired ownership model but performs mapper dispatch and resolution at the wrong frequency.

### Alternative 3: Compile-time polymorphism

The mapper can be a template parameter of the cartridge, with each MBC represented by a distinct cartridge type.

The problem is that the mapper type is not known at compile time. It is determined by the cartridge header at runtime. Therefore the runtime cartridge-loading boundary must erase that type somehow. The project would end up with either a type-erased wrapper around several concrete cartridge types or a runtime variant containing each template instantiation.

In effect, compile-time polymorphism would move the complexity rather than remove it. Each mapper-specific cartridge becomes a distinct machine-containing type, so the project must build, instantiate, and test a separate machine type for every mapper combination. This works against the goal of having one value-semantic machine representation whose cartridge behaviour varies according to runtime cartridge metadata.

**Rejected:** compile-time specialization does not match the runtime nature of cartridge selection and multiplies the number of distinct machine types the architecture must support and test.

### Alternative 4: Bank copy into a window buffer

On a bank switch, the selected 16 KB ROM bank could be copied into a fixed buffer representing the CPU-visible `0x4000–0x7FFF` window. Reads would then simply index that buffer.

This makes ordinary reads simple, but the fixed-window assumption does not hold for the hardware.

First, a far call changes the selected ROM bank and execution immediately continues from the newly mapped `0x4000–0x7FFF` region. Large games can perform such bank switches frequently, so every switch would require copying an entire 16 KB bank merely to establish the CPU-visible mapping. The cost is proportional to the window size rather than to the small state change that selected it.

Second, MBC1's mode register changes the meaning of the **fixed** `0x0000–0x3FFF` region. In one mode, the upper bank-selection bits participate in selecting the bank visible there. A single copied "switchable window" therefore cannot represent the complete mapping semantics: the supposedly fixed window can itself change.

**Rejected:** bank copying turns address mapping into bulk data movement and cannot cleanly represent MBC1's mode-dependent fixed window.

### Conclusion

The chosen design therefore uses a **value-owned closed mapper variant with cached derived offsets**. The mapper variant represents the genuinely polymorphic hardware behaviour and preserves the machine's copyable value semantics. Mapper state changes recompute the address mapping once; ordinary accesses consume that derived mapping without redispatching the mapper.

This is a deliberate departure from the primer's polymorphic-interface recommendation, not a claim that polymorphic mappers are inherently inferior. The distinction is that the hardware requires **polymorphic state-transition behaviour**, while the steady-state cartridge access path does not require polymorphic dispatch on every access.
