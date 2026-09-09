# Top-level build.
#
# Structure follows ADR 0008 (repository layout): four targets, one-way dependency,
# one top-level directory per target. Target names carry a gb_ prefix, which rule 8
# leaves as implementation detail, to avoid colliding with targets a fetched
# dependency defines.
#
# The CMake floor is the interim pin described in ADR 0001 (toolchain) A4: low enough
# for current CI images, revisited when a CI provider is chosen.
cmake_minimum_required(VERSION 3.25)

project(gameboy LANGUAGES CXX)

# ADR 0001 A1: C++20, no compiler extensions.
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_LIST_DIR}/cmake")
include(GbWarnings)
include(GbSanitizers)
include(GbPurity)

enable_testing()

add_subdirectory(core)
add_subdirectory(tools)
add_subdirectory(frontend)
add_subdirectory(tests)

# ADR 0001 B12 check 1: the core declares no link dependencies.
gb_assert_no_link_dependencies(gb_core)

# ADR 0001 B12 check 2 and B14: the header/direction scan, and the demonstration
# that it fails on a planted violation.
gb_add_purity_scan(gb_core "${CMAKE_CURRENT_LIST_DIR}/core")
gb_add_purity_selftest("${CMAKE_CURRENT_LIST_DIR}/cmake/purity-selftest")
