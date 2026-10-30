"""Freeze the 2026-10-30 dungeon loop stops of family D31.

Sources (incident captures copied from the viewing bots to
C:/hengband-backups/pdca/captures/unfixed-24h-1031):

- mining-door: n1-a life-446 20261030-234852-loop-detected (Yeek cave 1F).
  The mining closure picked the locked door [38,95] ('o1',
  fundraise:seek-treasure) 29 times from [37,96] until the CLI cell guard
  stopped the run ("confined to ... over 40 decisions").
- loot-piles-249 / loot-piles-273: n1-b life-249 20261030-002000 and life-273
  20261030-230842 (floor 2/13).  With a full pack the triage walked between
  multi-object piles whose unknown items it could not identify on the floor.
- confused-read: n1-a life-418 20261030-003514 (floor 3/19).  Confused, the
  no-wait ladder posted Teleport ('rd', no-wait:escape-scroll); the game
  refused it (混乱していてできない！) without a turn, and the stalled-command
  stop fired.

Each case keeps the stop board (the ring's last player_turn row), the last
recorded decision row's facts, and the monster races of the board.  The
mining case also keeps the checkpoint's remembered terrain, the fundraising
modes and the purpose ledger entry of the decision row; the loot cases keep
the ring's last look row (the reply to the triage's look probe).

The snapshot ring copy is the tail of a multi-member gzip: decoding starts at
the first member header and keeps whole members only.  Only this extraction
tool reads the captures; the committed test reads the frozen fixture alone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge
from tests.extract_recall_dungeon_prompt_fixture import ring_rows


ROOT = Path("C:/hengband-backups/pdca/captures/unfixed-24h-1031")
CASES = {
    "mining-door": "n1-a/life-446/incident-captures/20261030-234852-loop-detected",
    "loot-piles-249": "n1-b/life-249/incident-captures/20261030-002000-loop-detected",
    "loot-piles-273": "n1-b/life-273/incident-captures/20261030-230842-loop-detected",
    "confused-read": "n1-a/life-418/incident-captures/20261030-003514-loop-detected",
}
OUTPUT = Path(__file__).with_name("fixtures") / "dungeon-loops-20261030.json.gz"
MODE_FIELDS = ("_fundraising_mode", "_returning_to_town", "_emergency_return_active",
               "_crossarea_fundraising_enforced", "_last_return_trigger",
               "_fundraising_runs_started")
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "objective",
                   "position", "player", "messages")


def decision_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # The bounded tail starts in the middle of a JSON record.
    return rows


def main():
    races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
    cases = {}
    for name, relative in CASES.items():
        capture = ROOT / relative
        ring_path = capture / "snapshots" / "snapshots-current.jsonl.gz"
        tail_path = capture / "decision-tail.jsonl"
        state_path = capture / "policy-state.json"
        rows = ring_rows(ring_path.read_bytes())
        board = next(row for row in reversed(rows) if row["type"] == "player_turn")
        decisions = [row for row in decision_rows(tail_path)
                     if row.get("reason") != "loop-detected"]
        decision = decisions[-1]
        assert decision["turn"] == board["turn"], (name, decision["turn"], board["turn"])
        ids = {row["race_id"] for field in ("visible_monsters", "detected_monsters")
               for row in board.get(field, [])}
        case = dict(
            source=relative,
            sources={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (ring_path, tail_path, state_path)},
            board=board,
            decision={field: decision[field] for field in DECISION_FIELDS},
            monraces={str(key): asdict(races[key]) for key in sorted(ids)},
        )
        if name == "mining-door":
            checkpoint = json.loads(state_path.read_text(encoding="utf-8"))
            case["terrain"] = checkpoint["terrain"]
            case["modes"] = {field: checkpoint["modes_and_latches"][field]
                             for field in MODE_FIELDS}
            case["purpose"] = decision["claim"]["fundraising_purpose"]
            case["claim_goal"] = decision["claim"]["goal"]
        if name.startswith("loot-piles"):
            case["look"] = next(row for row in reversed(rows) if row["type"] == "look")
        cases[name] = case
    with gzip.open(OUTPUT, "wt", encoding="utf-8", newline="\n") as stream:
        json.dump(cases, stream, ensure_ascii=False, default=sorted, separators=(",", ":"))
    print(OUTPUT, OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
