"""Freeze the n1-b life-316 16:06:08 stuck-prompt on the Home's page 2.

Source: C:/hengband-backups/pdca/captures/n1b-316-stuck-1105/cap.tgz
(bot-20f748ae5, capture 20261105-160611).  Decision 21 posted the page switch
``equipment-transaction:seek-home-page``; the barrier refused the page it
reached.  Frozen: the skill and Home lists, the two store rows of turn 1212753,
the screen and state the control port read at the stop, and decision 21's
transaction facts.  Only this tool reads the capture.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path


ARCHIVE = Path("C:/hengband-backups/pdca/captures/n1b-316-stuck-1105/cap.tgz")
CAPTURE = "captures/20261105-160611-stuck-prompt-equipment-transaction-seek-home-page"
OUTPUT = Path(__file__).with_name("fixtures") / "store-page-cut-name-1105.json.gz"
TURN = 1212753


def _member(archive: tarfile.TarFile, name: str) -> bytes:
    stream = archive.extractfile(f"{CAPTURE}/{name}")
    assert stream is not None, name
    return gzip.decompress(stream.read())


def _rows(raw: bytes) -> list[dict]:
    return [json.loads(line) for line in io.BytesIO(raw) if line.strip()]


def main() -> None:
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        state = _rows(_member(archive, "state.jsonl.gz"))
        decisions = _rows(_member(archive, "bot-decisions.jsonl.gz"))
        control = json.loads(_member(archive, "control-at-stop.json.gz"))
    knowledge = [row for row in state if row["type"] == "knowledge"]
    decision = decisions[-1]
    assert decision["decision_sequence"] == 21
    optimization = decision["equipment_optimization"]
    case = {
        "source": {"archive_sha256": digest, "capture": CAPTURE},
        "skill": [r for r in knowledge if r["knowledge"]["category"] == "skill_exp"][-1],
        "home": [r for r in knowledge if r["knowledge"]["category"] == "home"][-1],
        "pages": [r for r in state if r["type"] == "store" and r["turn"] == TURN],
        "screen": control["screen"],
        "state": control["state"],
        "decision": {
            "reason": decision["reason"],
            "key": decision["key"],
            "transaction_next": optimization["transaction_next"],
            "transaction_target_loadout_id": optimization["transaction_target_loadout_id"],
            "store_visit": decision["store_visit"],
        },
    }
    OUTPUT.write_bytes(gzip.compress(
        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), mtime=0))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
