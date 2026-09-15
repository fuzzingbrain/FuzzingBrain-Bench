# SPDX-License-Identifier: Apache-2.0
"""The external arm must report as it goes, like every other arm.

Before this, an fbagent cell wrote nothing until the agent process exited: a
30-minute run was unobservable and a killed one lost every graded candidate.
"""

import json
import tempfile
from pathlib import Path

from fbbench.sweep.external import Judge


def _judge(cell, preserve=True):
    ws = Path(tempfile.mkdtemp())
    j = Judge(ws, Path("/nonexistent"), cell_dir=cell, preserve_pocs=preserve)
    j._open_progress()
    j.blobs.mkdir(parents=True, exist_ok=True)
    return j


def _grade(j, name, crashed, sig, detail, size=64):
    (j.blobs / name).write_bytes(b"X" * size)
    e = {"blob": name, "size": size, "crashed": crashed, "signature": sig}
    j.log.append(e)
    j._record(e, j.blobs / name, detail)
    return e


def test_every_candidate_is_readable_before_the_run_ends(tmp_path):
    cell = tmp_path / "cell"
    j = _judge(cell)
    _grade(j, "b0", False, "", "clean: no fault | target ran 0 ms | 64 bytes")
    _grade(j, "b1", True, "abrt|f|g", "crash: abrt|f|g")
    recs = [json.loads(l) for l in (cell / "progress.jsonl").read_text().splitlines()]
    assert len(recs) == 2
    assert recs[0]["crashed"] is False and "0 ms" in recs[0]["verdict"]
    assert recs[1]["crashed"] is True and recs[1]["unique_so_far"] == 1


def test_pocs_are_preserved_as_they_are_graded(tmp_path):
    cell = tmp_path / "cell"
    j = _judge(cell)
    _grade(j, "b0", False, "", "clean: no fault | target ran 0 ms | 64 bytes")
    _grade(j, "b1", True, "abrt|f|g", "crash: abrt|f|g")
    assert (cell / "pocs" / "clean" / "b0").is_file()
    assert (cell / "pocs" / "crashed" / "b1").is_file()
    meta = json.loads((cell / "pocs" / "crashed" / "b1.json").read_text())
    assert meta["crash_signature"] == "abrt|f|g" and meta["crashed"] is True


def test_a_running_tally_is_written(tmp_path):
    cell = tmp_path / "cell"
    j = _judge(cell)
    _grade(j, "b0", True, "abrt|f|g", "crash: abrt|f|g")
    _grade(j, "b1", True, "abrt|f|g", "crash: abrt|f|g")      # same fault again
    _grade(j, "b2", True, "segv|h", "crash: segv|h")
    p = json.loads((cell / "score.partial.json").read_text())
    assert p["in_progress"] is True and p["blobs_written"] == 3
    assert p["unique_crashes"] == 2


def test_preserve_pocs_off_still_streams_progress(tmp_path):
    cell = tmp_path / "cell"
    j = _judge(cell, preserve=False)
    _grade(j, "b0", True, "abrt|f|g", "crash: abrt|f|g")
    assert not (cell / "pocs").exists()
    assert (cell / "progress.jsonl").read_text().strip()


def test_a_reporting_failure_never_breaks_grading(tmp_path):
    """The judge's job is the verdict; reporting is strictly secondary."""
    cell = tmp_path / "cell"
    j = _judge(cell)
    j.cell_dir = Path("/proc/nowhere/at/all")     # every write will fail
    _grade(j, "b0", True, "abrt|f|g", "crash: abrt|f|g")
    assert j.log[-1]["crashed"] is True           # grading still recorded
