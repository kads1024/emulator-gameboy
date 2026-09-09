// Placeholder translation unit.
//
// It exists so the core target exists before any emulator code does, which is what
// lets the dependency-boundary checks (ADR 0001 B12) be built and demonstrated first.
// It is deleted when the first real core source lands.

namespace gb {

// Deliberately trivial: nothing here models the machine.
int core_placeholder() { return 0; }

}  // namespace gb
