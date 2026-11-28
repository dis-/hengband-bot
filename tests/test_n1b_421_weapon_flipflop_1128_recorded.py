"""The town search and the combat-weapon leaf read one answer for the main hand (n1-b life-421).

n1-b life-421 (Klackon Magic-Eater CL20, build bot-0f49e0d3e) stopped 2026-11-28 11:07 under
``town:blocked:equipment-slot-flipflop:main_hand``.  It came back from mining wearing two シャベル
(1d2) (+0,+0) (+1); the visit's search kept them (the target's hands: both shovels, melee 0.9 a
turn, absorbed attack 25.0), the town's combat-weapon leaf (policy ``_combat_weapon_ready``: a melee
weapon in the main hand) wielded the ロング・ソード (2d5) (+6,+2) again ('wka'), the transaction took
it off for the shovel ('ta', 'wl'), and the flip-flop guard stopped the visit.

Since 478b571d14 the search's attack cut reads the larger of the blows and the absorbed attack
(speed_valuation.offense_per_action), and the absorbed attack was read as if every use were always
there: 25.0 a turn from 17 マジック・ミサイル charges and two bolt rods, more than every weapon's blows
(the long sword 12.4), so every set tied on the attack and the worn shovels stayed by the worn-in-
place tie-break.  The fix: the absorbed attack counts the share its held uses sustain (19 of the 50
the owner names enough: me_loadout_offense ``SUSTAINED_ATTACK_USES``, 25.0 -> 9.5), and the search
asks the leaf's own question (equipment_optimizer ``holds_combat_weapon``) of every set while a
weapon is owned.

Recorded (tests/extract_n1b_421_weapon_flipflop_1128_fixture.py): the town-arrival checkpoint and
its 53 journal rows.  Row 35 is not compared: the live process ran with ``--owner-retired-log-only``
(the CLI rewrote that stop to the recorded key; not journalled).  After row 40 the bot's keys
differ from the record's (the record wears the shovels); the boards are still the recorded ones,
so rows 41-51 only check that no decision blocks or raises, and row 52's flip-flop detector reads
the recorded boards' main hand (it is not asked).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import equipment_target, me_loadout_offense
from hengbot.equipment_optimizer import holds_combat_weapon
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-421-weapon-flipflop-1128"
CLI_REWRITTEN_ROW = 35
SEARCHED_ROW = 36
DIVERGED_ROW = 41
LAST_ROW = 51
SWORD = "ロング・ソード (2d5) (+6,+2)"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class WeaponFlipflop421RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
        cls.policy = policy
        cls.rows = []
        cls.targets = {}
        for recorded, supply in steps[:LAST_ROW + 1]:
            board = supply()
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(board)
            cls.rows.append((recorded, key, policy.last_reason, board))
            target = equipment_target.loadout_target(policy)
            cls.targets[recorded["row"]] = getattr(getattr(target, "result", None), "best", None)
            post(policy, key if recorded["row"] >= DIVERGED_ROW else recorded["key"])

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_the_recorded_rows_replay(self):
        for recorded, key, reason, _board in self.rows[:DIVERGED_ROW]:
            if recorded["row"] != CLI_REWRITTEN_ROW:
                self.assertEqual((key, reason), (recorded["key"], recorded["reason"]),
                                 recorded["row"])

    def test_the_target_holds_the_sword(self):
        best = self.targets[SEARCHED_ROW]
        hands = {slot: owned.item.name for slot, owned in best.loadout.slots
                 if slot in ("main_hand", "sub_hand")}
        self.assertEqual(hands, {"main_hand": SWORD})
        self.assertTrue(holds_combat_weapon(best.loadout))
        self.assertGreater(best.metrics.expected_dps, best.metrics.device_dps)
        # 25.0 a turn at full uses, 19 of the 50 uses held.
        self.assertEqual(me_loadout_offense.SUSTAINED_ATTACK_USES, 50)
        self.assertAlmostEqual(best.metrics.device_dps, 25.01246942514342 * 19 / 50, places=6)

    def test_nothing_blocks_after_the_target(self):
        for recorded, key, reason, board in self.rows[DIVERGED_ROW:]:
            self.assertFalse(str(reason).startswith("town:blocked"), (recorded["row"], reason))
            self.assertNotEqual(reason, "town:restore-combat-weapon", recorded["row"])
            best = self.targets[recorded["row"]]
            self.assertTrue(best is None or holds_combat_weapon(best.loadout), recorded["row"])


class SustainedShareTest(unittest.TestCase):
    """CONSTRUCTED power lists: the uses read from the list's ``max``."""

    def test_uses_scale_the_absorbed_attack(self):
        lists = {"wand": (1, ({"name": "マジック・ミサイル", "max": 17},)),
                 "rod": (1, ({"name": "サンダー・ボルト", "max": 1}, {"name": "アイス・ボルト", "max": 1},
                             {"name": "イルミネーション", "max": 1}))}
        self.assertEqual(me_loadout_offense.held_attack_uses(lists), 19)
        powers = me_loadout_offense.held_magic_eater_powers(lists)
        self.assertIn((me_loadout_offense.ATTACK_USES_KEY, 19), powers)
        inputs = me_loadout_offense.offense_inputs(16, 20, 100, 0, 0, powers)
        self.assertEqual(inputs.attack_uses, 19)
        self.assertAlmostEqual(me_loadout_offense.sustained_share(inputs), 0.38)
        full = me_loadout_offense.offense_inputs(
            16, 50, 100, 0, 0, tuple(entry for entry in powers
                                     if entry[0] != me_loadout_offense.ATTACK_USES_KEY)
            + ((me_loadout_offense.ATTACK_USES_KEY, 99),))
        self.assertEqual(me_loadout_offense.sustained_share(full), 1.0)


