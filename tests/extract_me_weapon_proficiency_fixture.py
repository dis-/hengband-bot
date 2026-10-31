"""Extract the D50 n1-c life-072 Home boards (2026-10-31 22:3x, Lv14 Magic-Eater).

Source (read only): CAPTURE state.jsonl and jsonlog/bot-decisions.jsonl copied
from the viewing bot.  The Short Sword (1d7) (+0,+0) at proficiency 5711 stays
worn while Home holds a Long Sword (2d5) (+1,+4) at proficiency 1376
(Unskilled).  Boards are copied as recorded; nothing is constructed here.
"""
import gzip
import hashlib
import json
from pathlib import Path

CAPTURE = Path(r"C:\hengband-backups\pdca\captures\d50-weapon-1031\life-072")
TARGET = Path(__file__).parent / "fixtures" / "me-weapon-proficiency-20261031.json.gz"

# state.jsonl line numbers (0-based).
SKILL_EXP = 731  # the ~f skill list of the same Lv14 character (turn 1070936)
BOARDS = {
    "home-open": 740,          # turn 1071919, Home page with all 15 items
    "outside-1": 741,          # turn 1071925
    "outside-2": 742,
    "home-reentered": 743,     # turn 1071925, before the Glaive deposit
    "home-deposited": 744,     # after 'dn': the Glaive (2d5) is in Home
    "outside-after-deposit": 745,  # turn 1071937
}
DECISIONS = (434, 435, 436, 437)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    lines = (CAPTURE / "state.jsonl").read_text(encoding="utf-8").splitlines()
    boards = {name: json.loads(lines[number]) for name, number in BOARDS.items()}
    decisions = {}
    with open(CAPTURE / "jsonlog" / "bot-decisions.jsonl", encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            if number in DECISIONS:
                row = json.loads(line)
                equipment = row["equipment_optimization"]
                decisions[str(number)] = {
                    "turn": row["turn"], "key": row["key"], "reason": row["reason"],
                    "chosen_band": equipment.get("chosen_band"),
                    "band_descent": equipment.get("band_descent"),
                    "search_catalog_origins": equipment.get("search_catalog_origins"),
                    "transaction_next": equipment.get("transaction_next"),
                }
    data = {
        "provenance": {
            "capture": str(CAPTURE),
            "sha256": {
                name: _sha256(CAPTURE / name)
                for name in ("state.jsonl", "jsonlog/bot-decisions.jsonl")
            },
            "boards": BOARDS, "skill_exp": SKILL_EXP, "decisions": list(DECISIONS),
        },
        "boards": boards,
        "skill_exp": json.loads(lines[SKILL_EXP]),
        "decisions": decisions,
    }
    TARGET.write_bytes(gzip.compress(
        json.dumps(data, ensure_ascii=True, sort_keys=True).encode(), mtime=0))
    print(f"sha256={_sha256(TARGET)} bytes={TARGET.stat().st_size}")


if __name__ == "__main__":
    main()
