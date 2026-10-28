#!/usr/bin/env bash
# Add one forward tunnel to the existing master. Usage: ./tunnel-up.sh <NODE> <REMOTE_PORT> [LOCAL_PORT]
set -euo pipefail
CLUSTER="${CLUSTER:-grace}"; U="${HPRC_USER:-YOUR_NETID}"
SOCK=~/.ssh/cm/${CLUSTER}.sock; H="${U}@${CLUSTER}.hprc.tamu.edu"
NODE="${1:?need node, e.g. g027}"; RPORT="${2:?need remote port, e.g. 8000}"; LPORT="${3:-8300}"
ssh -S "$SOCK" -O check "$H"
ssh -S "$SOCK" -O forward -L "${LPORT}:${NODE}:${RPORT}" "$H"
echo "tunnel up: localhost:${LPORT} -> ${NODE}:${RPORT}"
curl -s "http://localhost:${LPORT}/v1/models" | head -c 400; echo
