import tests  # noqa: F401

import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "town-cat-no-wait-board.jsonl.gz"


class TownCatNoWaitReplayTests(unittest.TestCase):
    """Replay the captured town board through the real final WAIT guard.

    The single raw board is captured at turn 228022. The pre-fix decision log
    for this same board reports key ``6``, reason ``no-wait:flee``, one visible
    hostile, and 12 predicted damage over three turns. Variants made with
    ``dataclasses.replace`` below are DECLARED CONSTRUCTED controls.
    """

    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.raw = json.loads(next(stream))
        cls.knowledge = {
            2: MonraceKnowledge(
                max_hp=2,
                speed=110,
                can_summon=False,
                friendly=False,
                max_melee_damage=3,
            )
        }
        cls.captured = parse_snapshot(cls.raw, cls.knowledge)

    def replay_wait(self, snapshot, knowledge=None, *, took_damage=False):
        policy = HengbotPolicy(monrace_knowledge=knowledge or self.knowledge)
        policy._build_grid_index(snapshot)
        policy._took_damage = took_damage
        key = policy._forbid_wait_while_damaged(snapshot, "5")
        return key, policy.last_reason

    def test_captured_town_cat_is_meleed_instead_of_fled_from(self):
        self.assertTrue(self.captured.in_town)
        self.assertEqual(self.captured.player.hp, 200)
        self.assertEqual(self.captured.player.max_hp, 200)
        self.assertEqual(len(self.captured.visible_monsters), 1)
        self.assertEqual(self.captured.visible_monsters[0].race_id, 2)
        self.assertEqual(
            self.captured.visible_monsters[0].position.distance_to(
                self.captured.player.position
            ),
            1,
        )
        self.assertEqual(
            self.captured.visible_monsters[0].max_melee_damage, 3
        )
        self.assertEqual(
            self._policy_damage(self.captured, self.knowledge, turns=3), 12
        )

        key, reason = self.replay_wait(self.captured)

        self.assertEqual(key, "1")
        self.assertEqual(reason, "no-wait:melee")

    def test_material_damage_town_hostile_still_flees(self):
        material_knowledge = {
            2: replace(self.knowledge[2], max_melee_damage=30)
        }
        material = parse_snapshot(self.raw, material_knowledge)

        key, reason = self.replay_wait(material, material_knowledge)

        self.assertEqual(reason, "no-wait:flee")
        self.assertNotEqual(key, "1")

    def test_dungeon_board_under_fire_keeps_flee_rewrite(self):
        dungeon = replace(
            self.captured,
            town_flag=False,
            floor_key=(2, 1, 0),
        )

        key, reason = self.replay_wait(dungeon)

        self.assertEqual(reason, "no-wait:flee")
        self.assertNotEqual(key, "1")

    def test_low_hp_still_uses_material_threat_flee_rule(self):
        low_hp = replace(
            self.captured,
            player=replace(self.captured.player, hp=10),
        )

        key, reason = self.replay_wait(low_hp)

        self.assertEqual(reason, "no-wait:flee")
        self.assertNotEqual(key, "1")

    def test_observed_damage_keeps_existing_flee_rule(self):
        key, reason = self.replay_wait(self.captured, took_damage=True)

        self.assertEqual(reason, "no-wait:flee")
        self.assertNotEqual(key, "1")

    @staticmethod
    def _policy_damage(snapshot, knowledge, *, turns):
        policy = HengbotPolicy(monrace_knowledge=knowledge)
        return policy._predicted_damage(
            snapshot, policy._physical_hostiles(snapshot), turns=turns
        )


if __name__ == "__main__":
    unittest.main()