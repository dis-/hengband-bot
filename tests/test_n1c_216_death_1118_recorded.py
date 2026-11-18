"""n1-c life-216 (Magic-Eater Lv50, Angband 80F, 2026-11-18 13:36): killed while Recall counted
down by an unseen はぐれメタル (race 871: speed +80, AC 10000, 3d2 HP, EMPTY_MIND, casting every
turn), recorded.

The character (speed +29, see invisible, telepathy; the absorbed *Destruction* x70, Healing staff
and rod, Teleportation staff, Teleport Away wand; 5 Potions of Healing and 15 Teleportation
scrolls) was hit from the dark (「何かが純ログルスを放った。」), saw the metal once at distance 3
(game turn 7228517), walked on with the unseen retreat, read Recall at 758 HP and waited with
'5' while HP fell 758 -> 555 -> 630 (after a Potion of Healing; 225 taken) -> 261 -> 230 -> 361
-> 133 -> 288 -> dead (505 in one turn).

Four defects, one class each:

1. ``HiddenByHealingTest``: the observation's ``_took_damage`` compared HP with the previous
   board's only, so the drink's +300 hid the 225 taken after it and the Recall wait's
   unseen-attacker rung was skipped (``return:wait-recall`` at 7228541).  heal_offset.
2. ``UnseenFireTest``: deep_teleport ``fire_p95`` (owner 2026-11-14: 50F+ the teleport only when
   the p95 of the monsters with a line of fire reaches the HP) summed the monsters in view or
   sensed only, so it read 0 while 即死 (threat_tiers.instant_death, with the observed unseen
   loss) held at HP 261 and 133; the finders offered no teleport (``deep-teleport:no-means-fight``
   while Recall counted down).  The unseen loss is proof of a line of fire: the sum adds the
   same correction.
3. ``KillTimeTest``: the free attack's kill time (threat_projection ``free_attack``, the tiers'
   ``ceil(hp / free damage)``) read melee as ``min(expected damage, hp)``: five blows at 5% each
   against AC 10000 (attack-accuracy.cpp: 5% always hit) dealt more than the metal's 6 HP in
   expectation, so it died in one action and the engagement was T3 at distance 3.  The kill
   time now counts the landings a kill takes over the landing chance (attack_expectation
   ``kill_paced``; melee, the launcher's shots, a thrown torch and the devices' uses).
   The metal is still T3 on that board: about four actions, while the projection's incoming
   over four actions (661) stays below the HP (913).
4. ``RetreatHandoverTest``: the unseen retreat (policy_supply ``_unseen_retreat_key``) gave the
   board to the combat ladder only for a hostile in view that was adjacent or named in the
   messages, so the metal seen at distance 3 (p95 299 against the 83 that armed the retreat)
   was walked away from (``unseen:reverse-choke`` at 7228518).  A hostile in view with a line
   of fire whose p95 covers the retreat's unseen loss now ends the retreat.

Recorded: tests/fixtures/n1c-216-death-1118.jsonl.gz (tests/extract_n1c_216_death_1118_fixture.py),
the live boards 7228502-7228558, replayed by one fresh policy through the public ``choose_key``
from the first board on, as tests/test_n1c_207_death_1114_recorded does.  The fresh process reads
Recall on its first boards (it has no record of the live process's floor plan), which leaves the
boards' own observation untouched: the recorded HP, messages and pack are what each board reads.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import math
from pathlib import Path
import unittest
from unittest import mock

from hengbot import attack_expectation, deep_teleport, heal_offset, threat_projection, threat_tiers
from hengbot.baseitem_knowledge import load_baseitem_costs
from hengbot.model import parse_snapshot
from hengbot.policy_constants import UNSEEN_REVERSE_REASON
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "n1c-216-death-1118.jsonl.gz"
EDIT = Path(r"C:\hengband\lib\edit")
METAL = 871                 # はぐれメタル, MonraceDefinitions.jsonc
FIRST_HIT = 7228514         # 「何かが純ログルスを放った。」, 83 taken: the unseen retreat arms
SEEN = 7228517              # the one board the metal was in view (distance 3)
FIRST_DRINK = 7228538       # HP 555: 「何かが魔力の矢の呪文を唱えた。」, the first Healing drunk
AFTER_DRINK = 7228541       # HP 630: +300 from the drink, 225 from the next bolt
INSTANT_DEATH = 7228545     # HP 261: 369 taken unseen (bolt and Logrus), 即死 held


class Replay:
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.boards = [json.loads(line) for line in stream]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.costs = load_baseitem_costs(EDIT / "BaseitemDefinitions.jsonc")

    def board(self, turn):
        return next(board for board in self.boards if board["turn"] == turn)

    def decide(self, turn, edit=None):
        """(policy, the board of ``turn``, its key) after replaying the boards before it;
        ``edit(raw)`` changes the raw board of ``turn`` before it is parsed."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            for raw in self.boards:
                if raw["turn"] > turn:
                    break
                raw = copy.deepcopy(raw)
                if raw["turn"] == turn and edit is not None:
                    edit(raw)
                snapshot = parse_snapshot(raw, self.monrace)
                key = policy.choose_key(snapshot)
                if raw["turn"] == turn:
                    return policy, snapshot, key
                if key:
                    policy.confirm_key_posted(key)
        raise AssertionError(turn)


