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
| `$E000`–`$FDFF` | Echo RAM | WRAM, mirroring `C000–DDFF` |
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

This also conflicts with the principle that bus behaviour, rather than individual consumers, owns address decoding and access semantics (Rule 4).

### Alternative 2: Runtime device registry
Components register the address ranges they claim, and each access searches the registry for the responder.

This represents unmapped addresses naturally: no registered range matches. Temporary inaccessibility can also be represented by a registered responder declining the access or by changing the active mapping.

The mechanical failure is that address resolution becomes runtime work on every access. The bus must search or otherwise dispatch through a dynamic collection before the actual access can occur. That adds machinery directly to the path used for every memory access, even though the memory map is largely static.

Echo RAM itself does not require duplicated storage, since the selected device can normalize the address before accessing its underlying storage. The cost is instead in the runtime resolution mechanism.

### Alternative 3: Decode in the CPU
The CPU determines which component owns an address and calls that component directly, with no bus object.

This can be straightforward and fast for a CPU-centric emulator, and it makes the access path explicit at each call site.

The mechanical failure is that address decoding becomes a CPU responsibility. Non-CPU components that need bus accesses must either duplicate the decoding logic or route those accesses through some other mechanism. The memory map therefore becomes distributed rather than having one authoritative decoder.

This directly conflicts with ADR 0003's rule that **address decoding belongs to the bus, not to the component performing the access** (Rule 1). It also makes the access mechanism harder to use as the common synchronization point required by ADR 0002.

### Alternative 4: Polymorphic region objects
Each memory region derives from a common interface providing virtual `read` and `write` operations, and the bus holds a collection of those regions.

This models different responders cleanly and can represent unmapped addresses by having no matching region. Temporary inaccessibility can be represented by a region refusing an access or by its availability changing.

Echo RAM can be implemented without duplicated storage if the echo region forwards or translates its address to the underlying WRAM storage. However, every access requires region lookup followed by an indirect or virtual call.

The mechanical failure is therefore on the hottest path: every bus access pays for region dispatch, while ADR 0002 makes the bus access/advance mechanism a central synchronization point that is already exercised extremely frequently. Virtual dispatch and dynamic region resolution add overhead precisely where the architecture requires a cheap, predictable operation.

### Steel-man: why the flat array still wins initially
Alternative 1 is genuinely the fastest route to a machine that boots. A byte array plus a handful of special cases is easy to implement, has excellent locality, and avoids building an abstraction before there is enough emulator behaviour to justify it. That is why many successful emulators use some variation of it.

Its cost arrives later because the shortcuts accumulate as address-specific exceptions. Echoes, unmapped addresses, temporarily inaccessible resources, cartridge mapping, and device ownership all become special cases around what was originally supposed to be a simple array. By the time accurate timing and bus-visible behaviour matter, the emulator has to disentangle those assumptions or duplicate the memory model.

The four alternatives therefore all make an important part of the machine model implicit in some other mechanism: array special cases, runtime registry state, CPU-owned decoding, or polymorphic dispatch. The chosen contract instead makes the **bus the explicit authority for address decoding and access**, while keeping the access path compatible with ADR 0002's timing mechanism. That makes the architectural cost visible early rather than allowing it to emerge later as scattered special cases.
