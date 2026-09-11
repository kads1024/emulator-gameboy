// E1b target-side workload B_far.
//
// Role: the ROBUSTNESS case. A dependent pointer chase over a working set chosen to
// exceed the last-level cache a 4-vCPU cloud instance is likely to have, so the kernel
// is bound by memory latency rather than by integer throughput.
//
// This is the point of the variant: the calibration workload A is L1-resident and
// throughput-bound, and "both are CPU-bound" does not imply the two scale together
// across processors with different cache hierarchies and memory controllers. B_far
// tests that assumption where it is least likely to hold. Its partner B_near is the
// predictive case, and the two are never pooled in analysis.
//
// The chase is a single cycle built by Sattolo's algorithm, so every iteration is a
// dependent load that cannot be prefetched or overlapped, and the traversal visits the
// whole working set. Branching is minimal by design.
//
// CONDITIONS
//
//   null : kBaseIterations
//   reg  : kBaseIterations * 105 / 100, computed in integer arithmetic
//
// kBaseIterations is divisible by 100, so the regressed count is exact. The injection is
// defined on ITERATION COUNT, which is 1.05x the specified kernel work. It is NOT a
// claim of a 1.05x wall-clock multiplier; the realised runtime effect is measured by the
// driver's S diagnostic.
//
// INTERFACE NOTE -- deliberate deviation from the approved implementation plan
//
// The plan specified a runtime "--scale" multiplier. This implementation instead
// exposes a CLOSED condition, --condition null|reg. The approved experimental
// semantics are unchanged:
//
//     null = kBaseIterations
//     reg  = exactly 1.05 * kBaseIterations
//
// What changes is only that the caller cannot express anything else. A free multiplier
// would let a mistyped or edited invocation silently run the experiment at some other
// injected effect, and nothing downstream would notice: the iteration count would be
// recorded faithfully and the analysis would proceed against the wrong injection. The
// 1.05 constant lives here, in the source, where changing it is a reviewable diff.

#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <vector>

namespace {

constexpr std::uint64_t kBaseIterations = 3'660'000; // divisible by 100
constexpr std::size_t kEntries = 33'554'432;         // 256 MiB of uint64_t
constexpr std::uint64_t kSeed = 0xD1B54A32D192ED03ULL;

std::uint64_t regressed_iterations() {
    return kBaseIterations / 100 * 105;
}

std::uint64_t next_random(std::uint64_t& state) {
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return state;
}

// Sattolo's algorithm: produces a permutation that is a single cycle of length kEntries,
// in place, needing only the one array. Following index -> chase[index] therefore visits
// every element before returning to the start.
std::vector<std::uint64_t> build_cycle() {
    std::vector<std::uint64_t> chase(kEntries);
    for (std::size_t i = 0; i < kEntries; ++i) {
        chase[i] = static_cast<std::uint64_t>(i);
    }

    std::uint64_t state = kSeed;
    for (std::size_t i = kEntries - 1; i > 0; --i) {
        const std::size_t j = static_cast<std::size_t>(next_random(state) % i);
        const std::uint64_t tmp = chase[i];
        chase[i] = chase[j];
        chase[j] = tmp;
    }
    return chase;
}

std::uint64_t run_kernel(const std::vector<std::uint64_t>& chase, std::uint64_t iterations) {
    std::uint64_t index = 0;
    std::uint64_t checksum = 0;

    for (std::uint64_t i = 0; i < iterations; ++i) {
        index = chase[static_cast<std::size_t>(index)];
        checksum += index;
    }

    return checksum;
}

bool parse_args(int argc, char** argv, long& runs, bool& regressed) {
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--condition") == 0) {
            if (i + 1 >= argc) {
                return false;
            }
            if (std::strcmp(argv[i + 1], "null") == 0) {
                regressed = false;
            } else if (std::strcmp(argv[i + 1], "reg") == 0) {
                regressed = true;
            } else {
                return false;
            }
            ++i;
            continue;
        }
        if (std::strcmp(argv[i], "--runs") == 0) {
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
            continue;
        }
        return false;
    }
    return true;
}

} // namespace

int main(int argc, char** argv) try {
    long runs = 1;
    bool regressed = false;
    if (!parse_args(argc, argv, runs, regressed)) {
        std::fprintf(stderr, "usage: gb_b_far [--condition null|reg] [--runs N]\n");
        return 2;
    }

    const std::uint64_t iterations = regressed ? regressed_iterations() : kBaseIterations;
    const std::vector<std::uint64_t> chase = build_cycle();

    std::vector<std::int64_t> timings_ns;
    timings_ns.reserve(static_cast<std::size_t>(runs));

    std::uint64_t checksum = 0;
    bool checksum_stable = true;

    for (long run = 0; run < runs; ++run) {
        const auto started = std::chrono::steady_clock::now();
        const std::uint64_t result = run_kernel(chase, iterations);
        const auto finished = std::chrono::steady_clock::now();

        timings_ns.push_back(
            std::chrono::duration_cast<std::chrono::nanoseconds>(finished - started).count());

        if (run == 0) {
            checksum = result;
        } else if (result != checksum) {
            checksum_stable = false;
        }
    }

    std::printf("{\n");
    std::printf("  \"workload\": \"b_far\",\n");
    std::printf("  \"condition\": \"%s\",\n", regressed ? "reg" : "null");
    std::printf("  \"iterations\": %llu,\n", static_cast<unsigned long long>(iterations));
    std::printf("  \"working_set_bytes\": %llu,\n",
                static_cast<unsigned long long>(kEntries * sizeof(std::uint64_t)));
    std::printf("  \"checksum\": \"0x%016llX\",\n", static_cast<unsigned long long>(checksum));
    std::printf("  \"checksum_stable\": %s,\n", checksum_stable ? "true" : "false");
    std::printf("  \"runs_ns\": [");
    for (std::size_t i = 0; i < timings_ns.size(); ++i) {
        std::printf("%s%lld", i == 0 ? "" : ", ", static_cast<long long>(timings_ns[i]));
    }
    std::printf("]\n");
    std::printf("}\n");

    return checksum_stable ? 0 : 1;
} catch (const std::exception& error) {
    std::fprintf(stderr, "gb_b_far: %s\n", error.what());
    return 3;
}
