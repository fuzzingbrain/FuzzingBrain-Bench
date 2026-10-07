#!/usr/bin/env python3
"""<alias>.graph.json -> <alias>.callgraph.sqlite: the static call graph an agent
image ships next to gdb.

The JSON is what callgraph-tools (Joern) emits: {meta, nodes, edges}. A node is
{id "name@file:line", name, file, line, line_end, content}; an edge is a
[caller_id, callee_id] pair. The SQLite file is the CONTRACT between the graph
builder and the mcp-server's call-graph tools -- rebuild the graph with any tool
you like, emit this schema, and nothing downstream changes.

  meta(key, value)                      challenge, lang, entry, builder, counts
  functions(id, uid, name, file, line, line_end, depth, parent)
  calls(caller, callee)                 caller/callee are functions.id

`content` (the full source of every function) is dropped: the source is in the
image at /challenge/src, and the agent reads it with sed by file:line-line_end.
graal-01 goes from 191 MB to ~80 MB; a typical challenge is under 1 MB.

depth/parent are a BFS from meta.entry (the harness entrypoint), computed here
once so "is this reachable from the harness" and "how do I get there" are
indexed lookups, not recursive queries. depth -1 = not reachable in this graph.

Usage:
  build_sqlite.py <graph.json> [-o out.sqlite]
  build_sqlite.py --all <graphs_dir> [-o out_dir]        every *.graph.json
  build_sqlite.py --check <out.sqlite>                    print meta + a sanity report
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sqlite3
import sys
import time

SCHEMA_VERSION = "1"
DB_SUFFIX = ".callgraph.sqlite"

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE functions(
  id       INTEGER PRIMARY KEY,
  uid      TEXT NOT NULL UNIQUE,   -- the builder's node id, name@file:line
  name     TEXT NOT NULL,
  file     TEXT NOT NULL,          -- relative to the challenge source root
  line     INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  depth    INTEGER NOT NULL,       -- BFS distance from the harness entry; -1 unreachable
  parent   INTEGER                 -- predecessor on one shortest path from the entry
);
CREATE TABLE calls(
  caller INTEGER NOT NULL REFERENCES functions(id),
  callee INTEGER NOT NULL REFERENCES functions(id)
);
"""
INDEXES = """
CREATE INDEX functions_name ON functions(name);
CREATE INDEX functions_file ON functions(file);
CREATE INDEX calls_caller ON calls(caller, callee);
CREATE INDEX calls_callee ON calls(callee, caller);
"""


