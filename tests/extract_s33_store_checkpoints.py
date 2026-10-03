"""DECLARED CONSTRUCTED independent Phase 1 checkpoints after S3.3 diverges.

Run against group 2's source, with S33_CHECKPOINT_SOURCE naming that revision.
These are baseline-policy states produced by the existing frozen replay and
its documented walls, not recovered live checkpoints or current trajectories.
The current replay must stop at its first changed key (802).
"""
import base64
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import types

# Use the preserved original substrate driver, so regeneration does not follow
# the current implementation past its new first divergence.
fixture = types.ModuleType("test_store_reentry_recorded")
fixture.__file__ = str(Path(__file__).with_name("test_store_reentry_recorded.py"))
sys.modules[fixture.__name__] = fixture
exec(subprocess.check_output([
    "git", "show", "0d2ef6d6:tests/test_store_reentry_recorded.py"
]).decode("utf8"), fixture.__dict__)


def extract():
    revision = os.environ["S33_CHECKPOINT_SOURCE"]
    assert not subprocess.check_output([
        "git", "diff", "--name-only", revision, "--", "src"
    ]).strip(), "extract only against the declared baseline source"
    cls = fixture.StoreReentryRecordedTest
    cls.setUpClass()
    try:
        for index, row in enumerate(cls.prefix):
            if index not in fixture.LIVE_KEY_WALL:
                assert row == (cls.recorded[index]["key"], cls.recorded[index]["reason"]), index
        payload = dict(construction="DECLARED CONSTRUCTED baseline-policy independent checkpoints",
                       source_revision=os.environ["S33_CHECKPOINT_SOURCE"],
                       input_sha256=fixture.SHA256[fixture.FIXTURE],
                       checkpoints={str(index): base64.b64encode(data).decode("ascii")
                                    for index, data in cls.checkpoints.items() if index > 802})
        target = Path(__file__).parent / "fixtures/store-reentry.s33-independent-checkpoints.json.gz"
        target.write_bytes(gzip.compress(json.dumps(payload, sort_keys=True).encode(), mtime=0))
        print(len(payload["checkpoints"]), "independent checkpoints", target.stat().st_size, "bytes")
    finally:
        cls.tearDownClass()

if __name__ == "__main__":
    extract()
