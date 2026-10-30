#!/usr/bin/env bash
# Cancel one forward tunnel. Usage: ./tunnel-down.sh <NODE> <REMOTE_PORT> [LOCAL_PORT]
set -euo pipefail
CLUSTER="${CLUSTER:-cluster}"; U="${HPC_USER:?Set HPC_USER to your cluster username}"
: "${HPC_HOST:?Set HPC_HOST to your cluster login hostname}"
SOCK=~/.ssh/cm/${CLUSTER}.sock; H="${U}@${HPC_HOST}"
NODE="${1:?need node}"; RPORT="${2:?need remote port}"; LPORT="${3:-8300}"
ssh -S "$SOCK" -O cancel -L "${LPORT}:${NODE}:${RPORT}" "$H"
echo "tunnel down: localhost:${LPORT} -> ${NODE}:${RPORT}"
