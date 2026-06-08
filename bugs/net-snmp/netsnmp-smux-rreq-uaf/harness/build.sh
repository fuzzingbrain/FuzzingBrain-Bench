#!/bin/bash
# Build script for netsnmp-smux-rreq-uaf.
#
# Unlike netsnmp-vacm-parse-npd (which only builds snmplib), the SMUX harness
# exercises the SNMP *agent* and the smux mibgroup. It links internal smux_*
# symbols (smux_accept / smux_process / smux_parse_peer_auth / ...), so the
# agent must be configured WITH the smux mibgroup compiled in.
#
# Strategy: build net-snmp twice (asan, coverage), each time configuring the
# agent with mibgroup=smux, then link the libFuzzer harness per config against
# the agent + mibs + base libraries.
#
# Usage:
#   build.sh build-libs        # builds both library/agent trees, called once
#   build.sh harness <config>  # links the harness for one config
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"

# Configure flags shared by both library builds. The smux mibgroup is added on
# top of the default mib_modules so smux_* symbols are available to link.
CONFIGURE_FLAGS=(
    --disable-shared --enable-static
    --disable-manuals --disable-scripts
    --without-openssl --with-defaults
    --with-mib-modules=smux
)

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)
    unset MAKEFLAGS MFLAGS

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) CF="-fsanitize=address -g -O1"; LF="-fsanitize=address" ;;
            cov)  CF="-fprofile-instr-generate -fcoverage-mapping -g -O0"; LF="-fprofile-instr-generate -fcoverage-mapping" ;;
        esac

        cp -r /src/net-snmp /src/build-${CONFIG_LIB}
        pushd /src/build-${CONFIG_LIB} >/dev/null
        env CC=clang CFLAGS="${CF}" LDFLAGS="${LF}" \
            ./configure "${CONFIGURE_FLAGS[@]}"
        # Build snmplib, the agent libraries, and the mib modules (smux lives
        # in agent/mibgroup/smux). Building the full agent tree resolves the
        # internal smux_* symbols the harness references via extern.
        make -j${JOBS}
        popd >/dev/null
    done
    echo "net-snmp agent libs built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        debug)        CFH="-g -O0"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address" ;;
        debug-asan)   CFH="-g -O0"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address" ;;
        release-asan) CFH="-O2 -g"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address" ;;
        coverage)     CFH="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; BUILD=/src/build-cov; SAN="-fsanitize=fuzzer" ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    # Link order: agent (smux mibgroup) -> mibs -> helpers -> base library.
    # NOTE: exact .a paths/names may need adjustment to the configured tree
    # (see NOTES.md) — net-snmp emits libnetsnmpagent / libnetsnmpmibs /
    # libnetsnmphelpers / libnetsnmp under */.libs/.
    clang ${CFH} ${SAN} -fmacro-prefix-map=/src/= \
        -I "${BUILD}/include" \
        -I "${BUILD}/agent/mibgroup" \
        /src/harness/snmp_agent_e2e_fuzzer.c \
        "$(find ${BUILD} -name libnetsnmpagent.a|head -1)" \
        "$(find ${BUILD} -name libnetsnmpmibs.a|head -1)" \
        "$(find ${BUILD} -name libnetsnmp.a|head -1)" \
        -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
