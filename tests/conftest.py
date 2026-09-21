"""Suite-wide setup.

The agent toolbox is ON by default, because on a real run it must be: gdb is
part of the benchmark, not something a person installs. That default would
otherwise reach out to a registry from inside the test suite -- a suite that
needs the network is a suite that fails for reasons that have nothing to do
with the code, and this one is also required to spend no API credits.

So every test starts with the toolbox off, and the tests that are about the
toolbox switch it on explicitly for themselves.
"""
import pytest

from fbbench.sweep import mcp_episode as ep


@pytest.fixture(autouse=True)
def _no_registry_from_tests(monkeypatch):
    monkeypatch.setattr(ep, "AGENT_TOOLS_IMAGE", "", raising=False)
