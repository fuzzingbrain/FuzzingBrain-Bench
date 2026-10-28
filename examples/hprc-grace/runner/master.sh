#!/usr/bin/env bash
# Step 1: open a persistent SSH master to the cluster (interactive, password + 2FA, once).
# Run this in YOUR OWN terminal. The connection then stays up in the background and
# the other scripts reuse its socket (~/.ssh/cm/<cluster>.sock) with no re-auth.
#   CLUSTER=grace HPRC_USER=your_netid bash master.sh
set -euo pipefail
CLUSTER="${CLUSTER:-grace}"; U="${HPRC_USER:-YOUR_NETID}"
mkdir -p ~/.ssh/cm
# Remove a stale socket left by a reboot (nothing answering on it).
for s in ~/.ssh/cm/*.sock; do [ -S "$s" ] && ! pgrep -f -- "-S $s" >/dev/null && rm -f "$s"; done
ssh -M -S ~/.ssh/cm/${CLUSTER}.sock -fN \
    -o ControlPersist=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new \
    "${U}@${CLUSTER}.hprc.tamu.edu"
echo "master up. check:"; ssh -S ~/.ssh/cm/${CLUSTER}.sock -O check "${U}@${CLUSTER}.hprc.tamu.edu"
