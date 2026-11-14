"""Extract tests/fixtures/n1b-397-zul-arrival-1114/.

Source: n1-b life-397's incident capture 20261114-171836-no-key-exhausted
(build d7356e57ae), copied read-only from the viewing server to
C:/hengband-backups/pdca/captures/n1b-397-1114pm/incident-captures/: the
town-arrival checkpoint of the 17:18:20 Outpost visit with all 64 journal rows
(the Q25 claim, sales, the levitation ring put on, the inn walk and row 63 '<'
onto the global map), and the snapshot ring's 22 player-turn boards that
follow it (rows 2118-2139: the global-map walk to Zul, the meal, the '>' into
Zul and the arrival board at (64,1), turn 4473424, where the stop began), and
ring row 2140, the skill list the arrival's periodic request was answered with.

    PYTHONPATH="src;tests" python tests/extract_n1b_397_zul_arrival_1114_fixture.py
"""
import json
import lzma
import zlib
from pathlib import Path

from support.town_arrival_fixture import PRESET, extract

CAPTURE = Path("C:/hengband-backups/pdca/captures/n1b-397-1114pm/incident-captures/"
               "20261114-171836-no-key-exhausted")
TARGET = Path(__file__).with_name("fixtures") / "n1b-397-zul-arrival-1114"
RING_ROWS = range(2118, 2140)
# The ~f skill list the arrival's periodic:skill-exp-knowledge asked for (ring row 2140).
SKILL_EXP_ROW = 2140


def ring_rows(path: Path) -> list[dict]:
    data = path.read_bytes()
    rows, buf = [], data[data.index(b"\x1f\x8b\x08"):]
    while buf:
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = stream.decompress(buf)
        if not stream.eof:
            break  # the ring was copied while its last member was written
        rows.extend(json.loads(line) for line in out.decode("utf-8").splitlines() if line.strip())
        buf = stream.unused_data
    return rows


if __name__ == "__main__":
    extract(CAPTURE / "town-arrival", TARGET, 64, frozenset({"_loadout_report_path"}))
    rows = ring_rows(CAPTURE / "snapshots" / "snapshots-current.jsonl.gz")
    boards = [rows[index] for index in RING_ROWS]
    assert all(board["type"] == "player_turn" for board in boards)
    assert boards[-1]["turn"] == 4473424 and boards[-1]["floor"]["town_id"] == 4
    assert rows[SKILL_EXP_ROW]["knowledge"]["category"] == "skill_exp"
    # The decision tail's rows decided on those boards (the one after row 63's '<' on).
    tail = []
    for line in (CAPTURE / "decision-tail.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            tail.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # the bounded tail starts in the middle of a record
    start = max(index for index, row in enumerate(tail)
                if row.get("key") == "<" and row.get("reason") == "town:zul:enter-global")
    recorded = [[row["key"], row["reason"], row["turn"]] for row in tail[start + 1:start + 1 + len(boards)]]
    assert [turn for _key, _reason, turn in recorded] == [board["turn"] for board in boards]
    (TARGET / "ring-boards.json.xz").write_bytes(lzma.compress(json.dumps(
        {"boards": boards, "decisions": recorded, "skill_exp": rows[SKILL_EXP_ROW]},
        ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in TARGET.iterdir()))
