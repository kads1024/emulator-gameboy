# Core purity source scan. Run in script mode:
#   cmake -DGB_SCAN_DIR=<dir> -P cmake/purity_scan.cmake
#
# This is check 2 of ADR 0001 (toolchain) B12. It enforces two recorded rules:
#
#   1. B13's header denylist. The six headers B13 names are the operative core of the
#      list; the rest are members of the same two categories B13 defines - facilities
#      that perform I/O, and facilities that make the core's next state depend on
#      something other than its current state and its inputs (P11).
#   2. ADR 0008 (layout) rule 1's one-way dependency. The core may not include from
#      tools, frontend, or tests.
#
# A header not on this list is not thereby permitted: the categories govern, and the
# list is extended when a member of either category is found missing from it.

if(NOT DEFINED GB_SCAN_DIR)
  message(FATAL_ERROR "purity_scan.cmake requires -DGB_SCAN_DIR=<dir>")
endif()

# I/O: the core performs none. It accepts bytes and emits values.
set(GB_DENIED_IO
  iostream ostream istream fstream sstream syncstream iomanip
  cstdio stdio.h filesystem
)

# Determinism: the core's next state is a function of its state and its inputs (P11).
# Real-world time enters only as an explicit parameter, for the MBC3 RTC (ADR 0006 rule 7).
set(GB_DENIED_NONDETERMINISM
  chrono ctime time.h random thread mutex condition_variable future atomic
)

set(GB_DENIED_HEADERS ${GB_DENIED_IO} ${GB_DENIED_NONDETERMINISM})
set(GB_FORBIDDEN_INCLUDE_PREFIXES tools/ frontend/ tests/)

file(GLOB_RECURSE gb_sources
  "${GB_SCAN_DIR}/*.cpp" "${GB_SCAN_DIR}/*.cc" "${GB_SCAN_DIR}/*.cxx"
  "${GB_SCAN_DIR}/*.hpp" "${GB_SCAN_DIR}/*.hh" "${GB_SCAN_DIR}/*.h"
  "${GB_SCAN_DIR}/*.ipp" "${GB_SCAN_DIR}/*.inl"
)

set(gb_violations "")

foreach(src IN LISTS gb_sources)
  file(STRINGS "${src}" lines)
  set(lineno 0)
  foreach(line IN LISTS lines)
    math(EXPR lineno "${lineno}+1")
    if(NOT line MATCHES "^[ \t]*#[ \t]*include[ \t]*[<\"]([^>\"]+)[>\"]")
      continue()
    endif()
    set(included "${CMAKE_MATCH_1}")

    foreach(denied IN LISTS GB_DENIED_HEADERS)
      if(included STREQUAL denied)
        list(APPEND gb_violations
          "${src}:${lineno}: forbidden header <${denied}> in the core (ADR 0001 B13)")
      endif()
    endforeach()

    foreach(prefix IN LISTS GB_FORBIDDEN_INCLUDE_PREFIXES)
      if(included MATCHES "^${prefix}")
        list(APPEND gb_violations
          "${src}:${lineno}: core includes \"${included}\"; dependency runs one way (ADR 0008 rule 1)")
      endif()
    endforeach()
  endforeach()
endforeach()

list(LENGTH gb_sources gb_source_count)

if(gb_violations)
  foreach(v IN LISTS gb_violations)
    message(SEND_ERROR "${v}")
  endforeach()
  message(FATAL_ERROR "core purity scan failed")
endif()

message(STATUS "core purity scan: ${gb_source_count} file(s), no violations")
