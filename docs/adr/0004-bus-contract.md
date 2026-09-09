# ADR 0004: Bus contract

## Status summary

**Bus contract: regions, access paths, and permission semantics:** BLOCKING ARCHITECTURAL DECISION: accepted.

## Context

### The problem
The CPU can name 65,536 addresses. Behind those names sit ROM, several RAMs, a set of peripheral registers, one region that responds to nothing, and one region that is an accident of wiring. Something must decide who answers a given address, what happens when nobody does, and what happens when the responder is busy.

That decider is the bus. Because of ADR 0002 it also advances the clock, and because of ADR 0003 it owns the peripherals it routes to. This ADR fixes what it decodes, what each access path guarantees, and what an access observes when the machine declines to answer.

### The hardware facts that constrain the answer
1. **The address space is a set of names, not a block of storage.** Which chip responds to an address is determined by decoding logic. Two addresses that look adjacent may reach entirely different silicon, and some addresses reach nothing at all.
2. **Only one device drives the data lines at a time.** When no device is driving them during a read, the CPU still latches something. That value is not "zero"; it is whatever the electrical state of the bus produces. An emulator that returns a convenient constant is inventing a behaviour rather than modelling one.
3. **Echo RAM is not a feature.** It is the visible consequence of incomplete address decoding: the work RAM chip is selected across a wider range of addresses than its size requires, so the same storage answers to two sets of names. Nintendo documented the region as prohibited precisely because it was an artefact.
4. **Access permission is temporal, not spatial.** VRAM and OAM are readable at some moments and not others, depending on what the PPU is doing. The same address is legal and illegal at different points in the same frame.
5. **The boot ROM is a decode override.** At power-on it overlays the bottom of the address space; after the program writes the disable latch it is gone until the next reset, and the cartridge's bytes are visible underneath.
6. **HRAM is inside the CPU chip.** It is reachable when the external bus is occupied, which is why the DMA idle routine can execute from it. It is not simply "fast RAM."

### What makes this decision expensive to revisit
Every access in the emulator passes through this contract: the CPU's, every peripheral's on behalf of its owner, the debugger's, the trace writer's, and every test harness's. Its signatures and its guarantees appear in more call sites than anything else in the project, and `docs/scope.md` section 8 names the bus contract as one of the two things that must never be rewritten under force.

### Relationship to prior ADRs
ADR 0002 fixes *when* time advances and that exactly one caller may reach the timed entry points. ADR 0003 fixes who owns the components being routed to and that cross-component work is performed by the owner. This ADR fixes *what is decoded, by whom it may be accessed, and what an access returns*. It does not restate the timing rules.

### Out of scope for this ADR
The behaviour of individual I/O registers, which belongs to each peripheral. Cartridge mapping behaviour, which belongs to ADR 0006. The mechanism of DMA byte movement and of DMA bus conflict, both deferred by ADR 0002. The save-state format.

## Decision

**1. The bus is the sole address decoder.** One routing function maps an address to its responder. No component decodes addresses, and no call site bypasses routing to reach storage directly.

**2. Decoding is total.** Every address in `$0000`–`$FFFF` belongs to exactly one region. There is no default case that quietly absorbs unmatched addresses; an address that reaches no responder does so because a region says it reaches no responder.

**3. The region map is the contract.**
| Range | Region | Responder |
|---|---|---|
| `$0000`–`$3FFF` | ROM bank 0 | cartridge |
| `$4000`–`$7FFF` | ROM, switchable | cartridge |
| `$8000`–`$9FFF` | VRAM | PPU |
| `$A000`–`$BFFF` | External RAM | cartridge |
| `$C000`–`$DFFF` | WRAM | WRAM |
| `$E000`–`$FDFF` | Echo RAM | WRAM, mirroring `$C000`–`$DDFF` |
| `$FE00`–`$FE9F` | OAM | PPU |
| `$FEA0`–`$FEFF` | Prohibited | no responder |
| `$FF00`–`$FF7F` | I/O registers | the addressed peripheral |
| `$FF80`–`$FFFE` | HRAM | HRAM |
| `$FFFF` | IE | interrupt controller |

