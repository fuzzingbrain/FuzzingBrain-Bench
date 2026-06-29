"""Render a self-contained HTML report for one finished episode.

After a run, ``report.html`` lands next to ``score.json`` / ``traj.md`` and can
be opened straight in a browser — no server. It reads the run dir's
``score.json``, ``cost.json``, and ``transcript.jsonl`` and lays out, in the
GitHub-dark style of the AGF reports:

* a header with the bug / model / sanitizer / language tags,
* hero stats (tier score, turns, tool calls, cost),
* the capability ladder (reach -> crash -> differential -> class -> site),
* cards for token / cost breakdown, per-tool call counts, and run metadata,
* the full trajectory table (every tool call, its argument and result, with
  the grade() calls and the faulting call highlighted).

Everything the report shows is answer-free: it is the record of what the agent
did, which never includes the oracle's PoC / expected fault / location.
"""
from __future__ import annotations

import json
from pathlib import Path

from fbbench.runner.traj import build_traj

LADDER = ["reach", "crash", "differential", "class", "site"]
_LADDER_LABEL = {"reach": "reach", "crash": "crash", "differential": "differential",
                 "class": "class", "site": "site"}


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _tool_stats(nodes: list[dict]) -> list[tuple[str, int, int]]:
    """(tool, calls, errors) per tool, most-used first."""
    agg: dict[str, list[int]] = {}
    for n in nodes:
        row = agg.setdefault(n["tool"], [0, 0])
        row[0] += 1
        if not n["ok"]:
            row[1] += 1
    return sorted(((t, c, e) for t, (c, e) in agg.items()), key=lambda r: -r[1])


def _ladder_html(caps: dict, kb: list[str]) -> str:
    cells = []
    for k in LADDER:
        applicable = (not kb) or (k in kb)
        state = caps.get(k)
        if not applicable or state == "n/a":
            cls, glyph = "na", "·"
        elif state == "fired":
            cls, glyph = "fired", "●"
        else:
            cls, glyph = "miss", "○"
        cells.append(
            f'<div class="rung {cls}"><div class="g">{glyph}</div>'
            f'<div class="k">{_LADDER_LABEL[k]}</div></div>'
        )
    return '<div class="ladder">' + '<div class="arrow">→</div>'.join(cells) + "</div>"


def _stat(n: str, label: str, cls: str = "") -> str:
    return f'<div class="stat"><div class="n {cls}">{n}</div><div class="l">{_esc(label)}</div></div>'


