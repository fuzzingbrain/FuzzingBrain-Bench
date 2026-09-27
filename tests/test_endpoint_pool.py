"""Several copies of a self-hosted model, one episode on each at a time."""
import threading
import time

import fbbench.sweep.external as ex


def test_no_endpoint_configured_changes_nothing(monkeypatch):
    monkeypatch.delenv(ex.AGENT_ENDPOINTS_ENV, raising=False)
    e = ex._Endpoint()
    assert e.url is None
    e.release()                      # harmless


def test_concurrent_cells_never_share_a_server_and_the_third_waits(monkeypatch):
    monkeypatch.setenv(ex.AGENT_ENDPOINTS_ENV, "http://a/v1, http://b/v1")
    ex._endpoint_pools.clear()
    held, seen, lock = set(), [], threading.Lock()
    overlap = []

    def cell():
        e = ex._Endpoint()
        with lock:
            if e.url in held:
                overlap.append(e.url)
            held.add(e.url)
            seen.append((time.monotonic(), e.url))
        time.sleep(0.3)
        with lock:
            held.discard(e.url)
        e.release()
        e.release()                  # a second release must not duplicate it

    threads = [threading.Thread(target=cell) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not overlap, "two running cells were given the same server"
    starts = sorted(t for t, _ in seen)
    assert starts[2] - starts[0] >= 0.25, "the third cell did not wait for a free server"
    assert ex._endpoint_pool().qsize() == 2, "every server was handed back exactly once"
