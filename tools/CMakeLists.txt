# ADR 0008 (layout) rule 1: depends on the core, never the other way, and not on the
# other consumer target.

add_executable(gb_tools
  main.cpp
)

target_link_libraries(gb_tools PRIVATE gb_core gb_warnings gb_sanitizers)

gb_stage_sanitizer_runtime(gb_tools)
