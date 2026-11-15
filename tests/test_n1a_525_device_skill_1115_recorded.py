"""n1-a life-525 2026-11-15: a warrior at device skill 31 fundraises below the 50F gate.

Owner 2026-11-15, asked why the Lv37 warrior (eleven staves of *Destruction*, 42 charges,
in the Home; 178,528 gold; Yeek cave 1F for 9.5 hours) cannot meet 50F's 「*破壊* の手段
（杖か取り込んだ力で成功率80%以上）」, verbatim: 「装備で魔法道具使用能力を向上させて杖の
成功率を上げることで先に進むことができる」.

Game (C:/hengband/src): calc_device_ability adds ``8 * pval`` for every worn item with
TR_MAGIC_MASTERY and adj_int_dev of INT (player-status.cpp); the staff's chance is skill -
50 (use-execution.cpp).  Skill 31 is 1.45%; 80% needs 60.  The Home holds the 魔力支配の革
グローブ (+3, +24), the 魔法道具支配のアミュレット (+1, +8) and two 妖精の swords (+2,
+16): +32 already makes 63 (84.6%).  The Home's テレパシーの鉄冠, though, is a weak-ESP
crown (add_high_telepathy: eight ESP kinds, no TR_TELEPATHY), so 50F's telepathy is still
missing and the real catalog keeps its 49F band: the recorded visit replays unchanged.

Recorded: the town-arrival checkpoint of the 17:36:10 visit, its 10 journal rows and the
sidecar files (tests/extract_n1a_525_device_skill_1115_fixture.py).

DECLARED CONSTRUCTED:
* ``with_telepathy``: the Home crown is given TR_TELEPATHY (in the Home list and in the
  equipment catalog), the item n1-a lacks.  The optimizer then wears the device-skill
  gear with it and walks to the Home.
* ``worn_board``: row 2's board with the chosen set's device skill and telepathy, the
  board the transaction leads to (the journal ends before it).
* The shelf rows of the purchase tests (no seen shelf held MAGIC_MASTERY or telepathy),
  and the Home without its mastery gloves and swords for the device row.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import ability_gear, destruction_use, device_skill
from hengbot.equipment_optimizer import ABILITY_FLAG, TR_TELEPATHY, required_abilities
from hengbot.model import STORE_BLACK
from hengbot.policy import _effective_intrinsic_abilities, staged_prompt_chain_matches
from support.town_arrival_fixture import load
from tests.support import recorded as executor_harness

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-525-device-skill-1115"
CROWN = "テレパシーの鉄冠"
GLOVES = "魔力支配の革グローブ [1,+7] (+3) {+道, .}"
AMULET = "魔法道具支配のアミュレット (+1)"


def post(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def with_telepathy(policy):
    """DECLARED CONSTRUCTED: the Home crown with TR_TELEPATHY."""
    items = list(policy._home_knowledge_items)
    for index, item in enumerate(items):
        if CROWN in item.name:
            items[index] = replace(item, known_flags=item.known_flags | {TR_TELEPATHY})
    policy._home_knowledge_items = type(policy._home_knowledge_items)(items)
    home = policy._equipment_catalog._home
    for key, owned in list(home.items()):
        if CROWN in owned.item.name:
            home[key] = replace(owned, item=replace(
                owned.item, known_flags=owned.item.known_flags | {TR_TELEPATHY}))


def gate_of(policy, board):
    return policy._optimizer_destruction_means(
        board, policy._equipment_catalog.items, policy._character_calibration)


class N1a525DeviceSkillRecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        cls.policy, cls.journal, steps = load(FIXTURE, Path(cls.scratch.name) / "real")
        cls.replayed, cls.boards = [], []
        for recorded, supply in steps:
            board = supply()
            key = cls.policy.choose_key(board)
            cls.replayed.append(((key, cls.policy.last_reason), (recorded["key"], recorded["reason"])))
            cls.boards.append(board)
            post(cls.policy, key)
        # The constructed telepathy: the same visit from its arrival.
        cls.built, cls.built_journal, cls.built_steps = load(
            FIXTURE, Path(cls.scratch.name) / "built")
        with_telepathy(cls.built)
        for recorded, supply in cls.built_steps[:2]:
            post(cls.built, cls.built.choose_key(supply()))
        cls.built_board = cls.built_steps[2][1]()
        cls.built_key = cls.built.choose_key(cls.built_board)
        cls.built_reason = cls.built.last_reason

    @classmethod
    def tearDownClass(cls):
        for policy in (cls.policy, cls.built):
            policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_a_the_skill_and_the_staffs_success(self):
        board = self.boards[0]
        self.assertEqual((board.player.class_id, board.player.level, board.player.device_skill),
                         (0, 37, 31))
        self.assertAlmostEqual(destruction_use.staff_success(board.player, 50), 100 / 69)
        self.assertEqual(destruction_use.reliable_skill(), 60)
        staves = [item for item in self.policy._home_knowledge_items
                  if self.policy._is_destruction_staff(item)]
        self.assertEqual((sum(item.count for item in staves),
                          sum(item.count * item.charges for item in staves)), (11, 42))
        self.assertFalse(any(self.policy._is_destruction_staff(item) for item in board.inventory))
        # INT 8 (a zombie) adds adj_int_dev[5] = 1; no worn item has MAGIC_MASTERY.
        has, gate = gate_of(self.policy, board)
        self.assertFalse(has)
        self.assertEqual((gate.need, gate.base), (60, 30))
        self.assertFalse(destruction_use.holds_means(self.policy, board))
        self.assertEqual(self.policy._missing_required_abilities(board, 50),
                         {"destruction", "telepathy"})
        self.assertEqual(self.policy._missing_required_abilities(board, 49), set())

    def test_b_the_home_gear_raises_it_and_the_crown_is_no_telepathy(self):
        catalog = self.policy._equipment_catalog.items
        mastery = sorted((owned.item.name, device_skill.item_mastery(owned)) for owned in catalog
                         if device_skill.item_mastery(owned))
        self.assertEqual([gain for _name, gain in mastery], [16, 16, 24, 8])
        self.assertIn((GLOVES, 24), mastery)
        self.assertIn((AMULET, 8), mastery)
        self.assertTrue(all(owned.origin == "home" for owned in catalog
                            if device_skill.item_mastery(owned)))
        crown = next(owned for owned in catalog if CROWN in owned.item.name)
        self.assertNotIn(TR_TELEPATHY, crown.flags)
        self.assertEqual(len(crown.flags), 8)  # ESP kinds only
        # The gloves and the amulet alone reach the skill: 63, 84.6%.
        board = self.boards[1]
        _has, gate = gate_of(self.policy, board)
        result = self.policy._equipment_optimization_preparation.result
        sets = [entry.loadout for entry in result.top_candidates]
        worn = result.best.loadout
        both = type(worn)(tuple((slot, item) for slot, item in worn.slots
                                if slot not in ("arms", "neck"))
                          + (("arms", next(o for o in catalog if o.item.name == GLOVES)),
                             ("neck", next(o for o in catalog if o.item.name == AMULET))),
                          worn.hand_mode)
        self.assertEqual(gate.skill(both), 63)
        self.assertTrue(sets)
        # Without a telepathy the real catalog keeps the 49F band (no 50F set).
        bands = {decision.band: decision for decision in result.band_decisions}
        self.assertFalse(bands[80].satisfying_set_existed)
        self.assertEqual(result.chosen_depth, 49)

    def test_the_real_visit_replays_unchanged(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[-1]["reason"], "descend")

    def test_c_the_optimizer_wears_the_gear_with_the_telepathy(self):
        policy, board = self.built, self.built_board
        result = policy._equipment_optimization_preparation.result
        self.assertFalse(result.timed_out)
        bands = {decision.band: decision for decision in result.band_decisions}
        self.assertTrue(bands[80].satisfying_set_existed)
        self.assertEqual(result.chosen_depth, 80)
        best = result.best.loadout
        worn = {slot: item.item.name for slot, item in best.slots}
        self.assertEqual(worn["arms"], GLOVES)
        self.assertTrue(worn["head"].startswith(CROWN))
        _has, gate = gate_of(policy, board)
        self.assertGreaterEqual(gate.skill(best), gate.need)
        self.assertGreaterEqual(destruction_use.staff_success(
            replace(board.player, device_skill=gate.skill(best)), 50), 80)
        intrinsic = _effective_intrinsic_abilities(
            board.player, policy._character_calibration.intrinsic_abilities)
        abilities = set(intrinsic) | {name for name, flag in ABILITY_FLAG.items()
                                      if flag in best.flags}
        self.assertLessEqual(required_abilities(80), abilities)
        # The real board walks to the Home for that transaction.
        self.assertEqual((self.built_key, self.built_reason),
                         ("\x1b`n(.", "equipment-transaction:travel-home"))
        row = self.built_journal[2]
        raw = json.loads(row["line"] if row["line"] is not None else row["inputs"][-1])
        self.assertTrue(self.post(policy, raw, self.built_key, [], self.later(raw)))

    def worn_board(self):
        """DECLARED CONSTRUCTED: row 2's board wearing the chosen set."""
        policy, board = self.built, self.built_board
        best = policy._equipment_optimization_preparation.result.best.loadout
        _has, gate = gate_of(policy, board)
        player = board.player
        return replace(board, player=replace(
            player, device_skill=gate.skill(best),
            abilities=frozenset(player.abilities) | {"telepathy"}))

    def test_d_the_gate_passes_and_the_departure_takes_a_staff(self):
        policy = self.built
        worn = self.worn_board()
        self.assertTrue(worn.in_town)
        self.assertGreaterEqual(destruction_use.staff_success(worn.player, 50), 80)
        # The Home staff counts in town once the worn skill makes it reliable.
        self.assertTrue(destruction_use.holds_means(policy, worn))
        self.assertEqual(policy._missing_required_abilities(worn, 50), set())
        self.assertEqual(policy._missing_required_abilities(worn, 80), set())
        self.assertEqual(policy._resistance_depth_limit(worn), 80)
        # The 50F+ intent asks five carried uses: the Home-first take withdraws a staff
        # stack, and the carried staff is departure equipment (destruction-gate).
        self.assertGreaterEqual(policy._intended_dive_depth(worn), 50)
        self.assertEqual(policy._required_destruction_uses(worn), 5)
        self.assertEqual(policy._missing_destruction_uses(worn), 5)
        staff = next(item for item in policy._home_knowledge_items
                     if policy._is_destruction_staff(item))
        self.assertEqual(policy._procurement_missing_amount(worn, staff), 5)
        # Out of town the Home staff counts for nothing: the gate asks it carried.
        dungeon = replace(worn, town_flag=False, floor_key=(worn.floor_key[0], 50, 0))
        self.assertFalse(destruction_use.holds_means(policy, dungeon))
        # The real board's skill opens nothing.
        self.assertFalse(destruction_use.holds_means(policy, self.built_board))


