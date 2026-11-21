"""Owner 2026-11-22, asked after n1-b life-413's death on Angband 80F (a poison swamp):

1. 「逃げの手は全部床より先にする」: damaging_ground's step off replaces no escape the decision
   chose (reasons ``escapes``): the absorbed or the staff's Teleportation, Teleport Other,
   *Destruction*; only the other stops step off first.
2. 「床の被害も見積もりに入れる」: the immobile monster's ranged kill (immobile_ranged_kill
   ``plan``) adds the damaging ground of its walk and of its shooting cell to the damage the
   player must survive (damaging_ground ``floor_damage``).

Recorded (tests/fixtures/n1b-413-solar-death-1122, the same replay as
test_n1b_413_solar_death_1122_recorded): from (12,16) at HP 713 the approach to the
天使・クイルスルグ walked 23 cells, 13 of them on the swamp (HP 718 -> 538), and stood on it at (19,33);
on the death board (20,32), HP 491, the player stood on deep poison.

DECLARED CONSTRUCTED: the HP of the approach's first board lowered to 520 (pin 2); the escapes'
reasons and keys on the death board (pin 1: no such escape was chosen there).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import damaging_ground, destruction_use, goal_route, immobile_ranged_kill
from hengbot import immobile_threat_memory
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-solar-death-1122"
APPROACH, DEATH = 3100871, 3100999
LOWERED_HP = 520  # DECLARED: above the quylthulg's own danger (0), below it with the swamp


def _post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class DamagingGroundEscapes1122RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name) / "fixture")
        policy._me_power_resume_reads = True  # the live CLI's
        floor = json.loads(lzma.decompress((FIXTURE / "floor.json.xz").read_bytes()).decode(
            "utf-8", "surrogateescape"))
        cls.boards, cls.replayed, cls.approach = {}, {}, {}
        with contextlib.redirect_stdout(io.StringIO()):
            for recorded, supply in steps:
                policy.choose_key(supply())
                _post(policy, recorded["key"])
            decisions = list(floor["decisions"])
            for index, raw in enumerate(floor["boards"]):
                board = parse_snapshot(raw, policy._monrace_knowledge)
                key = policy.choose_key(board)
                if index + 1 < len(floor["boards"]) and floor["boards"][index + 1]["turn"] == raw["turn"]:
                    continue
                recorded = decisions.pop(0)
                cls.boards[raw["turn"]] = board
                cls.replayed[raw["turn"]] = (key, policy.last_reason, recorded)
                if raw["turn"] == APPROACH:
                    cls.approach = cls._plans(policy, board)
                _post(policy, recorded["key"])
        cls.policy = policy

    @classmethod
    def _plans(cls, policy, board):
        """The approach's target and its plans at the recorded HP and at ``LOWERED_HP``."""
        target = next(monster for monster in immobile_threat_memory.remembered(policy)
                      if immobile_ranged_kill.plan(policy, board, monster) is not None)
        # The route the plan committed on this board (the restored checkpoint keeps older ones).
        path = next(commitment.path for kind, commitment in goal_route._commitments(policy).items()
                    if "immobile_ranged_kill" in kind and commitment.turn == board.turn
                    and commitment.floor_key == board.floor_key)
        lowered = replace(board, player=replace(board.player, hp=LOWERED_HP))
        return {"target": target, "path": path,
                "full": immobile_ranged_kill.plan(policy, board, target),
                "lowered": immobile_ranged_kill.plan(policy, lowered, target)}

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    # ------------------------------------------------------------ 2: the ground in the walk's estimate

    def test_the_recorded_approach_still_walks_and_its_estimate_covers_the_swamp(self):
        key, reason, recorded = self.replayed[APPROACH]
        self.assertEqual((key, reason), (recorded["key"], recorded["reason"]))
        self.assertEqual(reason, immobile_ranged_kill.APPROACH_REASON)
        self.assertIsNotNone(self.approach["full"])
        path = self.approach["path"]
        board = self.boards[APPROACH]
        hurting = [cell for cell in path if damaging_ground.hurts_at(self.policy, board, cell)]
        self.assertEqual(len(path), 23)
        self.assertGreaterEqual(len(hurting), 13)
        # The swamp cost the walk 180 HP (718 -> 538); the estimate is not below it.
        self.assertGreaterEqual(damaging_ground.floor_damage(self.policy, board, path), 180)
        self.assertLess(damaging_ground.floor_damage(self.policy, board, path), board.player.hp)

    def test_the_walk_over_the_swamp_is_refused_when_the_ground_would_kill(self):
        self.assertIsNone(self.approach["lowered"])

    def test_resisted_deep_and_shallow_poison_tick_maxima(self):
        """hp-mp-processor.cpp: DEEP 6000+randint0(4000), else 3000+randint0(2000), per 10000,
        times calc_pois_damage_rate ((100+2)/3 = 34 with the resistance)."""
        board = self.boards[DEATH]
        self.assertIn("resist_pois", board.player.abilities)
        self.assertEqual(damaging_ground.floor_damage_at(self.policy, board, board.player.position), 34)

    # ------------------------------------------------------------ 1: every escape before the floor

    def step_off(self, key, reason):
        board = self.boards[DEATH]
        self.assertTrue(damaging_ground.hurts_here(self.policy, board))
        destruction_use._memory(self.policy).pending = None  # DECLARED: no *Destruction* this ask
        self.policy.last_reason = reason
        return damaging_ground.step_off_key(self.policy, board, key)

    def test_an_absorbed_teleport_on_the_swamp_is_not_replaced(self):
        self.assertIsNone(self.step_off("mAa", "emergency:teleport:absorbed-power"))

    def test_a_teleport_away_on_the_swamp_is_not_replaced(self):
        self.assertIsNone(self.step_off("mBa'", "emergency:teleport-follower:teleport-away:absorbed-power"))
        self.assertIsNone(self.step_off("aa'", "status-threat:teleport-away"))

    def test_a_staff_teleport_on_the_swamp_is_not_replaced(self):
        self.assertIsNone(self.step_off("ua", "emergency:teleport-staff"))

    def test_a_stop_that_is_no_escape_still_steps_off(self):
        self.assertIsNotNone(self.step_off("s", "search"))
        self.assertEqual(self.policy.last_reason, damaging_ground.STEP_REASON)
        self.assertIsNotNone(self.step_off("R&\r", "rest"))


if __name__ == "__main__":
    unittest.main()
