# One thin layer on top of a published JVM agent image: jdb and the jdb-run driver.
#
#   docker build -f tools/jdb/Dockerfile \
#     --build-arg BASE=docker.io/osanzas/fbbench-agent-json-java-02:latest \
#     --build-arg JDK_VERSION=17.0.20.1+1-1~deb12u1 \
#     -t docker.io/osanzas/fbbench-agent-json-java-02:latest  tools/jdb
#
# JDK_VERSION is the image's own openjdk-17-jre-headless version (build_images.sh
# reads it from the base), so the JDK comes from the same build and the JRE that
# runs the harness is not upgraded: a golden PoC produces the same signature as before.
ARG BASE
FROM ${BASE}
ARG JDK_VERSION
# The JDK brings javac, jshell, jar and two dozen other tools along with jdb. Only
# jdb is the change: every command the package added is removed again, so the
# agent's toolbox differs from the published image by exactly one debugger.
RUN set -e; before=$(dpkg-query -W -f='${Version}' openjdk-17-jre-headless); \
    test "$before" = "${JDK_VERSION}"; \
    J=$(dirname "$(dirname "$(readlink -f "$(command -v java)")")"); \
    ls "$J/bin" > /tmp/bin.before; ls /usr/bin > /tmp/usrbin.before; \
    apt-get update; \
    apt-get install -y --no-install-recommends "openjdk-17-jdk-headless=${JDK_VERSION}"; \
    rm -rf /var/lib/apt/lists/*; \
    test "$(dpkg-query -W -f='${Version}' openjdk-17-jre-headless)" = "$before"; \
    for t in $(ls "$J/bin" | grep -vxF -f /tmp/bin.before); do [ "$t" = jdb ] || rm -f "$J/bin/$t"; done; \
    for t in $(ls /usr/bin | grep -vxF -f /tmp/usrbin.before); do [ "$t" = jdb ] || rm -f "/usr/bin/$t"; done; \
    rm -f /tmp/bin.before /tmp/usrbin.before; \
    command -v jdb; ! command -v javac; ! command -v jshell
COPY jdb-run /usr/local/bin/jdb-run
# jdb wants source roots (the directory a package path starts from), not files.
# Derived from each .java file's own package line, so non-Maven layouts (mx suites) work too.
RUN chmod 0755 /usr/local/bin/jdb-run && mkdir -p /opt/fbbench-jdb \
 && find /challenge/harness /challenge/src -name '*.java' -print0 2>/dev/null \
    | xargs -0 -r grep -m1 -H '^package ' 2>/dev/null \
    | sed -n 's#^\(.*\)/[^/]*\.java:package \([A-Za-z0-9_.]*\).*#\1 \2#p' \
    | awk '{p=$2; gsub(/\./,"/",p); d=$1; if (p!="" && substr(d,length(d)-length(p)+1)==p) print substr(d,1,length(d)-length(p)-1)}' \
    | sort -u > /tmp/roots \
 && { echo /challenge/harness; cat /tmp/roots; } | paste -sd: > /opt/fbbench-jdb/sourcepath \
 && rm -f /tmp/roots && chmod 0644 /opt/fbbench-jdb/sourcepath
