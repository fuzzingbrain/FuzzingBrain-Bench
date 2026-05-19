# syntax=docker/dockerfile:1.6
FROM debian:bookworm-slim
ARG VULN_COMMIT=4502c1ba1c453702fd26966a5e5c10441e0d1384
ARG SOURCE_DATE_EPOCH=1735689600
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl tar \
    && rm -rf /var/lib/apt/lists/*

# avro at this commit enforces JDK 21+ via maven-enforcer-plugin.
# Pull Eclipse Temurin 21.
RUN curl -fsSL "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.5%2B11/OpenJDK21U-jdk_x64_linux_hotspot_21.0.5_11.tar.gz" \
    -o /tmp/jdk.tgz \
 && tar -C /opt -xzf /tmp/jdk.tgz \
 && ln -sf /opt/jdk-21.0.5+11 /opt/jdk21 \
 && rm /tmp/jdk.tgz

# avro (since the rewrite to 1.13+ parent POM) enforces Maven 3.9+.
RUN curl -fsSL https://archive.apache.org/dist/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.tar.gz \
    -o /tmp/mvn.tgz \
 && tar -C /opt -xzf /tmp/mvn.tgz \
 && ln -sf /opt/apache-maven-3.9.9/bin/mvn /usr/local/bin/mvn \
 && rm /tmp/mvn.tgz

ENV JAVA_HOME=/opt/jdk21
ENV PATH=/opt/jdk21/bin:${PATH}

# Avro's parent POM enforces a JDK 11 toolchain via maven-toolchains-plugin.
# Debian ships JDK 17; satisfy the toolchain probe by claiming the local
# JDK is JDK 11 — Avro Java is source/target compatible with 17.
RUN mkdir -p /root/.m2 \
 && printf '%s\n' \
    '<?xml version="1.0" encoding="UTF-8"?>' \
    '<toolchains>' \
    '  <toolchain>' \
    '    <type>jdk</type>' \
    '    <provides><version>11</version><vendor>openjdk</vendor></provides>' \
    '    <configuration><jdkHome>/opt/jdk21</jdkHome></configuration>' \
    '  </toolchain>' \
    '  <toolchain>' \
    '    <type>jdk</type>' \
    '    <provides><version>17</version><vendor>openjdk</vendor></provides>' \
    '    <configuration><jdkHome>/opt/jdk21</jdkHome></configuration>' \
    '  </toolchain>' \
    '  <toolchain>' \
    '    <type>jdk</type>' \
    '    <provides><version>21</version><vendor>openjdk</vendor></provides>' \
    '    <configuration><jdkHome>/opt/jdk21</jdkHome></configuration>' \
    '  </toolchain>' \
    '</toolchains>' > /root/.m2/toolchains.xml

# avro mono-repo (Java is one subdir; we only build lang/java/avro)
RUN git clone --filter=blob:none https://github.com/apache/avro /src/avro \
 && git -C /src/avro checkout ${VULN_COMMIT}

COPY harness/ /src/harness/
RUN chmod +x /src/harness/build.sh

RUN /src/harness/build.sh build-libs
RUN mkdir -p /out \
 && /src/harness/build.sh harness debug \
 && /src/harness/build.sh harness debug-asan \
 && /src/harness/build.sh harness release-asan \
 && /src/harness/build.sh harness coverage

RUN ls -la /out /out/lib /out/release-asan/harness
