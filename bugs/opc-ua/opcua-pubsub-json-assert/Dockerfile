# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=0b75ea2c5a78e72dc3c04302be7ec3546a556958
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        cmake make build-essential pkg-config python3 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/open62541/open62541 /src/open62541 \
 && git -C /src/open62541 checkout ${VULN_COMMIT} \
 && git -C /src/open62541 submodule update --init --recursive

COPY harness/fuzz_pubsub_json.cc /src/harness/fuzz_pubsub_json.cc
COPY harness/build.sh            /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

# Coverage config omitted: reach grades via the libFuzzer crash backtrace
# (the assert -> abort prints a symbolized stack), so no llvm-cov build is needed.
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan

RUN ls -la /out/*/harness
