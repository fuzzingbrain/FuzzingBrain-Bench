#!/usr/bin/env python3
"""Render a FuzzingBrain Bench episode transcript.jsonl as a standalone HTML view.

Input  : a transcript.jsonl produced by the runner (full-fidelity log:
         system prompt, initial user message, every assistant turn with its
         tool-call arguments, and every tool return verbatim).
Output : a single self-contained .html file (inline CSS/JS, no external deps) —
         open it directly in a browser.

Usage:
    python tools/transcript_view.py <transcript.jsonl> [-o out.html]
    python tools/transcript_view.py <run-dir>           # finds transcript.jsonl

If a score.json / cost.json sits next to the transcript, their headline numbers
are folded into the summary banner.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys


# ----------------------------------------------------------------------------- io

def load_jsonl(path: str) -> list[dict]:
    out = []
    with open(path) as fp:
        for line in fp:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_json(path: str) -> dict | None:
    try:
        with open(path) as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------------- render

def esc(s) -> str:
    return html.escape(s if isinstance(s, str) else json.dumps(s, ensure_ascii=False))


def pretty(obj) -> str:
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, indent=2, ensure_ascii=False)


def tool_badge(name: str) -> str:
    return f'<span class="tool tool-{esc(name)}">{esc(name)}</span>'


def render_grade_result(result: dict) -> str:
    """grade returns {harness_output:{stdout,stderr,exit_code,signal}} (model-facing)."""
    ho = result.get("harness_output", result)
    rows = []
    for k in ("exit_code", "signal"):
        if k in ho:
            rows.append(f'<span class="kv"><b>{k}</b> {esc(ho[k])}</span>')
    head = " ".join(rows)
    out = ""
    for stream in ("stdout", "stderr"):
        text = ho.get(stream, "")
        if text:
            out += f'<div class="stream-label">{stream}</div><pre class="stream">{esc(text)}</pre>'
    return f'<div class="grade-head">{head}</div>{out}'


def render_tool_result(ev: dict) -> str:
    tool = ev.get("tool", "")
    err = ev.get("is_error", False)
    inp = ev.get("input", {})
    result = ev.get("result", "")

    inp_html = ""
    if inp:
        inp_html = f'<div class="sub">args</div><pre class="args">{esc(pretty(inp))}</pre>'

    if tool == "grade" and isinstance(result, dict) and not err:
        body = render_grade_result(result)
    else:
        body = f'<pre class="result {"err" if err else ""}">{esc(pretty(result))}</pre>'

    cls = "result-card err" if err else "result-card"
    err_tag = '<span class="x">error</span>' if err else ""
    label = f'{tool_badge(tool)} {err_tag}'
    return f'''<details class="{cls}" open>
      <summary>{label}<span class="muted"> result</span></summary>
      {inp_html}{body}
    </details>'''


def render_assistant(ev: dict) -> str:
    turn = ev.get("turn", "?")
    text = ev.get("text", "") or ""
    ot = ev.get("output_tokens")
    calls = ev.get("tool_calls", [])

    tok = f'<span class="muted">· {ot} out-tok</span>' if ot is not None else ""
    text_html = f'<div class="think">{esc(text)}</div>' if text.strip() else \
        '<div class="think empty">(no visible reasoning text — provider returned tool calls only)</div>'

    calls_html = ""
    for tc in calls:
        calls_html += f'''<div class="callreq">{tool_badge(tc.get("name",""))}
          <pre class="args">{esc(pretty(tc.get("input", {})))}</pre></div>'''

    return f'''<div class="turn">
      <div class="turn-h"><span class="badge">turn {turn}</span> <span class="role">assistant</span> {tok}</div>
      {text_html}
      {calls_html}
    </div>'''


def render(transcript: list[dict], score: dict | None, cost: dict | None) -> str:
    start = next((e for e in transcript if e.get("event") == "start"), {})
    end = next((e for e in transcript if e.get("event") == "end"), {})

    bug = start.get("bug_id", "?")
    model = start.get("model", "?")
    kb = start.get("capability_set", [])
    sys_prompt = start.get("system_prompt", "")
    init_user = start.get("initial_user_message", "")
    tools = start.get("tools", [])

    # summary numbers
    n_calls: dict[str, int] = {}
    for e in transcript:
        if e.get("event") == "assistant":
            for tc in e.get("tool_calls", []):
                n_calls[tc.get("name", "?")] = n_calls.get(tc.get("name", "?"), 0) + 1
    caps = (score or end).get("capabilities", {})
    tier = (score or {}).get("tier_score")
    reason = (score or end).get("terminated_reason", "?")
    turns = (score or end).get("turns_used", "?")
    usd = (cost or score or {}).get("total_usd")
    solved = bool(kb) and all(caps.get(c) == "fired" for c in kb)

    cap_pills = " ".join(
        f'<span class="cap {("fired" if caps.get(c)=="fired" else "miss")}">{esc(c)}</span>'
        for c in (kb or ["reach", "crash", "class", "site"])
    )
    calls_pills = " ".join(f'{tool_badge(k)}<span class="n">×{v}</span>' for k, v in sorted(n_calls.items()))
    verdict = '<span class="v pass">SOLVED</span>' if solved else '<span class="v fail">NOT SOLVED</span>'

    # body events (skip start/end)
    body = []
    for e in transcript:
        ev = e.get("event")
        if ev == "assistant":
            body.append(render_assistant(e))
        elif ev == "tool_result":
            body.append(render_tool_result(e))
        elif ev == "retry":
            body.append(f'<div class="note retry">↻ retry ({esc(e.get("kind",""))}) turn {e.get("turn")} attempt {e.get("attempt")}</div>')
        elif ev == "truncation_continue":
            body.append(f'<div class="note">✂ truncated, nudged to continue (turn {e.get("turn")})</div>')

    tools_html = ""
    for t in tools:
        tools_html += f'<details class="tooldef"><summary>{tool_badge(t.get("name",""))} <span class="muted">{esc(t.get("description",""))}</span></summary><pre>{esc(pretty(t))}</pre></details>'

    usd_html = f' · ${usd:.2f}' if isinstance(usd, (int, float)) else ""
    tier_html = f'{tier}/{len(kb)}' if tier is not None and kb else "?"

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(bug)} · {esc(model)} · transcript</title>
<style>
:root {{ --bg:#0f1116; --card:#181b22; --card2:#1f232c; --line:#2a2f3a; --fg:#d6dae2;
  --muted:#8b93a3; --accent:#6ea8fe; --green:#3fb950; --red:#f85149; --amber:#d29922; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
.wrap {{ max-width:1000px; margin:0 auto; padding:24px 18px 120px; }}
header {{ position:sticky; top:0; z-index:5; background:rgba(15,17,22,.92);
  backdrop-filter:blur(6px); border-bottom:1px solid var(--line); margin:-24px -18px 18px; padding:14px 18px; }}
h1 {{ font-size:16px; margin:0 0 8px; font-weight:600; }}
h1 .sub {{ color:var(--muted); font-weight:400; }}
.bar {{ display:flex; flex-wrap:wrap; gap:6px 14px; align-items:center; font-size:12.5px; }}
.v.pass {{ color:var(--green); font-weight:700; }} .v.fail {{ color:var(--red); font-weight:700; }}
.cap {{ padding:1px 7px; border-radius:10px; font-size:11px; }}
.cap.fired {{ background:rgba(63,185,80,.18); color:var(--green); }}
.cap.miss {{ background:rgba(248,81,73,.15); color:var(--red); }}
.tool {{ padding:1px 6px; border-radius:5px; font-size:11.5px; background:var(--card2); color:var(--accent); }}
.tool-grade {{ color:#ffd166; }} .tool-exec {{ color:#a6e22e; }} .tool-write_file {{ color:#ff9aa2; }}
.n {{ color:var(--muted); font-size:11px; margin:0 8px 0 2px; }}
.kv b {{ color:var(--muted); font-weight:600; }} .kv {{ margin-right:12px; }}
details.meta {{ background:var(--card); border:1px solid var(--line); border-radius:8px; margin:8px 0; padding:6px 12px; }}
details.meta summary {{ cursor:pointer; color:var(--accent); }}
details.meta pre {{ white-space:pre-wrap; word-break:break-word; }}
.turn {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; margin:14px 0; }}
.turn-h {{ display:flex; gap:10px; align-items:center; margin-bottom:6px; }}
.badge {{ background:var(--accent); color:#06122b; font-weight:700; border-radius:6px; padding:1px 8px; font-size:11.5px; }}
.role {{ color:var(--muted); }} .muted {{ color:var(--muted); }}
.think {{ white-space:pre-wrap; word-break:break-word; margin:4px 0; }}
.think.empty {{ color:var(--muted); font-style:italic; }}
.callreq {{ margin:8px 0 0; padding:8px 10px; background:var(--card2); border-left:3px solid var(--accent); border-radius:0 6px 6px 0; }}
pre {{ margin:6px 0 0; padding:8px 10px; background:#0b0d12; border-radius:6px; overflow:auto;
  white-space:pre-wrap; word-break:break-word; font-size:12.5px; max-height:460px; }}
pre.args {{ background:#10141c; color:#c8d0dc; }}
.result-card {{ margin:8px 0 14px 26px; background:var(--card); border:1px solid var(--line);
  border-radius:8px; padding:6px 12px; }}
.result-card.err {{ border-color:var(--red); }}
.result-card summary {{ cursor:pointer; }}
.result-card .x {{ color:var(--red); font-weight:700; margin-left:6px; }}
.sub {{ color:var(--muted); font-size:11px; margin-top:6px; }}
.stream-label {{ color:var(--muted); font-size:11px; margin-top:8px; text-transform:uppercase; letter-spacing:.05em; }}
pre.stream {{ background:#08090d; }} pre.result.err {{ border-left:3px solid var(--red); }}
.grade-head {{ margin-top:6px; }}
.note {{ color:var(--amber); font-size:12px; margin:8px 0 8px 26px; }}
.tooldef {{ margin:4px 0; }} .tooldef summary {{ cursor:pointer; }}
.toolbar {{ margin-left:auto; }}
button {{ background:var(--card2); color:var(--fg); border:1px solid var(--line); border-radius:6px;
  padding:3px 9px; cursor:pointer; font:inherit; font-size:12px; }}
button:hover {{ border-color:var(--accent); }}
</style></head><body><div class="wrap">
<header>
  <h1>{esc(bug)} <span class="sub">· {esc(model)} · max_turns {esc(start.get("max_turns","?"))}</span></h1>
  <div class="bar">
    {verdict}
    <span class="kv"><b>tier</b> {tier_html}</span>
    <span>{cap_pills}</span>
    <span class="kv"><b>end</b> {esc(reason)}</span>
    <span class="kv"><b>turns</b> {esc(turns)}{usd_html}</span>
    <span class="toolbar"><button onclick="document.querySelectorAll('details.result-card,details.meta').forEach(d=>d.open=true)">expand all</button>
    <button onclick="document.querySelectorAll('details.result-card,details.meta').forEach(d=>d.open=false)">collapse</button></span>
  </div>
  <div class="bar" style="margin-top:6px">{calls_pills}</div>
</header>

<details class="meta"><summary>system prompt ({len(sys_prompt)} chars)</summary><pre>{esc(sys_prompt)}</pre></details>
<details class="meta"><summary>initial user message ({len(init_user)} chars)</summary><pre>{esc(init_user)}</pre></details>
<details class="meta"><summary>tool schemas ({len(tools)})</summary>{tools_html}</details>

{''.join(body)}
</div></body></html>'''


# ------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Render transcript.jsonl as standalone HTML")
    ap.add_argument("input", help="transcript.jsonl, or a run dir containing one")
    ap.add_argument("-o", "--output", help="output html path (default: <transcript>.html)")
    ap.add_argument("--open", action="store_true", help="print a file:// URL to open")
    args = ap.parse_args()

    path = args.input
    if os.path.isdir(path):
        path = os.path.join(path, "transcript.jsonl")
    if not os.path.isfile(path):
        print(f"error: no transcript at {path}", file=sys.stderr)
        return 2

    d = os.path.dirname(os.path.abspath(path))
    transcript = load_jsonl(path)
    score = load_json(os.path.join(d, "score.json"))
    cost = load_json(os.path.join(d, "cost.json"))

    out = args.output or os.path.splitext(path)[0] + ".html"
    with open(out, "w") as fp:
        fp.write(render(transcript, score, cost))
    print(f"wrote {out}  ({len(transcript)} events)")
    if args.open:
        print(f"  file://{os.path.abspath(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
