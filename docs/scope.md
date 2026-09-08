# Scope

This document defines what this project emulates and what it does not. It is the document every scope question is settled against. If a proposed feature cannot be classified as in or out by reading this file, that is a defect in this file.

## 1. Target

Sharp DMG: the original Game Boy, model DMG-01, containing the Sharp LR35902 system-on-chip. Nothing else.

The following are properties of the target hardware and are named constants in the code, never literals:

| Constant | Value |
|---|---|
| Master clock | 4,194,304 Hz (2^22 T-cycles per second) |
| M-cycle | 4 T-cycles |
| Scanline | 456 T-cycles |
| Frame | 154 scanlines = 70,224 T-cycles |
| Frame rate | 4,194,304 / 70,224 ≈ 59.727 Hz (not 60 Hz) |
| Screen | 160 x 144 pixels, 4 shades |

## 2. In scope

| Subsystem | Coverage |
|---|---|
| CPU (SM83) | Full instruction set including the `$CB` prefix. M-cycle-accurate memory access timing. Documented hardware bugs including the HALT bug. |
| Bus | Full 16-bit address space, region routing, access-permission rules, open bus, echo RAM, prohibited region. |
| Interrupt controller | All five sources. Line-based edge detection including STAT blocking. `IE`, `IF`, `IME`, dispatch timing. |
| PPU | Mode state machine, `LY`/`LYC`/`STAT`, VBlank and STAT interrupts, background, window, sprites, palettes, VRAM/OAM locking, Mode 3 penalties. |
| Timer | `DIV`, `TIMA`, `TMA`, `TAC`, shared internal counter, reload and write edge cases. |
| APU | Four channels: two square, wave, noise. Length counters, envelopes, sweep, frame sequencer. |
| Joypad | `$FF00` matrix scanning, active-low semantics, joypad interrupt. |
| OAM DMA | Transfer timing and bus conflict behavior. |
| Serial | The peripheral is in scope; the cable is not. `SB` (`$FF01`) and `SC` (`$FF02`) with correct read/write and unused-bit behavior, internal-clock transfer timing and completion, the serial interrupt, and serial output capture so test ROMs can be validated automatically. Nothing on the other end of the cable is emulated. |
| Cartridges | No-MBC, MBC1, MBC3 (+RTC), MBC5. Battery-backed RAM with disk persistence. |
| System | Boot ROM execution (user-supplied image) and skip-boot. Save states. |
| Tooling | Headless core. Debugger. Frontend with video, audio, input, frame pacing. |

## 3. Out of scope

Each exclusion carries its reason. The reason is the part that matters: it is what lets a future proposal be evaluated even if it is not named here.

**Game Boy Color.** It forks the PPU, the bus, and CPU timing simultaneously. A partial CGB implementation is worse than none, it produces games that *almost* work and a compatibility list that cannot be trusted.
- Cartridges marked CGB-only (`$0143 == $C0`) are detected at load and refused with a clear error. This is a product decision, not hardware fidelity: real DMG hardware would run such a cartridge and let its own code display an incompatibility screen. Refusing at load is chosen because a clear error is more useful than an unexplained screen, and because it keeps the compatibility list honest.
- Cartridges marked CGB-enhanced (`$0143 == $80`) run their DMG code path. This is not a compromise or a degraded mode: those cartridges contain a DMG path precisely so they can run on DMG hardware, and running it is what this hardware target does.

**Super Game Boy.** A separate product. It requires a command protocol layered over the joypad register and an SNES host to interpret it.

**Link cable emulation, two-instance synchronization, networking, trading.** Excluded for an architectural reason, not an effort one: two synchronized instances require a shared clock authority above the machine root, which is a different top-level design from the single-machine ownership tree this project is built on.

**MBC2, MBC6, MBC7, HuC1, HuC3, MMM01, Pocket Camera, TAMA5, and other exotic mappers.** Each is a separate behavioral surface with its own tests, justified only by the titles that need it. Revisitable at a milestone retrospective, and only with a specific named list of titles motivating it.

**Game Boy Advance anything.** A different machine.

**Commercial game ROMs** in the repository, its history, its test fixtures, its CI, or any released artifact. See section 7.

**Cheat engines, ROM patching, texture packs, upscaling beyond integer scaling, shader pipelines.** None of these are the hardware. They are a different product with a different audience.

## 4. Forward compatibility rule

**Game Boy Color imposes no requirements on this project.**
- No design may be justified on the grounds that it "would help if we added CGB later."
- No interface may carry a parameter, field, or abstraction whose only purpose is CGB.
- No review comment may block a design because it is CGB-hostile.

Exactly three accommodations are permitted, each because it has independent justification and costs nothing:
1. The core framebuffer carries post-palette shade indices, not RGB (see section 6).
2. Memory region sizes are named constants.
3. The master clock frequency is a named constant.

Forbidden, stated concretely so a review can fail against them:
- bank index parameters on VRAM or WRAM access functions
- a palette abstraction representing more than four shades
- speed-multiplier plumbing through the clock or peripherals
- attribute-map fields in tile-map handling
- any interface generalized "so CGB can slot in"

## 5. Accepted permanent behaviors

These are distinct from debt. They have no removal milestone because they are correct.

**Unplugged serial link.** With no link partner, the data line floats high. Therefore:
- Internal-clock transfers complete normally and leave `SB = $FF`.
- External-clock transfers never complete, because no external clock exists.

This is the behavior of a real Game Boy with nothing in the link port. It is not a shortcut, not a stub, and not a defect.

Adding an entry to this section requires an ADR that shows the behavior is what real hardware does under the same conditions. A behavior that is merely convenient, unimplemented, or approximate belongs in `docs/known-shortcuts.md` with a removal milestone, not here.

## 6. Framebuffer contract

The core emits **post-palette shade indices, 0–3, one per pixel**. Palette registers (`BGP`, `OBP0`, `OBP1`) are applied inside the PPU at the moment the pixel is produced. The frontend owns the mapping from shade index to a displayed color, and therefore owns any green tint, contrast, or color-scheme option.

The reason the palette is applied in the core rather than at presentation time: games rewrite palette registers during a frame, and fades are implemented exactly this way. A framebuffer of pre-palette color IDs cannot represent a frame whose palette changed partway down the screen, so deferring the lookup to the frontend silently discards real hardware behavior.

The core emits no RGB values. This satisfies accommodation 1 in section 4.

## 7. ROM policy
- No commercial game ROM appears in this repository, in its Git history, in its test fixtures, in CI, or in any released artifact. Without exception.
- Tests that require a commercial ROM accept a user-supplied path and skip cleanly when it is absent. A skip is reported visibly; it is never silent.
- Boot ROM images are user-supplied and are never distributed with this project.
- Freely redistributable test ROMs are fetched by checksum at build or test time and are not committed to this repository.

## 8. Quality goals and the rewrite budget

This project optimizes for correctness and maintainability over speed of implementation. It is expected to take many months.

Rewrites are budgeted and expected. Replacing a scanline renderer with a FIFO renderer is a local change behind a stable interface, and it is a planned outcome rather than a failure.

Two things must never be rewritten under force:
1. **The timing model.**
2. **The bus contract.**

Everything else may be replaced when evidence justifies it. A design that protects these two is correct even when it costs elsewhere.