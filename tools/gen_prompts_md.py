#!/usr/bin/env python3
"""Generate docs/PROMPTS.md from fbbench/prompts.py — the single source.

Every prompt is registered in prompts.py with `when` (the situation it is sent
in) and `why` (the business reason); this renders them into a readable catalog so
the team can review all model-facing text in one place. The .md is a generated
VIEW — never hand-edit it; edit prompts.py and re-run:

    PYTHONPATH=. python tools/gen_prompts_md.py        # write docs/PROMPTS.md
    PYTHONPATH=. python tools/gen_prompts_md.py --check # exit 1 if out of date

tests/test_prompts_doc.py runs --check so the doc can never drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fbbench.prompts import derived_prompts, registry

_OUT = Path(__file__).resolve().parents[1] / "docs" / "PROMPTS.md"

_HEADER = (
    "# FuzzingBrain-Bench — model-facing prompts\n\n"
    "**Auto-generated from `fbbench/prompts.py` by `tools/gen_prompts_md.py`. "
    "Do NOT edit by hand** — edit `prompts.py` and re-run the generator "
    "(`tests/test_prompts_doc.py` fails if this file is stale).\n\n"
    "Every string the benchmark sends to a model lives in `prompts.py`; each is "
    "listed below with **when** it is used and **why** (the business reason). "
    "Fixed prompts show their full text; dynamic ones show the template with "
    "`{placeholders}` for the per-episode values (description, setup() payload, "
    "file list, turn counts) substituted at runtime. The final **Assembled "
    "prompts** section shows the exact as-sent text for prompts the runner builds "
    "from several fragments, computed from the real builders so it cannot drift.\n"
)


def _render_entry(out: list[str], p) -> None:
    out.append(f"\n## `{p.id}`\n")
    out.append(f"- **When**: {p.when}")
    out.append(f"- **Why**: {p.why}")
    if p.fills:
        out.append(f"- **Type**: dynamic — fills `{p.fills}`")
    else:
        out.append("- **Type**: fixed")
    out.append("\n```\n" + p.text + "\n```\n")


def render() -> str:
    out = [_HEADER]
    prompts = registry()
    derived = derived_prompts()
    # table of contents
    out.append("\n## Index\n")
    for p in prompts:
        kind = "dynamic" if p.fills else "fixed"
        out.append(f"- [`{p.id}`](#{p.id.replace('.', '').replace('_', '-')}) — {kind}")
    for p in derived:
        out.append(f"- [`{p.id}`](#{p.id.replace('.', '').replace('_', '-')}) — assembled")
    out.append("\n---\n")
    for p in prompts:
        _render_entry(out, p)
    out.append("\n---\n")
    out.append("\n# Assembled prompts (exact text as sent)\n")
    out.append(
        "These are not single registry strings — the runner builds them from the "
        "fragments above. Shown here as the exact text the model receives, computed "
        "from the builder functions so this section can never drift from runtime.\n")
    for p in derived:
        _render_entry(out, p)
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    text = render()
    check = "--check" in sys.argv[1:]
    if check:
        cur = _OUT.read_text() if _OUT.exists() else ""
        if cur != text:
            print(f"OUT OF DATE: {_OUT} differs from prompts.py — "
                  f"run `python tools/gen_prompts_md.py`", file=sys.stderr)
            return 1
        print(f"up to date: {_OUT}")
        return 0
    _OUT.write_text(text)
    print(f"wrote {_OUT} ({len(registry())} prompts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
