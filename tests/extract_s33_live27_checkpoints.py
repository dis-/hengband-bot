"""Construct independent live27 Home-arrival and mining sites on the base.

Only the original baseline driver runs through the historical Home hold.
Current tests may inspect the independent sites without feeding later boards
as effects of a corrected arrival or a changed equipment decision.
"""
import base64
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import types
from unittest.mock import patch
from test_store_reentry_recorded import _Pickler
from hengbot.policy import HengbotPolicy

fixture = types.ModuleType("test_identify_staff_live27_recorded")
fixture.__file__ = str(Path(__file__).with_name("test_identify_staff_live27_recorded.py"))
sys.modules[fixture.__name__] = fixture
exec(subprocess.check_output([
    "git", "show", "0d2ef6d6:tests/test_identify_staff_live27_recorded.py"
]).decode("utf8"), fixture.__dict__)


def extract():
    assert not subprocess.check_output(["git", "diff", "--name-only", "0d2ef6d6", "--", "src"]).strip()
    original = HengbotPolicy.choose_key
    index = 0
    saved = {}
    def capture(policy, board):
        nonlocal index
        if index in (63, 104):
            stream = io.BytesIO()
            _Pickler(stream, policy._monrace_knowledge).dump((policy, board))
            saved[str(index)] = base64.b64encode(stream.getvalue()).decode("ascii")
        index += 1
        return original(policy, board)
    with patch.object(HengbotPolicy, "choose_key", capture):
        fixture.IdentifyStaffLive27RecordedTest().test_recorded_shortfall_enters_one_run_mining()
    assert set(saved) == {"63", "104"}
    import hashlib
    payload = dict(construction="DECLARED CONSTRUCTED baseline-policy independent checkpoints",
                   source_revision="0d2ef6d6", input_sha256=hashlib.sha256(fixture.FIXTURE.read_bytes()).hexdigest(),
                   checkpoints=saved)
    target = Path(__file__).parent / "fixtures/live27.s33-independent-checkpoints.json.gz"
    target.write_bytes(gzip.compress(json.dumps(payload, sort_keys=True).encode(), mtime=0))
    print(len(saved), "independent checkpoints", target.stat().st_size, "bytes")

if __name__ == "__main__":
    extract()