Region boundaries are named constants, never literals, per `docs/scope.md` section 4 accommodation 2.

**4. Echo RAM is decode, not duplication.** The region exists because the work RAM's selection logic ignores A13: the same 8 KiB answers across $E000–$FFFF as well as at $C000–$DFFF. Only the first 7,680 bytes of that mirror are ever observable, because OAM, the I/O registers, HRAM, and IE are decoded ahead of WRAM and claim the addresses at which the last 512 bytes would otherwise have appeared. The echo region resolves to the same storage as the region it mirrors. There is no second array and no copying. A write through one set of names is observable through the other because they are the same bytes.

**5. Three access paths exist, with these guarantees:**
| | CPU path | Component path | Debug path |
|---|---|---|---|
| Advances the clock | yes | no | no |
| Enforces access permission | yes | no | no |
| Triggers side effects | yes | as required by the operation | never |
| Callable by | the CPU only | owners, on behalf of components | tooling only |

These three names (**CPU path**, **component path**, **debug path**) are the canonical ones. Where other documents say "the timed path" or "the timed entry points," they mean the CPU path; there is no fourth path and no other timed one.

"Tooling," in the debug path's row, includes the test target. A test asserting the contents of memory without perturbing the machine is doing exactly what the debug path exists for, and reading through the CPU path instead would advance the clock and make the assertion measure something other than what it names.

The bus may additionally expose *named untimed queries* answering one specific question about a component it owns, such as whether an interrupt is pending. A query of that kind is owner-mediated work under ADR 0003 (ownership) rule 7: the caller names what it needs, the bus reads its own component to answer, and the generic component path stays reserved for owners. This is how the CPU learns of pending interrupts without a timed access and without owning anything, as ADR 0003 records.

**6. Access permission is queried from the owner of the resource.** The bus does not reason about PPU modes; it asks the PPU. Permission logic lives with the component that owns the storage, per `docs/architecture.md` P7.

**7. A denied or unanswered read returns a documented value, never a convenient one.** For each region, the value observed when no responder drives the bus (the prohibited region, a locked resource, an unimplemented register) is sourced from hardware documentation and confirmed by test. Where the value is not yet known, principle P14 applies: the code is loud about it and the gap is recorded, rather than returning a plausible constant.

**8. A denied write is dropped, and the drop is defined per region.** Silently ignoring a write is a modelled behaviour that must be stated, not an omission.

**9. The boot ROM is an overlay on the decode, controlled by a latch.** While enabled, the overlaid range resolves to the boot image; once the latch is written, the overlay is gone until the machine is reset. The latch is one-way.

**10. The debug path never lies.** It performs no access that changes machine state, and where an address has no responder it reports that fact distinguishably rather than returning a value that looks like data. A debugger that fabricates plausible bytes is worse than one that says "nothing here."

**11. The component path performs no permission checks.** It exists precisely because the component asking is the one that owns or is authorised to touch the resource, and applying CPU-facing rules to it would be modelling a restriction the hardware does not impose.

## Alternatives considered

### Alternative 1: Flat array with special-cased I/O
A 64 KiB byte array is treated as the machine's memory, with special cases added for cartridge addresses and I/O addresses. This is attractive because it is simple, fast, easy to debug, and close to the model used by many first emulators. It is also a genuinely effective way to get real software running quickly.

The mechanical failure is that the array does not naturally model **absence of a responder** or **temporary inaccessibility**. Those cases become additional address-specific conditionals layered around the array. Echo RAM can be implemented without duplicated storage by transforming the address before indexing, but once address decoding and device-specific behaviour are required around the array, the design is no longer meaningfully "flat." The special cases become an increasingly large second memory model.

This also conflicts with the principle that bus behaviour, rather than individual consumers, owns address decoding and access semantics (Rule 1).

### Alternative 2: Runtime device registry
Components register the address ranges they claim, and each access resolves the responder through the registry.

This represents unmapped addresses naturally: no registered range matches. Temporary inaccessibility can also be represented by a registered responder declining the access or by changing the active mapping. Echo RAM does not require duplicated storage either, since the selected device can normalize the address before accessing its underlying storage.

