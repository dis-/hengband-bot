"""Extract the fixtures of n1-c life-222's loop-detected stop (2026-11-25 13:21, Magic-Eater Lv45).

* tests/fixtures/n1c-222-destruction-approach-1125.jsonl.gz: the boards (``type``
  ``player_turn``, the last board of a turn) of turns 6850301-6851527 on floor (14,50,0), the
  floor from its arrival to the loop detector: the explore, the wall searches after the *Destruction*,
  the 全感知 that showed 大鷲王『ソロンドール』 (race 468, index 5) on (8,172), and the approach's
  alternation (26,176) '3' / (27,177) '7'.  Source: the incident capture
  ``incident-captures/20261125-132149-loop-detected/snapshots/snapshots-current.jsonl.gz``.
* tests/fixtures/n1c-222-me-lists-1125.json: the absorbed power lists of the same capture's
  town-arrival checkpoint (13:20, turn 6802253, the town visit just before the floor), read from its
  ``policy.pkl`` (``_me_device_lists``).

    PYTHONPATH="src;tests;." python tests/extract_n1c_222_destruction_approach_1125_fixture.py <capture-dir>
"""
import gzip
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"
BOARDS = FIXTURES / "n1c-222-destruction-approach-1125.jsonl.gz"
LISTS = FIXTURES / "n1c-222-me-lists-1125.json"
WINDOW = (6850301, 6851527)


def boards(capture: Path) -> None:
    kept = {}
    source = capture / "snapshots" / "snapshots-current.jsonl.gz"
    with gzip.open(source, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            floor = raw.get("floor") or {}
            if (raw.get("type") == "player_turn" and floor.get("dungeon_id") == 14
                    and floor.get("level") == 50 and WINDOW[0] <= raw.get("turn", 0) <= WINDOW[1]):
                kept[raw["turn"]] = raw  # the last board of a turn is the decision's
    with gzip.GzipFile(BOARDS, "wb", mtime=0) as out:
        for turn in sorted(kept):
            out.write((json.dumps(kept[turn], ensure_ascii=False, sort_keys=True) + "\n")
                      .encode("utf-8", "surrogateescape"))
    print(BOARDS, BOARDS.stat().st_size, len(kept))


def lists(capture: Path) -> None:
    sys.path.insert(0, str(TESTS))
    import tests  # noqa: F401 -- isolate runtime files
    from replay_town_arrival import restore

    with TemporaryDirectory() as raw:
        policy = restore(capture / "town-arrival", Path(raw))
        found = {kind: rows for kind, (_turn, rows) in policy._me_device_lists.items()}
        turns = {kind: turn for kind, (turn, _rows) in policy._me_device_lists.items()}
    LISTS.write_text(json.dumps({"lists": found, "source": {
        "checkpoint": "n1-c/life-222/incident-captures/20261125-132149-loop-detected/town-arrival",
        "turns": turns}}, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(LISTS, LISTS.stat().st_size)


if __name__ == "__main__":
    capture = Path(sys.argv[1])
    boards(capture)
    lists(capture)
