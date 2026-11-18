"""A begun *Destruction* fetch is walked to its end before seek-loot takes the board (1119).

Owner 2026-11-18 (maintainability Q3, 「命の危険が無ければ取り終える」): 「取りに歩き始めたら、命の
危険（即死の見込み・見える強敵）が出ない限り、取り終えるまでほかの歩きに譲らない。今の回数の上限
（40回）は残す。」 (loot_walk).

n1-b life-411 (Magic-Eater Lv50, Angband 95F, 2026-11-19 05:41:23, loop-detected, build
bot-d66100109).  A blue dragon nest lay behind the wall north of the player; the sensed
ストーム・ワーム (race 1190) at (9,117) was a T1 the approach owned, and at (15,121) the use was
due: destruction_loot's fetch began (``MEMORY`` "fetch" (15,121)) and walked west to the Ice
Ball wand at (13,117).  On (13,117) the T1 was not read strong, threat_tiers'
``sensed_t1_destruction_key`` did not ask destruction_loot, and seek-loot stepped east toward
(13,122); on (13,118) the use was due again and the committed fetch stepped west: '4' and '6'
in turn (the Recall the livelock leave read did not end it: the Recall wait's return:seek-loot
took seek-loot's place) until the loop detector.

Now the ordinary walk continues the begun fetch first: on (13,117) the fetch tries the wand
(the pickup is refused: the absorbed Ice Ball stands at 99, owner 2026-11-13) and, with no
valuable pile left in the circle, ends; on (13,118), where the use is due again, no fetch begins
afresh and the use is made instead of the step back west.

Recorded: the capture's state.jsonl (hengband.net
~/hengbot-soak/n1-b/life-411/captures/20261119-054123-loop-detected/), its player-turn boards
8168452-8168523.  The Magic-Eater's power lists are the viewer's own record of them
(~/hengbot-soak/n1-b/spectate.json ``magic_eater_powers``, read at turns 8168442 (staff),
8168477 (wand) and 8168367 (rod); fixtures/n1b-411-loot-walk-1119.me-lists.json).  DECLARED
RECONSTRUCTED: the floor's earlier power uses the capture starts after (me_powers'
``FloorMemory``): the detection the decision log shows at turn 8168364
(me-power:deep-explore-redetect:detect-all:powerful, (13,120)) and the floor's once-only
arrival casts (new-floor, deep-arrival-unhasted) the log's earlier boards ran; without them
the replay casts them again instead of walking.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import destruction_loot, me_powers
from hengbot.model import SV_ROD_DETECTION, SV_STAFF_DETECT_EVIL, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-loot-walk-1119.jsonl.gz"
ME_LISTS = Path(__file__).with_name("fixtures") / "n1b-411-loot-walk-1119.me-lists.json"
FETCH_BEGINS = 8168481   # (15,121): the use due, the fetch begins ('7')
ON_THE_WAND = 8168493    # (13,117): live seek-loot '6' with the fetch still committed
STEPPED_BACK = 8168496   # (13,118): live destruction-loot:fetch '4', back west
FETCH_CELL = Position(15, 121)
WAND_CELL = Position(13, 117)
REDETECT = (8168364, Position(13, 120))


def _floor_uses(first):
    """The floor's earlier power uses (DECLARED RECONSTRUCTED, the module docstring)."""
    turn, cell = REDETECT
    memory = me_powers.FloorMemory(first.floor_key, first.turn)
    memory.uses.append(me_powers.Use(("staff", SV_STAFF_DETECT_EVIL), ("rod", SV_ROD_DETECTION),
                                     "deep-explore-redetect", cell, turn))
    for power in me_powers.POWERS:
        if ("new-floor" in power.triggers and power.effect != "detect-evil") or (
                "deep-arrival-unhasted" in power.triggers):
            memory.uses.append(me_powers.Use(power.ident, power.ident, "new-floor", cell, turn))
    return memory


class LootWalkCommit1119RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream if line.strip()]
        cls.lists = json.loads(ME_LISTS.read_text(encoding="utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, until):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = parse_snapshot(copy.deepcopy(self.boards[0]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {kind: (first.turn, tuple(listed["rows"]))
                                   for kind, listed in self.lists.items()}
        setattr(policy, me_powers.MEMORY, _floor_uses(first))
        answers = {}
        for raw in self.boards:
            board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
            key = policy.choose_key(board)
            answers[board.turn] = (board, key, policy.last_reason)
            if board.turn == until:
                return policy, answers
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError(f"turn {until} not in {FIXTURE.name}")

    def test_the_fetch_begins_where_the_use_is_due(self):
        _, answers = self.replay(FETCH_BEGINS)
        board, key, reason = answers[FETCH_BEGINS]
        self.assertEqual(board.player.position, FETCH_CELL)
        self.assertEqual((key, reason), ("7", "destruction-loot:fetch"))

    def test_on_the_wand_the_begun_fetch_is_finished_first(self):
        policy, answers = self.replay(ON_THE_WAND)
        board = answers[ON_THE_WAND][0]
        self.assertEqual(board.player.position, WAND_CELL)
        memory = getattr(policy, destruction_loot.MEMORY)
        # The fetch tried the wand (refused: 99 absorbed) and, with nothing left, ended; before
        # Q3 seek-loot took the board with the fetch still committed and the wand untried.
        self.assertIn(WAND_CELL, memory["tried"])
        self.assertIsNone(memory["fetch"])
        self.assertEqual(answers[ON_THE_WAND][1:], ("6", "seek-loot"))

    def test_the_use_is_made_instead_of_the_step_back(self):
        _, answers = self.replay(STEPPED_BACK)
        board, key, reason = answers[STEPPED_BACK]
        self.assertEqual(board.player.position, Position(13, 118))
        # Recorded: destruction-loot:fetch '4' (back west onto the wand).
        self.assertEqual((key, reason), ("mA3", "emergency:destruction:absorbed-power"))


if __name__ == "__main__":
    unittest.main()
