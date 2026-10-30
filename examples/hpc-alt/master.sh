#!/usr/bin/env bash
# Step 1: open a persistent SSH master to the cluster (interactive, password + Duo, once).
# Run this in YOUR OWN terminal. The connection then stays up in the background and
# the other scripts reuse its socket (~/.ssh/cm/<cluster>.sock) with no re-auth.
#   HPC_USER=your_user HPC_HOST=login.example.org bash master.sh
set -euo pipefail
CLUSTER="${CLUSTER:-cluster}"; U="${HPC_USER:?Set HPC_USER to your cluster username}"
: "${HPC_HOST:?Set HPC_HOST to your cluster login hostname}"
mkdir -p ~/.ssh/cm
# Remove a stale socket left by a reboot (nothing answering on it).
for s in ~/.ssh/cm/*.sock; do [ -S "$s" ] && ! pgrep -f -- "-S $s" >/dev/null && rm -f "$s"; done
ssh -M -S ~/.ssh/cm/${CLUSTER}.sock -fN \
    -o ControlPersist=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new \
    "${U}@${HPC_HOST}"
echo "master up. check:"; ssh -S ~/.ssh/cm/${CLUSTER}.sock -O check "${U}@${HPC_HOST}"
