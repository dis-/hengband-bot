"""Extract the n1-c life-143 stop of 2026-11-05 18:01 (berserk, ``mBp2``).

The newest of the three stop captures: its last player_turn board, the skill row
the restarted process had read, the last decisions and the screen at the stop.
Only this extraction tool reads the capture; the committed test reads the fixture.
"""
import gzip
import json
import tarfile
from pathlib import Path

from tests.extract_n1c_loops_0336_1102_fixtures import write


ARCHIVE = Path("C:/hengband-backups/pdca/captures/n1c-143-1105/cap.tgz")
STOP = "captures/20261105-180115-stuck-prompt-quest-strategy-ranged-fire-magic-eater/"
FIXTURE = Path(__file__).with_name("fixtures") / "me-berserk-missile-20261105.json.gz"
DECISION_FIELDS = ("time", "decision_sequence", "turn", "reason", "key")


def member(archive, name):
    return gzip.decompress(archive.extractfile(STOP + name).read()).decode("utf-8", "replace")


def rows(text):
    return [json.loads(line) for line in text.splitlines() if line.startswith("{")]


def main() -> None:
    with tarfile.open(ARCHIVE) as archive:
        state = rows(member(archive, "state.jsonl.gz"))
        decisions = rows(member(archive, "bot-decisions.jsonl.gz"))
        control = json.loads(member(archive, "control-at-stop.json.gz"))
    decided = [row for row in decisions if row.get("decision_sequence") is not None]
    write(FIXTURE, dict(
        source=STOP,
        board=[row for row in state if row["type"] == "player_turn"][-1],
        skill=[row for row in state if row["type"] == "knowledge"
               and row["knowledge"]["category"] == "skill_exp"][-1],
        decisions=[{field: row.get(field) for field in DECISION_FIELDS} for row in decided[-3:]],
        stop_screen=control["screen"]))


if __name__ == "__main__":
    main()
