#!/usr/bin/env bash
# Open the persistent SSH control connection used by the tunnel.
set -euo pipefail

DTAI_USER=${DTAI_USER:?set DTAI_USER to the NCSA username}
DTAI_LOGIN=${DTAI_LOGIN:-dtai-login.delta.ncsa.illinois.edu}
SOCK=${DTAI_SOCK:-$HOME/.ssh/cm/deltaai.sock}

mkdir -p "$(dirname "$SOCK")"
if [ -S "$SOCK" ] && ! ssh -S "$SOCK" -O check "$DTAI_USER@$DTAI_LOGIN" >/dev/null 2>&1; then
  rm -f -- "$SOCK"
fi

ssh -M -S "$SOCK" -fN \
  -o ControlPersist=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -o StrictHostKeyChecking=accept-new \
  "$DTAI_USER@$DTAI_LOGIN"

ssh -S "$SOCK" -O check "$DTAI_USER@$DTAI_LOGIN"
