"""Extract tests/fixtures/n1b-413-solar-death-1122/ (n1-b life-413's death on Angband 80F).

Source, copied read-only from the viewing server (~/hengbot-soak/n1-b/life-413) to
C:/hengband-backups/pdca/captures/n1b-413-20261122-041850-death:

 - ``incident-captures/20261122-041845-player-death/town-arrival/`` -- the town-arrival
   checkpoint of 04:18:09 (turn 3060644, ``policy.pkl``), the visit's 73 journal rows (to the
   Recall wait before the arrival on 80F) and the sidecar files, all xz-compressed
   (tests/support/town_arrival_fixture.extract; the loadout report is left out);
 - ``captures/20261122-041850-exit-no-marker/`` -- state.jsonl.gz (the 62 player-turn boards of
   Angband 80F, turn 3100691 to the death board 3100999; the arrival turn's
   two boards, one decision) and bot-decisions.jsonl.gz (their
   decision rows, decision_sequence 31143-31203), kept as ``floor.json.xz``.

    python tests/extract_n1b_413_solar_death_1122_fixture.py
"""
import gzip
import json
import lzma
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

ROOT = Path("C:/hengband-backups/pdca/captures/n1b-413-20261122-041850-death")
VISIT = ROOT / "incident-captures" / "20261122-041845-player-death" / "town-arrival"
CAPTURE = ROOT / "captures" / "20261122-041850-exit-no-marker"
TARGET = Path(__file__).with_name("fixtures") / "n1b-413-solar-death-1122"
ROWS = 73
FIRST_SEQUENCE = 31143  # me-power:new-floor:map-area, the first decision on 80F


def _rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    extract(VISIT, TARGET, ROWS, frozenset({"_loadout_report_path"}))
    boards = [row for row in _rows(CAPTURE / "state.jsonl.gz")
              if row.get("type") == "player_turn" and not row["floor"]["in_town"]]
    decisions = [{"decision_sequence": row["decision_sequence"], "turn": row["turn"],
                  "key": row["key"], "reason": row["reason"], "player": row.get("player"),
                  "messages": row.get("messages")}
                 for row in _rows(CAPTURE / "bot-decisions.jsonl.gz")
                 if row.get("decision_sequence", 0) >= FIRST_SEQUENCE and "reason" in row]
    # Two boards of the arrival turn 3100691 (the first with the arrival message), one decision.
    assert len(boards) == len(decisions) + 1, (len(boards), len(decisions))
    (TARGET / "floor.json.xz").write_bytes(lzma.compress(json.dumps(
        {"boards": boards, "decisions": decisions}, ensure_ascii=False).encode(
            "utf-8", "surrogateescape"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))


if __name__ == "__main__":
    main()
