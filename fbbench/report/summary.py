"""Build a self-contained, answer-free sweep summary page.

After a sweep, :func:`write_summary` injects a params+results blob into
``summary_template.html`` and writes ``<output>/index.html`` — a double-clickable
matrix of every (bug x model) cell, each linking to that episode's own report.

ANSWER SAFETY: the summary reads only each cell's ``score.json`` (its own crash
signatures + cost + terminated reason). It never opens an answer artifact of
any kind, and emits no bug class or crash location. Crash
signatures are the AGENT's findings, distilled from harness output it had
already seen; they say what it hit, never what it was supposed to hit.
"""
from __future__ import annotations

from fbbench.runner.latency import pool as pool_latency
from fbbench.sweep.orchestrator import cell_dir

import json
import re
from pathlib import Path

_TEMPLATE = Path(__file__).with_name("summary_template.html")
_DIFFICULTY = Path(__file__).with_name("difficulty.json")


def _load_difficulty() -> tuple[dict[str, list[int]], int, int]:
    """Load and validate the frozen challenge-by-discovery-position matrix."""
    data = json.loads(_DIFFICULTY.read_text())
    matrix, cap = data["difficulty"], data["cap"]
    if type(cap) is not int or cap < 1 or not matrix:
        raise ValueError("Invalid difficulty matrix or scoring cap")
    for challenge, weights in matrix.items():
        if (not isinstance(weights, list) or len(weights) < cap
                or any(type(w) is not int or not 1 <= w <= 5 for w in weights)
                or weights != sorted(weights)):
            raise ValueError(f"Invalid position weights for {challenge}")
    maximum = sum(sum(weights[:cap]) for weights in matrix.values())
    if maximum != data["max_score"]:
        raise ValueError("Difficulty matrix maximum does not match metadata")
    return matrix, cap, maximum


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _image_pattern(image: str, alias: str) -> str:
    """One challenge's image ref with its own alias collapsed to a placeholder.

    A sweep runs 68 different images, so their full refs never agree and reporting
    "mixed" would be useless. Replacing just the alias leaves exactly what they DO
    share — registry, repository and tag —

        docker.io/osanzas/fbbench-agent-<alias>:latest
        -> docker.io/osanzas/fbbench-agent-<alias>:latest

    so a sweep whose challenges came from one place shows one value, and one that
    mixed registries or tags still says "mixed" honestly.

    The name, not the tag: since :latest became the self-contained image the tag
    says nothing about how a run was graded, and `grading` reports that from what
    the run observed. What the name still answers is "which artifact produced
    this", which is the reproducibility question.
    """
    named = image.replace(alias, "<alias>") if alias else image
    return named if ":" in named.rpartition("/")[2] else named + ":latest (implicit)"


def _scan_dimensions(exp_dir: Path) -> tuple[list[str], list[str], list[int]]:
    """Infer (bugs, models, samples) from the on-disk cell tree."""
    bugs, models, samples = [], set(), set()
    for bug_dir in sorted(p for p in exp_dir.iterdir() if p.is_dir()):
        has_cell = False
        for model_dir in sorted(p for p in bug_dir.iterdir() if p.is_dir()):
            for seed_dir in model_dir.iterdir():
                if seed_dir.name.startswith("seed-") and (seed_dir / "score.json").is_file():
                    has_cell = True
                    models.add(model_dir.name)
                    try:
                        samples.add(int(seed_dir.name.split("-", 1)[1]))
                    except ValueError:
                        pass
        if has_cell:
            bugs.append(bug_dir.name)
    return bugs, sorted(models), sorted(samples)