def build_report_html(run_dir: Path) -> str:
    score = _load(run_dir / "score.json")
    cost = _load(run_dir / "cost.json")
    tpath = run_dir / "transcript.jsonl"
    nodes = build_traj(tpath) if tpath.is_file() else []

    bug = score.get("bug_id", run_dir.parent.parent.name if run_dir.name.startswith("seed")
                     else run_dir.name)
    model = score.get("model", "—")
    caps = score.get("capabilities", {})
    tier = score.get("tier_score", 0)
    reason = score.get("terminated_reason", "—")
    turns = score.get("turns_used", 0)
    dur = score.get("duration_s", 0.0)
    usd = score.get("total_usd", cost.get("total_usd", 0.0))
    err = score.get("error", "")

    # capability_set + sanitizer / language come from the transcript start event.
    kb: list[str] = []
    sanitizer = language = ""
    if tpath.is_file():
        for line in tpath.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("event") == "start":
                kb = sorted(e.get("capability_set", []) or [])
                break

    grades = [n for n in nodes if n["tool"] == "grade"]
    faults = [n for n in grades if n["crash"]]
    tool_rows = _tool_stats(nodes)

    in_tok = cost.get("input_tokens", 0)
    out_tok = cost.get("output_tokens", 0)
    cache_r = cost.get("cache_read_tokens", 0)

    tags = []
    if language:
        tags.append(language)
    if sanitizer:
        tags.append(sanitizer)
    tags.append("full-scan" if score.get("full_scan") else "described")
    tag_html = "".join(f'<span class="tag">{_esc(t)}</span>' for t in tags)

    solved = bool(caps) and all(caps.get(k) == "fired" for k in (kb or LADDER))
    verdict_cls = "g" if solved else ("r" if reason == "error" else "a")

    # ---- trajectory rows ----
    traj_rows = []
    for n in nodes:
        mark = "💥" if n["crash"] else ("✗" if not n["ok"] else "")
        rcls = "crash" if n["crash"] else ("err" if not n["ok"] else "")
        traj_rows.append(
            f'<tr class="{rcls}"><td class="r">{n["n"]}</td><td class="r">{n["turn"]}</td>'
            f'<td><code>{_esc(n["tool"])}</code></td>'
            f'<td class="arg">{_esc(n["arg"])}</td>'
            f'<td class="out">{_esc(n["out"])}</td>'
            f'<td class="mk">{mark}</td></tr>'
        )

    tool_rows_html = "".join(
        f'<tr><td><code>{_esc(t)}</code></td><td class="r">{c}</td>'
        f'<td class="r">{e or ""}</td></tr>'
        for t, c, e in tool_rows
    )

    err_card = (
        f'<div class="note">Episode ended in <b>error</b>: <code>{_esc(err)}</code></div>'
        if err else ""
    )

    return _TEMPLATE.format(
        bug=_esc(bug), model=_esc(model), tags=tag_html,
        tier=tier, verdict_cls=verdict_cls,
        turns=turns, ncalls=len(nodes), usd=f"{usd:.4f}",
        ladder=_ladder_html(caps, kb),
        reason=_esc(reason), dur=f"{dur:.1f}",
        refus=score.get("refusal_retries", 0), malf=score.get("malformed_retries", 0),
        in_tok=f"{in_tok:,}", out_tok=f"{out_tok:,}", cache_r=f"{cache_r:,}",
        in_usd=f'{cost.get("input_usd", 0.0):.4f}',
        out_usd=f'{cost.get("output_usd", 0.0):.4f}',
        ngrades=len(grades), nfaults=len(faults),
        tool_rows=tool_rows_html or '<tr><td colspan="3" class="muted">no tool calls</td></tr>',
        traj_rows="".join(traj_rows) or '<tr><td colspan="6" class="muted">no trajectory</td></tr>',
        err_card=err_card,
    )


