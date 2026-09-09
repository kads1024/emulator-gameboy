// Placeholder test.
//
// It exists so that the test target, its framework wiring, and CTest registration are
// standing and demonstrably working before any emulator code exists. It is replaced by
// the first real test.

#include <catch2/catch_test_macros.hpp>

TEST_CASE("the test harness runs", "[harness]") {
    REQUIRE(1 + 1 == 2);
}