def build_summary(exp_dir: str | Path, *, exp: str | None = None,
                  models: list[str] | None = None, bugs: list[str] | None = None,
                  samples: list[int] | None = None, max_turns: int = 0,
                  total_cost: float | None = None, elapsed_s: float = 0.0) -> dict:
    exp_dir = Path(exp_dir)
    s_bugs, s_models, s_samples = _scan_dimensions(exp_dir)
    bugs = bugs or s_bugs
    models = models or s_models
    samples = samples if samples is not None else s_samples

    difficulty, cap, corpus_max = _load_difficulty()

    cells = []
    cost_sum = 0.0
    scores_by_model: dict[str, list[dict]] = {}   # for the pooled latency
    cfg_seen: dict[str, set] = {}     # config key -> set of values seen across cells
    # The crash signatures seen, unioned across a pair's samples and across a
    # challenge's models. Counted on the UNION, not summed from the cells: two
    # samples that produced the same signature found one crash, and summing the
    # per-cell answers would count it twice.
    pair_sigs: dict[tuple[str, str], set[str]] = {}
    challenge_sigs: dict[str, set[str]] = {}
    for bug in bugs:
        for model in models:
            for sample in samples:
                # the one place that decides a cell's path, so the summary
                # looks where the run actually wrote
                cd = cell_dir(exp_dir, bug, model, sample)
                sj = cd / "score.json"
                if not sj.is_file():
                    continue
                sc = _load(sj)
                scores_by_model.setdefault(model, []).append(sc)
                lat = sc.get("latency") or {}
                cost = float(sc.get("total_usd") or 0.0)
                cost_sum += cost
                cfg = sc.get("config") or {}
                for k, v in cfg.items():
                    if isinstance(v, (list, dict)):
                        continue
                    cfg_seen.setdefault(k, set()).add(v)
                # Derived, and it has to be derived HERE: every bug has its own
                # image, so the full refs never agree — it is the tag they share.
                if cfg.get("image"):
                    # Under its own key: the generic loop above already collected
                    # the 68 raw refs under "image", and adding the pattern there
                    # would make every sweep disagree with itself.
                    cfg_seen.setdefault("image_pattern", set()).add(
                        _image_pattern(cfg["image"], bug))
                report = cd / "report.html"
                sigs = sorted(sc.get("crash_signatures") or [])
                pair_sigs.setdefault((bug, model), set()).update(sigs)
                challenge_sigs.setdefault(bug, set()).update(sigs)
                cells.append({
                    "bug": bug, "model": model, "sample": sample,
                    "crashes": int(sc.get("unique_crashes", 0)),
                    # The signatures behind that count (crash type + top frames),
                    # so the page can dedupe across seeds and show WHAT was hit
                    # rather than only how many. The agent's own findings — see
                    # the answer-safety note at the top of this module.
                    "sigs": sigs,
                    "difficulty_weights": difficulty.get(bug, [])[:cap],
                    "cost": cost,
                    "mode": cfg.get("mode") or sc.get("mode") or "blind",
                    "reason": sc.get("terminated_reason", ""),
                    "lat_p50": lat.get("p50_s"),
                    "lat_mean": lat.get("mean_s"),
                    "report": (str(report.relative_to(exp_dir)) if report.is_file() else ""),
                })

    # Sweep-level run config: a value if every cell agrees, else "mixed".
    def _agree(key, default=None):
        vals = cfg_seen.get(key)
        if not vals:
            return default
        return next(iter(vals)) if len(vals) == 1 else "mixed"

    config = {
        "mode": _agree("mode", "blind"),
        "max_turns": _agree("max_turns", max_turns),
        "timeout_s": _agree("timeout_s"),
        "stop_on_crash": _agree("stop_on_crash"),
        "preserve_pocs": _agree("preserve_pocs"),
        # No default: a sweep whose cells disagree, or that recorded nothing,
        # should say so rather than inherit a claim about how it was graded.
        "grading": _agree("grading"),
        # WHICH ARTIFACT produced these numbers. Not the tag: the tag no longer
        # selects a grading mode (see fbbench.images), so a bare "latest" would
        # answer nothing a reader needs. A sweep whose bugs pin their own images
        # reads "mixed", which is true.
        "image": _agree("image_pattern"),
    }

    # Per (challenge, model): the union across that pair's samples. Keyed with a
    # separator no alias or model id contains, so the page can look a pair up
    # without shipping a nested map.
    pairs = {
        f"{b} {m}": {
            "crashes": len(sm),
            "weighted_score": (sum(difficulty[b][:min(len(sm), cap)])
                               if b in difficulty else None),
        }
        for (b, m), sm in sorted(pair_sigs.items())
    }
    # Sweep headline: per challenge, the union across every model. Two models
    # that produced the same signature reached ONE crash on that challenge —
    # summing the per-model answers would report two.
    totals = {
        "crashes": sum(len(sm) for sm in challenge_sigs.values()),
        "challenges_with_crashes": sum(1 for sm in challenge_sigs.values() if sm),
    }

    # Sum the weights of the credited discovery positions. A partial run's
    # denominator sums those same positions over the challenges it ran.
    scores = {}
    for model in models:
        ran = [b for b in bugs if (b, model) in pair_sigs]
        scored = [b for b in ran if difficulty.get(b)]
        scores[model] = {
            "scored": sum(sum(difficulty[b][:min(len(pair_sigs[(b, model)]), cap)])
                          for b in scored),
            "max": sum(sum(difficulty[b][:cap]) for b in scored),
            "challenges_run": len(ran),
            # Ran, but no matrix row: the challenge post-dates the frozen table.
            # Counted nowhere rather than silently scored 0, and named so a
            # shrinking denominator cannot be mistaken for a worse model.
            "unscored": sorted(set(ran) - set(scored)),
        }
    # Totals are only comparable when every model faced the same challenges.
    comparable = len({frozenset(b for b in bugs if (b, m) in pair_sigs)
                      for m in models}) <= 1

    return {
        "exp": exp or exp_dir.name,
        # What this page reports: `crashes` = the distinct crash signatures the
        # agent produced, deduped over the samples and models that share a cell.
        "pairs": pairs,
        "totals": totals,
        "models": models,
        "bugs": bugs,
        "samples": samples,
        "max_turns": max_turns,
        "config": config,
        "total_cost": total_cost if total_cost is not None else cost_sum,
        "elapsed_s": elapsed_s,
        # Per-model difficulty-weighted score, each over its own denominator.
        "scores": scores,
        # Per-model model response latency, pooled over every call of its cells.
        "latency": {m: pool_latency(scores_by_model.get(m, [])) for m in models},
        "comparable": comparable,
        # The frozen matrix this run was scored against: the position weights for
        # THIS run's challenges, the per-challenge cap, and the whole-corpus
        # ceiling for context.
        "difficulty": {b: difficulty[b] for b in bugs if difficulty.get(b)},
        "cap": cap,
        "corpus_max": corpus_max,
        "cells": cells,
    }


def write_summary(exp_dir: str | Path, **meta) -> Path:
    """Build the summary and write <exp_dir>/index.html (self-contained)."""
    exp_dir = Path(exp_dir)
    data = build_summary(exp_dir, **meta)
    out = exp_dir / "index.html"
    if not data.get("elapsed_s"):
        # A re-render (--report-only) does not know how long the sweep took;
        # keep the figure the original page recorded rather than dropping it.
        m = re.search(r'"elapsed_s": ([0-9.]+)', out.read_text()) if out.exists() else None
        if m:
            data["elapsed_s"] = float(m.group(1))
    tmpl = _TEMPLATE.read_text()
    # Inject as the textContent of <script type="application/json">; escape the
    # only sequence that could close that tag early. The blob is answer-free.
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = (tmpl.replace("__SUMMARY_JSON__", blob)
                .replace("__EXP__", data["exp"]))
    out.write_text(html)
    return out
