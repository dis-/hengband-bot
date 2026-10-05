"""Freeze independent pre-*Identify*-deferral substrates, never live effects.

Run one module at a time with PYTHONPATH pointing to src archived from
3b12a514 (and tests plus the repository root), e.g.:
  <python> tests/extract_suitefix4_checkpoints.py store
  <python> tests/extract_suitefix4_checkpoints.py staff
The historical drivers and all their walls come from that same revision.
New current replays stop at 212/1714; these checkpoints do not extend them.
"""
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest

SOURCE = "3b12a514"
ROOT = Path(__file__).resolve().parents[1]


def historical(name):
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / "tests" / (name + ".py"))
    sys.modules[name] = module
    exec(subprocess.check_output([
        "git", "show", f"{SOURCE}:tests/{name}.py"
    ]).decode("utf8"), module.__dict__)
    return module


def extract(kind):
    store = historical("test_store_reentry_recorded")
    module = store if kind == "store" else historical("test_identify_staff_swap_churn_recorded")
    cls = module.StoreReentryRecordedTest if kind == "store" else module.IdentifyStaffSwapChurnRecordedTest
    original_setup = cls.setUpClass
    original_step = cls._step
    saved = {}
    # Retain the old Home-absence proof and every live-key wall after 212.
    wanted = (set(store.CHECKPOINTS) | {219, 267, 273, 802}) if kind == "store" else {2817, 2846}

    def step(klass, policy, index):
        if index in wanted:
            buffer = io.BytesIO()
            store._Pickler(buffer, klass.monrace).dump(policy)
            saved[str(index)] = dict(
                policy=base64.b64encode(buffer.getvalue()).decode("ascii"),
                files={str(p.relative_to(klass.directory)): base64.b64encode(p.read_bytes()).decode("ascii")
                       for p in klass.directory.rglob("*") if p.is_file()},
            )
        result = original_step(policy, index)
        if index == (212 if kind == "store" else 1714):
            print("baseline boundary", index, result[:2],
                  "need", policy._identification_need,
                  "candidate", policy._identification_candidate,
                  "obtainability", policy._identification_source_obtainability(result[2], full=True),
                  "needs", [(n.store_type, n.category) for n in policy._enumerate_town_needs(result[2])], flush=True)
        return result

    def setup(klass):
        original_setup()
        if kind == "staff":
            for index, row in enumerate(klass.prefix):
                if index not in module.LIVE_KEY_WALL:
                    assert row == (klass.recorded[index]["key"], klass.recorded[index]["reason"]), index
        payload = dict(construction="DECLARED CONSTRUCTED independent baseline-policy substrates",
                       source_revision=SOURCE, input_sha256=module.SHA256[module.FIXTURE],
                       checkpoints={i: v for i, v in saved.items() if int(i) > (212 if kind == "store" else 1714)})
        target = ROOT / "tests/fixtures" / f"{kind}.suitefix4-independent-checkpoints.json.gz"
        target.write_bytes(gzip.compress(json.dumps(payload, sort_keys=True).encode(), mtime=0))
        print("fixture", target.name, "sha256", hashlib.sha256(target.read_bytes()).hexdigest(), flush=True)

    cls._step = classmethod(step)
    cls.setUpClass = classmethod(setup)
    # Verify that every imported production module really is the baseline.
    for name, loaded in tuple(sys.modules.items()):
        path = getattr(loaded, "__file__", None)
        if name.startswith("hengbot.") and path and path.endswith(".py"):
            relative = "src/" + name.replace(".", "/") + ".py"
            assert Path(path).read_bytes().replace(b"\r\n", b"\n") == subprocess.check_output([
                "git", "show", f"{SOURCE}:{relative}"
            ]).replace(b"\r\n", b"\n"), name
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    extract(sys.argv[1])