The mechanical failure is that registration moves the machine's topology into runtime state. Which component answers which address becomes data established by a sequence of registration calls rather than structure fixed by the design. A field-by-field serialiser can then no longer reconstruct the machine from component state alone: it must also know what was registered, by whom, and in what order. That is P12.

This is the same failure mode as the callback alternative rejected in ADR 0003, wearing a different disguise. The two designs look unrelated (one dispatches on address, the other on event) but both establish at runtime a relationship the hardware fixes at design time, and both defeat reconstruction from component state for the same reason. A principle that catches two superficially unrelated designs is a real constraint rather than a stylistic preference, which is why the correspondence is worth stating rather than leaving for the reader to notice.

Secondarily, the registry introduces dynamism into a machine whose memory map is fixed and known in advance. That is an abstraction with no hardware counterpart, which is P10.

The obvious rebuttal is that the usual objection to a registry (that resolution costs runtime work on every access) is easily answered: index a 256-entry page table by the high byte of the address and resolution becomes a single array lookup, no worse than the flat array. That rebuttal is correct, and it is why the rejection above does not rest on resolution cost. The page table still has to be populated, and populating it is registration. The topology remains established at runtime, and the serialisation problem is unchanged.

### Alternative 3: Decode in the CPU
The CPU determines which component owns an address and calls that component directly, with no bus object.

This can be straightforward and fast for a CPU-centric emulator, and it makes the access path explicit at each call site.

The mechanical failure is that address decoding becomes a CPU responsibility. Non-CPU components that need bus accesses must either duplicate the decoding logic or route those accesses through some other mechanism. The memory map therefore becomes distributed rather than having one authoritative decoder.

This directly conflicts with the rule that **address decoding belongs to the bus, not to the component performing the access** (Rule 1). It is also structurally unavailable under ADR 0003: a CPU that decodes must be able to reach every peripheral it might address, which means holding handles to components it does not own, and ADR 0003's Rule 2 forbids exactly that. Separately, it makes the access mechanism harder to use as the common synchronization point required by ADR 0002.

### Alternative 4: Polymorphic region objects
Each memory region derives from a common interface providing virtual `read` and `write` operations, and the bus holds a collection of those regions.

This models different responders cleanly and can represent unmapped addresses by having no matching region. Temporary inaccessibility can be represented by a region refusing an access or by its availability changing.

Echo RAM can be implemented without duplicated storage if the echo region forwards or translates its address to the underlying WRAM storage. However, every access requires region lookup followed by an indirect or virtual call.

The mechanical failure is therefore on the hottest path: every bus access pays for region dispatch, while ADR 0002 makes the bus access/advance mechanism a central synchronization point that is already exercised extremely frequently. Virtual dispatch and dynamic region resolution add overhead precisely where the architecture requires a cheap, predictable operation.

### Steel-man: why the flat array still wins initially
Alternative 1 is genuinely the fastest route to a machine that boots. A byte array plus a handful of special cases is easy to implement, has excellent locality, and avoids building an abstraction before there is enough emulator behaviour to justify it. That is why many successful emulators use some variation of it.

Its cost arrives later because the shortcuts accumulate as address-specific exceptions. Echoes, unmapped addresses, temporarily inaccessible resources, cartridge mapping, and device ownership all become special cases around what was originally supposed to be a simple array. By the time accurate timing and bus-visible behaviour matter, the emulator has to disentangle those assumptions or duplicate the memory model.

### What the alternatives have in common
All four alternatives make an important part of the machine model implicit in some other mechanism: array special cases, runtime registration state, CPU-owned decoding, or polymorphic dispatch. The chosen contract instead makes the **bus the explicit authority for address decoding and access**, while keeping the access path compatible with ADR 0002's timing mechanism. That makes the architectural cost visible early rather than allowing it to emerge later as scattered special cases.

## Consequences

### The memory map exists in exactly one place
Adding a region, changing a permission rule, or correcting a decode boundary is an edit to one function and one table. No component, tool, or test contains a second copy of the map, and there is no call site that can drift from it. This is the payoff for which the four alternatives were rejected.

