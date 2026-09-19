#!/usr/bin/env bash
# Bootstrap FuzzingBrain-Bench. One command, no assumptions about the machine.
#
#   ./setup.sh
#
# Creates .venv beside this file, installs the pinned dependency set, and puts
# `fb-bench` inside it. Nothing to activate, nothing installed globally.
#
# What this cannot supply, and what you still need:
#   - Docker, running, with permission to pull images and start containers
#   - a model API key in .env (ANTHROPIC_API_KEY=... / OPENAI_API_KEY=...)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

py="${PYTHON:-python3}"
command -v "$py" >/dev/null || { echo "setup: no '$py' on PATH. Install Python 3.10+ (or set PYTHON=/path/to/python3)." >&2; exit 1; }
"$py" - <<'PY' || { echo "setup: fb-bench needs Python 3.10 or newer." >&2; exit 1; }
import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
echo "setup: using $("$py" -V) at $(command -v "$py")"

if [ ! -x .venv/bin/python ]; then
  echo "setup: creating .venv"
  "$py" -m venv .venv || { echo "setup: could not create a venv. On Debian/Ubuntu: apt install python3-venv" >&2; exit 1; }
fi

echo "setup: installing pinned dependencies"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.lock
# --no-deps: requirements.lock is the whole set; letting pip re-resolve here
# would drift off the pins the recorded cells were produced on.
.venv/bin/python -m pip install --quiet --no-deps -e .


echo "setup: verifying"
.venv/bin/python -c "import fbbench, yaml, anthropic; print('  imports ok')"
.venv/bin/fb-bench --help >/dev/null 2>&1 && echo "  fb-bench entry point ok" || {
  echo "setup: fb-bench did not start. Report this with the output above." >&2; exit 1; }
if docker info >/dev/null 2>&1; then echo "  docker ok"; else
  echo "  WARNING: docker is not reachable — the bench cannot run challenges without it"; fi

cat <<'DONE'

setup: done.

  Run the test suite:  .venv/bin/python -m pytest tests -q
  Run one challenge:   .venv/bin/fb-bench run libavif-01 --arm api --model claude-opus-5

  Agent arms (optional): see fbbench/agent_tools/README.md for the tool image,
  and docs/external-agents.md for running an agent of your own.

DONE
