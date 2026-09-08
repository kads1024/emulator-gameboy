# ADR 0006: Cartridge representation

## Status summary
- **Cartridge structure and the cached-offset read path:** BLOCKING ARCHITECTURAL DECISION — accepted.
- **Closed variant as the mapper representation:** PROVISIONAL — adjudication mechanism recorded in the Status section.

## Context

### The problem
A cartridge holds up to 8 MB of ROM. The CPU can name 32 KB of it at a time. Between them sits a chip whose entire job is to decide which bytes are currently visible.

How that chip is represented determines the shape of the most frequently executed read in the emulator: while a program runs from ROM, every instruction fetch and every immediate operand passes through it.

### The hardware facts that constrain the answer
1. **The mapper is a latch, not a computation.** Writes into the ROM address range do not store data; they set registers inside the cartridge. Those registers drive the ROM chip's upper address lines continuously. When the CPU reads, no decision is made by the mapper — the decision was made at the moment of the last register write, and the wires have been holding it ever since.
2. **The read is an address computation, not a dispatch.** With the bank latched, the byte the CPU receives is determined by concatenating the latched bank bits with the address bits the CPU supplied. Multiply and add, in the primer's phrasing.
3. **The mapper set is closed and fixed at load time.** A cartridge's type byte is read once from the header. No cartridge changes its mapper while running, and the set of mappers this project supports is enumerated in `docs/scope.md`.
4. **MBC3 contains a clock.** The cartridge has an input the console does not: real-world time. It is the only part of the machine that does.
5. **ROM and cartridge RAM have different lifetimes.** ROM is fixed and comes from outside the machine. Battery-backed RAM survives power-off and is part of what the player owns.

### Constraints from prior decisions
The read path is hot, per ADR 0002's consequences. The cartridge is a component owned by the bus and holds no references, per ADR 0003. Virtual dispatch requires hardware polymorphism to justify it, per principle P10. Time may not be read from the host inside the core, per principle P11. The save-state requirements distinguish what is reloaded from a file from what is captured.

### What makes this decision expensive to revisit
The shape of the read path appears in every fetch, and the split between cartridge data and mapper state determines what a save state contains and what it reconstructs.

### Out of scope
The register semantics of each individual mapper — MBC1's banking modes, RAM enable values, MBC3's latch sequence — which are implementation detail documented per mapper. The on-disk formats for battery RAM and for RTC persistence. The save-state format.

## Decision
**1. A cartridge is one component with four distinguishable parts:** a parsed header, immutable after load; the ROM bytes; the RAM bytes; and the mapper's state.
**2. Mapper state is a closed `std::variant` of small, trivially copyable structs** — one alternative per supported mapper. No inheritance, no virtual functions, no heap.
**3. The mapper's output is cached as resolved offsets.** The current ROM offsets for both windows, the current RAM offset, and whether RAM is currently accessible are stored, and are recomputed only when a mapper register changes.
**4. The read path is a masked array index using those cached offsets.** It contains no `visit`, no branch on mapper type, and no per-access recomputation. This mirrors fact 1: on hardware, a read consults latched wires, and the latching happened earlier.
**5. Writes into the mapper's register ranges dispatch through the variant once,** update that mapper's registers, and recompute the cached offsets. All mapper-specific behaviour lives on this path.
**6. Masking for undersized ROM and RAM happens when offsets are recomputed,** not on each access. A cartridge with fewer banks than its bank register can express resolves to a wrapped offset once, at write time.
**7. The cartridge consumes time through an explicit parameter,** from the first implementation, even though only MBC3 uses it and every other mapper ignores it. Time is never read from the host inside the core.
**8. Access to disabled cartridge RAM follows ADR 0004 rule 7.** The observed value is documented and sourced, not chosen for convenience.
**9. ROM bytes are supplied from outside and are not part of the save state. RAM bytes are.** The header is derived from the ROM and is reconstructed on load rather than captured.
**10. The mapper alternative is selected once, at load, from the header type byte,** and does not change for the life of the cartridge.