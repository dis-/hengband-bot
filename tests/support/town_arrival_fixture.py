"""Town-arrival checkpoint fixtures: extract one, load one (town rebuild stage 3-3).

A fixture keeps a capture's town-arrival checkpoint (``policy.pkl``), the
first journal rows and the sidecar files the restored policy reads (base64),
all xz-compressed, in ``tests/fixtures/<name>/``.  ``extract`` writes one from
an incident capture's ``town-arrival/``; ``load`` restores it into a scratch
directory and returns what ``tests/replay_town_arrival.py`` replays.
"""
import base64
import gzip
import json
import lzma
from pathlib import Path

from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)

PRESET = 9 | lzma.PRESET_EXTREME


def extract(visit: Path, target: Path, rows: int, left_out: frozenset = frozenset()) -> None:
    """Write the fixture of ``visit``'s first ``rows`` journal rows to ``target``."""
    target.mkdir(parents=True, exist_ok=True)
    (target / "policy.pkl.xz").write_bytes(
        lzma.compress((visit / POLICY_FILE).read_bytes(), preset=PRESET))
    journal = gzip.decompress((visit / JOURNAL_FILE).read_bytes()).splitlines(True)
    (target / "journal.jsonl.xz").write_bytes(
        lzma.compress(b"".join(journal[:rows]), preset=PRESET))
    manifest = json.loads((visit / SIDECAR_MANIFEST).read_text(encoding="utf-8"))
    files = {}
    for role, entry in manifest.items():
        if role in left_out:
            manifest[role] = {**entry, "copied": False, "reason": "left-out"}
        elif entry.get("copied"):
            files[role] = base64.b64encode((visit / SIDECAR_DIRECTORY / role).read_bytes()).decode("ascii")
    (target / "sidecars.json.xz").write_bytes(lzma.compress(json.dumps(
        {"manifest": manifest, "files": files}, ensure_ascii=False).encode("utf-8"), preset=PRESET))


def load(fixture: Path, scratch: Path):
    """(arrival policy, journal rows, [(recorded row, board supplier)])."""
    from replay_town_arrival import adopt_calibration, decisions, journal, restore
    visit = scratch / "town-arrival"
    (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
    (visit / POLICY_FILE).write_bytes(lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
    (visit / JOURNAL_FILE).write_bytes(gzip.compress(
        lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
    sidecars = json.loads(lzma.decompress((fixture / "sidecars.json.xz").read_bytes()))
    (visit / SIDECAR_MANIFEST).write_text(
        json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
    for role, data in sidecars["files"].items():
        (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
    runtime = scratch / "runtime"
    runtime.mkdir()
    policy = restore(visit, runtime)
    calibration = visit / SIDECAR_DIRECTORY / "_character_calibration_path"
    if calibration.is_file():
        adopt_calibration(policy, calibration, runtime)
    return policy, journal(visit), list(decisions(policy, visit, runtime))
