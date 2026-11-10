"""Extract tests/fixtures/n1a-505-explore-loop-1110/.

Sources, copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/:

- ``louse-0234``: n1-a life-505 (warrior Lv25, Angband 6F, random quest 49, build
  7404002a7) captures/20261110-023409-loop-detected state.jsonl and decisions, with the
  remembered terrain of its incident twin incident-captures/20261110-023404-loop-detected
  (n1a-505-explore-loop-1110/).
- ``hunt-0229``: n1-c life-186 (Magic-Eater Lv29, dungeon 3 23F, build 7404002a7)
  captures/20261110-022954-loop-detected state.jsonl and decisions, with the remembered
  terrain of its incident twin incident-captures/20261110-022951-loop-detected
  (n1c-186-hunt-loop-1110/).

Each fixture holds its rows (boards and knowledge responses, in order), the decision rows
(turn, sequence, key, reason, position), the monster knowledge
(lib/edit/MonraceDefinitions.jsonc) of every race on the boards, the knowledge of the floor's
dungeon (lib/edit/DungeonDefinitions.jsonc) and the stop's remembered terrain.

    python tests/extract_n1a_505_explore_loop_1110_fixtures.py
"""
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from extract_n1c_183_stairs_explore_loop_1109_fixtures import GAME, lines
import extract_n1c_183_stairs_explore_loop_1109_fixtures as base
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.monrace_knowledge import load_monrace_knowledge

ROOT = Path("C:/hengband-backups/pdca/captures")
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-505-explore-loop-1110"
CASES = (
    ("louse-0234", "n1a-505-explore-loop-1110/20261110-023409-loop-detected",
     "n1a-505-explore-loop-1110/incident-023404"),
    ("hunt-0229", "n1c-186-hunt-loop-1110/20261110-022954-loop-detected",
     "n1c-186-hunt-loop-1110/incident-022951"),
)


def main() -> None:
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    dungeons = load_dungeon_knowledge(GAME / "DungeonDefinitions.jsonc")
    base.OUTPUT = OUTPUT
    for name, capture, incident in CASES:
        rows = [row for row in lines(ROOT / capture / "state.jsonl.gz")
                if row.get("type") in {"player_turn", "knowledge"}]
        base.write(name, rows, lines(ROOT / capture / "bot-decisions.jsonl.gz"),
                   ROOT / incident, races)
        path = OUTPUT / f"{name}.json.gz"
        fixture = json.loads(gzip.decompress(path.read_bytes()))
        dungeon = rows[0]["floor"]["dungeon_id"]
        fixture["dungeons"] = {str(dungeon): asdict(dungeons[dungeon])}
        path.write_bytes(gzip.compress(json.dumps(
            fixture, ensure_ascii=False, default=sorted, separators=(",", ":")).encode("utf-8"),
            mtime=0))


if __name__ == "__main__":
    main()
