# syntax=docker/dockerfile:1.6
#
# Per-bug reproducibility build for krb5-import-name-assert.
FROM gcr.io/oss-fuzz-base/base-builder
ARG VULN_COMMIT=340253c
ARG SOURCE_DATE_EPOCH=1780092000
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV LIB_FUZZING_ENGINE="-fsanitize=fuzzer"
RUN apt-get update && apt-get install -y --no-install-recommends \
        autoconf \
        bison \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/krb5/krb5 /src/krb5 \
 && git -C /src/krb5 checkout ${VULN_COMMIT}
COPY harness/fuzz_gss.c  /src/krb5/src/tests/fuzzing/fuzz_gss.c
COPY harness/build.sh    /src/harness/build.sh
RUN chmod +x /src/harness/build.sh
RUN find / -name libFuzzingEngine.a 2>/dev/null
RUN env | grep FUZZ
RUN echo $LIB_FUZZING_ENGINE
RUN mkdir -p /out \
 && /src/harness/build.sh debug \
 && /src/harness/build.sh debug-asan \
 && /src/harness/build.sh release-asan \
 && /src/harness/build.sh coverage
RUN ls -la /out/*/harness
