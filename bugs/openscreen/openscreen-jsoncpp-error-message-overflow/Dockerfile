# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
# jsoncpp SHA chromium/openscreen vendored at fuzz time (post-1.9.4).
ARG VULN_COMMIT=42e892d96e47b1f6e29844cc705e148ec4856448
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        make build-essential python3 \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/open-source-parsers/jsoncpp /src/jsoncpp \
 && git -C /src/jsoncpp checkout ${VULN_COMMIT}

COPY harness/repro_jsoncpp_cr_oob.cc /src/harness/repro_jsoncpp_cr_oob.cc
COPY harness/build.sh                /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
