# Warning configuration. ADR 0001 (toolchain) B1, B2, B3, and A8.
#
# B2: this is the single place warning flags are defined. No target sets its own,
# and nothing is applied globally.
# A8: a configuration that cannot support a required flag fails to configure, rather
# than quietly dropping it.

include_guard(GLOBAL)
include(CheckCXXCompilerFlag)

add_library(gb_warnings INTERFACE)

# ADR 0001 A2 and A3: clang and GCC are the enforcing compilers. The MSVC front end
# cannot express -Wconversion, so a clean build under it would mean something
# different from a clean build under the other two. Configuring with it is refused
# rather than silently weakened.
if(MSVC AND NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  message(FATAL_ERROR
    "This project's warning discipline requires clang or GCC (ADR 0001 A2/A3). "
    "The MSVC front end cannot enforce -Wconversion. Use clang targeting "
    "x86_64-pc-windows-msvc for Microsoft standard-library coverage.")
endif()

set(GB_REQUIRED_WARNING_FLAGS
  -Wall
  -Wextra
  -Wpedantic
  -Wconversion
  -Wsign-conversion
)

foreach(flag IN LISTS GB_REQUIRED_WARNING_FLAGS)
  string(MAKE_C_IDENTIFIER "GB_HAS${flag}" flag_var)
  check_cxx_compiler_flag("${flag}" ${flag_var})
  if(NOT ${flag_var})
    message(FATAL_ERROR
      "Required warning flag ${flag} is not supported by this compiler "
      "(${CMAKE_CXX_COMPILER_ID}). ADR 0001 A8 forbids configuring without it.")
  endif()
endforeach()

target_compile_options(gb_warnings INTERFACE ${GB_REQUIRED_WARNING_FLAGS} -Werror)
