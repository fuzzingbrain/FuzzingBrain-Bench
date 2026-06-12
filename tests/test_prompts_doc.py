"""Guards that prompts stay centralized and the generated catalog never drifts.

- docs/PROMPTS.md must match what tools/gen_prompts_md.py would write from
  fbbench/prompts.py (so the readable catalog can't go stale).
- every registered prompt must carry a non-empty when/why (so the catalog is
  always documented).
- no model-facing prose should be hand-written back into the runner modules.
"""
from __future__ import annotations

import re
from pathlib import Path

from fbbench import prompts

REPO = Path(__file__).resolve().parents[1]


def test_prompts_md_in_sync():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gen_prompts_md", REPO / "tools" / "gen_prompts_md.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    cur = (REPO / "docs" / "PROMPTS.md").read_text()
    assert cur == gen.render(), \
        "docs/PROMPTS.md is stale — run `python tools/gen_prompts_md.py`"


def test_every_prompt_documented():
    reg = prompts.registry()
    assert reg, "no prompts registered"
    ids = [p.id for p in reg]
    assert len(ids) == len(set(ids)), "duplicate prompt id"
    for p in reg:
        assert p.when.strip(), f"{p.id}: empty 'when'"
        assert p.why.strip(), f"{p.id}: empty 'why'"
        assert p.text.strip(), f"{p.id}: empty text"


def test_no_inline_nudges_in_runner():
    # The mid-episode nudges must come from prompts.py, not be re-hardcoded.
    epi = (REPO / "fbbench" / "runner" / "episode.py").read_text()
    for marker in ("Do NOT stop.", "was cut off before any tool call",
                   "[Budget: turn "):
        assert marker not in epi, \
            f"inline prompt text {marker!r} leaked back into episode.py"


def test_fullscan_system_prompt_is_as_sent():
    # The catalog must show the EXACT full-scan system prompt the model receives,
    # not just the un-rewritten fragments. derived_prompts() computes it from the
    # builder; assert it equals what episode.run_episode sends (system_prompt(True)).
    derived = {p.id: p.text for p in prompts.derived_prompts()}
    assert "system_prompt_fullscan_assembled" in derived
    assert derived["system_prompt_fullscan_assembled"] == prompts.system_prompt(full_scan=True)
    # and it must actually be in the rendered catalog
    md = (REPO / "docs" / "PROMPTS.md").read_text()
    assert prompts.system_prompt(full_scan=True) in md, \
        "full-scan system prompt (as sent) is not shown verbatim in PROMPTS.md"


def test_diffscan_prompt_centralized():
    # The diff-scan first-turn prompt must come from prompts.build_diffscan_message,
    # not be re-hardcoded in the diff-scan tooling.
    lib = (REPO / "tools" / "diffscan_lib.py").read_text()
    for marker in ("DIFF-SCAN MODE", "A recent pull request modified",
                   "memory-safety crash (overflow"):
        assert marker not in lib, \
            f"diff-scan prompt text {marker!r} leaked back into diffscan_lib.py"
    assert "build_diffscan_message" in lib, \
        "diffscan_lib.py should delegate to prompts.build_diffscan_message"