class CombatWeaponRequiredTest(unittest.TestCase):
    """CONSTRUCTED: worn shovels, a sword in the pack, an absorbed attack above every blow."""

    def test_the_search_keeps_a_weapon_in_the_main_hand(self):
        from dataclasses import replace
        from hengbot.equipment_optimizer import (
            SLOT_BODY, SLOT_LIGHT, SLOT_MAIN_HAND, SLOT_SUB_HAND, LoadoutMetrics, optimize_loadout)
        from hengbot.warrior_loadout_search import enumerate_single_slot_variants
        from test_warrior_loadout_search import owned

        def equipped(item_id, tval, slot, **kw):
            return replace(owned(item_id, tval, **kw), origin="equipped", equipped_slot=slot)

        items = (equipped("light", 39, SLOT_LIGHT), equipped("robe", 36, SLOT_BODY, ac=2),
                 equipped("shovel-a", 20, SLOT_MAIN_HAND, dice=(1, 2)),
                 equipped("shovel-b", 20, SLOT_SUB_HAND, dice=(1, 2)),
                 replace(owned("sword", 23, dice=(2, 5)), origin="pack"))

        def evaluate(loadout):
            main = loadout.item_at(SLOT_MAIN_HAND)
            melee = 12.4 if main is not None and main.id == "sword" else 0.9
            return LoadoutMetrics(expected_dps=melee, survival_turns=20.0, combat_margin=4.4,
                                  device_dps=25.0, evaluation_complete=True)

        current = frozenset(item.id for item in items if item.origin == "equipped")
        loadouts = list(enumerate_single_slot_variants(items, current_item_ids=current,
                                                       require_light=True))
        self.assertTrue(any(not holds_combat_weapon(loadout) for loadout in loadouts))
        common = dict(depth=19, current_item_ids=current, require_light=True,
                      require_body=True)
        free = optimize_loadout(items, evaluate, candidate_loadouts=loadouts,
                                require_weapon=False, **common)
        self.assertFalse(holds_combat_weapon(free.best.loadout))
        result = optimize_loadout(items, evaluate, candidate_loadouts=loadouts, **common)
        self.assertEqual(result.best.loadout.item_at(SLOT_MAIN_HAND).id, "sword")


if __name__ == "__main__":
    unittest.main()
