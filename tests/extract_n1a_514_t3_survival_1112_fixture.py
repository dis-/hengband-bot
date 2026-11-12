"""Extract tests/fixtures/n1a-514-t3-survival-1112.json.gz.

Source, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1a-514-death-1112/: n1-a life-514 (Half-Giant
Warrior Lv46, Angband 49F) died 2026-11-12 11:54:51; captures/20261112-115451-exit-no-marker
holds state.jsonl.gz (every board of the floor's last minutes, 11282844-11284461, with the
character and skill-knowledge rows between them) and bot-decisions.jsonl.gz.

The fixture keeps every row of state.jsonl in order (``player_turn``, ``knowledge``,
``character``; the ``store`` rows are not on this floor and are left out), the decision rows
(turn, sequence, key, reason, rung, position, HP) and the race knowledge
(lib/edit/MonraceDefinitions.jsonc) of every race on the boards.

    python tests/extract_n1a_514_t3_survival_1112_fixture.py
"""
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from extract_n1c_183_stairs_explore_loop_1109_fixtures import GAME, lines
from hengbot.monrace_knowledge import load_monrace_knowledge

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1a-514-death-1112/captures/"
               "20261112-115451-exit-no-marker")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-514-t3-survival-1112.json.gz"
KEPT = ("player_turn", "knowledge", "character")
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "rung", "position", "player")


def main() -> None:
    rows = [row for row in lines(CAPTURE / "state.jsonl.gz") if row.get("type") in KEPT]
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    ids = {monster["race_id"] for row in rows
           for field in ("visible_monsters", "detected_monsters") for monster in row.get(field, [])}
    fixture = {
        "rows": rows,
        "decisions": [{field: row.get(field) for field in DECISION_FIELDS}
                      for row in lines(CAPTURE / "bot-decisions.jsonl.gz")],
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    payload = gzip.compress(json.dumps(fixture, ensure_ascii=False, default=sorted,
                                       separators=(",", ":")).encode("utf-8"), mtime=0)
    OUTPUT.write_bytes(payload)
    print(len(rows), len(fixture["decisions"]), len(payload))


if __name__ == "__main__":
    main()
