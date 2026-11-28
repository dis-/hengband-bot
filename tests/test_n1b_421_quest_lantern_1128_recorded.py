"""Q34's opening light is the light's radius, and Q34 stays first after a released opening
(n1-b life-421, 1128).

n1-b life-421 (Klackon Magic-Eater CL31, a Feanorian lamp of radius 5 worn) took Q34 at CL31 and
walked to the floor's brass lantern anyway; the default auto-pick file (lib/pref/picktype.prf
``?:[GEQ $LEVEL 30]``: ``(!未鑑定の光源``, ``(!油つぼ``) destroyed the flask and the lantern as the
player stepped on them, and the opening held on the empty cell
(``quest:blocked:opening-lantern-missing``) until ``loop-detected`` (2026-11-28 16:49:19).  At
CL1 the character's melee (2.88 per 10 game turns) missed the Magic-Eater's 3.5 row, the opening
released it, and the (level, id) order took Q1 and Q14 first; the quest value table passed Q34
over as ``no-need`` (its history is not counted) until the Q33 speed boots were needed.

Recorded (tests/extract_n1b_421_quest_lantern_1128_fixture.py, ``n1b-421-quest-lantern-1128``):
the birth board (turn 1, CL1) and the boards 4961288-4961463: the Outpost before the request, the
quest floor from its start stair [1,20] down the outer corridor to the emptied lantern cell
[10,20].  Replayed through ``choose_key`` from a fresh production policy.

DECLARED CONSTRUCTED:
- the dark case sets the board's ``player.light_radius`` to 1 on the emptied lantern cell;
- the quest value table is asked as a production instance (``quest_value`` on), which the
  recorded policy's ``all-fixed-quests`` profile turns off.
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import quest_opening_light, quest_opening_readiness, quest_value
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import WAIT_KEY
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-421-quest-lantern-1128.jsonl.xz"
BIRTH = 1
REQUEST = 4961301         # recorded ('3q\x1b', 'fixedquest:request')
ENTRY = 4961401           # recorded ('2', 'quest-strategy:approach-opening-lantern')
EMPTIED = 4961463         # recorded ('5', 'quest:blocked:opening-lantern-missing') until the loop guard
LANTERN_CELL = Position(10, 20)
LANTERN_REASONS = ("quest-strategy:approach-opening-lantern", "quest-strategy:pickup-opening",
                   "quest-strategy:equip-opening-lantern", "quest:blocked:opening-lantern")


class N1b421QuestLantern1128RecordedTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        lines = lzma.decompress(FIXTURE.read_bytes()).decode("utf-8").splitlines()
        cls.raws = [json.loads(line) for line in lines if line.strip()]
        cls.scratch = TemporaryDirectory()
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def policy(self, raw):
        type(self).count += 1
        directory = Path(self.scratch.name) / str(self.count)
        directory.mkdir()
        policy = _policy(directory, self.monrace)
        policy._instance_profile = replace(policy._instance_profile, quest_value=True)
        board = parse_snapshot(copy.deepcopy(raw), self.monrace)
        policy.prime(board)
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        return policy

    def board(self, turn):
        return next(raw for raw in reversed(self.raws) if raw["turn"] == turn)

    def decide(self, policy, raw):
        board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.monrace))
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return key, policy.last_reason, board

    # -- the quest floor -------------------------------------------------------------------

    def test_the_worn_lamp_meets_the_opening_light_and_the_quest_goes_on(self):
        quest = [raw for raw in self.raws if ENTRY <= raw["turn"] <= EMPTIED]
        policy = self.policy(quest[0])
        for raw in quest:
            key, reason, board = self.decide(policy, raw)
            self.assertEqual(board.floor_key[2], 34)
            self.assertTrue(quest_opening_light.met(
                board, policy.approved_quest_strategy(34).engagement_plan["opening_light"]))
            self.assertTrue(key, (raw["turn"], reason))
            self.assertFalse(reason.startswith(LANTERN_REASONS), (raw["turn"], key, reason))
        # The stuck board: on the emptied lantern cell the opening door route is walked, no hold.
        self.assertEqual(board.player.position, LANTERN_CELL)
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(reason, "quest-strategy:approach-opening-door")

    def test_no_light_and_no_lantern_gives_the_floor_up(self):
        dark = copy.deepcopy(self.board(EMPTIED))
        dark["player"]["light_radius"] = 1
        policy = self.policy(dark)
        key, reason, board = self.decide(policy, dark)
        self.assertEqual(board.grid_at(LANTERN_CELL).object_count, 0)
        self.assertNotEqual(key, WAIT_KEY)
        self.assertEqual(reason, quest_opening_light.RECALL_REASON, key)
        self.assertEqual(policy._unviable_quest_floor, board.floor_key)
        self.assertTrue(policy._returning_to_town)

    # -- the town --------------------------------------------------------------------------

    def test_q34_is_the_head_and_taken_at_the_request(self):
        policy = self.policy(self.board(REQUEST))
        board = parse_snapshot(copy.deepcopy(self.board(REQUEST)), self.monrace)
        self.assertEqual(policy._fixed_quest_head(board).id, 34)
        self.assertTrue(policy._evaluate_fixed_quest_readiness(board, 34, require_target_town=True))
        self.assertEqual(quest_value.verdict(policy, board, 34).why, "always")

    def test_q34_stays_first_at_birth_when_the_opening_releases(self):
        for released in (False, True):
            policy = self.policy(self.board(BIRTH))
            board = parse_snapshot(copy.deepcopy(self.board(BIRTH)), self.monrace)
            if released:
                quest_opening_readiness.release(policy, "strategy-force:dps")
            self.assertEqual(board.player.level, 1)
            known = policy._known_fixed_quests(board)
            self.assertEqual(known[1].status, known[34].status)   # both untaken, both level 5
            self.assertEqual(policy._fixed_quest_head(board).id, 34, released)
            self.assertFalse(policy._untaken_quest_held_back(board, known[34]), released)
            # The row the opening could not buy at CL1: the Klackon Magic-Eater's melee.
            self.assertFalse(policy._evaluate_fixed_quest_readiness(board, 34, require_target_town=True))
            dps = policy._fixed_quest_readiness["strategy_force"]["dps"]
            self.assertLess(dps["measured"], dps["required"])


if __name__ == "__main__":
    unittest.main()