class N1a525ShelfRecordedTest(unittest.TestCase):
    """The depth-ability purchase of the 50F band (ability_gear)."""

    def setUp(self):
        self.scratch = TemporaryDirectory()
        self.policy, _journal, steps = load(FIXTURE, Path(self.scratch.name))
        for _recorded, supply in steps[:7]:
            post(self.policy, self.policy.choose_key(supply()))
        self.board = steps[7][1]()   # the Weapon Smith's page, open
        self.row = self.board.store.items[0]

    def tearDown(self):
        self.policy._home_disposal.history_path.unlink(missing_ok=True)
        self.scratch.cleanup()

    def shelf(self, *rows):
        """DECLARED CONSTRUCTED: a Black Market page of ``rows``."""
        return replace(self.board, store=replace(
            self.board.store, store_type=STORE_BLACK, items=list(rows)))

    def ware(self, name, tval, flags, pval, price=40000):
        return replace(self.row, letter="a", name=name, count=1, tval=tval, sval=1,
                       price=price, is_equipment=True, known_flags=frozenset(flags), pval=pval)

    def drop_home_mastery(self, keep=AMULET):
        """DECLARED CONSTRUCTED: the Home without its mastery gear but ``keep``."""
        home = self.policy._equipment_catalog._home
        for key, owned in list(home.items()):
            if device_skill.item_mastery(owned) and owned.item.name != keep:
                del home[key]

    def test_a_mastery_row_that_reaches_the_skill_is_bought(self):
        self.drop_home_mastery()
        # The amulet (+8) leaves 39: gloves (+3, 24) make 63, gloves (+2, 16) 55.
        plus3 = self.ware("魔力支配のグローブ (+3)", 31, (device_skill.TR_MAGIC_MASTERY,), 3)
        plus2 = self.ware("魔力支配のグローブ (+2)", 31, (device_skill.TR_MAGIC_MASTERY,), 2, 30000)
        self.assertIs(ability_gear.purchase(self.policy, self.shelf(plus2, plus3)), plus3)
        self.assertIsNone(ability_gear.purchase(self.policy, self.shelf(plus2)))

    def test_control_no_staff_buys_no_mastery(self):
        self.drop_home_mastery()
        self.policy._home_knowledge_items = type(self.policy._home_knowledge_items)(
            item for item in self.policy._home_knowledge_items
            if not self.policy._is_destruction_staff(item))
        plus3 = self.ware("魔力支配のグローブ (+3)", 31, (device_skill.TR_MAGIC_MASTERY,), 3)
        self.assertIsNone(ability_gear.purchase(self.policy, self.shelf(plus3)))

    def test_the_real_home_buys_the_telepathy_and_no_mastery(self):
        # The landing is 50F (the alternate dungeon's recall depth): both of its gaps are
        # open.  The real Home reaches 63, so no mastery row is bought; telepathy is the
        # 11-04 rule's own row.
        self.assertEqual(self.policy._equipment_departure_destination_depth(self.board), 50)
        self.assertEqual(ability_gear._landing_missing(self.policy, self.board),
                         {"destruction", "telepathy"})
        helm = self.ware("テレパシーの兜", 32, (TR_TELEPATHY,), 0)
        plus3 = self.ware("魔力支配のグローブ (+3)", 31, (device_skill.TR_MAGIC_MASTERY,), 3)
        self.assertIs(ability_gear.purchase(self.policy, self.shelf(helm)), helm)
        self.assertIsNone(ability_gear.purchase(self.policy, self.shelf(plus3)))


if __name__ == "__main__":
    unittest.main()