### Rule 7 creates research debt, not implementation debt
The contract requires that every unanswered or denied read return a documented value. The values themselves are not yet known: the prohibited region's behaviour, what a locked VRAM or OAM read returns, and the read-back of unimplemented I/O bits all have to be sourced from hardware documentation and confirmed by test at the milestone that implements each region. Some of them may be mode-dependent.

Until each value is sourced, principle P14 applies: the code is loud, and the gap is visible. A plausible constant returned quietly is a defect under this contract, not a placeholder. These are expected to be among the first entries in `docs/known-shortcuts.md`, and each is retired by citing a source and a passing test, not by someone deciding a value looks right.

### Echo RAM's truncation falls out of decode order
The last 512 bytes of work RAM have no echo name, and this requires no special rule. The incomplete decoding would mirror the full region, but OAM, the I/O registers, HRAM, and `IE` claim the addresses where the remainder would have appeared, and they win. Anything in the implementation that handles this as a special case is modelling the symptom rather than the mechanism.

### The PPU sits on the CPU's read path
Every CPU access to VRAM or OAM asks the PPU whether the access is permitted, per rule 6. That query is on the hottest path in the emulator, alongside the advance mechanism named in ADR 0002. It must be a cheap examination of already-computed state, not a recomputation, not a virtual call, and not a search.

### The debug path cannot return a plain byte
Rule 10 requires the debug path to distinguish "no responder" from data. A read that can only return a byte cannot express that distinction, so the debug read's result is a value that may be absent, and every consumer (the debugger, the memory viewer, the trace writer, the disassembler) handles absence explicitly.

This is the first place in the project where an API shape is dictated by an accuracy principle rather than by convenience, and it is deliberate: a debugger that invents plausible bytes for unmapped addresses will eventually cost more hours than the branch costs to write.

### The boot ROM overlay is machine state, and the image is not
The overlay latch is part of the machine's state and is saved and restored with it. The boot image itself is not: like cartridge ROM, it is supplied from outside and reattached on load. A state captured while the overlay is active therefore restores correctly only when the same boot image is supplied, and the save-state design must say so rather than discovering it.

### Open question: the CPU test harness and the region map
The SM83 per-opcode suite supplies arbitrary memory contents across the address space and expects reads and writes to behave uniformly. This contract makes the region map fixed, so uniform behaviour cannot come from bypassing the decode.

The presumed resolution, consistent with ADR 0003 rule 9, is that the harness installs test-oriented components which store and return bytes at their own addresses, leaving the map and the routing untouched. Whether that covers every address the suite exercises (the prohibited region in particular, which by rule 2 has no responder at all) is not known until the suite is fetched and examined.

This is recorded as an open question to be settled when the CPU test harness is built. It is not settled by relaxing the contract, and no test-only path through the bus is introduced.

### Deferred by this ADR
- **What the CPU observes during an OAM DMA transfer.** Deferred by ADR 0002, and constrained by this one: it is a question about responders and permission, and its answer is expressed within this contract rather than as a special case inside the CPU.
- **The behaviour of individual I/O registers,** which belongs to each peripheral.
- **Cartridge mapping behaviour,** which belongs to ADR 0006.

## Status

### Classification

**Bus contract: regions, access paths, and permission semantics:** BLOCKING ARCHITECTURAL DECISION: accepted.

### What would reopen this
The discovery of a hardware behaviour that cannot be expressed as *address → region → responder → permission → value*: specifically, a case where what answers an address depends on something other than the address and the state of the owning component.

Candidates to watch, none of which is currently believed to break the model: the CPU's view of the bus during a DMA transfer, and any behaviour where two responders drive the data lines simultaneously.

### Unresolved work items, not decision gaps
The per-region values required by rule 7 are unsourced. This is a research task with a known method, not an undecided part of the contract.

### Review triggers
- The milestone that implements VRAM and OAM locking -> the first real exercise of rule 6.
- The milestone that implements OAM DMA -> the first candidate to strain the model.
- The first time a rule 7 value must be sourced, which tests whether the discipline holds under the temptation to pick something plausible.