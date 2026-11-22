"""A never-moving breeder that blinds and confuses is walked away from, not shot.

n1-a life-533 (Warrior Lv22, neither resist_blind/resist_lite nor resist_conf) saw its first
百目口 (race 253: NEVER_MOVE, MULTIPLY, BR_LITE, CONF) on Orc Cave 19F five cells away
(2026-11-22 15:14:41, decision 16767) and shot it (``ranged:fire-target``, the 11-08 rule that a
breeder in the line of fire is shot).  The light breaths and confusion spells of it and its
children kept the player blind and confused until it died there at 15:15.

Owner 2026-11-22 「撃たずに射線の外へ離れる」 (撃たずに射線の外へ歩いて離れ、その階ではもう近寄りません): without
those resistances such a breeder is remembered like a never-moving summoner
(status_breeder_avoid, policy_combat ``_immobile_summoner_key``): its line-of-fire cells leave
every walk for the floor visit and the player inside them steps out, ahead of the shooting rungs.

Recorded: n1-a life-533's town-arrival checkpoint (tests/fixtures/n1a-533-cure-mushroom-1122) and
the Orc Cave 19F boards from the arrival to decision 16767
(tests/fixtures/n1a-533-mouther-avoid-1122), decided through the public ``choose_key`` with the
recorded keys posted.  Decisions 16322-16766 replay as recorded.

DECLARED CONSTRUCTED: the control board is the board of decision 16767 with resist_lite and
resist_conf from the equipment (``ability_sources``), decided by a copy of the same policy.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import lzma
import pickle
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import status_breeder_avoid
from hengbot.model import Position, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import DIRECTION_DELTAS
from support.town_arrival_fixture import load

CHECKPOINT = Path(__file__).with_name("fixtures") / "n1a-533-cure-mushroom-1122"
FIXTURE = Path(__file__).with_name("fixtures") / "n1a-533-mouther-avoid-1122"
SIGHTING = 16767
MOUTHER = 253
PLAYER_CELL, MOUTHER_CELL = Position(51, 107), Position(48, 112)


def _post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def _resisting(raw):
    """DECLARED CONSTRUCTED: the same board with resist_lite and resist_conf worn."""
    raw = copy.deepcopy(raw)
    for name in ("resist_lite", "resist_conf"):
        raw["player"]["ability_sources"][name]["equipment"] = True
    return raw


class MoutherAvoid1122RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(CHECKPOINT, Path(cls.scratch.name) / "fixture")
        floor = json.loads(lzma.decompress((FIXTURE / "floor.json.xz").read_bytes()).decode(
            "utf-8", "surrogateescape"))
        cls.replayed = []
        with contextlib.redirect_stdout(io.StringIO()):
            for recorded, supply in steps:
                policy.choose_key(supply())
                _post(policy, recorded["key"])
            for raw, recorded in zip(floor["boards"], floor["decisions"]):
                if recorded["decision_sequence"] == SIGHTING:
                    break
                key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
                cls.replayed.append((recorded, (key, policy.last_reason)))
                _post(policy, recorded["key"])
            cls.recorded = recorded
            control = pickle.loads(pickle.dumps(policy))
            cls.board = parse_snapshot(raw, policy._monrace_knowledge)
            cls.key = policy.choose_key(cls.board)
            cls.reason = policy.last_reason
            cls.resisting = parse_snapshot(_resisting(raw), control._monrace_knowledge)
            cls.control_key = control.choose_key(cls.resisting)
            cls.control_reason = control.last_reason
        cls.policy, cls.control = policy, control

    @classmethod
    def tearDownClass(cls):
        for policy in (cls.policy, cls.control):
            policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_record(self):
        self.assertEqual(len(self.replayed), 445)
        for recorded, decided in self.replayed:
            self.assertEqual(decided, (recorded["key"], recorded["reason"]),
                             recorded["decision_sequence"])
        self.assertEqual((self.recorded["key"], self.recorded["reason"]),
                         ("fn*t5\x1b", "ranged:fire-target"))
        [mouther] = [monster for monster in self.board.visible_monsters
                     if monster.race_id == MOUTHER]
        self.assertEqual((mouther.position, mouther.distance), (MOUTHER_CELL, 5))
        self.assertEqual(self.board.player.position, PLAYER_CELL)
        self.assertTrue(status_breeder_avoid.kept_away(self.policy, self.board, mouther))

    def test_the_first_sighting_steps_out_of_its_line_instead_of_firing(self):
        # Before: ('fn*t5\x1b', 'ranged:fire-target').
        self.assertEqual(self.reason, status_breeder_avoid.STEP_OUT_REASON)
        self.assertIn(self.key, DIRECTION_DELTAS)
        cells = self.policy._immobile_summoner_avoid_cells
        self.assertIn(PLAYER_CELL, cells)
        dy, dx = DIRECTION_DELTAS[self.key]
        # The step leaves its line (the nearest cell outside it is one step away here).
        self.assertNotIn(Position(PLAYER_CELL.y + dy, PLAYER_CELL.x + dx), cells)

    def test_its_line_of_fire_stays_out_of_the_walks_on_this_floor(self):
        _floor, remembered = self.policy._immobile_summoner_memory
        self.assertEqual(remembered.get(MOUTHER_CELL), MOUTHER)
        self.assertIn(PLAYER_CELL, self.policy._engagement_avoid_cells)

    def test_with_resist_light_and_confusion_it_is_shot_as_before(self):
        self.assertEqual((self.control_key, self.control_reason),
                         ("fn*t5\x1b", "ranged:fire-target"))


if __name__ == "__main__":
    unittest.main()