class TheRecordingTest(Replay, unittest.TestCase):

    def test_the_boards(self):
        self.assertEqual(len(self.boards), 23)
        hp = {board["turn"]: board["player"]["hp"] for board in self.boards}
        self.assertEqual((hp[FIRST_DRINK], hp[AFTER_DRINK]), (555, 630))
        seen = [monster["race_id"] for monster in self.board(SEEN)["visible_monsters"]]
        self.assertEqual(seen, [METAL])
        after = self.board(AFTER_DRINK)["messages"]
        self.assertTrue(any(message.endswith("気分が良くなった。") for message in after))
        self.assertTrue(any(message.startswith("何かが魔力の矢") for message in after))


class HiddenByHealingTest(Replay, unittest.TestCase):

    def test_the_damage_after_the_drink_is_damage(self):
        policy, snapshot, key = self.decide(AFTER_DRINK)
        self.assertTrue(policy._took_damage)
        self.assertEqual(policy._last_damage_amount, 555 + 300 - 630)
        self.assertIsNotNone(policy._unseen_attack_evidence)
        # The Recall wait's unseen-attacker rung answers it (live: return:wait-recall '5').
        self.assertNotEqual(policy.last_reason, "return:wait-recall")
        self.assertTrue(policy.last_reason.startswith("unseen-recall:"), policy.last_reason)

    def test_no_message_no_credit(self):
        # DECLARED CONSTRUCTED control: hp_player's message removed from the board; a potion that
        # left the pack without it (sold, dropped, destroyed) restores nothing.
        def silent(raw):
            raw["messages"] = [message for message in raw["messages"]
                               if not message.endswith(heal_offset.HEAL_MESSAGES)]
        policy, _snapshot, _key = self.decide(AFTER_DRINK, silent)
        self.assertFalse(policy._took_damage)



class UnseenFireTest(Replay, unittest.TestCase):

    def test_instant_death_board_reads_the_teleport(self):
        policy, snapshot, key = self.decide(INSTANT_DEATH)
        death = threat_tiers.instant_death(policy, snapshot)
        self.assertTrue(death.next_action)
        self.assertEqual(death.unseen_correction, 369)
        self.assertGreaterEqual(deep_teleport.fire_p95(policy, snapshot), snapshot.player.hp)
        self.assertTrue(deep_teleport.allows(policy, snapshot))
        self.assertFalse(deep_teleport.no_means(policy, snapshot))
        # Live: unseen-recall:heal 'qb' under {"branch": "deep-teleport:no-means-fight"}.
        self.assertEqual(policy.last_reason, "emergency:teleport")

    def test_without_the_unseen_hit_no_teleport(self):
        # DECLARED CONSTRUCTED control: the board's messages emptied (no unseen-attack evidence):
        # nothing in view or sensed has a line of fire, the sum is 0 and the 11-14 rule holds.
        def quiet(raw):
            raw["messages"] = []
        policy, snapshot, _key = self.decide(INSTANT_DEATH, quiet)
        self.assertEqual(deep_teleport.fire_p95(policy, snapshot), 0)
        self.assertFalse(deep_teleport.allows(policy, snapshot))



