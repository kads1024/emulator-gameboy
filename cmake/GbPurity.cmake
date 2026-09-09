# Core dependency boundary. ADR 0001 (toolchain) B12 and B14, ADR 0008 (layout) rule 2.

include_guard(GLOBAL)

set(GB_PURITY_SCAN_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/purity_scan.cmake")

# B12 check 1: the target declares no link dependencies.
#
# The language runtime the toolchain links implicitly is not a declared dependency and
# is not what this check is about. An interface target that carries only compile and
# link options (the warning and sanitizer configuration) is likewise not a library:
# the check walks through such targets and fails on anything that resolves to an
# actual library. This is not an allowlist - nothing is named - it is a test of what a
# link entry *is*.
function(gb_assert_no_link_dependencies target)
  set(_pending "${target}")
  set(_seen "")

  while(_pending)
    list(POP_FRONT _pending current)
    if(current IN_LIST _seen)
      continue()
    endif()
    list(APPEND _seen "${current}")

    set(_deps "")
    foreach(prop LINK_LIBRARIES INTERFACE_LINK_LIBRARIES)
      get_target_property(_value "${current}" ${prop})
      if(_value)
        list(APPEND _deps ${_value})
      endif()
    endforeach()

    foreach(dep IN LISTS _deps)
      # Unwrap the one generator expression a link entry can legitimately carry.
      string(FIND "${dep}" "$<LINK_ONLY:" _link_only_at)
      if(_link_only_at EQUAL 0)
        string(REPLACE "$<LINK_ONLY:" "" dep "${dep}")
        string(REPLACE ">" "" dep "${dep}")
      endif()
      if(NOT TARGET "${dep}")
        message(FATAL_ERROR
          "Core purity violation: target '${current}' declares link dependency "
          "'${dep}', which is not a target and therefore an external library. "
          "The core links only the standard library (ADR 0001 B12).")
      endif()
      get_target_property(_type "${dep}" TYPE)
      if(NOT _type STREQUAL "INTERFACE_LIBRARY")
        message(FATAL_ERROR
          "Core purity violation: target '${current}' links '${dep}' (${_type}). "
          "The core links only the standard library (ADR 0001 B12).")
      endif()
      list(APPEND _pending "${dep}")
    endforeach()
  endwhile()

  list(LENGTH _seen _count)
  message(STATUS "core purity: '${target}' declares no link dependencies "
                 "(${_count} interface node(s) walked)")
endfunction()

# B12 check 2: the header and dependency-direction scan, run on every build of the
# core so a violation fails the build rather than waiting for a review.
function(gb_add_purity_scan target scan_dir)
  add_custom_target(gb_purity_scan ALL
    COMMAND "${CMAKE_COMMAND}" -DGB_SCAN_DIR=${scan_dir} -P "${GB_PURITY_SCAN_SCRIPT}"
    COMMENT "Scanning core for forbidden headers and dependency direction (ADR 0001 B12)"
    VERBATIM)
  add_dependencies(${target} gb_purity_scan)
endfunction()

# B14: the check is itself tested. The fixture contains a planted violation, and the
# test passes only when the scan rejects it. No broken commit is required to prove the
# guard works.
function(gb_add_purity_selftest fixture_dir)
  add_test(NAME purity_check_rejects_planted_violation
    COMMAND "${CMAKE_COMMAND}" -DGB_SCAN_DIR=${fixture_dir} -P "${GB_PURITY_SCAN_SCRIPT}")
  set_tests_properties(purity_check_rejects_planted_violation PROPERTIES WILL_FAIL TRUE)
endfunction()
