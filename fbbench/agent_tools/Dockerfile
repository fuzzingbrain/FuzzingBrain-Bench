# The agent toolbox: tools the AGENT arms get and the bare api arm does not.
#
# Built once, published once, pulled by every machine that runs the benchmark.
# Nothing here is compiled on a user's machine and nothing is committed to the
# repo -- the image IS the artefact, and its digest is what makes two runs on
# two machines comparable.
#
#   docker build -t <registry>/fbbench-agent-tools:v1 fbbench/agent_tools/
#   docker push  <registry>/fbbench-agent-tools:v1
#   export FBBENCH_AGENT_TOOLS_IMAGE=<registry>/fbbench-agent-tools@sha256:...
#
# Everything under /tools/bin must be STATICALLY linked: these are bind-mounted
# into 78 different challenge images, Debian and OSS-Fuzz based, with different
# library versions. A binary that borrows anything from its host will start on
# some challenges and not others, which is the worst failure mode available.
#
# ALPINE, not Debian. This is the whole reason: Alpine's C library (musl) treats
# self-contained binaries as the normal case, while Debian's (glibc) resists
# being baked in -- parts of it load more pieces at runtime and cannot be made
# static at all. Five attempts on Debian shed expat, gmp and mpfr and still could
# not shake libc, libm and libstdc++. Same gdb source, same flags; the
# foundation is what changed.
#
# A musl-built gdb debugging a glibc-built harness is fine -- gdb inspects the
# target from outside and shares nothing with it. The one thing it gives up is
# detailed thread debugging on a glibc target, which breakpoints, backtraces and
# `info args` do not need.
FROM alpine:3.20 AS build

ARG GDB_VERSION=14.2

RUN apk add --no-cache \
        build-base wget tar xz \
        zlib-dev zlib-static \
        texinfo bison flex \
        linux-headers

WORKDIR /src
RUN wget -q "https://ftp.gnu.org/gnu/gdb/gdb-${GDB_VERSION}.tar.xz" \
    && tar xf "gdb-${GDB_VERSION}.tar.xz"

# Alpine has no gmp-static/mpfr-static packages, and the -dev ones ship only
# shared libraries -- the first Alpine build shed libc, libm and libstdc++ and
# was left holding exactly these two. Built from source into a private prefix
# so the only copies gdb can find there are archives.
ARG GMP_VERSION=6.3.0
ARG MPFR_VERSION=4.2.1
RUN cd /src \
    && wget -q "https://ftp.gnu.org/gnu/gmp/gmp-${GMP_VERSION}.tar.xz" \
    && wget -q "https://ftp.gnu.org/gnu/mpfr/mpfr-${MPFR_VERSION}.tar.xz" \
    && tar xf gmp-${GMP_VERSION}.tar.xz && tar xf mpfr-${MPFR_VERSION}.tar.xz \
    && cd gmp-${GMP_VERSION} \
    && ./configure --prefix=/opt/static --disable-shared --enable-static \
    && make -j4 && make install \
    && cd ../mpfr-${MPFR_VERSION} \
    && ./configure --prefix=/opt/static --disable-shared --enable-static --with-gmp=/opt/static \
    && make -j4 && make install \
    && ls /opt/static/lib

# --without-python: CPython cannot be linked statically in any way worth
#   shipping. It costs pretty-printers and gdb scripting; breakpoints,
#   backtraces, `info args` and memory inspection are unaffected.
# --without-expat: XML target descriptions, unused here, one less dependency.
# --disable-tui / --without-curses: the agent drives gdb with -batch, never
#   interactively.
RUN mkdir /build && cd /build \
    && CC="gcc -static" CXX="g++ -static" \
       LDFLAGS="-static -L/opt/static/lib" CFLAGS="-O2" CXXFLAGS="-O2" \
       ../src/gdb-${GDB_VERSION}/configure \
        --disable-shared --enable-static \
        --without-python --without-expat \
        --disable-tui --without-curses \
        --disable-source-highlight --disable-werror \
        --with-static-standard-libraries \
        --with-gmp=/opt/static --with-mpfr=/opt/static \
    && make -j4 all-gdb

# gdb does not link itself with the compiler -- it links through libtool:
#
#   CC_LD  = $(LIBTOOL) --mode=link $(CXX)
#   gdb:     $(CC_LD) $(INTERNAL_LDFLAGS) -o gdb ...
#
# and to libtool `-static` does NOT mean "produce a self-contained executable".
# It means "prefer static libtool archives when resolving -l flags", and libtool
# consumes it rather than passing it to the compiler. That is why five builds
# oscillated -- musl libc dynamic, then libstdc++ dynamic, then musl again --
# depending on which layer a forced -static reached. Nothing was wrong with the
# toolchain or with Alpine; the flag was being addressed to the wrong program.
#
# libtool's flag for a genuinely self-contained executable is `-all-static`.
# Passing it at configure time would break configure, which link-tests with the
# compiler directly and would reject an option gcc does not have -- so the flag
# belongs on the final link and nowhere else.
RUN cd /build/gdb \
    && rm -f gdb \
    && make gdb LDFLAGS="-all-static -L/opt/static/lib" \
    && strip gdb

# Refuse to ship a binary that borrows anything. It would work here and fail on
# the 33 challenge images with no debugger -- a failure nobody would attribute
# to the toolbox.
#
# NOT ldd: on Alpine ldd IS the musl loader, and it prints
# "libc.musl-x86_64.so.1 => /lib/ld-musl-x86_64.so.1" even for a fully static
# binary. Four builds were rejected on that false positive. A dynamic
# executable carries an INTERP program header naming its loader; a static one
# has none, so readelf answers the question ldd cannot.
RUN readelf -l /build/gdb/gdb | grep -q "INTERP" \
    && { echo "REFUSING: gdb needs a loader and will not run everywhere" >&2; exit 1; } \
    || echo "static: no INTERP header"
RUN /build/gdb/gdb --version | head -1 && ls -lh /build/gdb/gdb | awk '{print "size:", $5}'

FROM scratch
COPY --from=build /build/gdb/gdb /tools/bin/gdb
