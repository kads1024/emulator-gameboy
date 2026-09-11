# The tools boundary. ADR 0008 (layout) rule 1: may depend on core, the standard
# library, and third-party as needed; nothing depends on it in the other direction.
#
# Rule 3 fixes the dependency boundary a file falls under, not the number of binaries
# produced within it, so this directory hosts one executable per subdirectory and they
# all share the same row of rule 1's table.

add_subdirectory(benchmarks)
add_subdirectory(calibration)
