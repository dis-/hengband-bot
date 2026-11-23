"""The wait of deep_teleport's Recall picks the reachable items before *Destruction* (1123).

Owner 2026-11-23: 「帰還を読んでから待つ間に拾う — 先に帰還を読み、発動までの間に、見える起きた敵が
いなければ拾う（11-18 の帰還待ちの拾いと同じ）。」, then 「見える敵がいなければ拾いを先に」 (before the
*Destruction* on, and the approach to, the T1s known only by detection) and 「眠っていても止める」
(a sleeping hostile in view stops it).  deep_recall_loot ``key``, asked by destruction_use ``key``
and ``loot_then_use``.

Recorded (tests/extract_deep_recall_loot_1123_fixture.py), n1-c life-220 on Angband 80F,
2026-11-22 17:33: arrived at (5,91) with an item 2 cells off at (4,89) and 48 hostiles known only
by detection; the absorbed *Destruction* failed, the Word of Recall was read under
``deep-teleport:recall`` (live 3002050), and on the next board (live 3002058, recalling, no
hostile in view, HP 855/855) the *Destruction* was cast again ('mA3',
``emergency:destruction:absorbed-power``) and deleted the item.

The boards are replayed as recorded from the town's recall wait, one decision a turn as live
decided them (the second board of turn 3002041, left by the failed cast, was not decided live):
the replay casts the *Destruction* on 3002041 and reads the Recall on 3002050 as live did.

DECLARED CONSTRUCTED:
* the absorbed-power lists (``_me_device_lists``) are those of the same life's town-arrival
  checkpoint of 18:19 (the lists are read from the screen, the snapshot log does not carry them);
* ``test_a_sleeping_hostile_in_view_stops_it``: one of the detected hostiles is put in view asleep
  on the recorded 3002058 board;
* ``test_a_recall_read_by_another_rule_keeps_the_order``: the wait's record of the
  deep-teleport read is cleared on the recorded 3002058 board.
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import deep_recall_loot, deep_teleport
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "deep-recall-loot-1123"
WAIT = 3002058
ITEM = Position(4, 89)
HERE = Position(5, 91)


class DeepRecallLoot1123RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode("utf-8")
        cls.raws = [json.loads(line) for line in lines.splitlines() if line.strip()]
        cls.lists = json.loads(lzma.decompress(
            (FIXTURE / "me-device-lists.json.xz").read_bytes()).decode("utf-8"))

    def replay(self):
        """Replay up to the wait board: (policy, its raw board, the reasons decided before)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        start = parse_snapshot(copy.deepcopy(self.raws[0]), self.monrace)
        policy.prime(start)
        policy._skill_exp_cache = (0, 0, start.player.level, policy._town_visit_epoch)
        # DECLARED CONSTRUCTED (module docstring): the absorbed-power lists.
        policy._me_device_lists = {kind: (start.turn, tuple(rows))
                                   for kind, (_turn, rows) in self.lists.items()}
        reasons = []
        decided = set()
        for raw in self.raws:
            if raw["turn"] in decided:
                # The board the failed cast left on the same turn: live decided none on it.
                continue
            decided.add(raw["turn"])
            if raw["turn"] == WAIT:
                return policy, raw, reasons
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            reasons.append((raw["turn"], policy.last_reason))
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError("the wait board is not in the fixture")

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        return board, key, policy.last_reason

    def test_the_wait_picks_the_item_before_the_destruction(self):
        policy, raw, reasons = self.replay()
        self.assertIn(deep_teleport.RECALL_REASON, [reason for _turn, reason in reasons])
        board, key, reason = self.decide(policy, raw)
        self.assertEqual((board.floor_key, board.player.position), ((1, 80, 0), HERE))
        self.assertTrue(board.player.recalling)
        self.assertEqual([m for m in board.visible_monsters if m.hostile], [])
        self.assertTrue([m for m in board.detected_monsters if m.hostile])
        self.assertEqual(board.player.hp, board.player.max_hp)
        self.assertTrue(deep_recall_loot.applies(policy, board))

        # Recorded: ('mA3', 'emergency:destruction:absorbed-power'), deleting the item at (4,89).
        self.assertEqual((key, reason), ("7", "return:seek-loot"))
        self.assertEqual(policy._loot_target, ITEM)

    def test_a_sleeping_hostile_in_view_stops_it(self):
        policy, raw, _reasons = self.replay()
        raw = copy.deepcopy(raw)
        # DECLARED CONSTRUCTED (module docstring): a detected hostile put in view, asleep.
        sleeper = dict(raw["detected_monsters"][0], asleep=True, detected=False, esp=False)
        raw["visible_monsters"] = [*raw.get("visible_monsters", []), sleeper]
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        self.assertTrue([m for m in board.visible_monsters if m.hostile and m.asleep])
        self.assertIsNone(deep_recall_loot.key(policy, board))

        _board, _key, reason = self.decide(policy, raw)

        self.assertNotEqual(reason, "return:seek-loot")

    def test_a_recall_read_by_another_rule_keeps_the_order(self):
        policy, raw, _reasons = self.replay()
        # DECLARED CONSTRUCTED (module docstring): no deep-teleport read on record.
        setattr(policy, deep_recall_loot.MEMORY, None)

        board, key, reason = self.decide(policy, raw)

        self.assertFalse(deep_recall_loot.applies(policy, board))
        self.assertEqual((key, reason), ("mA3", "emergency:destruction:absorbed-power"))


if __name__ == "__main__":
    unittest.main()
