# The emulated machine. ADR 0008 (layout) rule 1: depends on the standard library and
# nothing else. Its dependency set is asserted at the top level, not assumed.

add_library(gb_core STATIC
  placeholder.cpp
)

# ADR 0008 rule 4: headers live beside sources; the consumable interface is the
# target's usage requirements. Include paths are rooted at the repository so an
# include reads "core/<file>" and names the target it comes from.
target_include_directories(gb_core PUBLIC "${PROJECT_SOURCE_DIR}")

target_link_libraries(gb_core PRIVATE gb_warnings gb_sanitizers)
