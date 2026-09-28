"""Images are fetched before a run, and large preserved candidates are compressed
losslessly as each cell ends."""
import hashlib
import os
import shutil
import subprocess

import pytest

from fbbench import images, pocs


# ------------------------------------------------------------------ prepull
def test_a_prepulled_image_is_started_without_asking_the_registry(monkeypatch):
    calls = []
    monkeypatch.setattr(images.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(images, "PREPULLED", set())
    img = "docker.io/osanzas/fbbench-agent-demo-01:latest"
    assert images.pull_policy(img) == "always"
    assert images.prepull([img, img], log=lambda *_: None) == []
    assert calls == [["docker", "pull", "-q", img]]        # once, however often it is listed
    assert images.pull_policy(img) == "missing"


def test_a_failed_prepull_is_reported_not_fatal(monkeypatch):
    monkeypatch.setattr(images.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "TLS timeout"))
    monkeypatch.setattr(images, "PREPULLED", set())
    monkeypatch.setattr(images, "_t", None, raising=False)
    import time
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    img = "docker.io/osanzas/fbbench-agent-demo-02:latest"
    assert images.prepull([img], log=lambda *_: None) == [img]
    assert images.pull_policy(img) == "always"


def test_each_arm_prepulls_the_images_it_starts():
    from fbbench.sweep.orchestrator import _run_images
    ext = _run_images("external", ["avro-03"], None)
    assert any("fbbench-agent-avro-03" in i for i in ext)
    assert any("fbbench-challenge-avro-03" in i for i in ext)     # end-of-run grading
    assert _run_images("claudecode", ["avro-03"], None) == ext
    api = _run_images("api", ["avro-03"], None)
    assert len(api) == 1 and "fbbench-challenge-avro-03" in api[0]


# ------------------------------------------------------------ compression
needs_zstd = pytest.mark.skipif(shutil.which("zstd") is None, reason="zstd not installed")


@needs_zstd
def test_large_candidates_are_compressed_losslessly_and_listed(tmp_path):
    crashed = tmp_path / "pocs" / "crashed"
    crashed.mkdir(parents=True)
    big = crashed / "blob-001"
    big.write_bytes(b"A" * (3 << 20) + os.urandom(4096))
    small = crashed / "blob-002"
    small.write_bytes(b"x" * 100)
    (crashed / "blob-001.json").write_text("{}")
    want = hashlib.sha256(big.read_bytes()).hexdigest()

    done = pocs.compress_large_pocs(tmp_path, threshold=1 << 20)

    assert done == ["crashed/blob-001"]
    assert not big.exists() and small.exists() and (crashed / "blob-001.json").exists()
    z = crashed / "blob-001.zst"
    back = subprocess.run(["zstd", "-q", "-d", "-c", "--long=27", str(z)],
                          capture_output=True, check=True).stdout
    assert hashlib.sha256(back).hexdigest() == want
    man = (tmp_path / "pocs" / pocs.MANIFEST).read_text()
    assert f"crashed/blob-001\t{(3 << 20) + 4096}\t{want}" in man
    assert "zstd -d --long=27" in man                     # how to get it back, in the file


@needs_zstd
def test_nothing_is_replaced_when_verification_fails(tmp_path, monkeypatch):
    d = tmp_path / "pocs" / "clean"
    d.mkdir(parents=True)
    f = d / "blob-001"
    f.write_bytes(b"B" * (2 << 20))
    monkeypatch.setattr(pocs, "_sha256_zst", lambda p: "0" * 64)
    assert pocs.compress_large_pocs(tmp_path, threshold=1 << 20) == []
    assert f.exists() and not list(d.glob("*.zst*"))


def test_compression_is_a_noop_without_zstd(tmp_path, monkeypatch):
    d = tmp_path / "pocs"
    d.mkdir()
    (d / "blob").write_bytes(b"C" * 10)
    monkeypatch.setattr(pocs.shutil, "which", lambda _: None)
    assert pocs.compress_large_pocs(tmp_path, threshold=1) == []
    assert (d / "blob").exists()


def test_the_matrix_compresses_each_cell_and_waits_before_the_summary():
    import inspect
    from fbbench.sweep import orchestrator
    src = inspect.getsource(orchestrator.run_matrix)
    assert "compress_in_background(cell_dir(out, bug, model, sample))" in src
    assert src.index("wait_for_compression()") < src.rindex("_write_summary(out")
