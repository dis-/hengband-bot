"""Extract tests/fixtures/n1a-522-quest-search-1114.json.gz.

Source, copied read-only from the viewing server (~/hengbot-soak/n1-a/life-522):
C:/hengband-backups/pdca/captures/n1a-522-quest-search-1114/ -- n1-a life-522 (Zombie Warrior Lv28,
Angband 24F, RANDOM quest 41, target race 948, build bot-5bfd83ac0), stopped by the runner's
``stall:floor-dwell:quest-search:loop`` at 2026-11-14 05:34:12.

- ``rows``: every board of captures/20261114-053412-stall-floor-dwell-quest-search-loop/state.jsonl.gz
  (the last 114 boards before the stop, all on the lap east of the traps at (38,71), (38,72),
  (38,73) and (40,71));
- ``decisions``: that capture's decision rows (turn, sequence, key, reason, position, messages);
- ``terrain``: the bot's remembered terrain of the floor, read from jsonlog/checkpoints/
  map-left-1-24-41.txt (flight_recorder.render_remembered_map, written when the bot left the floor
  at 05:34:21, 9 seconds after the restart; its first row and column are y 5, x 4: the offset at
  which every wall and 40 of the 42 floor cells of the last board coincide with it);
- ``monraces``: the monster knowledge (lib/edit/MonraceDefinitions.jsonc) of the target and of every
  race on the boards.

    python tests/extract_n1a_522_quest_search_1114_fixture.py
"""
import gzip
import json
from dataclasses import asdict
from pathlib import Path

from extract_n1c_183_stairs_explore_loop_1109_fixtures import GAME, lines
from hengbot.monrace_knowledge import load_monrace_knowledge

SOURCE = Path("C:/hengband-backups/pdca/captures/n1a-522-quest-search-1114")
CAPTURE = SOURCE / "captures/20261114-053412-stall-floor-dwell-quest-search-loop"
MAP = SOURCE / "jsonlog/checkpoints/map-left-1-24-41.txt"
OUTPUT = Path(__file__).with_name("fixtures") / "n1a-522-quest-search-1114.json.gz"
DECISION_FIELDS = ("decision_sequence", "turn", "key", "reason", "position", "messages")
TARGET = 948  # quest 41's r_idx (the boards' progress.quests)
ORIGIN = (5, 4)  # the map's first row and column (module docstring)
GLYPHS = {"#": ("wall_t",), "+": ("door_t",), ":": ("rubble_t",), ".": ("floor_t",),
          "<": ("floor_t", "upstairs"), ">": ("floor_t", "downstairs")}


def terrain() -> dict:
    cells = {name: [] for names in GLYPHS.values() for name in names}
    for y, line in enumerate(MAP.read_text(encoding="utf-8").splitlines()):
        for x, glyph in enumerate(line):
            for name in GLYPHS.get(glyph, ()):
                cells[name].append([y + ORIGIN[0], x + ORIGIN[1]])
    return cells


def main() -> None:
    races = load_monrace_knowledge(GAME / "MonraceDefinitions.jsonc")
    rows = [row for row in lines(CAPTURE / "state.jsonl.gz") if row.get("type") == "player_turn"]
    ids = {TARGET} | {monster["race_id"] for row in rows
                      for field in ("visible_monsters", "detected_monsters")
                      for monster in row.get(field, [])}
    fixture = {
        "rows": rows,
        "decisions": [{field: row.get(field) for field in DECISION_FIELDS}
                      for row in lines(CAPTURE / "bot-decisions.jsonl.gz")],
        "terrain": terrain(),
        "monraces": {key: asdict(races[key]) for key in sorted(ids)},
    }
    payload = gzip.compress(json.dumps(fixture, ensure_ascii=False, default=sorted,
                                       separators=(",", ":")).encode("utf-8"), mtime=0)
    OUTPUT.write_bytes(payload)
    print(OUTPUT.name, len(rows), len(fixture["decisions"]), len(payload))


if __name__ == "__main__":
    main()
