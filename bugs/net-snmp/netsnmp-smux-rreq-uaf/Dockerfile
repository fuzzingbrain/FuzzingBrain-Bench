# syntax=docker/dockerfile:1.6
#
# Per-bug reproducibility build for netsnmp-smux-rreq-uaf.
# Reuses the netsnmp-vacm-parse-npd Dockerfile structure (same net-snmp repo);
# differs only in vuln_commit, harness source, and the agent/smux build.
FROM debian:bookworm-slim
ARG VULN_COMMIT=1852fec16
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates clang libclang-rt-14-dev \
        build-essential autoconf automake libtool pkg-config \
        perl \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/net-snmp/net-snmp /src/net-snmp \
 && git -C /src/net-snmp checkout ${VULN_COMMIT}

COPY harness/snmp_agent_e2e_fuzzer.c /src/harness/snmp_agent_e2e_fuzzer.c
COPY harness/build.sh                /src/harness/build.sh
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out/*/harness
