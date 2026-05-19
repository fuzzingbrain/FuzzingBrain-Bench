# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=d0418739c27fe95b0d38fc6aa2e3cb22b7ac1cee
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        build-essential cmake pkg-config \
        libssl-dev zlib1g-dev libicu-dev \
    && rm -rf /var/lib/apt/lists/*

ENV GIT_TERMINAL_PROMPT=0
RUN git clone --depth 1 https://github.com/FreeRDP/FreeRDP /src/freerdp \
 && git -C /src/freerdp fetch --depth 1 origin ${VULN_COMMIT} \
 && git -C /src/freerdp checkout ${VULN_COMMIT}

COPY harness/TestFuzzNTLMMessage.c /src/harness/TestFuzzNTLMMessage.c
COPY harness/build.sh              /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
