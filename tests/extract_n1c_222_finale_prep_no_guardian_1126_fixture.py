"""Extract tests/fixtures/n1c-222-finale-prep-no-guardian-1126.json.gz (tests/test_finale_prep_no_guardian_1126_recorded.py).

Source: n1-c life-222 (Zombie Magic-Eater Lv49, Angband recall depth 99 after the 99F expedition),
the live decision log's snapshots:

- ``town``: ``jsonlog/snapshots/snapshots-20261126-012209-523c59.jsonl.gz``, the last
  ``player_turn`` board of turn 9366822 (2026-11-26 01:13:26, decision 23603): the town board the
  target dungeon turned from Angband to the Castle (the conquest target), the expedition's 30
  Potions of Healing in the pack;
- ``castle``: ``jsonlog/snapshots/snapshots-current.jsonl.gz`` (as of 01:36), the last
  ``player_turn`` board of turn 9551660 (01:27:32, decision 27419, ``hunt:detected-target``):
  the Castle 65F with 皇帝『レイザーク』 detected, before the kill and the ``conquest:*`` loot of
  01:27:45.

    python tests/extract_n1c_222_finale_prep_no_guardian_1126_fixture.py <town.jsonl.gz> <castle.jsonl.gz> [out]
"""
import gzip
import json
import sys
from pathlib import Path

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-222-finale-prep-no-guardian-1126.json.gz"
TURNS = {"town": 9366822, "castle": 9551660}


def _board(source: Path, turn: int) -> dict:
    kept = None
    with gzip.open(source, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            if raw.get("type") == "player_turn" and raw.get("turn") == turn:
                kept = raw  # the last board of a turn is the decision's
    assert kept is not None, turn
    return kept


def main(town: Path, castle: Path, out: Path = FIXTURE) -> None:
    boards = {"town": _board(town, TURNS["town"]), "castle": _board(castle, TURNS["castle"])}
    with gzip.GzipFile(out, "wb", mtime=0) as stream:
        stream.write(json.dumps(boards, ensure_ascii=False, sort_keys=True)
                     .encode("utf-8", "surrogateescape"))
    print(out, out.stat().st_size)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), *(Path(arg) for arg in sys.argv[3:4]))
