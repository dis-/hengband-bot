"""Freeze the 2026-10-30 n1-c life-045 Greater Hell-Beast mining boards.

Source: the viewing zombie Magic-Eater n1-c life-045 (Lv7, build 475bc157b):
its snapshot ring (copied to C:/hengband-backups/pdca/captures/me-stockout-1031/)
and its decision log beside it.  On Yeek cave 1F, mining (mode "mine",
12 of 16 veins collected), the unique Greater Hell-Beast (race 39) came into
view asleep at turn 136152; the decision kept mining
(fundraise:seek-treasure), and from 136186 the bot threw torches, fired
devices and meleed it for thousands of game turns.

Frozen: the dungeon boards of turns 136152 and 136186, the last
skill-proficiency and Home knowledge rows before them, the recorded
decision rows of those turns, and the race knowledge of the visible monster
(lib/edit/MonraceDefinitions.jsonc, read from the hengband checkout; run
with PYTHONPATH=src from C:/hengband).  Only this extraction tool reads the capture;
the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


CAPTURE = Path("C:/hengband-backups/pdca/captures/me-stockout-1031")
RING = CAPTURE / "life-045-snapshots-current.jsonl.gz"
DECISIONS = CAPTURE / "life-045-bot-decisions.jsonl"
OUTPUT = Path(__file__).with_name("fixtures") / "me-hellbeast-mining-20261030.json.gz"
SIGHTED_TURN, ATTACK_TURN = 136152, 136186
DECISION_FIELDS = ("turn", "reason", "key", "player", "floor", "position", "mining", "fundraising")


def ring_rows(data: bytes) -> list[dict]:
    rows, buf = [], data[data.index(b"\x1f\x8b\x08"):]
    while buf:
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = stream.decompress(buf)
        rows.extend(json.loads(line) for line in out.decode("utf-8").splitlines()
                    if line.strip())
        if not stream.eof:
            break  # the ring was copied while its last member was written
        buf = stream.unused_data
    return rows


def main():
    rows = ring_rows(RING.read_bytes())

    def board(turn):
        index = next(i for i, row in enumerate(rows)
                     if row["type"] == "player_turn" and row["turn"] == turn)
        return index, rows[index]

    def knowledge(category, before):
        return next(row for row in reversed(rows[:before]) if row["type"] == "knowledge"
                    and row["knowledge"]["category"] == category)

    sighted_index, sighted = board(SIGHTED_TURN)
    _, attack = board(ATTACK_TURN)
    for raw in (sighted, attack):
        assert [m["race_id"] for m in raw["visible_monsters"]] == [39]
        assert (raw["floor"]["dungeon_id"], raw["floor"]["level"]) == (2, 1)
    decisions = {}
    with DECISIONS.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("turn") in (SIGHTED_TURN, ATTACK_TURN):
                decisions.setdefault(str(row["turn"]), {k: row.get(k) for k in DECISION_FIELDS})
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    case = dict(
        source="n1-c life-045 (build 475bc157b) snapshot ring and decision log",
        sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (RING, DECISIONS)},
        sighted=sighted,
        attack=attack,
        knowledge=[knowledge("skill_exp", sighted_index), knowledge("home", sighted_index)],
        decisions=decisions,
        monraces={"39": asdict(races[39])},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
