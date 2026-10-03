"""DECLARED CONSTRUCTED independent approach/guardian baseline checkpoints.

The current prefix diverges at 1183. Construct later independent operation
sites with group 2 source; never use these to assert current trajectory fidelity.
"""
import base64
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import types
from test_store_reentry_recorded import _Pickler

fixture = types.ModuleType("test_town_approach_retired_recorded")
fixture.__file__ = str(Path(__file__).with_name("test_town_approach_retired_recorded.py"))
sys.modules[fixture.__name__] = fixture
exec(subprocess.check_output([
    "git", "show", "0d2ef6d6:tests/test_town_approach_retired_recorded.py"
]).decode("utf8"), fixture.__dict__)


def extract():
    revision = os.environ["S33_CHECKPOINT_SOURCE"]
    assert not subprocess.check_output([
        "git", "diff", "--name-only", revision, "--", "src"
    ]).strip()
    cls = fixture.TownApproachRetiredRecordedTest
    cls.setUpClass()
    sites = set(fixture.PATH) | {fixture.WALK_START - 10}
    saved = {}
    consume = cls._consume.__func__
    def checkpoint(cls, policy, index, directory):
        if index in sites:
            stream = io.BytesIO()
            _Pickler(stream, cls.monrace).dump(policy)
            saved[str(index)] = base64.b64encode(stream.getvalue()).decode("ascii")
        return consume(cls, policy, index, directory)
    cls._consume = classmethod(checkpoint)
    replay = cls._replay()
    quantity = {1178: "dm", 1906: "dn"}
    differences = [index for index, row in enumerate(replay)
                   if (row["key"] if index not in quantity else cls.recorded[index]["key"], row["reason"])
                   != (cls.recorded[index]["key"], cls.recorded[index]["reason"])]
    assert differences == [*fixture.STALE_GATE_WINDOW, fixture.STOP], differences
    assert set(map(int, saved)) == sites
    payload = dict(construction="DECLARED CONSTRUCTED baseline-policy independent checkpoints",
                   source_revision=revision, input_sha256=fixture.FIXTURE_SHA256,
                   checkpoints=saved)
    target = Path(__file__).parent / "fixtures/town-approach.s33-independent-checkpoints.json.gz"
    target.write_bytes(gzip.compress(json.dumps(payload, sort_keys=True).encode(), mtime=0))
    print(len(saved), "independent checkpoints", target.stat().st_size, "bytes")

if __name__ == "__main__":
    extract()
