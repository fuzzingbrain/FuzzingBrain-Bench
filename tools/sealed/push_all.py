#!/usr/bin/env python3
"""Retag + push all locally-built sealed CHALLENGE images to a registry.

  fbbench-challenge/<bug>:latest  ->  <registry>/<owner>/fbbench-challenge-<bug>:latest

Challenge images are answer-free by construction (build_challenge.py leak-audits
before building), so publishing them does not leak the answer key.

Usage:
  push_all.py [--registry ghcr.io] [--owner owensanzas] [--only a,b] [--dry-run]
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def local_challenge_images(prefix="fbbench-challenge"):
    out = subprocess.run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                         capture_output=True, text=True).stdout
    imgs = {}
    for line in out.splitlines():
        if line.startswith(prefix + "/") and line.endswith(":latest"):
            bug = line[len(prefix) + 1:-len(":latest")]
            imgs[bug] = line
    return imgs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="ghcr.io")
    ap.add_argument("--owner", default="owensanzas")
    ap.add_argument("--only", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    imgs = local_challenge_images()
    if a.only:
        want = set(a.only.split(",")); imgs = {b: t for b, t in imgs.items() if b in want}
    report = {"pushed": [], "fail": []}
    for bug, local in sorted(imgs.items()):
        remote = f"{a.registry}/{a.owner}/fbbench-challenge-{bug}:latest"
        if a.dry_run:
            print(f"DRY  {local} -> {remote}"); continue
        rt = subprocess.run(["docker", "tag", local, remote], capture_output=True, text=True)
        if rt.returncode != 0:
            report["fail"].append((bug, "tag: " + rt.stderr[-200:])); print(f"FAIL tag {bug}"); continue
        pr = subprocess.run(["docker", "push", remote], capture_output=True, text=True)
        if pr.returncode == 0:
            report["pushed"].append(bug); print(f"PUSHED {remote}", flush=True)
        else:
            report["fail"].append((bug, "push: " + (pr.stderr or pr.stdout)[-300:]))
            print(f"FAIL push {bug}: {(pr.stderr or pr.stdout).strip().splitlines()[-1:]}", flush=True)
    json.dump(report, open(ROOT / "tools" / "sealed" / "push_report.json", "w"), indent=2)
    print(f"\n=== push: pushed={len(report['pushed'])} fail={len(report['fail'])} / {len(imgs)} ===")
    if report["fail"]:
        print("FAILURES (first 3):")
        for b, e in report["fail"][:3]:
            print(f"  {b}: {e}")

if __name__ == "__main__":
    main()
