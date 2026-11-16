"""Freeze n1-a life-528's last Quest 25 boards (2026-11-16 13:13:08-13:13:13) and its Home shelf.

Source: n1-a life-528 (warrior Lv41, device skill 33, build bot-0f3b00a68) on hengband.net, the
death stop ~/hengbot-soak/n1-a/life-528/captures/20261116-131318-exit-no-marker (its ring: the
previous process's decisions 73-105 and the last process's 0-49, the death), copied to
C:/hengband-backups/pdca/captures/n1a-528-q25-death-1116/captures with
~/hengbot-soak/n1-a/life-528/jsonlog/q25-battle.json as the last process left it, and the town
arrival of incident-captures/20261116-131313-player-death (12:54:07): its journal row 5 is the
board inside the Home (capacity 240) that shows the shelf's seven Wands of Teleport Other
(77 charges) while the pack held the Rod of Teleport Other.  The boards are cut as
tests/extract_n1b_382_q25_patrol_owner_1113_fixture.py cuts them (its ``process``): ``first`` the
previous process's tail, ``second`` the last process.

Only this extraction tool reads the capture; the committed test reads the fixture alone.
"""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests import extract_n1b_382_q25_patrol_owner_1113_fixture as cut

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-528-q25-death-1116.json.gz"
LAST = "20261116-131318-exit-no-marker"
ARRIVAL = Path("..") / "incident-captures" / "20261116-131313-player-death" / "town-arrival"
HOME_ROW = 5


def _previous(directory: str):
    """The previous process's tail in the ring: the decisions before the last restart."""
    capture = ROOT / directory
    rows = cut.ring_rows(capture / "state.jsonl.gz")
    first_turn = min(row["turn"] for row in rows if row.get("type") == "player_turn")
    decisions = [row for row in cut._decisions(capture / "bot-decisions.jsonl.gz")
                 if row["turn"] >= first_turn and row.get("floor", {}).get("quest_id") == cut.QUEST]
    restart = max(index for index, row in enumerate(decisions) if row["decision_sequence"] == 0)
    boards, recorded = [], []
    for row in decisions[:restart]:
        same = [board for board in rows if board.get("type") == "player_turn"
                and board["turn"] == row["turn"]]
        board = same[-1]
        position = row["position"]
        assert (board["player"]["y"], board["player"]["x"]) == (position["y"], position["x"]), row
        boards.append(dict(board, messages=row["messages"]))
        recorded.append({"sequence": row["decision_sequence"], "turn": row["turn"],
                         "reason": row["reason"], "key": row["key"]})
    return boards, recorded


def main():
    cut.ROOT = ROOT
    first_boards, first_recorded = _previous(LAST)
    boards, recorded, knowledge = cut.process(LAST, restarted=True)
    with gzip.open(ROOT / ARRIVAL / "journal.jsonl.gz", "rt", encoding="utf-8") as stream:
        journal = [json.loads(line) for line in stream]
    home = json.loads(journal[HOME_ROW]["line"])
    assert home["store"]["capacity"] == 240, home["store"].get("capacity")
    races = load_monrace_knowledge(find_monrace_definitions(Path(__file__), None))
    ids = {monster["race_id"] for board in (*first_boards, *boards)
           for field in ("visible_monsters", "detected_monsters") for monster in board.get(field, [])}
    case = dict(source="n1a-528-q25-death-1116",
                first=dict(boards=first_boards, recorded=first_recorded),
                second=dict(boards=boards, recorded=recorded),
                skill=knowledge.get("skill_exp"), home=knowledge.get("home"), home_board=home,
                monraces={key: asdict(races[key]) for key in sorted(ids) if key in races},
                battle_record=json.loads((ROOT / "q25-battle.json").read_text(encoding="utf-8")))
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    sys.stdout.write(f"{OUTPUT} {OUTPUT.stat().st_size} {len(first_boards)} {len(boards)} "
                     f"{first_recorded[0]['sequence']}-{first_recorded[-1]['sequence']} "
                     f"{recorded[0]['sequence']}-{recorded[-1]['sequence']} {sorted(knowledge)}\n")


if __name__ == "__main__":
    main()
