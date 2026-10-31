"""Freeze the D49 n1-c stops of 2026-10-31 19:22-19:38 and the D47 Q2 loop.

Sources (automatic captures of the viewing Magic-Eater n1-c, build
cfc32e192; C:/hengband-backups/pdca/captures/):
  opening  n1c-churn-1031-19/life-066 incident 20261031-192207: Lv7 afraid
           beside 忍び寄る人形『メリー』, seven futile melee keys, then
           quest:blocked:opening-route (no-progress:quest).  Ring rows 885-892.
  inn      n1c-churn-1031-19/life-067 incident 20261031-192914: the walk from
           Morivant's Tower to the inn after stage 1 (me-staff:return-to-shop),
           owner-retired-burst.  Ring rows 3738-3751 (one board per turn); the
           sequence record is the 192859 capture's ``_me_staff_sequence``.
  tower    n1c-churn-1031-19/life-068 incident 20261031-193656: the Tower
           approach after the inn teleport (me-staff:approach-tower),
           loop-detected after 30 town-blocked decisions.  Ring rows 3250-3264.
  q2       n1c-life065-loop-1031 capture 20261031-191957: Q2 TAKEN, the board
           in Telmora after fixedquest:q2-travel (state rows 14-15).

The snapshot ring copy is the tail of a multi-member gzip: decoding starts at
the first member header and keeps whole members only.  Only this extraction
tool reads the captures; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import json
import zlib
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge


ROOT = Path("C:/hengband-backups/pdca/captures")
CHURN = ROOT / "n1c-churn-1031-19"
OPENING = CHURN / "life-066/incident-captures/20261031-192207-quest-blocked-opening-route"
INN = CHURN / "life-067/incident-captures/20261031-192914-town-blocked-owner-retired-burst"
INN_STATE = CHURN / "life-067/incident-captures/20261031-192859-town-blocked-owner-retired-burst"
TOWER = CHURN / "life-068/incident-captures/20261031-193656-loop-detected"
Q2 = ROOT / "n1c-life065-loop-1031/captures/20261031-191957-loop-detected/state.jsonl.gz"
OUTPUT = Path(__file__).with_name("fixtures") / "me-staff-loops-20261031.json.gz"


def ring_rows(path: Path) -> list[dict]:
    data = path.read_bytes()
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


def knowledge(rows, before, category):
    return next((row for row in reversed(rows[:before]) if row["type"] == "knowledge"
                 and row["knowledge"]["category"] == category), None)


def walk(capture: Path, first: int, last: int, state: Path) -> dict:
    rows = ring_rows(capture / "snapshots" / "snapshots-current.jsonl.gz")
    boards, turns = [], set()
    for row in rows[first:last + 1]:
        if row["type"] == "player_turn" and row["turn"] not in turns:
            turns.add(row["turn"])
            boards.append(row)
    record = json.loads((state / "policy-state.json").read_text(encoding="utf-8"))
    return dict(boards=boards, skill=knowledge(rows, first, "skill_exp"),
                home=knowledge(rows, first, "home"),
                sequence=record["state"]["_me_staff_sequence"])


def main():
    opening_rows = ring_rows(OPENING / "snapshots" / "snapshots-current.jsonl.gz")
    opening = dict(boards=[row for row in opening_rows[885:893] if row["type"] == "player_turn"],
                   skill=knowledge(opening_rows, 885, "skill_exp"),
                   home=knowledge(opening_rows, 885, "home"))
    assert [board["turn"] for board in opening["boards"]][:2] == [83713, 83726]
    inn = walk(INN, 3738, 3751, INN_STATE)
    assert (inn["boards"][0]["player"]["y"], inn["boards"][0]["player"]["x"]) == (19, 56)
    tower = walk(TOWER, 3250, 3264, TOWER)
    assert (tower["boards"][-1]["player"]["y"], tower["boards"][-1]["player"]["x"]) == (34, 81)
    with gzip.open(Q2, "rt", encoding="utf-8") as stream:
        q2_rows = [json.loads(line) for line in stream if line.strip()]
    q2 = dict(boards=q2_rows[14:16])
    assert q2["boards"][0]["turn"] == 5135211
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    ids = {row["race_id"] for case in (opening, inn, tower, q2) for board in case["boards"]
           for field in ("visible_monsters", "detected_monsters")
           for row in board.get(field, [])}
    fixture = dict(
        source="D49/D47 n1-c captures of 2026-10-31 (build cfc32e192)",
        opening=opening, inn=inn, tower=tower, q2=q2,
        monraces={key: asdict(races[key]) for key in sorted(ids)},
    )
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(fixture, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
