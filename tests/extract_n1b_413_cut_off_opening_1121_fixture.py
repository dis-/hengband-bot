"""Extract tests/fixtures/n1b-413-cut-off-opening-1121/pin.json.xz.

Source: n1-b life-413 (Angband 12F, RANDOM quest 43), the two stops of 2026-11-21
(n1b-413-20261121-190207-stall-floor-dwell-melee-rearm-empty-hand and
n1b-413-20261121-201135-stall-floor-dwell-stuck-walled-off-wield-digger).  The 20:11 run was a
fresh process started on the 19:02 stop's save; its bot-stdout.log holds every key it sent.  The
save (renamed for the replaying uid) was loaded by a headless game of the same tree and the
recorded keys from the first move (line 13) to the one before the first 'ta' (line 452) were
posted to it through the control port; each answered board was kept (boards.jsonl).  The replay
ends where the recorded run did: (46,30), the 'ta' next.  The boards are decided here on a fresh
policy, as the restarted bot decided them (no key of its own sent), so that its remembered
terrain and visit counts are the run's; the last board and that memory are the pin.

    python tests/extract_n1b_413_cut_off_opening_1121_fixture.py <boards.jsonl>
"""
import copy
import json
import lzma
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests"), str(ROOT)]

import tests  # noqa: F401,E402
from hengbot.model import parse_snapshot  # noqa: E402
from hengbot.monrace_knowledge import load_monrace_knowledge  # noqa: E402
from support.recorded import EDIT, _policy  # noqa: E402
from support.town_arrival_fixture import PRESET  # noqa: E402

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-cut-off-opening-1121"


if __name__ == "__main__":
    boards = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()]
    with TemporaryDirectory() as directory:
        policy = _policy(Path(directory), load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc"))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), policy._monrace_knowledge))
        policy.consume_skill_knowledge({"player": {"level": boards[0]["player"]["level"]},
                                        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]}})
        for raw in boards:
            policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        board = {key: value for key, value in boards[-1].items() if key not in ("key_index", "key")}
        pin = {
            "board": board,
            "terrain": {name: sorted(map(list, getattr(policy, f"_remembered_{name}_t")))
                        for name in ("known", "marked", "floor", "wall", "door", "rubble")},
            "upstairs": sorted([cell.y, cell.x] for cell in policy._remembered_upstairs),
            "visits": sorted([cell.y, cell.x, count] for cell, count in policy._visit_counts.items()),
            "avoid": sorted([cell.y, cell.x] for cell in policy._engagement_avoid_cells),
            "hostiles_seen": sum(1 for raw in boards if raw.get("visible_monsters")),
        }
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "pin.json.xz").write_bytes(lzma.compress(
        json.dumps(pin, ensure_ascii=False).encode("utf-8"), preset=PRESET))
    print(sorted((path.name, path.stat().st_size) for path in FIXTURE.iterdir()), pin["avoid"],
          pin["hostiles_seen"])
