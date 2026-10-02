"""Produce the declared xbow-pref optimizer supplements (not capture-time).

Runs the unwalled classC2 / live27 scenarios of
tests/test_xbow_pref_recorded_divergence.py with the frozen optimizer falling
back to the CURRENT optimizer for input signatures that the capture-time
fixtures do not hold, and writes exactly those results to
tests/fixtures/<name>.optimizer.xbow-pref-supplement.json.gz.  Recorded entries
are never rewritten.  Prints the LF-normalized sha256 for SUPPLEMENT_SHA256.

Run: PYTHONPATH=src;tests;scripts python tests/extract_xbow_pref_optimizer_supplement.py
"""
from contextlib import contextmanager
import gzip
import hashlib
import json
import subprocess
from unittest.mock import patch

import tests  # noqa: F401 -- isolate runtime writes
from hengbot import warrior_optimization
import recorded_equipment_decisions as frozen
import test_xbow_pref_recorded_divergence as divergence

REAL_OPTIMIZE = warrior_optimization.optimize_loadout
COMPUTED: dict[str, dict[str, object]] = {"classC2": {}, "live27": {}}


@contextmanager
def recording(name):
    path = frozen.Path(frozen.__file__).parent / "fixtures" / f"{name}.optimizer.json.gz"
    payload = gzip.decompress(path.read_bytes()).replace(b"\r\n", b"\n")
    assert hashlib.sha256(payload).hexdigest() == frozen.FIXTURE_SHA256[name]
    records = json.loads(payload)["results"]

    def optimize(items, evaluator, **kwargs):
        signature = frozen.input_signature(items, kwargs)
        if signature in records:
            return frozen.decode(records[signature])
        encoded = frozen.encode(REAL_OPTIMIZE(items, evaluator, **kwargs))
        COMPUTED[name][signature] = encoded
        return frozen.decode(encoded)

    with patch.object(warrior_optimization, "optimize_loadout", optimize):
        yield


def main():
    revision = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
    ).stdout.strip()
    with patch.object(frozen, "recorded_equipment_decisions", recording):
        print("classC2", divergence.classC2_public_board_decisions()[2][0][:2])
        print("live27", divergence.live27_unwalled_first_divergence())
    for name, results in COMPUTED.items():
        payload = {
            "declared": "ADDITIONAL entries computed by the current optimizer for "
                        "inputs first arising under the 2026-10-02 launcher rule; "
                        "not capture-time outputs",
            "producer": "tests/extract_xbow_pref_optimizer_supplement.py",
            "source_revision": revision,
            "module": "tests.test_xbow_pref_recorded_divergence",
            "results": results,
        }
        body = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf8")
        frozen.supplement_path(name).write_bytes(gzip.compress(body, mtime=0))
        print(name, len(results), sorted(results),
              hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest())


if __name__ == "__main__":
    main()
