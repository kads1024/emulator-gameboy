# Calibration workload for ADR 0007 (performance floor) rule 4.
#
# Deliberately does not link gb_core. It is the denominator of the calibrated ratio, and
# a denominator that executed the emulator's code would move when the emulator moved,
# which is the one thing it must not do.

add_executable(gb_calibration main.cpp)

target_link_libraries(gb_calibration PRIVATE gb_warnings gb_sanitizers)

gb_stage_sanitizer_runtime(gb_calibration)
