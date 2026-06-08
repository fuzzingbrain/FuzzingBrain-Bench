# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=adca75ad5d978fde166d18efedee039e36394c8f
ARG JSONCPP_TAG=1.9.4
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        make build-essential python3 \
    && rm -rf /var/lib/apt/lists/*

# Bug is in bundled jsoncpp; openscreen pins jsoncpp 1.9.4
# (third_party/jsoncpp/README.chromium at VULN_COMMIT).
RUN git clone --depth 1 -b ${JSONCPP_TAG} \
        https://github.com/open-source-parsers/jsoncpp /src/jsoncpp

COPY harness/repro_jsoncpp_array_string_index.cc /src/harness/repro_jsoncpp_array_string_index.cc
COPY harness/build.sh                            /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs

RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
