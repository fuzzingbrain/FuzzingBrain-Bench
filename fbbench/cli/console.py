"""Terminal colour / glyph helpers and the tier display mapping."""
from __future__ import annotations

import os
import sys

# Flag -> tier label, ordered high-capability first (matches the SPEC ladder).
# differential is the patch-differential rung (vuln faults ∧ fixed build does not):
# reach ⊇ crash ⊇ differential ⊇ class ⊇ site. It is graded only for bugs that declare
# it in capability_set (i.e. those with a fixed-asan reference binary).
TIERS = [("reach", "T5"), ("crash", "T4"), ("differential", "T3"), ("class", "T2"), ("site", "T1")]

GLYPH = {"fired": "●", "not_fired": "○", "n/a": "·"}

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s


def bold(s: str) -> str:   return _c("1", s)
def dim(s: str) -> str:    return _c("2", s)
def green(s: str) -> str:  return _c("32", s)
def red(s: str) -> str:    return _c("31", s)
def yellow(s: str) -> str: return _c("33", s)
def cyan(s: str) -> str:   return _c("36", s)
def gray(s: str) -> str:   return _c("90", s)


def fmt_status(status: str, in_kb: bool) -> tuple[str, str]:
    """Return (coloured glyph, coloured status word) for a single flag."""
    if not in_kb:
        return gray(GLYPH["n/a"]), gray("n/a (not in K_b)")
    if status == "fired":
        return green(GLYPH["fired"]), green("fired")
    if status == "not_fired":
        return red(GLYPH["not_fired"]), red("not fired")
    return gray(GLYPH["n/a"]), gray(status)
