# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=1a3e1e05b71e15197f7decc451a2f650ff2ee591
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        build-essential cmake pkg-config \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Pin to the parent of the fix merge (PR #28620 / merge 8e1fa1bbd) for
# issue #28619 — opencv master at clone time is already patched.
RUN git clone --filter=blob:none https://github.com/opencv/opencv /src/opencv \
 && git -C /src/opencv checkout ${VULN_COMMIT}

COPY harness/ /src/harness/
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
