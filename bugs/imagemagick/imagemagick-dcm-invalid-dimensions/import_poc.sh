#!/usr/bin/env bash
# Import AGF crash input into poc/poc.bin and verify against the bundled harness.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
O2_PROJ="/Users/kylekim/Desktop/TAMU/Thesis/O2_Vulnerability_Management/projects/imagemagick/dcm-decoder-invalid-dimensions"
SRC="${1:-}"

pick_input() {
  local src="$1"
  if [[ -f "$src" ]]; then
    printf '%s\n' "$src"
    return
  fi
  if [[ -d "$src" ]]; then
    find "$src" -type f \( -iname '*.bin' -o -iname '*.dcm' -o -iname 'crash*' -o -iname 'id:*' \) -size +0c \
      | while read -r f; do
          wc -c <"$f" | tr -d ' '
          printf '\t%s\n' "$f"
        done \
      | sort -n | head -1 | cut -f2
    return
  fi
  return 1
}

if [[ -z "$SRC" ]]; then
  if [[ -f "$O2_PROJ/crash_input.bin" ]]; then
    SRC="$O2_PROJ/crash_input.bin"
  elif [[ -d "$O2_PROJ/trajectory" ]]; then
    SRC="$O2_PROJ/trajectory"
  else
    echo "usage: $0 [trajectory-folder-or-crash-file]" >&2
    echo "  download: https://drive.google.com/drive/folders/1u6ltj7vSVi06bhddzUxO8NKyRnzWr4Nf" >&2
    exit 1
  fi
fi

INPUT="$(pick_input "$SRC" || true)"
if [[ -z "$INPUT" || ! -f "$INPUT" ]]; then
  echo "error: no crash input found under $SRC" >&2
  exit 1
fi

mkdir -p "$ROOT/poc"
cp "$INPUT" "$ROOT/poc/poc.bin"
echo "copied -> $ROOT/poc/poc.bin ($(wc -c <"$ROOT/poc/poc.bin") bytes)"

HARNESS="$ROOT/binaries/release-asan/harness"
if [[ ! -x "$HARNESS" ]]; then
  echo "warning: build harness first (docker build . && extract binaries)" >&2
  exit 0
fi

echo "=== grade smoke (linux harness; run 'make regression' on Linux after import) ==="
"$HARNESS" "$ROOT/poc/poc.bin" 2>&1 || true
