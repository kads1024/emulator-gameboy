// Placeholder translation unit.
//
// It exists so the core target exists before any emulator code does, which is what
// lets the dependency-boundary checks (ADR 0001 B12) be built and demonstrated first.
// It is deleted when the first real core source lands.

namespace gb {

// Deliberately trivial: nothing here models the machine.
//
// The check below is right that nothing declares or uses this function: its only purpose
// is to give the core target a symbol before any real code exists. Giving it internal
// linkage would make it an unused static function and trip -Wunused-function, so the two
// guards would contradict each other over a function that is deleted the moment the first
// real core source lands.
// NOLINTNEXTLINE(misc-use-internal-linkage)
int core_placeholder() {
    return 0;
}

} // namespace gb
