# Sanitizer configuration. ADR 0001 (toolchain) A7, A8, B10, B11.
#
# B10: Linux is the authoritative sanitizer environment and carries ASan and UBSan with
# their runtime libraries and full diagnostics.
# B11: on Windows, ASan works and UBSan's runtime does not link against the installed
# SDK; UBSan in trap mode does work and reports a trap rather than a diagnostic.
# A8: nothing here degrades silently. If a selected sanitizer does not build, or its
# runtime cannot be found, the configure fails rather than producing a binary that
# looks sanitized and is not.

include_guard(GLOBAL)
include(CheckCXXSourceCompiles)

add_library(gb_sanitizers INTERFACE)
set(GB_SANITIZERS_ACTIVE OFF)

if(CMAKE_BUILD_TYPE STREQUAL "Debug")
  if(WIN32)
    # ASan is incompatible with the Microsoft debug C runtime: a binary linked against
    # ucrtbased aborts inside the allocator before main. The sanitized Windows debug
    # configuration therefore links the release CRT. What is lost is the CRT's own debug
    # heap checking, which ASan supersedes; what is kept is a debug build that runs.
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL" CACHE STRING
        "Release CRT: required for ASan on Windows" FORCE)

    set(_gb_san_flags -fsanitize=address -fsanitize=undefined -fsanitize-trap=undefined)
    set(_gb_san_desc "ASan + UBSan (trap mode: a trap, not a diagnostic - reproduce under Linux to diagnose, per B11)")
  else()
    set(_gb_san_flags -fsanitize=address -fsanitize=undefined -fno-omit-frame-pointer)
    set(_gb_san_desc "ASan + UBSan with full diagnostics (B10)")
  endif()

  set(CMAKE_REQUIRED_FLAGS "${_gb_san_flags}")
  set(CMAKE_REQUIRED_LINK_OPTIONS "${_gb_san_flags}")
  check_cxx_source_compiles("int main() { return 0; }" GB_SANITIZERS_USABLE)
  unset(CMAKE_REQUIRED_FLAGS)
  unset(CMAKE_REQUIRED_LINK_OPTIONS)

  if(NOT GB_SANITIZERS_USABLE)
    message(FATAL_ERROR
      "The debug configuration requires sanitizers and they do not link here: "
      "${_gb_san_flags}. ADR 0001 A8 forbids a preset that quietly drops them.")
  endif()

  target_compile_options(gb_sanitizers INTERFACE ${_gb_san_flags})
  target_link_options(gb_sanitizers INTERFACE ${_gb_san_flags})
  set(GB_SANITIZERS_ACTIVE ON)
  message(STATUS "Debug sanitizers: ${_gb_san_desc}")
endif()

# On Windows, ASan is a dynamic runtime and an executable built with it will not start
# unless that runtime is findable. ADR 0001 B11 records the requirement as "the LLVM
# runtime directory on PATH"; staging the DLL beside the executable removes the
# requirement instead of documenting it, so a freshly built binary runs, and so the test
# framework's build-time test discovery can execute the binary it just linked.
#
# Defined unconditionally, and a no-op where it does not apply: a function that exists
# only in one configuration turns an unrelated preset into a configure error, which is
# how this one was found.
function(gb_stage_sanitizer_runtime target)
  if(NOT WIN32 OR NOT GB_SANITIZERS_ACTIVE)
    return()
  endif()

  execute_process(
    COMMAND "${CMAKE_CXX_COMPILER}" -print-runtime-dir
    OUTPUT_VARIABLE _gb_runtime_dir
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET)

  # Recent clang reports a per-triple runtime directory while the Windows runtime DLLs
  # are installed in a sibling directory, so search the resource lib tree rather than
  # only the reported path.
  file(GLOB _gb_asan_dlls "${_gb_runtime_dir}/clang_rt.asan_dynamic-*.dll")
  if(NOT _gb_asan_dlls)
    get_filename_component(_gb_runtime_root "${_gb_runtime_dir}" DIRECTORY)
    file(GLOB_RECURSE _gb_asan_dlls "${_gb_runtime_root}/clang_rt.asan_dynamic-*.dll")
  endif()
  if(NOT _gb_asan_dlls)
    message(FATAL_ERROR
      "Debug builds link ASan but its runtime was not found under '${_gb_runtime_dir}'. "
      "A binary that cannot start is not a sanitized binary (ADR 0001 A8).")
  endif()

  add_custom_command(TARGET ${target} POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different ${_gb_asan_dlls} "$<TARGET_FILE_DIR:${target}>"
    COMMENT "Staging ASan runtime beside ${target}"
    VERBATIM)
endfunction()