def write_report(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    html = build_report_html(run_dir)
    out = run_dir / "report.html"
    out.write_text(html)
    return out


_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{bug} · {model} — FB·Bench run report</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--card2:#1c2230;--line:#2a3038;--txt:#e6edf3;
--muted:#8b949e;--accent:#58a6ff;--green:#3fb950;--amber:#d29922;--red:#f85149;--purple:#bc8cff;}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);line-height:1.55;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}}
.wrap{{max-width:1080px;margin:0 auto;padding:44px 24px 80px;}}
header h1{{font-size:1.9rem;margin:0 0 6px;letter-spacing:-.02em;}}
header h1 .m{{color:var(--accent);}}
.sub{{color:var(--muted);font-size:1rem;}}
.tag{{display:inline-block;font-size:.72rem;background:#1f6feb22;color:var(--accent);
border:1px solid #1f6feb55;border-radius:20px;padding:3px 11px;margin-right:6px;}}
h2{{font-size:1.25rem;margin:48px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line);}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0 8px;}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 16px;text-align:center;}}
.stat .n{{font-size:2rem;font-weight:700;letter-spacing:-.02em;}}
.stat .n.g{{color:var(--green)}}.stat .n.a{{color:var(--accent)}}.stat .n.r{{color:var(--red)}}.stat .n.p{{color:var(--purple)}}
.stat .l{{color:var(--muted);font-size:.82rem;margin-top:2px;}}
.ladder{{display:flex;align-items:center;gap:6px;margin:18px 0 4px;flex-wrap:wrap;}}
.ladder .arrow{{color:var(--muted);font-size:1.1rem;}}
.rung{{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 18px;text-align:center;min-width:108px;}}
.rung .g{{font-size:1.5rem;line-height:1;}}
.rung .k{{font-size:.8rem;color:var(--muted);margin-top:5px;}}
.rung.fired{{border-color:#2386364d;background:#23863618;}}.rung.fired .g{{color:var(--green);}}
.rung.miss .g{{color:#46506080;}}
.rung.na{{opacity:.4;}}.rung.na .g{{color:var(--muted);}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;}}
.card h3{{margin:0 0 10px;font-size:.95rem;}}
table{{width:100%;border-collapse:collapse;font-size:.88rem;}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top;}}
th{{color:var(--muted);font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;}}
td.r{{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap;}}
td.mk{{text-align:center;}}td.muted,.muted{{color:var(--muted);}}
code{{background:#0d1117;border:1px solid var(--line);border-radius:4px;padding:0 5px;font-size:.9em;color:#ff7b72;}}
.mini td{{padding:5px 8px;}}.mini td:first-child{{font-weight:600;}}
.traj td.arg{{color:var(--muted);font-family:ui-monospace,monospace;font-size:.82rem;word-break:break-all;}}
.traj td.out{{font-family:ui-monospace,monospace;font-size:.82rem;color:#9da7b3;word-break:break-all;}}
.traj tr.crash td{{background:#f8514915;}}.traj tr.crash td.mk{{color:var(--red);}}
.traj tr.err td.out{{color:var(--amber);}}
.note{{background:#f8514915;border:1px solid #f8514944;border-radius:10px;padding:11px 15px;color:#ffa198;font-size:.88rem;margin:16px 0;}}
.foot{{color:var(--muted);font-size:.8rem;margin-top:48px;border-top:1px solid var(--line);padding-top:16px;}}
@media(max-width:760px){{.stats,.grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body><div class="wrap">

<header>
<div style="margin-bottom:10px">{tags}</div>
<h1>{bug} <span class="m">· {model}</span></h1>
<div class="sub">FuzzingBrain&nbsp;Bench — single-episode run report</div>
</header>

{err_card}

<div class="stats">
  <div class="stat"><div class="n {verdict_cls}">{tier}/5</div><div class="l">tier score</div></div>
  <div class="stat"><div class="n">{turns}</div><div class="l">turns used</div></div>
  <div class="stat"><div class="n a">{ncalls}</div><div class="l">tool calls</div></div>
  <div class="stat"><div class="n p">${usd}</div><div class="l">total cost</div></div>
</div>

<h2>Capability ladder</h2>
{ladder}

<h2>Breakdown</h2>
<div class="grid">
  <div class="card"><h3>Tokens &amp; cost</h3>
    <table class="mini">
      <tr><td>input</td><td class="r">{in_tok} tok</td><td class="r">${in_usd}</td></tr>
      <tr><td>output</td><td class="r">{out_tok} tok</td><td class="r">${out_usd}</td></tr>
      <tr><td>cache read</td><td class="r">{cache_r} tok</td><td class="r"></td></tr>
      <tr><td><b>total</b></td><td class="r"></td><td class="r">${usd}</td></tr>
    </table>
  </div>
  <div class="card"><h3>Tool calls</h3>
    <table><thead><tr><th>tool</th><th class="r">calls</th><th class="r">err</th></tr></thead>
    <tbody>{tool_rows}</tbody></table>
  </div>
  <div class="card"><h3>Run</h3>
    <table class="mini">
      <tr><td>terminated</td><td class="r">{reason}</td></tr>
      <tr><td>duration</td><td class="r">{dur}s</td></tr>
      <tr><td>grade() calls</td><td class="r">{ngrades}</td></tr>
      <tr><td>faulting grades</td><td class="r">{nfaults}</td></tr>
      <tr><td>refusal retries</td><td class="r">{refus}</td></tr>
      <tr><td>malformed retries</td><td class="r">{malf}</td></tr>
    </table>
  </div>
</div>

<h2>Trajectory</h2>
<table class="traj"><thead><tr><th class="r">#</th><th class="r">turn</th><th>tool</th>
<th>argument</th><th>result</th><th></th></tr></thead>
<tbody>{traj_rows}</tbody></table>

<div class="foot">Generated by FuzzingBrain&nbsp;Bench · the report records the agent's own
actions only — no oracle PoC, expected fault, or crash location is ever included.</div>

</div></body></html>
"""
