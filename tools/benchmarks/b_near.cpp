// E1b target-side workload B_near.
//
// Role: the PREDICTIVE case. Branchy integer work over a small, cache-resident table,
// which is the shape an SM83 interpreter will have. It is deliberately similar in
// character to the calibration workload A, and deliberately not identical to it: a
// different mixing function, a different table width, and a different branch structure,
// so that a favourable result cannot be an artefact of comparing A against a copy of
// itself.
//
// Its partner B_far is the robustness case. The two are never pooled in analysis.
//
// CONDITIONS
//
//   null : kBaseIterations
//   reg  : kBaseIterations * 105 / 100, computed in integer arithmetic
//
// kBaseIterations is divisible by 100, so the regressed count is exact with no rounding.
// The injection is defined on ITERATION COUNT, which is 1.05x the specified kernel work.
// It is NOT a claim of a 1.05x wall-clock multiplier: the realised runtime effect is
// measured by the driver's S diagnostic and is not assumed.
//
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
//
// This is a tool, not the core, so ADR 0001 (toolchain) B13's header denylist does not
// apply here.

#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <vector>

namespace {

constexpr std::uint64_t kBaseIterations = 120'000'000; // divisible by 100
constexpr std::size_t kTableBits = 12;                 // 4096 entries
constexpr std::size_t kTableSize = std::size_t{1} << kTableBits;
constexpr std::uint64_t kSeed = 0x9E3779B97F4A7C15ULL;

std::uint64_t regressed_iterations() {
    // Exact by construction: kBaseIterations is divisible by 100, so the integer
    // division below loses nothing.
    return kBaseIterations / 100 * 105;
}

std::vector<std::uint32_t> build_table() {
    std::vector<std::uint32_t> table(kTableSize);
    std::uint64_t state = kSeed;
    for (std::size_t i = 0; i < kTableSize; ++i) {
        // splitmix64, distinct from A's xorshift so the two workloads are not the
        // same kernel wearing different constants.
        state += 0x9E3779B97F4A7C15ULL;
        std::uint64_t z = state;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        z = z ^ (z >> 31);
        table[i] = static_cast<std::uint32_t>(z);
    }
    return table;
}

std::uint64_t run_kernel(const std::vector<std::uint32_t>& table, std::uint64_t iterations) {
    std::uint64_t state = kSeed;
    std::uint64_t checksum = 0;

    for (std::uint64_t i = 0; i < iterations; ++i) {
        state = state * 6364136223846793005ULL + 1442695040888963407ULL; // LCG

        const std::size_t index = static_cast<std::size_t>(state >> 40) & (kTableSize - 1);
        const std::uint32_t value = table[index];

        // Three-way data-dependent branch: a denser dispatch shape than A's two-way,
        // and unpredictable by construction.
        switch (value & 3U) {
        case 0:
            checksum += value;
            break;
        case 1:
            // Widened before the multiply, not after: multiplying in 32 bits and
            // letting the result widen implicitly is a real ambiguity about where the
            // wrap was intended, and clang-tidy is right to flag it.
            checksum ^= static_cast<std::uint64_t>(value) * 3U;
            break;
        default:
            checksum -= value ^ static_cast<std::uint32_t>(state);
            break;
        }
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
        std::fprintf(stderr, "usage: gb_b_near [--condition null|reg] [--runs N]\n");
        return 2;
    }

    const std::uint64_t iterations = regressed ? regressed_iterations() : kBaseIterations;
    const std::vector<std::uint32_t> table = build_table();

    std::vector<std::int64_t> timings_ns;
    timings_ns.reserve(static_cast<std::size_t>(runs));

    std::uint64_t checksum = 0;
    bool checksum_stable = true;

    for (long run = 0; run < runs; ++run) {
        const auto started = std::chrono::steady_clock::now();
        const std::uint64_t result = run_kernel(table, iterations);
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
    std::printf("  \"workload\": \"b_near\",\n");
    std::printf("  \"condition\": \"%s\",\n", regressed ? "reg" : "null");
    std::printf("  \"iterations\": %llu,\n", static_cast<unsigned long long>(iterations));
    std::printf("  \"table_entries\": %llu,\n", static_cast<unsigned long long>(kTableSize));
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
    std::fprintf(stderr, "gb_b_near: %s\n", error.what());
    return 3;
}
