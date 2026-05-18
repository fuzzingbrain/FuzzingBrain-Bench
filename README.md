# FuzzingBrain Bench

A public benchmark and trophy case of **50 zero-day vulnerabilities** surfaced by
[FuzzingBrain](https://github.com/OwenSanzas/FuzzingBrain-V2) across 27 widely-used
open-source projects.

- **Website:** https://owensanzas.github.io/FuzzingBrain-Bench/
- **Trophies (social view):** https://owensanzas.github.io/FuzzingBrain-Bench/trophies.html
- **Benchmark (research view):** https://owensanzas.github.io/FuzzingBrain-Bench/benchmark.html

| | |
|---|---|
| Total bugs | **50** |
| Fixed upstream | 42 |
| Confirmed (awaiting patch) | 8 |
| Projects covered | 27 |
| Verified accessible | 2026-05-05 |

Every entry was discovered by FuzzingBrain, reported upstream, and is accompanied by a
public reproducer.

## Why this exists

Most fuzzing benchmarks measure rediscovery of *known* bugs. FuzzingBrain Bench
measures something closer to what we actually want: finding **novel** bugs in modern
code. Every bug here was unknown to its upstream when reported.

## Repository layout

```
FuzzingBrain-Bench/
├── docs/                    # Static site (served by GitHub Pages)
│   ├── index.html           # Landing
│   ├── trophies.html        # AFL++-style flat list
│   ├── benchmark.html       # Benchmark intro / schema / how to use
│   ├── bugs.json            # Single source of truth (50 entries)
│   └── assets/
│       ├── style.css
│       └── site.js
└── bugs/                    # Per-bug directories (PoCs, verify scripts) — filling in
    └── <project>/<id>/
        ├── README.md
        ├── poc/
        ├── verify.sh
        └── Dockerfile       (optional)
```

## The schema

Every entry in `docs/bugs.json` carries at minimum:

| field | meaning |
|---|---|
| `id` | stable kebab-case slug |
| `project` | upstream project name |
| `title` | one-line bug summary |
| `status` | `fixed` or `confirmed` |
| `bug_class` | sanitizer tag — `heap-buffer-overflow`, `oom`, `null-deref`, &hellip; |
| `report` | canonical link to the upstream issue / PR / advisory |

As PoC files and verify scripts land in `bugs/<project>/<id>/`, the corresponding entry
in `bugs.json` will be extended with `commit`, `harness`, `cve`, and `disclosed`
fields.

## Reproducing a bug

Once a bug's directory is populated:

```bash
git clone https://github.com/OwenSanzas/FuzzingBrain-Bench
cd FuzzingBrain-Bench/bugs/<project>/<id>
./verify.sh
```

`verify.sh` exits `0` when the expected sanitizer report is observed, non-zero
otherwise — making it a clean target for evaluating automated triage / patching agents.

## Status

The catalogue (the 50 entries) is **complete**. PoC files and verification scripts are
being added on a rolling basis. Track progress via the repo's
[issues](https://github.com/OwenSanzas/FuzzingBrain-Bench/issues).

## Contributing

To propose a new entry:

1. Open a PR adding an object to `docs/bugs.json`.
2. Create a directory under `bugs/<project>/<id>/` with at least a `README.md` and
   the upstream report link.
3. If you can include a `poc/` and a `verify.sh`, even better.

Every entry must link to a **public** upstream report (issue, PR, bugzilla, advisory).

## License

The catalogue and site are released under the MIT license. PoC inputs derive from the
public upstream reports linked from each entry and remain governed by the licenses of
their respective projects.

Maintained by [@OwenSanzas](https://github.com/OwenSanzas).
