"""Extract the #47 n1-c life-055 unidentified {average} lantern boards (2026-10-31).

Sources (read only):
  CAPTURE  bot-decisions.jsonl and state-tail.jsonl copied from the viewing bot
           (the D40 equipment swap loop capture; the Wooden Torch is out,
           light radius 0, and the Brass Lantern {average} is carried, known=false).
  SERVER   copies of life-055 files read from the viewing server at 07:46/07:52:
           character-calibration.json, and the first 40 lines of state.jsonl
           (the same save reloaded at turn 204781: the ~f skill list and the
           recorded C screen of turn 205220 with its mutation list).
Boards are copied as recorded; nothing is constructed here.
"""
import gzip
import hashlib
import json
from pathlib import Path

CAPTURE = Path(r"C:\hengband-backups\pdca\captures\n1c-equip-loop-1031")
SERVER = Path(r"C:\hengband-backups\pdca\captures\n1c-equip-loop-1031-server")
TARGET = Path(__file__).parent / "fixtures" / "unid-light-20261031.json.gz"

# state-tail.jsonl line numbers (1-based, line 1 is a truncated fragment).
BOARDS = {
    "in-home": 35,   # turn 208664, Home screen, the Short Sword just deposited
    "outside": 36,   # turn 208671, the board after leaving Home
}
# The decisions on those boards and the Q34 lantern chain of the same life.
DECISIONS = (58, 59, 60, 938, 939, 4993, 4994)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    lines = (CAPTURE / "state-tail.jsonl").read_text(encoding="utf-8").splitlines()
    boards = {name: json.loads(lines[number - 1]) for name, number in BOARDS.items()}
    decisions = {}
    with open(CAPTURE / "bot-decisions.jsonl", encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            if number in DECISIONS:
                row = json.loads(line)
                decisions[str(number)] = {
                    "turn": row["turn"], "key": row["key"], "reason": row["reason"],
                    "light_radius": row.get("light_radius"),
                    "light_candidates": (row.get("equipment_optimization") or {})
                    .get("search_slot_candidate_counts", {}).get("light"),
                }
            if number > max(DECISIONS):
                break
    head = [json.loads(line) for line in
            (SERVER / "state-head.jsonl").read_text(encoding="utf-8").splitlines()]
    skill = next(row for row in head if row.get("type") == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp")
    character = next(row for row in head if row.get("type") == "character")
    data = {
        "provenance": {
            "capture": str(CAPTURE), "server_copy": str(SERVER),
            "sha256": {
                name: _sha256(path) for name, path in (
                    ("state-tail.jsonl", CAPTURE / "state-tail.jsonl"),
                    ("bot-decisions.jsonl", CAPTURE / "bot-decisions.jsonl"),
                    ("character-calibration.json", SERVER / "character-calibration.json"),
                    ("state-head.jsonl", SERVER / "state-head.jsonl"),
                )
            },
            "boards": BOARDS, "decisions": list(DECISIONS),
        },
        "boards": boards,
        "decisions": decisions,
        "calibration": json.loads((SERVER / "character-calibration.json").read_text(encoding="utf-8")),
        "skill_exp": skill,
        "character": character,
    }
    TARGET.write_bytes(gzip.compress(
        json.dumps(data, ensure_ascii=True, sort_keys=True).encode(), mtime=0))
    print(f"sha256={_sha256(TARGET)} bytes={TARGET.stat().st_size}")


if __name__ == "__main__":
    main()
