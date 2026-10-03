"""Construct independent overweight sites from the original baseline driver.

The corrected arrival changes the Home key at 3. Historical later scenes
are independent substrates, not effect boards of that new deposit.
"""
import base64
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import types
from test_store_reentry_recorded import _Pickler

fixture = types.ModuleType("test_overweight_home_hold_recorded")
fixture.__file__ = str(Path(__file__).with_name("test_overweight_home_hold_recorded.py"))
sys.modules[fixture.__name__] = fixture
exec(subprocess.check_output([
    "git", "show", "0d2ef6d6:tests/test_overweight_home_hold_recorded.py"
]).decode("utf8"), fixture.__dict__)


def extract():
    revision = "0d2ef6d6"
    assert not subprocess.check_output(["git", "diff", "--name-only", revision, "--", "src"]).strip()
    cls = fixture.OverweightHomeHoldRecordedTest
    cls.setUpClass()
    case = cls()
    saved = {}
    def prepare(index, policy, board):
        if index in (fixture.HOME, fixture.HOME + 1, fixture.STOP):
            stream = io.BytesIO()
            _Pickler(stream, cls.monrace).dump((policy, board))
            saved[str(index)] = base64.b64encode(stream.getvalue()).decode("ascii")
    @fixture.pre_four_staff_cap_rule()
    @fixture.shelf_wall_on_replay
    def construct():
        return case._replay(fixture.STOP, walls=True, prepare=prepare)
    rows = construct()
    assert rows[:fixture.STEP_OFF_WALL] == [case._live(i) for i in range(fixture.STEP_OFF_WALL)]
    assert rows[fixture.STEP_OFF_WALL][1] == case._live(fixture.STEP_OFF_WALL)[1]
    payload = dict(construction="DECLARED CONSTRUCTED baseline-policy independent checkpoints",
                   source_revision=revision, input_sha256=fixture.SHA256[fixture.FIXTURE],
                   checkpoints=saved)
    target = Path(__file__).parent / "fixtures/overweight-home.s33-independent-checkpoints.json.gz"
    target.write_bytes(gzip.compress(json.dumps(payload, sort_keys=True).encode(), mtime=0))
    print(len(saved), "independent checkpoints", target.stat().st_size, "bytes")

if __name__ == "__main__":
    extract()
