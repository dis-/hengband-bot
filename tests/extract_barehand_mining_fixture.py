"""Freeze the 2026-10-31 n1-c life-065 bare-handed mining boards (D45).

Source: the viewing zombie Magic-Eater n1-c life-065 (Lv9, build aa56fccb0),
copied to C:/hengband-backups/pdca/captures/n1c-barehand-1031/
cap-n1c-barehand-1031/: state-window.jsonl (snapshot rows of game turns
767566-779610 with the skill knowledge row), decisions-window.jsonl (decision
rows 777802-779200) and state-latest.jsonl / decisions-latest.jsonl (the
bare-handed fight still going at 12:41, turns 790055-791632).  Mining on
Yeek cave 1F, 'ta' (fundraise:wield-digging-tool) took off the Short Sword at
turn 778659; a breeding white worm mass (race 31) came into view at 778665
and fundraise:eliminate-multiplier, the ranged fire and melee took every
later turn with the main hand empty.

Frozen: the boards of turns 778659 (sword worn, nothing in view), 778665
(hand empty, the worm mass in view two cells away), 778697 (hand empty, the
worm masses adjacent) and 791632 (the last recorded board, a worm mass
adjacent), the skill-proficiency knowledge row, the recorded decision rows of
those turns, and the race knowledge of race 31 and of the non-breeding
Yeek cave 1F race 52 (Blue yeek, the constructed sleeper of the owner rule
2026-10-31 「眠っている敵なら外してよい」) (lib/edit/
MonraceDefinitions.jsonc, read from the hengband checkout; run with
PYTHONPATH=src from C:/hengband).  Only this extraction tool reads the
capture; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


CAPTURE = Path("C:/hengband-backups/pdca/captures/n1c-barehand-1031/cap-n1c-barehand-1031")
WINDOW = CAPTURE / "state-window.jsonl"
LATEST = CAPTURE / "state-latest.jsonl"
DECISIONS = (CAPTURE / "decisions-window.jsonl", CAPTURE / "decisions-latest.jsonl")
OUTPUT = Path(__file__).with_name("fixtures") / "me-barehand-mining-20261031.json.gz"
BOARDS = {"worn": 778659, "sighted": 778665, "adjacent": 778697, "latest": 791632}
WORM_MASS = 31
BLUE_YEEK = 52
DECISION_FIELDS = ("turn", "reason", "key", "player", "floor", "position", "mining", "fundraising")


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main():
    window, latest = rows(WINDOW), rows(LATEST)
    boards = {}
    for name, turn in BOARDS.items():
        source = latest if name == "latest" else window
        boards[name] = next(row for row in source
                            if row["type"] == "player_turn" and row["turn"] == turn)
    assert [item["slot"] for item in boards["worn"]["equipment"]].count("main_hand") == 1
    for name in ("sighted", "adjacent", "latest"):
        raw = boards[name]
        assert not any(item["slot"] in ("main_hand", "sub_hand") for item in raw["equipment"])
        assert {m["race_id"] for m in raw["visible_monsters"]} == {WORM_MASS}
        assert (raw["floor"]["dungeon_id"], raw["floor"]["level"]) == (2, 1)
    assert not boards["worn"]["visible_monsters"]
    skill = next(row for row in window if row["type"] == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp")
    decisions = {}
    for path in DECISIONS:
        for row in rows(path):
            if row.get("turn") in BOARDS.values():
                decisions.setdefault(str(row["turn"]), []).append(
                    {k: row.get(k) for k in DECISION_FIELDS})
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    case = dict(
        source="n1-c life-065 (build aa56fccb0) snapshot rows and decision logs",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (WINDOW, LATEST, *DECISIONS)},
        boards=boards,
        knowledge=skill,
        decisions=decisions,
        monraces={str(race): asdict(races[race]) for race in (WORM_MASS, BLUE_YEEK)},
    )
    OUTPUT.parent.mkdir(exist_ok=True)
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
