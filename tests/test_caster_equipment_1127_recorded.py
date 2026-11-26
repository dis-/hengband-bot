"""A realm caster wears no anti-magic and counts its mana in the gear (n1-a life-545, 2026-11-27).

Owner 2026-11-27 (verbatim): 「盗賊が反魔法装備をしているが、意図通りか？意図通りであるなら魔法書を
持ち歩いている理由を確認」.  Not intended: the Sorcery Rogue wore ☆死天使アズリエルの革製ラージ・
シールド {+探赤r毒暗獄沌;麻[魔} (TR_NO_MAGIC 69) with the books 1 and 2 carried, and 革グローブ [1,+0].

Game facts (C:/hengband/src):
* io/input-key-processor.cpp:424-455: under anti-magic ``m`` is refused before the book question
  (「反魔法バリアが魔法を邪魔した！」, the turn reset) for every class but the Berserker and the Smith;
  the study ``G`` (:372-384), scrolls and devices are not refused.
* player/player-status.cpp:721-735: a class with has_glove_mp_penalty (ROGUE) keeps 3/4 of its
  mana in gloves without FREE_ACT, DEC_MANA, EASY_SPELL, or MAGIC_MASTERY / DEX of a positive pval;
  :737-810 the armour weight (the Rogue's weapon a third); :827-858 over 400 the Rogue keeps
  ``msp - msp * over / 1000``.

Recorded (tests/extract_n1a_545_anti_magic_1127_fixture.py, ``n1a-545-anti-magic-1127``): the
town-arrival checkpoint of 2026-11-27 03:11:52 (Amberite Rogue CL23, 59 MP).  Row 7 wears the
shield again (the mining set's restore) and row 10 is the visit's loadout search; live it kept the
shield and the gloves (the loadout report of 03:11:58).

DECLARED CONSTRUCTED:
* the replay keeps the recorded calibration sidecar across the dump rows (the character dump's
  file is not in the fixture: ``_publish_character_dump`` is a no-op, so the dump row does not
  reject the calibration it would have re-derived);
* ``test_without_the_ban_the_shield_is_chosen`` puts the old ban (NO_AC only) back;
* ``test_without_the_shield_the_spells_are_means`` takes NO_MAGIC off the worn shield's flags;
* the glove and weight items of the formula tests are constructed (weights from the recorded set).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import (caster_mana, class_roles, equipment_rules, equipment_target, item_fate,
                     item_need, realm_spells)
from hengbot.equipment_optimizer import Loadout, OwnedEquipment, owned_armor_fill_slots
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import InventoryItem
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.warrior_loadout_search import _gear_state
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-545-anti-magic-1127"
SEARCH_ROW = 10
SHIELD_ID = "equipped:410a9d5228e150b0:0"
GLOVES_ID = "equipped:aa2dc39428972b1c:0"
NO_MAGIC = 69
ROGUE, WARRIOR, MAGIC_EATER = 3, 0, 16


def _post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


_REPLAYED: dict = {}


def replayed():
    """(policy before row 10, row 10's board, row 10's recorded row), replayed once."""
    if not _REPLAYED:
        scratch = TemporaryDirectory()
        _REPLAYED["scratch"] = scratch
        with mock.patch.object(HengbotPolicy, "_publish_character_dump", lambda *a, **k: None):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                policy, _journal, steps = load(FIXTURE, Path(scratch.name))
            for recorded, supply in steps[:SEARCH_ROW]:
                board = supply()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    key = policy.choose_key(board)
                assert (key, policy.last_reason) == (recorded["key"], recorded["reason"]), recorded
                _post(policy, recorded["key"])
            _REPLAYED["board"] = steps[SEARCH_ROW][1]()
            _REPLAYED["recorded"] = steps[SEARCH_ROW][0]
            _REPLAYED["policy"] = checkpoint_bytes(policy)
            _REPLAYED["calibration"] = policy._character_calibration
            assert policy._character_calibration is not None
    policy = restore_checkpoint_bytes(HengbotPolicy, _REPLAYED["policy"])
    # The calibration lives in its runtime file, outside the checkpoint (replay_town_arrival
    # adopt_calibration): the one the replay validated.
    policy._character_calibration = _REPLAYED["calibration"]
    policy._character_calibration_loaded = True
    return policy, _REPLAYED["board"], _REPLAYED["recorded"]


def search(policy, board):
    with mock.patch.object(HengbotPolicy, "_publish_character_dump", lambda *a, **k: None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            key = policy.choose_key(board)
    return key, equipment_target.loadout_target(policy)


def _in_dungeon(board):
    """DECLARED CONSTRUCTED: the board on a dungeon floor (the mana reserve is a dungeon's)."""
    return replace(board, town_flag=False, store=None)


def _without_no_magic(board):
    equipment = tuple(replace(item, known_flags=item.known_flags - {NO_MAGIC})
                      for item in board.equipment)
    return replace(board, equipment=equipment)


class AntiMagicShield545RecordedTest(unittest.TestCase):
    def test_recorded_board_wears_the_shield_and_the_books(self):
        _policy, board, recorded = replayed()
        self.assertEqual(recorded["reason"], "equipment-transaction:approach-home")
        self.assertEqual(board.player.class_id, ROGUE)
        shield = next(item for item in board.equipment if item.slot == "sub_hand")
        self.assertIn(NO_MAGIC, shield.known_flags)
        self.assertEqual({item.sval for item in board.inventory
                          if item.tval == realm_spells.BOOK_TVAL}, {0, 1})
        self.assertEqual(board.player.max_mp, 59)

    def test_the_search_takes_the_shield_and_the_gloves_off(self):
        policy, board, recorded = replayed()
        key, preparation = search(policy, board)
        self.assertEqual((key, policy.last_reason), (recorded["key"], recorded["reason"]))
        loadout = preparation.result.best.loadout
        self.assertNotIn(SHIELD_ID, loadout.item_ids)
        self.assertNotIn(GLOVES_ID, loadout.item_ids)
        self.assertIsNone(loadout.item_at("arms"))
        takeoffs = {(action.item_id, action.target_slot) for action in preparation.transaction.actions
                    if action.kind == "takeoff"}
        self.assertIn((SHIELD_ID, "sub_hand"), takeoffs)
        self.assertIn((GLOVES_ID, "arms"), takeoffs)
        self.assertFalse(preparation.blockers)

    def test_without_the_ban_the_shield_is_chosen(self):
        # DECLARED CONSTRUCTED: the old ban (NO_AC alone) for every class.
        policy, board, _recorded = replayed()
        with mock.patch.object(equipment_rules, "search_banned_flags",
                               lambda _class_id: equipment_rules.LOADOUT_BANNED_FLAGS):
            _key, preparation = search(policy, board)
        self.assertIn(SHIELD_ID, preparation.result.best.loadout.item_ids)

    def test_the_worn_anti_magic_takes_every_spell_away(self):
        policy, board, _recorded = replayed()
        self.assertTrue(realm_spells.anti_magic_worn(board))
        for spell_id in (realm_spells.DETECT_MONSTERS, realm_spells.PHASE_DOOR,
                         realm_spells.DETECT_DOORS_TRAPS, realm_spells.LIGHT_AREA):
            self.assertTrue(realm_spells.learned(policy, spell_id), spell_id)
            self.assertEqual(realm_spells.success(policy, board, spell_id), 0)
            self.assertFalse(realm_spells.known_reliable(policy, board, spell_id, 1, stunned=False))
        self.assertEqual(realm_spells.escape_reserve(policy, board), 0)
        dungeon = _in_dungeon(board)
        self.assertEqual(realm_spells.escape_reserve(policy, dungeon), 0)
        self.assertFalse(realm_spells.mana_rest_due(policy, replace(
            dungeon, player=replace(dungeon.player, mp=0))))
        self.assertIsNone(realm_spells.escape_means(policy, dungeon, realm_spells.SV_SCROLL_PHASE_DOOR))
        self.assertFalse(realm_spells.identify_reliable(policy, board))
        self.assertFalse(realm_spells.recall_held(policy, board))

    def test_without_the_shield_the_spells_are_means(self):
        # DECLARED CONSTRUCTED: the worn shield's NO_MAGIC taken off its flags.
        policy, board, _recorded = replayed()
        bare = _without_no_magic(board)
        self.assertFalse(realm_spells.anti_magic_worn(bare))
        self.assertGreater(realm_spells.success(policy, bare, realm_spells.DETECT_MONSTERS), 80)
        self.assertGreater(realm_spells.escape_reserve(policy, _in_dungeon(bare)), 0)

    def test_the_shield_is_sale_fodder_for_the_rogue_only(self):
        policy, board, _recorded = replayed()
        shield = next(item for item in board.equipment if item.slot == "sub_hand")
        shelved = replace(shield, slot=item_fate.HOME_STOCK_SLOT)
        self.assertTrue(item_fate._anti_magic_unwearable(board, shield))
        self.assertEqual(item_need._ground(policy, board, shelved), item_need.GROUND_ANTI_MAGIC)
        warrior = replace(board, player=replace(board.player, class_id=WARRIOR))
        self.assertFalse(item_fate._anti_magic_unwearable(warrior, shield))


def _item(tval, weight, *, flags=(), pval=0, slot="a", sval=1):
    return InventoryItem(slot=slot, name=f"item-{tval}-{weight}", count=1, tval=tval, sval=sval,
                         aware=True, known=True, fully_known=True, is_equipment=True,
                         weight=weight, pval=pval, known_flags=frozenset(flags))


def _game_msp(msp, gloves, weight, *, gloves_penalise=True):
    """update_max_mana's tail for the Rogue (player-status.cpp:721-858), integer arithmetic."""
    if gloves is not None and gloves_penalise:
        msp = (3 * msp) // 4
    over = weight - 400
    if over > 0:
        msp -= msp * over // 1000
    return max(msp, 0)


class CasterManaFormulaTest(unittest.TestCase):
    # The recorded set's weights (decipounds): 理力のシミター 130, the shield 100, ドルイドのサイ皮よろい
    # 110, エルフのクローク 5, 闇の鋼鉄ヘルメット 60, 革グローブ 5, 忍びの軟革ブーツ 20.
    def _loadout(self, *, gloves=True, body_weight=110, shield=True):
        slots = [("main_hand", _item(23, 130)), ("body", _item(36, body_weight)),
                 ("outer", _item(35, 5)), ("head", _item(32, 60)), ("feet", _item(30, 20)),
                 ("bow", _item(19, 110))]
        if shield:
            slots.append(("sub_hand", _item(34, 100)))
        if gloves:
            slots.append(("arms", _item(31, 5)))
        return Loadout(tuple((name, OwnedEquipment(f"id-{name}", item, "home"))
                             for name, item in slots), "one_handed")

    def test_the_recorded_set_loses_a_quarter_to_the_gloves(self):
        loadout = self._loadout()
        slots = tuple((name, owned.item) for name, owned in loadout.slots)
        profile = caster_mana.caster_mana(ROGUE)
        # 130 // 3 + 100 + 110 + 5 + 60 + 5 + 20 = 343 (the launcher is not counted).
        self.assertEqual(caster_mana.armour_weight(slots, profile), 343)
        self.assertAlmostEqual(caster_mana.kept_share(slots, ROGUE), 0.75)
        self.assertAlmostEqual(caster_mana.mana_utility(loadout, ROGUE), -0.1)
        self.assertEqual(caster_mana.mana_utility(self._loadout(gloves=False), ROGUE), 0.0)
        # 59 MP live with the gloves: 79 without them by the game's formula (3 * 79 // 4 = 59).
        self.assertEqual(_game_msp(79, gloves=True, weight=343), 59)

    def test_the_share_follows_the_game_formula(self):
        for msp in (40, 59, 79, 120):
            for body in (110, 250, 400, 600):
                for gloves in (False, True):
                    loadout = self._loadout(gloves=gloves, body_weight=body)
                    slots = tuple((name, owned.item) for name, owned in loadout.slots)
                    weight = caster_mana.armour_weight(slots, caster_mana.caster_mana(ROGUE))
                    expected = _game_msp(msp, gloves or None, weight)
                    modelled = msp * caster_mana.kept_share(slots, ROGUE)
                    # The share drops the game's integer rounding: at most one point per step.
                    self.assertLessEqual(abs(modelled - expected), 2, (msp, body, gloves))

    def test_the_exempt_gloves(self):
        self.assertTrue(caster_mana.glove_penalty(_item(31, 5)))
        for flags, pval in (((46,), 0), ((70,), 0), ((39,), 0), ((3,), 2), ((6,), 1)):
            self.assertFalse(caster_mana.glove_penalty(_item(31, 5, flags=flags, pval=pval)), flags)
        self.assertTrue(caster_mana.glove_penalty(_item(31, 5, flags=(3,), pval=0)))
        self.assertTrue(caster_mana.glove_penalty(_item(31, 5, flags=(3,), pval=-1)))

    def test_penalising_gloves_do_not_fill_the_arms_for_a_caster(self):
        gloves = OwnedEquipment("gloves", _item(31, 5), "home")
        free_action = OwnedEquipment("fa", _item(31, 5, flags=(46,), sval=2), "home")
        self.assertEqual(owned_armor_fill_slots((gloves,), class_id=ROGUE), frozenset())
        self.assertEqual(owned_armor_fill_slots((gloves, free_action), class_id=ROGUE),
                         frozenset({"arms"}))
        self.assertEqual(owned_armor_fill_slots((gloves,), class_id=WARRIOR), frozenset({"arms"}))
        self.assertEqual(owned_armor_fill_slots((gloves,)), frozenset({"arms"}))

    def test_the_gear_state_keeps_the_bare_hands_for_a_caster(self):
        bare, gloved = self._loadout(gloves=False), self._loadout(gloves=True)
        _key, bare_vector = _gear_state(bare, ROGUE)
        _key, gloved_vector = _gear_state(gloved, ROGUE)
        # Neither vector is no-worse everywhere: the gloves' AC against their mana.
        self.assertTrue(any(a > b for a, b in zip(bare_vector, gloved_vector)))
        self.assertTrue(any(a < b for a, b in zip(bare_vector, gloved_vector)))


class OtherClassesUnchangedTest(unittest.TestCase):
    def test_the_warrior_reads_no_mana_and_no_new_ban(self):
        loadout = CasterManaFormulaTest()._loadout()
        self.assertEqual(caster_mana.mana_utility(loadout, WARRIOR), 0.0)
        self.assertEqual(equipment_rules.search_banned_flags(WARRIOR),
                         equipment_rules.LOADOUT_BANNED_FLAGS)
        self.assertEqual(_gear_state(loadout, WARRIOR), _gear_state(loadout))
        shield = OwnedEquipment("shield", _item(34, 100, flags=(NO_MAGIC,)), "home")
        self.assertEqual(equipment_rules.loadout_banned_item_ids((shield,), WARRIOR), frozenset())

    def test_the_magic_eater_bans_the_anti_magic_without_mana_costs(self):
        # input-key-processor.cpp:424-455 refuses the Magic-Eater's ``m`` as well.
        self.assertTrue(class_roles.refused_by_anti_magic(MAGIC_EATER))
        shield = OwnedEquipment("shield", _item(34, 100, flags=(NO_MAGIC,)), "home")
        self.assertEqual(equipment_rules.loadout_banned_item_ids((shield,), MAGIC_EATER),
                         frozenset({"shield"}))
        self.assertIsNone(caster_mana.caster_mana(MAGIC_EATER))
        loadout = CasterManaFormulaTest()._loadout()
        self.assertEqual(caster_mana.mana_utility(loadout, MAGIC_EATER), 0.0)
        self.assertEqual(_gear_state(loadout, MAGIC_EATER), _gear_state(loadout))


if __name__ == "__main__":
    unittest.main()
