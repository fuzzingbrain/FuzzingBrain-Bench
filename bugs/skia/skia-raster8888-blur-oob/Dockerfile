# syntax=docker/dockerfile:1.6
#
# =============================================================================
# KNOWN GAP / BUILD-SIZE RISK (see NOTES.md):
#   Skia is a very large build. `tools/git-sync-deps` pulls multiple GB of
#   third_party sources and a bundled clang; the GN/Ninja build of `skia` is
#   long-running and memory-hungry. This Dockerfile encodes the faithful build
#   path but was NOT executed/validated in this benchmark copy (NO docker / NO
#   compile per task brief). It may be infeasible to build in a standard CI box;
#   the entry's binaries could not be validated. The harness, PoC, grader, and
#   source-line claims are authored from the verified O2 source record and a
#   line-by-line check of the chromium-vendored skia tree (see PROVENANCE.md).
# =============================================================================
FROM debian:bookworm-slim
ARG VULN_COMMIT=d3ea842c93e59fec607736bd605f77216264483e
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        build-essential python3 curl pkg-config \
        ninja-build \
    && rm -rf /var/lib/apt/lists/*

# NOTE: the rolled chromium-vendored skia revision d3ea842c... may not be
# resolvable from the public skia.googlesource.com shallow CDN (it was a
# chromium DEPS roll point). If the exact SHA cannot be fetched, the closest
# reachable skia main commit that still contains the unpatched
# eval_blur_passes X->Y rebind getAddr should be used; the fix landed in
# CL 1225736 (commit d2740c899a1ec8a22209840bd8350f22f8c27ecf), so any commit
# strictly before that on skia/main carries the bug. See NOTES.md.
RUN git clone https://skia.googlesource.com/skia /src/skia \
 && (git -C /src/skia checkout ${VULN_COMMIT} \
     || echo "WARN: ${VULN_COMMIT} not fetchable; pin to a pre-fix skia/main commit (see NOTES.md)")

COPY harness/skia_image_filter_chain_construction_fuzzer.cc /src/harness/skia_image_filter_chain_construction_fuzzer.cc
COPY harness/build.sh                                       /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
