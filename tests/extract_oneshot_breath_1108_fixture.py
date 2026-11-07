"""Extract the 2026-11-08 fixture of the one-shot breath rule (oneshot_breath).

Source, read-only from the viewing server: n1-c life-161's state.jsonl (Angband 44F, 2026-11-08
00:14, died to 『ウートガルザ・ロキ』's cold breath), plain or gzip-compressed, whole or any slice
that holds the last skill list before the window.

Output: tests/fixtures/oneshot-breath-n1c-161-1108.json.xz ({"skill": <the last "knowledge" row
with skill_exp before the window>, "boards": [<player_turn rows of turns FIRST..LAST>]}): the walk
to the down stair from two boards before the giant ESP first showed the sleeping Loki (turn
3226983) to two boards after it last did (3227072).

    python tests/extract_oneshot_breath_1108_fixture.py <state.jsonl[.gz]>
"""
import gzip
import json
import lzma
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "oneshot-breath-n1c-161-1108.json.xz"
FIRST, LAST = 3226959, 3227094


def main() -> None:
    source = Path(sys.argv[1])
    opener = gzip.open if source.suffix == ".gz" else open
    skill, boards = None, []
    with opener(source, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("type") == "knowledge" and "skill_exp" in line and row["turn"] <= FIRST:
                skill = row
            elif row.get("type") == "player_turn" and FIRST <= row["turn"] <= LAST:
                boards.append(row)
    FIXTURE.write_bytes(lzma.compress(
        json.dumps({"skill": skill, "boards": boards}, ensure_ascii=False).encode("utf-8"),
        preset=9 | lzma.PRESET_EXTREME))


if __name__ == "__main__":
    main()
