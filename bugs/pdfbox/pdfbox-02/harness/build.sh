#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"

HARNESS_DIR=/src/harness
PDFBOX_ROOT=/src/pdfbox

if [ "${cmd}" = "build-libs" ]; then
    cd "${PDFBOX_ROOT}"
    # InlineImage requires the full pdfbox module (pdmodel.graphics.image).
    mvn -B -q -DskipTests -Dcheckstyle.skip -Dspotless.check.skip=true \
        -pl pdfbox -am install
    JAR=$(find "${PDFBOX_ROOT}/pdfbox/target" -maxdepth 1 -name 'pdfbox-*.jar' \
        -not -name '*sources*' -not -name '*javadoc*' -not -name '*tests*' \
        | head -1)
    test -n "${JAR}"
    cp "${JAR}" /src/pdfbox.jar
    mkdir -p /src/deps
    mvn -B -q -pl pdfbox dependency:copy-dependencies \
        -DoutputDirectory=/src/deps -DincludeScope=runtime -Dmdep.useBaseVersion=true
    echo "built pdfbox jar"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    LIB=/out/lib
    mkdir -p "${OUT}" "${LIB}/classes" "${LIB}/deps"

    if [ ! -f "${LIB}/classes/PocRunner.class" ]; then
        cp /src/pdfbox.jar "${LIB}/pdfbox.jar"
        cp /src/deps/*.jar "${LIB}/deps/" 2>/dev/null || true
        CP="${LIB}/pdfbox.jar:${LIB}/deps/*"
        javac -d "${LIB}/classes" -encoding utf-8 \
            -cp "${CP}" \
            "${HARNESS_DIR}/InlineImageFuzzer.java" \
            "${HARNESS_DIR}/PocRunner.java"
    fi

    cat > "${OUT}/harness" <<'EOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
LIB="${DIR}/../lib"
exec java -Xmx256m \
    -cp "${LIB}/classes:${LIB}/pdfbox.jar:${LIB}/deps/*" \
    -DtargetClass=InlineImageFuzzer \
    PocRunner "$@"
EOF
    chmod +x "${OUT}/harness"
    echo "built ${OUT}/harness"
    exit 0
fi
exit 2
