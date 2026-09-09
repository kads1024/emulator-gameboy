# Every automated check. ADR 0008 (layout) rule 1: may depend on core, tools, and the
# test framework. ADR 0001 (toolchain) B17 and B18: the framework is fetched at
# configure time, pinned to an exact release and verified by hash, and it links to the
# tests only - never to the core.

include(FetchContent)

FetchContent_Declare(Catch2
  URL      https://github.com/catchorg/Catch2/archive/refs/tags/v3.11.0.tar.gz
  URL_HASH SHA256=82fa1cb59dc28bab220935923f7469b997b259eb192fb9355db62da03c2a3137
  # B1: consumed as a system include, so its diagnostics are not this project's
  # problem and cannot be silenced by weakening this project's own flags.
  SYSTEM
)
FetchContent_MakeAvailable(Catch2)

# The debug configuration sanitizes everything it links, including the framework.
#
# ASan enables the standard library's container and string annotations, and the MSVC
# standard library marks objects accordingly and refuses to link annotated objects
# against unannotated ones. Building the framework unsanitized would therefore either
# break the link or force the annotations off, and turning a sanitizer feature off to
# make a link succeed is the quiet degradation ADR 0001 (toolchain) A8 forbids. The
# framework is built with the same sanitizer configuration as everything else instead.
foreach(catch2_target IN ITEMS Catch2 Catch2WithMain)
  if(TARGET ${catch2_target})
    target_link_libraries(${catch2_target} PRIVATE gb_sanitizers)
  endif()
endforeach()

add_executable(gb_tests
  placeholder_test.cpp
)

target_link_libraries(gb_tests PRIVATE
  gb_core
  gb_warnings
  gb_sanitizers
  Catch2::Catch2WithMain
)

# Catch2's TEST_CASE macro expands to __COUNTER__, which clang 22 reports under
# -Wpedantic as a C2y extension. The diagnostic is raised at the expansion site, which
# is our translation unit, so consuming Catch2 as a SYSTEM include does not suppress it.
#
# The suppression is scoped to this target and to that one diagnostic. It does not touch
# the warning interface target (ADR 0001 B2), it does not apply to any target containing
# code this project wrote, and it suppresses a report about a compiler extension used by
# the framework rather than about anything in this repository.
#
# It is carried on an interface target linked after gb_warnings so that it appears after
# -Wpedantic on the command line; a suppression that precedes the flag it suppresses is
# silently undone, which is the kind of quiet degradation ADR 0001 A8 forbids.
include(CheckCXXCompilerFlag)
check_cxx_compiler_flag(-Wno-c2y-extensions GB_HAS_WNO_C2Y_EXTENSIONS)
add_library(gb_catch2_macro_workaround INTERFACE)
if(GB_HAS_WNO_C2Y_EXTENSIONS)
  target_compile_options(gb_catch2_macro_workaround INTERFACE -Wno-c2y-extensions)
endif()
target_link_libraries(gb_tests PRIVATE gb_catch2_macro_workaround)

gb_stage_sanitizer_runtime(gb_tests)

list(APPEND CMAKE_MODULE_PATH "${catch2_SOURCE_DIR}/extras")
include(Catch)
catch_discover_tests(gb_tests)
