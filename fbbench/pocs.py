"""Lossless compression of the large candidates a cell preserves.

Every graded candidate is kept under <cell>/pocs/{crashed,clean}/, which is the
forensic record of a run and is not negotiable. But an agent chasing an
out-of-memory fault writes inputs of hundreds of MB to several GB, and each one
it grades is preserved: in the 77-challenge Qwen run one challenge left 8.4 GB
and the full folder passed 25 GB. Those inputs are nearly always one byte
repeated, so they compress by three to five orders of magnitude.

A file is replaced only after its compressed copy has been decompressed again
and hashed to the original's SHA-256, and each one is listed in
<cell>/pocs/COMPRESSED.tsv with its original size and hash. Nothing below the
threshold is touched, and nothing is ever dropped.

Restore a file with:  zstd -d --long=27 <file>.zst
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
from pathlib import Path

LARGE_POC_BYTES = 50 << 20
MANIFEST = "COMPRESSED.tsv"
_HEADER = ("# Candidates over 50 MB, compressed losslessly with zstd.\n"
           "# Restore one with: zstd -d --long=27 <path>.zst\n"
           "# path\toriginal_bytes\toriginal_sha256\n")

_lock = threading.Lock()
_pending: list[threading.Thread] = []


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_zst(path: Path) -> str:
    h = hashlib.sha256()
    p = subprocess.Popen(["zstd", "-q", "-d", "-c", "--long=27", str(path)],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for chunk in iter(lambda: p.stdout.read(1 << 20), b""):
        h.update(chunk)
    return h.hexdigest() if p.wait() == 0 else ""


def compress_large_pocs(cell_dir, threshold: int = LARGE_POC_BYTES) -> list[str]:
    """Compress every preserved candidate over `threshold` bytes in one cell.
    Returns the relative paths compressed. Never raises: a record that stays
    uncompressed is a disk-space problem, and a crash here would be a lost cell.
    """
    pocs = Path(cell_dir) / "pocs"
    if not pocs.is_dir() or shutil.which("zstd") is None:
        return []
    done = []
    for f in sorted(pocs.rglob("*")):
        try:
            if (not f.is_file() or f.suffix in (".zst", ".tmp") or f.name == MANIFEST
                    or f.stat().st_size <= threshold):
                continue
            size, want = f.stat().st_size, _sha256_file(f)
            tmp = f.with_name(f.name + ".zst.tmp")
            r = subprocess.run(["zstd", "-q", "-T0", "--long=27", "-f", str(f), "-o", str(tmp)],
                               capture_output=True)
            if r.returncode != 0 or _sha256_zst(tmp) != want:
                tmp.unlink(missing_ok=True)
                continue
            os.replace(tmp, f.with_name(f.name + ".zst"))
            rel = str(f.relative_to(pocs))
            with _lock:
                man = pocs / MANIFEST
                new = not man.exists()
                with open(man, "a") as m:
                    if new:
                        m.write(_HEADER)
                    m.write(f"{rel}\t{size}\t{want}\n")
            f.unlink()
            done.append(rel)
        except Exception:  # noqa: BLE001
            continue
    return done


def compress_in_background(cell_dir) -> None:
    """Start compressing one finished cell without holding up the next one."""
    t = threading.Thread(target=compress_large_pocs, args=(cell_dir,), daemon=True)
    with _lock:
        _pending.append(t)
    t.start()


def wait_for_compression() -> None:
    """Block until every cell started with compress_in_background is done."""
    with _lock:
        threads = list(_pending)
        _pending.clear()
    for t in threads:
        t.join()
