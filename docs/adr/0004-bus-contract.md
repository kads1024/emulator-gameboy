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

**4. Echo RAM is decode, not duplication.** The region exists because the work RAM's selection logic ignores the address bit that distinguishes the two ranges, so the same 8 KiB of storage answers to both sets of names. The echo region resolves to the same storage as the region it mirrors. There is no second array and no copying. A write through one set of names is observable through the other because they are the same bytes.

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