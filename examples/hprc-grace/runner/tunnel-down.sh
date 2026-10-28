#!/usr/bin/env bash
# Cancel one forward tunnel. Usage: ./tunnel-down.sh <NODE> <REMOTE_PORT> [LOCAL_PORT]
set -euo pipefail
CLUSTER="${CLUSTER:-grace}"; U="${HPRC_USER:-YOUR_NETID}"
SOCK=~/.ssh/cm/${CLUSTER}.sock; H="${U}@${CLUSTER}.hprc.tamu.edu"
NODE="${1:?need node}"; RPORT="${2:?need remote port}"; LPORT="${3:-8300}"
ssh -S "$SOCK" -O cancel -L "${LPORT}:${NODE}:${RPORT}" "$H"
echo "tunnel down: localhost:${LPORT} -> ${NODE}:${RPORT}"
