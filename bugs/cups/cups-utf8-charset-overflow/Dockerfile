# cups-utf8-charset-overflow — heap OOB read in cupsUTF8ToCharset (transcode.c)
FROM debian:bookworm-slim
ARG VULN_COMMIT=2e818010c9cda04649c872646dd3b90686e309ab
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git clang make pkg-config zlib1g-dev libavahi-client-dev libssl-dev \
        autoconf automake libclang-rt-14-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/OpenPrinting/cups /src/cups \
    && git -C /src/cups checkout ${VULN_COMMIT}
COPY harness/fuzz_transcode.cc /src/harness/fuzz_transcode.cc
COPY harness/build.sh          /src/harness/build.sh
RUN chmod +x /src/harness/build.sh
RUN /src/harness/build.sh build-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage \
 && ls -la /out/*/harness
