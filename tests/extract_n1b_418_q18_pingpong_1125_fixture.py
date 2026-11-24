"""Extract the fixtures of n1-b life-418's Q18 livelock stop (2026-11-25 06:22, Magic-Eater Lv38).

* tests/fixtures/n1b-418-q18-1125.jsonl.gz: the boards (``type`` ``player_turn``, the last board
  of a turn) of turns 3419883-3420056 on floor (0,35,18): the shriek hold on the choke (1,15), the
  walk on through the shouted (1,16) (1,17) (2,18) with the siren's shriek on (1,16), the choke
  (1,19) walked off at once, and the alternation (2,20) '2' exit-walk / (3,20) '8' exit-to-choke
  for the giant squid 482 (index 8) on (9,24), seen from (3,20) only, sensed by ESP from (2,20),
  until the ping-pong guard escalated to the livelock stop.  Source: the incident capture
  ``incident-captures/20261125-062225-livelock-exhausted/snapshots/snapshots-current.jsonl.gz``.
* tests/fixtures/n1b-418-me-lists-1125.json: the absorbed power lists of the same capture's
  town-arrival checkpoint (06:20, turn 3415525, just before the quest was entered), read from its
  ``policy.pkl`` (``_me_device_lists``).

    PYTHONPATH="src;tests;." python tests/extract_n1b_418_q18_pingpong_1125_fixture.py <capture-dir>
"""
import gzip
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"
BOARDS = FIXTURES / "n1b-418-q18-1125.jsonl.gz"
LISTS = FIXTURES / "n1b-418-me-lists-1125.json"
WINDOW = (3419883, 3420056)


def boards(capture: Path) -> None:
    kept = {}
    source = capture / "snapshots" / "snapshots-current.jsonl.gz"
    with gzip.open(source, "rt", encoding="utf-8", errors="surrogateescape") as stream:
        for line in stream:
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            if (raw.get("type") == "player_turn" and (raw.get("floor") or {}).get("quest_id") == 18
                    and WINDOW[0] <= raw.get("turn", 0) <= WINDOW[1]):
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
        "checkpoint": "n1-b/life-418/incident-captures/20261125-062225-livelock-exhausted/town-arrival",
        "turns": turns}}, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(LISTS, LISTS.stat().st_size)


if __name__ == "__main__":
    capture = Path(sys.argv[1])
    boards(capture)
    lists(capture)
