// Fixture for the purity check's self-test (ADR 0001 B14).
//
// This file is deliberately in violation and is deliberately outside every target's
// source directory, so nothing compiles it. The test named
// purity_check_rejects_planted_violation passes only when the scan rejects this file.
// If that test ever passes without the scan failing, the guard is broken.

#include <cstdio>   // forbidden by ADR 0001 B13: the core performs no I/O
#include <chrono>   // forbidden by ADR 0001 B13: determinism (P11)
#include "tools/something.hpp"  // forbidden by ADR 0008 rule 1: dependency runs one way

int planted_violation();
