"""Freeze the 2026-10-30 21:03 n1-c life-036 Tower of Sorcery stop (D24).

Source: the automatic capture incident-captures/20261030-210325-no-key-exhausted
of the viewing Magic-Eater n1-c life-036 (Lv8, Morivant, gold 14711), build
347b1bc7.  The bot walked to the Tower of Sorcery (building 8), posted
``1rf12\\r\\x1b`` (me-staff:recharge:5) and the game answered
「鑑定の杖 (21回分)を＄480 で再充填しました。」; the next decision stopped on
quest:blocked:me-staff with the empty key until the character retired.

The snapshot ring copy is the 16 MiB tail of a multi-member gzip: decoding
starts at the first member header and keeps whole members only.  Frozen: the
approach board (turn 649320, one step from the Tower entrance), the board the
game wrote after the recorded recharge (turn 649330, on the entrance grid),
the last skill-proficiency and Home knowledge rows the process consumed
before them,
and the monster knowledge of their monsters.

Only this extraction tool reads the capture; the committed test reads the
frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


CAPTURE = Path(
    "C:/hengband-backups/pdca/captures/n1c-1030-2100/life-036/"
    "incident-captures/20261030-210325-no-key-exhausted")
RING = CAPTURE / "snapshots" / "snapshots-current.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "me-tower-recharge-20261030.json.gz"


def ring_rows(data: bytes) -> list[dict]:
    rows, buf = [], data[data.index(b"\x1f\x8b\x08"):]
    while buf:
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = stream.decompress(buf)
        if not stream.eof:
            break  # the ring was copied while its last member was written
        rows.extend(json.loads(line) for line in out.decode("utf-8").splitlines()
                    if line.strip())
        buf = stream.unused_data
    return rows


def main():
    rows = ring_rows(RING.read_bytes())
    boards = [row for row in rows if row["type"] == "player_turn"]
    skill = next(row for row in reversed(rows) if row["type"] == "knowledge"
                 and row["knowledge"]["category"] == "skill_exp")
    home = next(row for row in reversed(rows) if row["type"] == "knowledge"
                and row["knowledge"]["category"] == "home")
    approach, recharged = boards[-3], boards[-1]
    assert (approach["turn"], approach["player"]["y"], approach["player"]["x"]) == (649320, 19, 56)
    assert (recharged["turn"], recharged["player"]["y"], recharged["player"]["x"]) == (649330, 20, 55)
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = {row["race_id"] for board in (approach, recharged)
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    case = dict(
        source="incident-20261030-210325-no-key-exhausted (n1-c life-036)",
        sources={RING.name: hashlib.sha256(RING.read_bytes()).hexdigest()},
        approach=approach,
        recharged=recharged,
        skill_knowledge=skill,
        home_knowledge=home,
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(case, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
