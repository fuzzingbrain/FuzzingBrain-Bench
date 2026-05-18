# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim

ARG VULN_COMMIT=d44baeb67ac21b3ff23ede8d103c21c8830ea8dd
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates \
        clang libclang-rt-14-dev \
        build-essential autoconf automake libtool pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/jqlang/jq /src/jq \
 && git -C /src/jq checkout ${VULN_COMMIT}

COPY harness/jq_fuzz_compile.c /src/harness/jq_fuzz_compile.c
COPY harness/build.sh          /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
