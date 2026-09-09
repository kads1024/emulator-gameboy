# Known shortcuts
Every deliberate deviation from hardware behaviour lives here, with the condition under which it is removed. An undocumented deviation is a defect, not a shortcut.

## What belongs here
A deviation belongs here when the emulator knowingly does something the hardware does not, and the intention is to stop doing it.

A behaviour does **not** belong here when it is what real hardware does under the same conditions. That is an accepted permanent behaviour and belongs in `docs/scope.md` section 5, which has its own admission rule.

A behaviour that is neither — an unknown, an approximation nobody chose, a value returned because it seemed plausible — is a defect. Principle P14 in `docs/architecture.md` requires it to be loud rather than silent, and this file is not where it is laundered into acceptability.

## The rules
1. **Every entry has a removal condition.** There are no open-ended entries. If a deviation cannot be given one, it is not a shortcut: it is either a permanent behaviour, which requires an ADR and an entry in `docs/scope.md` section 5, or a defect.
2. **Every entry has a stable ID**, of the form `KS-0001`. IDs are allocated in order and never reused, including after an entry is retired.
3. **Every deviating code site names its entry.** A source comment containing the ID marks each place the deviation lives, in the form `KS-0001:` followed by a short description. An entry whose deviation has no single code site says so explicitly in its Sites field.
4. **Retired entries are moved, not deleted.** When a deviation is removed, its entry moves to the Retired section with the date and the change that removed it. The file is a record, not a to-do list.
5. **An entry is retired only when a test proves the deviation is gone.** "It looks right now" does not retire an entry.

These rules exist so that a check can later assert, mechanically, that every ID appearing in the source has an open entry here and every open entry has at least one source site.

## Entry format
Each entry uses these fields, in this order.

| Field | Content |
|---|---|
| `ID` | `KS-NNNN`. Allocated in order, never reused. |
| `Title` | One line naming the deviation. |
| `Hardware` | What the real machine does. |
| `Emulator` | What this emulator does instead. |
| `Reason` | Why the shortcut exists. "Not implemented yet" is a valid reason. |
| `Detection` | How someone would notice this biting: the test that fails, the visible symptom, or the assertion that fires. |
| `Removal` | A milestone name or a concrete condition. Never open-ended. |
| `Sites` | Where the deviation lives in the source, by ID marker, or an explicit statement that it has no single site. |
| `Added` | Date. |

Template, illustrative only — this is not an entry:

    ID:         KS-0000
    Title:      Example entry, not a real shortcut
    Hardware:   What the DMG does.
    Emulator:   What this emulator does instead.
    Reason:     Why we accepted this for now.
    Detection:  The named test that fails, or the symptom that appears.
    Removal:    The milestone or condition after which this must be gone.
    Sites:      KS-0000 markers in the source, or "no single site".
    Added:      YYYY-MM-DD

## Open entries
None. No emulation code exists yet.

An empty list here is an assertion, not an oversight: as of the last commit touching this file, the project knowingly deviates from hardware behaviour in zero places.

## Retired entries
None.