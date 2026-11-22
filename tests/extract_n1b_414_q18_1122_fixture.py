"""Extract the fixtures of n1-b life-414's Q18 death (2026-11-22 10:42, Magic-Eater Lv33).

* tests/fixtures/n1b-414-q18-1122.jsonl.gz: the boards (``type`` ``player_turn``, the last board
  of a turn) of turns 1769330-1769533 (decisions 22885-22904, 10:42:33-10:42:34): the walk on
  from the choke (1,9), the shrieks on (1,16) and (2,18), the choke (1,19) left at once, the two
  hasted seahorses 443 and the giant squid 482 on (3,20), the Recall and death on (1,19).
  Source: the incident capture's ``capture/state.jsonl.gz``, copied read-only to
  C:/hengband-backups/pdca/n1b-414-death-1122/.
* tests/fixtures/n1b-414-me-lists-0848-1122.json: the absorbed power lists of the same life's
  08:48 town-arrival checkpoint (tests/fixtures/n1b-414-weapon-ready-1122, the latest one held
  locally; the 10:41 one stayed on the viewing server).  The dump at death (10:42) shows the
  absorbed wand of Teleport Away at 23 charges and the absorbed rod of it, 1 rod.

    python tests/extract_n1b_414_q18_1122_fixture.py [<state.jsonl.gz>]
"""
import gzip
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"
BOARDS = FIXTURES / "n1b-414-q18-1122.jsonl.gz"
LISTS = FIXTURES / "n1b-414-me-lists-0848-1122.json"
SOURCE = Path("C:/hengband-backups/pdca/n1b-414-death-1122/capture/state.jsonl.gz")
WINDOW = (1769330, 1769533)


def boards(state_path: Path) -> None:
    kept = {}
    with gzip.open(state_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            try:
                raw = json.loads(line)
            except ValueError:
                continue
            if raw.get("type") == "player_turn" and WINDOW[0] <= raw.get("turn", 0) <= WINDOW[1]:
                kept[raw["turn"]] = raw  # the last board of a turn is the decision's
    with gzip.GzipFile(BOARDS, "wb", mtime=0) as out:
        for turn in sorted(kept):
            out.write((json.dumps(kept[turn], ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
    print(BOARDS, BOARDS.stat().st_size, len(kept))


def lists() -> None:
    sys.path.insert(0, str(TESTS))
    import tests  # noqa: F401 -- isolate runtime files
    from support.town_arrival_fixture import load

    with TemporaryDirectory() as raw:
        policy, _journal, _steps = load(FIXTURES / "n1b-414-weapon-ready-1122", Path(raw))
        found = {kind: rows for kind, (_turn, rows) in policy._me_device_lists.items()}
        turns = {kind: turn for kind, (turn, _rows) in policy._me_device_lists.items()}
        policy._home_disposal.history_path.unlink(missing_ok=True)
    LISTS.write_text(json.dumps({"lists": found, "source": {
        "checkpoint": "n1-b/life-414/town-arrival/20261122-084821.496358536-turn1565228",
        "turns": turns}}, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(LISTS, LISTS.stat().st_size)


if __name__ == "__main__":
    boards(Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE)
    lists()
