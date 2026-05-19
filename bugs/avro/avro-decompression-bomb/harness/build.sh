#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"

HARNESS_DIR=/src/harness
JAVA_SUBDIR=/src/avro/lang/java/avro

if [ "${cmd}" = "build-libs" ]; then
    cd "${JAVA_SUBDIR}"
    # avro-java module only; skip tests; offline-tolerant best-effort.
    mvn -B -q -DskipTests -Dcheckstyle.skip -Dspotless.check.skip=true package
    JAR=$(find "${JAVA_SUBDIR}/target" -maxdepth 1 -name 'avro-*.jar' \
        -not -name '*sources*' -not -name '*javadoc*' -not -name '*tests*' \
        | head -1)
    test -n "${JAR}"
    cp "${JAR}" /src/avro-java.jar
    # Resolve transitive runtime deps to /src/deps/
    mkdir -p /src/deps
    mvn -B -q dependency:copy-dependencies \
        -DoutputDirectory=/src/deps -DincludeScope=runtime -Dmdep.useBaseVersion=true
    echo "built avro java jar: ${JAR}"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    LIB=/out/lib
    mkdir -p "${OUT}" "${LIB}/classes" "${LIB}/deps"

    if [ ! -f "${LIB}/classes/PocRunner.class" ]; then
        cp /src/avro-java.jar "${LIB}/avro-java.jar"
        cp /src/deps/*.jar "${LIB}/deps/" 2>/dev/null || true
        # Build classpath glob: avro jar + all deps
        CP="${LIB}/avro-java.jar:${LIB}/deps/*"
        javac -d "${LIB}/classes" \
            -cp "${CP}" \
            "${HARNESS_DIR}/DecompressionBombFuzzer.java" \
            "${HARNESS_DIR}/PocRunner.java"
    fi

    cat > "${OUT}/harness" <<'EOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
LIB="${DIR}/../lib"
# -Xmx256m: keep heap small so the decompression bomb hits OOM fast.
exec java -Xmx256m \
    -cp "${LIB}/classes:${LIB}/avro-java.jar:${LIB}/deps/*" \
    -DtargetClass=DecompressionBombFuzzer \
    PocRunner "$@"
EOF
    chmod +x "${OUT}/harness"
    echo "built ${OUT}/harness"
    exit 0
fi
exit 2
