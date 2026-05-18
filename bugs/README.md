# `bugs/` &mdash; per-bug PoC directories

Each subdirectory holds the reproducer for one entry in
[`../docs/bugs.json`](../docs/bugs.json):

```
bugs/<project>/<id>/
├── README.md      # Description, vulnerable version, reproduction notes
├── poc/           # The input(s) that trigger the bug
├── verify.sh      # Runs the target with the PoC; exits 0 on expected sanitizer crash
└── Dockerfile     # (optional) pinned reproduction environment
```

The `<id>` matches the `id` field in `bugs.json`.

PoCs are landing on a rolling basis &mdash; the catalogue in `bugs.json` is the
authoritative list; what you see here is whatever has been packaged so far.

To contribute a PoC for an existing entry, open a PR adding the matching directory.
