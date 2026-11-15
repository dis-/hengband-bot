"""Extract tests/fixtures/n1c-214-equip-departure-1116/n1c-214-0044/.

Source: n1-c life-214's incident capture of 2026-11-16 00:46:37
(``town:blocked:unmet:equipment_departure_ready``, Magic-Eater Lv42, build
bot-37d6ee994), copied read-only from the viewing server's
incident-captures/20261116-004637-town-blocked-unmet-equipment_departure_ready/
to C:/hengband-backups/pdca/captures/n1c-214-equip-departure-1116/.  Its
town-arrival checkpoint (00:44:15, turn 6,027,241) and all 341 journal rows
replay as recorded on main 2449505d8 (tests/replay_town_arrival.py).

A whole-visit replay takes about fifteen minutes, so the fixture is a
mid-visit checkpoint: the arrival checkpoint replayed through rows 0-281 on
main 2449505d8 (every row decided as recorded and posted with its recorded
key, as the live CLI posts it), then pickled with ``checkpoint_bytes`` and the
runtime files it reads (``_copy_runtime_files``) like an arrival checkpoint.
The fixture's journal is the capture's rows 282-340 (the second equipment
session from its Home exit, the takeoff, the refused wield, the abandonment,
the rest of the visit and the stop).

DECLARED CONSTRUCTED: the checkpoint is a replay's state before row 282, not a
live arrival; ``ROW_OFFSET`` maps fixture rows back to the capture's.

    python tests/extract_n1c_214_equip_departure_1116_fixture.py
    (run with PYTHONPATH on a main 2449505d8 checkout: src, tests and the root)
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import base64
import copy
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.cli import _handle_owner_retirement
from hengbot.latch_onset_capture import checkpoint_bytes
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import (
    DIRECTORY, JOURNAL_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST, _copy_runtime_files,
)
from replay_town_arrival import adopt_calibration, decisions, journal, restore

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-214-equip-departure-1116")
TARGET = Path(__file__).with_name("fixtures") / "n1c-214-equip-departure-1116" / "n1c-214-0044"
ROW_OFFSET = 282
PRESET = 9 | lzma.PRESET_EXTREME
# The append-only loadout report log is large and never read back by a decision.
LEFT_OUT = frozenset({"_loadout_report_path"})
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)


def post(policy, board, key, visit_before):
    key = policy.validate_read_key(board, key)
    key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def main() -> None:
    visit = CAPTURE / DIRECTORY
    with TemporaryDirectory(prefix="n1c214-extract-") as raw:
        scratch = Path(raw)
        policy = restore(visit, scratch)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path", scratch)
        recorded = journal(visit)
        for row, supply in list(decisions(policy, visit, scratch))[:ROW_OFFSET]:
            board = supply()
            before = copy.copy(policy._store_visit)
            key = policy.choose_key(board)
            entry = recorded[row["row"]]
            if (key, policy.last_reason) != (entry["key"], entry["reason"]):
                raise SystemExit(f"row {row['row']} diverged: {key!r} {policy.last_reason}")
            post(policy, board, entry["key"], before)
        TARGET.mkdir(parents=True, exist_ok=True)
        (TARGET / "policy.pkl.xz").write_bytes(lzma.compress(checkpoint_bytes(policy), preset=PRESET))
        copied = scratch / "sidecar-copy"
        copied.mkdir()
        _copy_runtime_files(policy, copied)
        manifest = json.loads((copied / SIDECAR_MANIFEST).read_text(encoding="utf-8"))
        files = {}
        for role, entry in manifest.items():
            if role in LEFT_OUT:
                manifest[role] = {**entry, "copied": False, "reason": "left-out"}
            elif entry.get("copied"):
                files[role] = base64.b64encode(
                    (copied / SIDECAR_DIRECTORY / role).read_bytes()).decode("ascii")
        (TARGET / "sidecars.json.xz").write_bytes(lzma.compress(json.dumps(
            {"manifest": manifest, "files": files}, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    rows = gzip.decompress((visit / JOURNAL_FILE).read_bytes()).splitlines(True)
    (TARGET / "journal.jsonl.xz").write_bytes(lzma.compress(b"".join(rows[ROW_OFFSET:]), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
