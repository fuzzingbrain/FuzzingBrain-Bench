# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=f23fcd33052c7c8a307eaa3e1b1a4c0cdcf45651
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

# hunspell builds with autotools (autoreconf needs autoconf/automake/libtool/
# gettext/autopoint). clang + the matching compiler-rt provide the libFuzzer and
# AddressSanitizer runtimes.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        build-essential autoconf automake libtool \
        gettext autopoint pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/hunspell/hunspell /src/hunspell \
 && git -C /src/hunspell checkout ${VULN_COMMIT}

COPY harness/hunspell_hashmgr_dic_loader_fuzzer.cc /src/harness/hunspell_hashmgr_dic_loader_fuzzer.cc
COPY harness/build.sh                              /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
