"""n1-a life-535 (2026-11-23 05:15, 城42階) waited out the light hounds' blindness and was stopped.

Recorded (capture 20261123-051536-loop-detected; bot-decisions.jsonl.gz SHA256
7883409613c0bb6d7a40af32c0e0d843af465158bcbc48fbf0d5ba8e24efc87c, state.jsonl.gz SHA256
9679a3775dcaf5beb7cad808767eac88b3a955e353c28ad4d19d4512360a64db): the Lv43 warrior, HP
1110/1110, no resistance to blindness or light, struck a light hound at (28,65) (decision
81120) and the pack's flash breaths blinded it (「ライト・ハウンドが閃光のブレスを吐いた。」
「目が見えなくなってしまった！」), again each time sight came back: three onsets on (28,65),
a short anaguma:walk west once it saw (81145-81149), a fourth onset on (27,60).  With no hostile
beside it the bot sent '5' as blind:short-wait 28 times (owner 2026-11-10 G1 「HP が高く、光・
閃光・暗黒のブレスによる短い盲目なら治療薬を使わず、隣の敵は殴り、いなければ治るまで待つ」;
it carried Cure Critical Wounds, which clears blindness, spells-status.cpp cure_critical_wounds
set_blindness(0), kept by that rule).  The wait was not a row of the loop guard's stationary
table, so the 40-decision window (81114-81153: the walk before the fight, the 24 waits, the
walk, 4 waits) held six cells and the guard stopped the bot (cli: 「loop detected at
floor=(12, 42, 0) cells=[(26, 61), (26, 63), (27, 60), (27, 62), (27, 64), (28, 65)]」).

Now blind:short-wait is an EXEMPT row (reasons.py, bound status_cure.SHORT_BLIND_MAX_GAME_TURNS per
onset).  Fixtures (tests/fixtures/n1a-535-blind-loop-1123): decisions.json.xz, the decisions
81113-81153 (the first only the guard's previous position; fields sequence, turn, reason, key,
position, floor, messages, player); boards.json.xz, the state boards 75-108 of the capture (the
turns of the decisions 81120-81153).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from collections import deque
import hashlib
import json
import lzma
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from hengbot import status_cure
from hengbot.cli import LOOP_WINDOW, STATIONARY_EXEMPT_REASONS, _cell_loop_guard_applies, _is_looping
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import find_monrace_definitions, load_monrace_knowledge

FIXTURES = Path(__file__).with_name("fixtures") / "n1a-535-blind-loop-1123"
WAIT = status_cure.SHORT_BLIND_WAIT_REASON


def _load(name):
    return json.loads(lzma.decompress((FIXTURES / name).read_bytes()))


def _guard_stop_sequence(rows):
    """cli's cell guard over the recorded decisions (the dungeon branch of the main loop)."""
    recent = deque(maxlen=LOOP_WINDOW)
    previous = None
    for row in rows:
        position = Position(row["position"]["y"], row["position"]["x"])
        floor = row["floor"]
        snapshot = SimpleNamespace(
            in_town=False, inside_arena=False,
            floor_key=(floor["dungeon_id"], floor["level"], floor["quest_id"]),
            player=SimpleNamespace(position=position))
        if _cell_loop_guard_applies(snapshot, row["reason"], previous, None, row["key"]):
            recent.append((snapshot.floor_key, position.y, position.x))
            if _is_looping(recent):
                return row["decision_sequence"]
        else:
            recent.clear()
        previous = position
    return None


class N1a535ShortBlindWaitRecordedTest(unittest.TestCase):
    def test_fixture_is_the_recorded_stop(self):
        digests = {name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
                   for name in ("decisions.json.xz", "boards.json.xz")}
        self.assertEqual(digests, {
            "decisions.json.xz": "dec35b925ef2edddbfd898b3dbec2b5c5b4c030415416e6e13173c58153e068f",
            "boards.json.xz": "071a92ceb1c5d27bca6da161f84b61d3f3f8148ee73bfc435ff12f56535c4fe9",
        })
        rows = _load("decisions.json.xz")
        self.assertEqual(len(rows), LOOP_WINDOW + 1)
        self.assertEqual((rows[0]["decision_sequence"], rows[-1]["decision_sequence"]), (81113, 81153))
        waits = [row for row in rows if row["reason"] == WAIT]
        self.assertEqual(len(waits), 28)
        self.assertEqual({row["key"] for row in waits}, {"5"})
        self.assertGreaterEqual(min(row["player"]["hp"] for row in waits), 1104)  # of 1110
        onsets = [row for row in rows if status_cure.BLINDED in row["messages"]]
        self.assertEqual([row["decision_sequence"] for row in onsets], [81121, 81128, 81137, 81150])

    def test_the_blind_wait_no_longer_trips_the_guard(self):
        self.assertIn(WAIT, STATIONARY_EXEMPT_REASONS)
        rows = _load("decisions.json.xz")
        self.assertIsNone(_guard_stop_sequence(rows))
        # Without the row the exact live stop returns (revert proof).
        with patch("hengbot.cli.STATIONARY_EXEMPT_REASONS", STATIONARY_EXEMPT_REASONS - {WAIT}):
            self.assertEqual(_guard_stop_sequence(rows), 81153)

    def test_every_recorded_wait_is_the_owner_short_blindness(self):
        """Each blind board of the capture is a flash-breath blindness within its bound at full HP
        (short_blind_holds), so the wait is the owner's G1 hold and not a cure skipped by mistake."""
        races = load_monrace_knowledge(find_monrace_definitions(Path.cwd(), None))
        policy = SimpleNamespace()
        held = []
        onsets = []
        for row in _load("boards.json.xz"):
            board = parse_snapshot(row["board"], races)
            status_cure.observe(policy, board)
            if not board.player.blind:
                continue
            onset = getattr(policy, status_cure._SHORT_BLIND)
            self.assertIsNotNone(onset, row["line"])
            onsets.append(onset[1])
            self.assertLessEqual(board.turn - onset[1], status_cure.SHORT_BLIND_MAX_GAME_TURNS, row["line"])
            held.append(status_cure.short_blind_holds(policy, board))
        self.assertEqual(len(held), 28)
        self.assertTrue(all(held))
        # Four flash-breath onsets (the capture's 「目が見えなくなってしまった！」 boards).
        self.assertEqual(sorted(set(onsets)), [6062067, 6062104, 6062155, 6062232])


if __name__ == "__main__":
    unittest.main()
