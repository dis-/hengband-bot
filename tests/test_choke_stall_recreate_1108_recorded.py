"""A stall-released choke is not re-planned for the same pack on the floor.

Recorded n1-c life-162 (Lv27, 380 HP), Orc cave 19F, 2026-11-08 01:46,
``loop-detected``.  At (33, 91) eight awake 闘熊 (race 173, FRIENDS +
ANIMAL) stood around the player and hit it; ``_melee_swarm_combat_key``
planned a choke at (32, 92) and stepped ``9`` there.  Pack animals use the
hiding move decider and keep out of a corridor-like cell while the player's
HP is high (monster-sweep-grid.cpp:190-230, 479-483), so at (32, 92) no bear
was visible, the floor's inherited no-progress budget (>= 300) released the
plan with ``engagement-stall-bound`` and seek-loot stepped ``1`` back.  The
plan was minted again on the next board: HP 380 -> 307, no blow struck.

The fixture is the capture's boards 8..47 (state.jsonl, which rotates) with
their recorded decisions.  DECLARED CONSTRUCTED: the inherited outcome budget
of the (32, 92) choke at the first board -- 300 spent decisions, as recorded
by decision 508, with a high-water marker no board here improves.  Without it
a fresh policy would need the 300 earlier decisions the capture does not
hold.  The (33, 91) boards after the first attack are the recorded boards on
which the old policy stepped away; the fixed policy, which stays and fights,
is fed them in order as the boards it would have stood on.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot import threat_tiers
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy


FIXTURES = Path(__file__).with_name("fixtures")
FIXTURE = FIXTURES / "choke-stall-recreate-1108.jsonl.gz"
CALIBRATION = FIXTURES / "choke-stall-recreate-1108.character-calibration.json"
FIXTURE_SHA256 = "875475780523fbc8f3cf587ddc5d347f19b275744b075b761d59a0e856003ca3"
CHOKE = Position(32, 92)
OPEN_CELL = Position(33, 91)
BEAR = 173  # 闘熊
DIRECTIONS = {
    "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
    "4": (0, -1), "6": (0, 1),
    "1": (1, -1), "2": (1, 0), "3": (1, 1),
}


# Threat tiers step 6 (DECLARED CONSTRUCTED): the eight bears are T2 (the free attacks' 383 over
# the 21 turns to clear against HP 380; the Speed dose wins) and no selected target, so the tiers
# leave them (ChokeStallTiersRecorded below).  The 11-08 rule is pinned with the tiers not acting.
@patch.object(threat_tiers, "acts_here", new=lambda *args, **kwargs: False)
class ChokeStallRecreateRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.rows = [json.loads(line) for line in stream]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        shutil.copyfile(CALIBRATION, policy._character_calibration_path)
        first = parse_snapshot(copy.deepcopy(self.rows[0]["board"]), self.monrace)
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, None)
        # DECLARED CONSTRUCTED (module docstring): decision 508's budget.
        policy._choke_outcome_floor = first.floor_key
        policy._choke_outcome_budgets[CHOKE] = (
            300,
            (first.player.exp, first.player.gold, 0, 0, 10**9, first.player.max_hp),
        )
        return policy

    def decide(self, policy, row):
        snapshot = policy.with_known_skill_exp(
            parse_snapshot(copy.deepcopy(row["board"]), self.monrace)
        )
        return snapshot, policy.choose_key(snapshot), policy.last_reason

    def assert_strikes_adjacent_bear(self, snapshot, key, reason):
        self.assertEqual(reason, "melee", key)
        self.assertIn(key, DIRECTIONS)
        dy, dx = DIRECTIONS[key]
        target = Position(snapshot.player.position.y + dy, snapshot.player.position.x + dx)
        bears = {
            monster.position
            for monster in snapshot.visible_monsters
            if monster.race_id == BEAR and not monster.asleep
        }
        self.assertIn(target, bears)

    def test_stall_release_ends_in_a_blow_at_an_adjacent_bear(self):
        policy = self.policy()
        decided = [self.decide(policy, row) for row in self.rows[:4]]
        # Boards 8..10 decide as recorded: the plan is still minted once and
        # the stall bound releases it at the choke.
        for (_snapshot, key, reason), row in zip(decided[:3], self.rows[:3]):
            self.assertEqual((key, reason), (row["decision"]["key"], row["decision"]["reason"]))
        self.assertEqual(decided[1][0].player.position, OPEN_CELL)
        self.assertEqual(decided[2][0].player.position, CHOKE)
        # The stall release is what the old policy minted a fresh plan after.
        self.assertEqual(self.rows[3]["decision"]["reason"], "melee:choke")
        snapshot, key, reason = decided[3]
        self.assertEqual(snapshot.player.position, OPEN_CELL)
        self.assertNotEqual(policy.choke_engagement_state()["phase"], "reposition")
        self.assert_strikes_adjacent_bear(snapshot, key, reason)

    def test_the_player_stays_and_fights_instead_of_crossing_the_three_cells(self):
        policy = self.policy()
        for row in self.rows[:3]:
            self.decide(policy, row)
        open_rows = [row for row in self.rows[3:] if row["board"]["player"]["y"] == OPEN_CELL.y
                     and row["board"]["player"]["x"] == OPEN_CELL.x]
        self.assertEqual(len(open_rows), 17)
        # Every one of these boards was recorded as the ``9`` step to the choke.
        self.assertEqual({row["decision"]["key"] for row in open_rows}, {"9"})
        for row in open_rows:
            with self.subTest(sequence=row["decision"]["decision_sequence"]):
                snapshot, key, reason = self.decide(policy, row)
                self.assert_strikes_adjacent_bear(snapshot, key, reason)


class ChokeStallTiersRecorded(unittest.TestCase):
    """With the tiers acting (step 6, answer 4): the bears are an unselected T2 and are left."""

    @classmethod
    def setUpClass(cls):
        ChokeStallRecreateRecorded.setUpClass.__func__(cls)

    policy = ChokeStallRecreateRecorded.__dict__["policy"]
    decide = ChokeStallRecreateRecorded.__dict__["decide"]

    def test_the_unselected_t2_pack_is_left(self):
        policy = self.policy()
        decided = []
        for row in self.rows[:4]:
            snapshot, key, reason = self.decide(policy, row)
            decided.append((snapshot, key, reason))
            policy.confirm_key_posted(key)
        leaving = [(snapshot, key, reason) for snapshot, key, reason in decided
                   if reason.startswith(("flee", "emergency:"))]
        self.assertTrue(leaving, [(key, reason) for _snapshot, key, reason in decided])
        snapshot, key, reason = leaving[0]
        result = threat_tiers.assess(policy, snapshot, policy._strategic_hostiles(snapshot))
        self.assertEqual((result.tier, result.selected), (threat_tiers.T2, []))
        self.assertFalse(any(reason.startswith("melee:choke") for _s, _k, reason in decided))


if __name__ == "__main__":
    unittest.main()
