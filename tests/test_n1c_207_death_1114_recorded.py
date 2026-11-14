"""50F+, 即死: after a Teleportation that landed in the same threat's line of fire, *Destruction*.

Owner 2026-11-14 (verbatim) 「前の着地が射線内なら次は *破壊*」.  n1-c life-207 (zombie
Magic-Eater Lv49) died at 2026-11-14 22:57:21 on 金鉱 80F, a cave floor of about 63x22: on the
即死 board (the next action's p95 of the monsters with a line of fire, 415, over HP 407) it read
Teleportation five times, each landing in the same room within the ストーム・ワイアーム's line of
fire (spells-teleport.cpp teleport_player_aux picks among the farther half of the floor's few
cells), and died to its lightning breath with the absorbed *Destruction* (62 charges) unused.
deep_teleport owns the rule: the first teleport keeps the 11-13 order, the next one gives way to
*Destruction* when the previous landing was in the line of fire of a threat now in its sure radius.

Recorded: tests/fixtures/n1c-207-death-1114.jsonl.gz (tests/extract_n1c_207_death_1114_fixture.py),
the live boards, one fresh policy replaying the boards from the first teleport board (turn 8350929)
through the public ``choose_key``.  DECLARED CONSTRUCTED: the depth gate walled off, as
tests/test_deep_teleport_1114_recorded; and the absorbed *Destruction* list (62 of 62 charges, 95%)
shown before the first board -- the live character held the power (the death dump's absorbed list,
*破壊* (62)), which the fresh process has not listed.

* 8350929 (22:57:21, the live first emergency:teleport, HP 407): Teleportation as before.
* 8350932 (the live second emergency:teleport, HP 409, landed at (19,17) with the wyrm six cells
  away and the グリーン・ドラゴン in the line of fire): *Destruction* leaving both.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from hengbot import deep_teleport, destruction_use, instant_death
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-207-death-1114.jsonl.gz"
FIXTURE_SHA256 = "ffbbe4b482bbe163171e0c7160636bead17ac83a49ce41b5595a66122d44c481"
EDIT = Path(r"C:\hengband\lib\edit")
DESTRUCTION_LIST = {"kind": "staff", "rows": [{"name": "*破壊*", "current": 62, "max": 62,
                                               "fail": 5, "success": 95}]}
FIRST_TELEPORT = 8350929
SECOND_TELEPORT = 8350932
GREEN_DRAGON, STORM_WYRM = 561, 1190   # MonraceDefinitions.jsonc


class TeleportLandedInFireRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")

    def decide(self, turn, before=None):
        """(policy, the board of ``turn``, its reason) after replaying the boards from the first
        teleport board; ``before(policy, snapshot)`` runs before the board of ``turn`` is decided."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        boards = [board for board in self.boards if board["turn"] >= FIRST_TELEPORT]
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            for index, raw in enumerate(boards):
                snapshot = parse_snapshot(copy.deepcopy(raw), self.monrace)
                if index == 0:
                    observe_lists(policy, replace(snapshot, turn=snapshot.turn - 1,
                                                  magic_eater_power_list=DESTRUCTION_LIST))
                if raw["turn"] == turn and before is not None:
                    before(policy, snapshot)
                key = policy.choose_key(snapshot)
                if raw["turn"] == turn:
                    return policy, snapshot, policy.last_reason
                if key:
                    policy.confirm_key_posted(key)
        raise AssertionError(turn)

    def test_the_first_teleport_keeps_the_scroll_first(self):
        policy, snapshot, reason = self.decide(FIRST_TELEPORT)
        self.assertEqual((snapshot.dungeon_level, snapshot.player.hp), (80, 407))
        self.assertTrue(instant_death.instant_death(policy, snapshot).next_action)
        self.assertGreaterEqual(deep_teleport.fire_p95(policy, snapshot), snapshot.player.hp)
        self.assertEqual(reason, "emergency:teleport")
        pending = getattr(policy, deep_teleport.MEMORY).pending
        self.assertEqual(pending[:3], (snapshot.floor_key, snapshot.turn, snapshot.player.position))

    def test_the_teleport_after_a_landing_in_fire_gives_way_to_destruction(self):
        policy, snapshot, reason = self.decide(SECOND_TELEPORT)
        self.assertEqual(snapshot.player.hp, 409)
        self.assertGreaterEqual(deep_teleport.fire_p95(policy, snapshot), snapshot.player.hp)
        floor, indices = getattr(policy, deep_teleport.MEMORY).landed
        self.assertEqual(floor, snapshot.floor_key)
        self.assertEqual([monster.race_id for monster in snapshot.visible_monsters
                          if monster.index in indices], [GREEN_DRAGON, STORM_WYRM])
        self.assertEqual(
            reason, destruction_use.REASON + deep_teleport.LANDED_SUFFIX + ":absorbed-power")
        # Asked before the ladder's read is watched: no Teleportation read is awaited.
        self.assertIsNone(policy._emergency_consumable_issue_watch)

    def test_the_landing_refuses_the_teleport_before_the_decision(self):
        refusals = []

        def probe(policy, snapshot):
            deep_teleport.observe(policy, snapshot)  # what choose_key settles first on this board
            refusals.append(([m.race_id for m in deep_teleport.landed_threats(policy, snapshot)],
                             deep_teleport.allows(policy, snapshot)))
        self.decide(SECOND_TELEPORT, probe)
        self.assertEqual(refusals, [([GREEN_DRAGON, STORM_WYRM], False)])

    def test_without_a_usable_destruction_the_teleport_is_read(self):
        def failed_use(policy, snapshot):
            destruction_use._memory(policy).fallback = snapshot.floor_key
        policy, snapshot, reason = self.decide(SECOND_TELEPORT, failed_use)
        self.assertEqual(deep_teleport.landed_threats(policy, snapshot), [])
        self.assertEqual(reason, "emergency:teleport")


if __name__ == "__main__":
    unittest.main()
