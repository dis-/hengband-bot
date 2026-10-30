"""Extract the D40 n1-c life-055 equipment swap loop (2026-10-31 07:38-07:42).

Sources (read only):
  CAPTURE  bot-decisions.jsonl and state-tail.jsonl copied from the viewing bot.
  SERVER   copies of life-055 files read from the viewing server at 07:46/07:52:
           character-calibration.json (written 07:38 by the looping session),
           loadout-report.jsonl, and the first 40 lines of state.jsonl (after
           the 07:42 restart the game reloaded the same save, turn 204781:
           the ~f skill list and the earlier weapon proficiencies).
Boards are copied as recorded; nothing is constructed here.
"""
import gzip
import hashlib
import json
from pathlib import Path

CAPTURE = Path(r"C:\hengband-backups\pdca\captures\n1c-equip-loop-1031")
SERVER = Path(r"C:\hengband-backups\pdca\captures\n1c-equip-loop-1031-server")
TARGET = Path(__file__).parent / "fixtures" / "equip-tie-loop-20261031.json.gz"

# state-tail.jsonl line numbers (1-based, line 1 is a truncated fragment).
BOARDS = {
    "cutlass-worn-in-home": 35,      # turn 208664, after depositing the Short Sword
    "cutlass-worn-outside": 36,      # turn 208671, the board after leaving
    "short-sword-worn-in-home": 48,  # turn 208696, after depositing the Cutlass
    "short-sword-worn-outside": 49,  # turn 208706
}
DECISIONS = (4993, 4994, 5001, 5002)
REPORTS = (82, 87)  # pack Cutlass at proficiency 3192; first loop report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _report(row):
    return {
        "time": row["time"],
        "candidates": [
            {
                "main_hand": candidate["slots"].get("main_hand"),
                "sub_hand": candidate["slots"].get("sub_hand"),
                "melee_hands": candidate["melee_hands"],
            }
            for candidate in row["candidates"]
        ],
    }


def main():
    lines = (CAPTURE / "state-tail.jsonl").read_text(encoding="utf-8").splitlines()
    boards = {name: json.loads(lines[number - 1]) for name, number in BOARDS.items()}
    decisions = {}
    with open(CAPTURE / "bot-decisions.jsonl", encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            if number in DECISIONS:
                row = json.loads(line)
                equipment = row["equipment_optimization"]
                decisions[str(number)] = {
                    "turn": row["turn"], "key": row["key"], "reason": row["reason"],
                    "result_source": equipment["result_source"],
                    "transaction_next": equipment["transaction_next"],
                    "fresh_search_transition": equipment.get("fresh_search_transition"),
                }
    reports = (SERVER / "loadout-report.jsonl").read_text(encoding="utf-8").splitlines()
    head = [json.loads(line) for line in
            (SERVER / "state-head.jsonl").read_text(encoding="utf-8").splitlines()]
    skill = next(row for row in head if row.get("type") == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp")
    # The first player_turn carrying both swords (turn 205213).
    earlier = next(row for row in head if row.get("type") == "player_turn"
                   and {(item.get("tval"), item.get("sval")) for item in row["inventory"]}
                   >= {(23, 10), (23, 12)})
    data = {
        "provenance": {
            "capture": str(CAPTURE), "server_copy": str(SERVER),
            "sha256": {
                name: _sha256(path) for name, path in (
                    ("state-tail.jsonl", CAPTURE / "state-tail.jsonl"),
                    ("bot-decisions.jsonl", CAPTURE / "bot-decisions.jsonl"),
                    ("character-calibration.json", SERVER / "character-calibration.json"),
                    ("loadout-report.jsonl", SERVER / "loadout-report.jsonl"),
                    ("state-head.jsonl", SERVER / "state-head.jsonl"),
                )
            },
            "boards": BOARDS, "decisions": list(DECISIONS), "reports": list(REPORTS),
        },
        "boards": boards,
        "decisions": decisions,
        "reports": {str(number): _report(json.loads(reports[number])) for number in REPORTS},
        "calibration": json.loads((SERVER / "character-calibration.json").read_text(encoding="utf-8")),
        "skill_exp": skill,
        "earlier_weapons": {
            "turn": earlier["turn"],
            "items": [item for item in earlier["inventory"] if item.get("tval") == 23],
        },
    }
    TARGET.write_bytes(gzip.compress(
        json.dumps(data, ensure_ascii=True, sort_keys=True).encode(), mtime=0))
    print(f"sha256={_sha256(TARGET)} bytes={TARGET.stat().st_size}")


if __name__ == "__main__":
    main()