def _sha256_short(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def build(json_path: str, out_path: str, quiet: bool = False) -> dict:
    t0 = time.time()
    with open(json_path) as f:
        g = json.load(f)
    meta, nodes, edges = g["meta"], g["nodes"], g["edges"]

    index = {n["id"]: i for i, n in enumerate(nodes)}
    if len(index) != len(nodes):
        raise ValueError(f"{json_path}: duplicate node ids")
    entry_uid = meta.get("entry")
    entry = index.get(entry_uid)

    out_adj: dict[int, list[int]] = collections.defaultdict(list)
    pairs: list[tuple[int, int]] = []
    dangling = 0
    seen: set[tuple[int, int]] = set()
    for e in edges:
        a, b = index.get(e[0]), index.get(e[1])
        if a is None or b is None:
            dangling += 1
            continue
        if (a, b) in seen:          # the builder emits one edge per call site
            continue
        seen.add((a, b))
        pairs.append((a, b))
        out_adj[a].append(b)

    depth = [-1] * len(nodes)
    parent: list[int | None] = [None] * len(nodes)
    if entry is not None:
        depth[entry] = 0
        queue = [entry]
        for u in queue:
            for v in out_adj[u]:
                if depth[v] < 0:
                    depth[v] = depth[u] + 1
                    parent[v] = u
                    queue.append(v)
    reachable = sum(1 for d in depth if d >= 0)

    issues = list(meta.get("issues") or [])
    if entry is None:
        issues.append(f"entry {entry_uid!r} is not a node")
    nofile = sum(1 for n in nodes if not n.get("file"))
    if nofile:
        issues.append(f"{nofile} nodes without a file")
    if dangling:
        issues.append(f"{dangling} edges to unknown nodes dropped")

    tmp = out_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    db.executemany(
        "INSERT INTO functions VALUES (?,?,?,?,?,?,?,?)",
        ((i, n["id"], n["name"], n.get("file") or "", int(n.get("line") or 0),
          int(n.get("line_end") or n.get("line") or 0), depth[i], parent[i])
         for i, n in enumerate(nodes)))
    db.executemany("INSERT INTO calls VALUES (?,?)", pairs)
    db.executescript(INDEXES)
    rows = {
        "schema_version": SCHEMA_VERSION,
        "challenge": meta.get("challenge", ""),
        "lang": meta.get("lang", ""),
        "entry": entry_uid or "",
        "entry_id": "" if entry is None else str(entry),
        "builder": meta.get("method", ""),
        "source_json": os.path.basename(json_path),
        "source_sha256": _sha256_short(json_path),
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_functions": str(len(nodes)),
        "n_calls": str(len(pairs)),
        "n_call_sites": str(len(edges)),
        "edges_resolved": str(meta.get("edges_resolved", "")),
        "edges_byname": str(meta.get("edges_byname", "")),
        "reachable_from_entry": str(reachable),
        "issues": json.dumps(issues),
    }
    db.executemany("INSERT INTO meta VALUES (?,?)", rows.items())
    db.commit()
    db.execute("VACUUM")
    db.close()
    os.replace(tmp, out_path)

    report = {**rows, "out": out_path, "mb": round(os.path.getsize(out_path) / 2**20, 1),
              "seconds": round(time.time() - t0, 1)}
    if not quiet:
        print(f"{rows['challenge']:18s} {rows['lang']:4s} fn={len(nodes):>7} calls={len(pairs):>8} "
              f"reach={reachable:>6} {report['mb']:>6} MB {report['seconds']:>5}s"
              + (f"  ISSUES: {issues}" if issues else ""))
    return report


def check(db_path: str) -> int:
    db = sqlite3.connect(f"file:{db_path}?mode=ro&immutable=1", uri=True)
    meta = dict(db.execute("SELECT key, value FROM meta"))
    for k, v in meta.items():
        print(f"{k:22s} {v}")
    n_fn, = db.execute("SELECT count(*) FROM functions").fetchone()
    n_calls, = db.execute("SELECT count(*) FROM calls").fetchone()
    bad, = db.execute("SELECT count(*) FROM calls c LEFT JOIN functions f ON f.id=c.callee "
                      "WHERE f.id IS NULL").fetchone()
    print(f"\nfunctions={n_fn} calls={n_calls} dangling_callees={bad}")
    ok = (n_fn == int(meta["n_functions"]) and n_calls == int(meta["n_calls"]) and bad == 0
          and meta["schema_version"] == SCHEMA_VERSION)
    print("OK" if ok else "MISMATCH")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="a graph.json, or a directory with --all, or a .sqlite with --check")
    ap.add_argument("-o", "--out", help="output file (or directory with --all)")
    ap.add_argument("--all", action="store_true", help="convert every *.graph.json in PATH")
    ap.add_argument("--check", action="store_true", help="verify an existing .sqlite")
    args = ap.parse_args(argv)

    if args.check:
        return check(args.path)
    if args.all:
        out_dir = args.out or args.path
        os.makedirs(out_dir, exist_ok=True)
        names = sorted(f for f in os.listdir(args.path) if f.endswith(".graph.json"))
        if not names:
            print(f"no *.graph.json in {args.path}", file=sys.stderr)
            return 1
        reports = []
        for name in names:
            alias = name[: -len(".graph.json")]
            reports.append(build(os.path.join(args.path, name),
                                 os.path.join(out_dir, alias + DB_SUFFIX)))
        with open(os.path.join(out_dir, "callgraph-build-report.json"), "w") as f:
            json.dump(reports, f, indent=1)
        with_issues = [r["challenge"] for r in reports if json.loads(r["issues"])]
        print(f"\n{len(reports)} built, {sum(r['mb'] for r in reports):.0f} MB total"
              + (f"; with issues: {with_issues}" if with_issues else ""))
        return 0
    alias = os.path.basename(args.path)
    alias = alias[: -len(".graph.json")] if alias.endswith(".graph.json") else os.path.splitext(alias)[0]
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.path)), alias + DB_SUFFIX)
    build(args.path, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
