# E1b target-side workloads. ADR 0008 (layout) rule 8: a target directory may hold more
# than one executable, and these share the tools boundary with the calibration workload.
#
# Neither links gb_core: like the calibration workload they are measurement instruments,
# not consumers of the machine.

add_executable(gb_b_near b_near.cpp)
target_link_libraries(gb_b_near PRIVATE gb_warnings gb_sanitizers)
gb_stage_sanitizer_runtime(gb_b_near)

add_executable(gb_b_far b_far.cpp)
target_link_libraries(gb_b_far PRIVATE gb_warnings gb_sanitizers)
gb_stage_sanitizer_runtime(gb_b_far)