class KillTimeTest(Replay, unittest.TestCase):

    def metal(self):
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        snapshot = parse_snapshot(copy.deepcopy(self.board(SEEN)), self.monrace)
        metal = next(monster for monster in snapshot.visible_monsters if monster.race_id == METAL)
        return policy, snapshot, metal

    def test_the_metal_takes_about_four_actions(self):
        policy, snapshot, metal = self.metal()
        self.assertEqual((metal.hp, metal.distance), (6, 3))
        self.assertEqual(self.monrace[METAL].armor_class, 10000)
        self.assertEqual(snapshot.player.main_hand_blows, 5)
        # Live (min(expected, hp)): 6, one action.  A blow lands 5% of the time: 20 blows a kill.
        self.assertAlmostEqual(attack_expectation.melee(policy, snapshot, metal), 1.5)
        free, _cost = threat_projection.free_attack(policy, snapshot, metal)
        self.assertAlmostEqual(free, 1.5)
        result = threat_tiers.assess(policy, snapshot, [metal])
        self.assertEqual(result.free_turns, 4)

    def test_a_likely_kill_keeps_its_one_action(self):
        # Two blows at 90% for 20 against 10 HP: one action, as before.
        self.assertEqual(attack_expectation.kill_paced(36.0, 20.0, 10, 2), 10)
        # One blow at 95%: one action.
        self.assertEqual(attack_expectation.kill_paced(19.0, 20.0, 10, 1), 10)
        # Far below the HP: the kill time of the expectation (n1-a life-450's 8 blows at 31%
        # for 16 against 120 HP: ceil(120 / 40.46) = 3 actions).
        paced = attack_expectation.kill_paced(40.46, 16.31, 120, 8)
        self.assertEqual(paced, 40.46)



class RetreatHandoverTest(Replay, unittest.TestCase):

    def seen_board(self, edit=None):
        """(policy, the SEEN board) with the retreat armed on FIRST_HIT.  DECLARED CONSTRUCTED:
        the fresh process reads Recall on these boards (the live one walked the retreat), so the
        retreat is armed by asking its rung on FIRST_HIT, as the live ladder did."""
        policy = HengbotPolicy(monrace_knowledge=self.monrace, baseitem_costs=self.costs)
        policy._skill_exp_request_key = lambda snapshot: None
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
            for raw in self.boards:
                raw = copy.deepcopy(raw)
                if raw["turn"] == SEEN and edit is not None:
                    edit(raw)
                snapshot = parse_snapshot(raw, self.monrace)
                key = policy.choose_key(snapshot)
                if raw["turn"] == FIRST_HIT:
                    armed = policy._unseen_retreat_key(snapshot, policy._physical_hostiles(snapshot))
                    self.assertEqual(policy.last_reason, UNSEEN_REVERSE_REASON)
                    self.assertIsNotNone(armed)
                    self.assertEqual(policy._unseen_retreat_loss, 83)
                if raw["turn"] == SEEN:
                    return policy, snapshot
                if key:
                    policy.confirm_key_posted(key)
        raise AssertionError(SEEN)

    def test_the_metal_in_view_ends_the_retreat(self):
        policy, snapshot = self.seen_board()
        self.assertEqual(policy._unseen_retreat_floor, snapshot.floor_key)
        # Live: unseen:reverse-choke, walking out of the metal's sight.
        self.assertIsNone(policy._unseen_retreat_key(snapshot, policy._physical_hostiles(snapshot)))
        self.assertIsNone(policy._unseen_retreat_floor)

    def test_a_weak_monster_in_view_does_not(self):
        # DECLARED CONSTRUCTED control: the retreat's loss raised above the metal's p95 (299):
        # a monster in view that cannot account for the unseen hits leaves the retreat walking.
        policy, snapshot = self.seen_board()
        policy._unseen_retreat_loss = 300
        key = policy._unseen_retreat_key(snapshot, policy._physical_hostiles(snapshot))
        self.assertIsNotNone(key)
        self.assertEqual(policy.last_reason, UNSEEN_REVERSE_REASON)


if __name__ == "__main__":
    unittest.main()
