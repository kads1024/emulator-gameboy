// Calibration workload for the performance gate. ADR 0007 (performance floor) rule 4.
//
// ============================== DO NOT MODIFY ==============================
//
// This program is the denominator of the calibrated ratio. Its runtime is what the
// emulator's runtime is divided by, so that a host which is uniformly slower cancels
// out of the comparison.
//
// The moment a performance baseline is recorded against it, this file is FROZEN.
// ADR 0007's consequence is explicit: any change to the calibration workload
// invalidates every historical baseline. Changing it is a re-baselining event with the
// same review requirement as changing the baseline itself, not an ordinary edit.
//
// If you are here because you want the benchmark to be more representative, or faster,
// or tidier: that is a re-baselining decision, and it belongs in a commit that says so.
//
// ==========================================================================
//
// What it does, and why this shape:
//
//   * Deterministic. The same iteration count always performs the same work and
//     produces the same checksum, so a changed checksum means the workload changed
//     rather than the host being slow. This is the workload-equivalence check ADR 0007
//     Alternative 3 describes, and it is not a performance measure.
//   * Single-threaded, CPU-bound, no allocation and no syscalls inside the timed
//     region, so the measurement contains no waiting.
//   * A mix of integer arithmetic, data-dependent branching, and a small table lookup
//     that stays in L1. A pure register-only loop would be insensitive to the cache and
//     branch behaviour a host actually varies in, which is what the ratio exists to
//     cancel.
//   * The result is consumed, so the optimiser cannot delete the loop. The checksum is
//     printed, which is a data dependency it cannot see through.
//
// This is a tool, not the core: ADR 0001 (toolchain) B13's header denylist governs the
// core, and <chrono> is available here.

#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <vector>

namespace {

// Frozen parameters. Changing either is a re-baselining event.
constexpr std::uint64_t kIterations = 300'000'000;
constexpr std::size_t kTableBits = 12; // 4096 entries, 32 KiB: L1-resident on any host
constexpr std::size_t kTableSize = std::size_t{1} << kTableBits;
constexpr std::uint64_t kSeed = 0x0123456789ABCDEFULL;

std::vector<std::uint64_t> build_table() {
    std::vector<std::uint64_t> table(kTableSize);
    std::uint64_t state = kSeed;
    for (std::size_t i = 0; i < kTableSize; ++i) {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        table[i] = state;
    }
    return table;
}

// The timed kernel. Returns a checksum so the work cannot be elided and so that two
// runs can be proven to have done the same thing.
std::uint64_t run_kernel(const std::vector<std::uint64_t>& table) {
    std::uint64_t state = kSeed;
    std::uint64_t checksum = 0;

    for (std::uint64_t i = 0; i < kIterations; ++i) {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;

        const std::size_t index = static_cast<std::size_t>(state) & (kTableSize - 1);
        const std::uint64_t value = table[index];

        // Data-dependent branch: unpredictable by construction, which is the branch
        // behaviour an interpreter dispatch loop actually exhibits.
        if ((value & 1U) != 0U) {
            checksum += value ^ state;
        } else {
            checksum ^= value + state;
        }
    }

    return checksum;
}

// Parses --runs. Returns false on anything it cannot parse, rather than silently
// substituting a value: a measurement run with the wrong run count is worse than one
// that refuses to start.
bool parse_runs(int argc, char** argv, long& runs) {
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--runs") != 0) {
            continue;
        }
        if (i + 1 >= argc) {
            return false;
        }
        char* end = nullptr;
        errno = 0;
        const long value = std::strtol(argv[i + 1], &end, 10);
        if (errno != 0 || end == argv[i + 1] || *end != '\0' || value < 1 || value > 1000) {
            return false;
        }
        runs = value;
        ++i;
    }
    return true;
}

} // namespace

int main(int argc, char** argv) try {
    long runs = 5;
    if (!parse_runs(argc, argv, runs)) {
        std::fprintf(stderr, "usage: gb_calibration [--runs N]   (1 <= N <= 1000)\n");
        return 2;
    }

    const std::vector<std::uint64_t> table = build_table();

    std::vector<std::int64_t> timings_ns;
    timings_ns.reserve(static_cast<std::size_t>(runs));

    std::uint64_t checksum = 0;
    bool checksum_stable = true;

    for (long run = 0; run < runs; ++run) {
        const auto started = std::chrono::steady_clock::now();
        const std::uint64_t result = run_kernel(table);
        const auto finished = std::chrono::steady_clock::now();

        const auto elapsed =
            std::chrono::duration_cast<std::chrono::nanoseconds>(finished - started).count();
        timings_ns.push_back(elapsed);

        if (run == 0) {
            checksum = result;
        } else if (result != checksum) {
            checksum_stable = false;
        }
    }

    // JSON on stdout so the harness can consume it without parsing prose.
    std::printf("{\n");
    std::printf("  \"iterations\": %llu,\n", static_cast<unsigned long long>(kIterations));
    std::printf("  \"table_entries\": %llu,\n", static_cast<unsigned long long>(kTableSize));
    std::printf("  \"checksum\": \"0x%016llX\",\n", static_cast<unsigned long long>(checksum));
    std::printf("  \"checksum_stable\": %s,\n", checksum_stable ? "true" : "false");
    std::printf("  \"runs_ns\": [");
    for (std::size_t i = 0; i < timings_ns.size(); ++i) {
        std::printf("%s%lld", i == 0 ? "" : ", ", static_cast<long long>(timings_ns[i]));
    }
    std::printf("]\n");
    std::printf("}\n");

    // An unstable checksum means the runs did not do the same work, so the timings are
    // not comparable. That is a hard failure, not a note in the output.
    return checksum_stable ? 0 : 1;
} catch (const std::exception& error) {
    // Allocating the table is the only thing here that can throw. A measurement harness
    // that dies with an unhandled exception gives the caller no usable signal.
    std::fprintf(stderr, "gb_calibration: %s\n", error.what());
    return 3;
}
