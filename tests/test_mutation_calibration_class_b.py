"""Issue #103 / #88 stage 2: the class-B (stat-changing) mutations calibrate.

Inputs are labeled: RECORDED = the life-014 Lv36 periodic dump and its
character response / next board (Linux soak 2026-10-23, mutations [12, 65]),
and the L28 recorded inputs of test_character_sheet_calibration; DECLARED =
a mutation list, the '@' symbols, a shield skill or the stat rows written by
the test the way the game would print them for that mutation list.
"""
import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

from dataclasses import replace
import gzip
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest

import hengbot.character_sheet as character_sheet
from hengbot.character_sheet import (CharacterSheetUnavailable, derive_equipped_calibration,
                                    displayed_modifier, parse_character_sheet)
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import MonraceKnowledge, MonsterBlow
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import CHARACTER_DUMP_MACRO
from hengbot.warrior_defense_evaluator import ADJ_DEX_TO_AC
from hengbot.warrior_equipment_evaluator import modify_stat_value, stat_index
from hengbot.warrior_loadout_evaluator import constitution_hp_bonus
from tests.test_character_sheet_calibration import recorded_equipped_inputs

FIXTURES = Path(__file__).parent / "fixtures/mutation-calibration"
LIFE014_DUMP = FIXTURES / "life014-lv36-bot-test.txt.gz"
LIFE014_STATE = FIXTURES / "life014-lv36-state.jsonl.gz"

# Design DESIGN-mutation-calibration-1019.md section 4 / 5.1.
DESIGN_CLASS_A = frozenset(range(0, 64)) | frozenset(
    {75, 76, 77, 78, 79, 80, 81, 82, 86, 87, 88, 89, 92, 94, 95})
DESIGN_CLASS_B = frozenset(range(64, 75)) | frozenset({83, 84, 85, 90, 91})
DESIGN_TABLE = {64: (4, 0, 0, 0, 0, 0), 65: (-4, 0, 0, 0, 0, 0), 66: (0, 4, 4, 0, 0, 0),
                67: (0, -4, -4, 0, 0, 0), 68: (0, 0, 0, 0, 4, 0), 69: (0, 0, 0, 0, 2, 0),
                70: (0, 0, 0, 0, -4, 0), 71: (0, 0, 0, 0, -2, -1), 72: (0, 0, 0, 0, 0, -4),
                73: (0, 0, 0, 0, 0, -1), 83: (0, 0, 0, 0, 0, -2), 84: (0, 0, 0, 0, 0, -1),
                85: (0, 0, 0, -1, 0, 0), 90: (0, 0, 0, 3, 0, 0), 91: (0, 0, 0, -3, 0, 0)}
# Gear AC of 83/84/85 from calc_to_ac (player-status.cpp), visible in the AC total.
MUTATION_AC = {83: 5, 84: 10, 85: 25}


def at_symbol(compensation):
    """The '@' column glyph of change_display_by_mutation for one stat."""
    if compensation == 0:
        return "."
    return str(abs(compensation)) if abs(compensation) < 10 else "*"


def declared_l28(mutations, effects=frozenset()):
    """DECLARED: the RECORDED L28 sheet as the game prints it with ``mutations``.

    Also returns the calibration of the same sheet without mutations.
    """
    plain = derive_equipped_calibration(*_declared_l28((), effects)[:3], effects=effects)
    declared = _declared_l28(mutations, effects)
    return declared[:3] + (plain,) + declared[3:]


def _declared_l28(mutations, effects):
    sheet, snapshot, character = recorded_equipped_inputs()
    bonus = [sum(DESIGN_TABLE.get(value, (0,) * 6)[index] for value in mutations)
             for index in range(6)]
    tsuyoshi = [4 if "tsuyoshi" in effects and index in (0, 4) else 0 for index in range(6)]
    chr_reset = 74 in mutations
    rows, use = list(sheet.rows), list(snapshot.player.stat_use)
    for index, row in enumerate(sheet.rows):
        printed = row.race + row.profession + row.personality
        equipment = 3 if index in (3, 5) else 0  # the weapon's visible '3' in DEX and CHR
        total = 0 if index == 5 and chr_reset else (
            printed + bonus[index] + equipment + tsuyoshi[index])
        actual = modify_stat_value(row.base, total)
        rows[index] = replace(row, actual=actual,
                              modifier=displayed_modifier(row.base, actual, printed))
        use[index] = actual
    dex_ac = ADJ_DEX_TO_AC[stat_index(use[3])] - ADJ_DEX_TO_AC[stat_index(snapshot.player.stat_use[3])]
    ac = snapshot.player.ac + dex_ac + sum(MUTATION_AC.get(value, 0) for value in mutations)
    hp = (snapshot.player.max_hp + constitution_hp_bonus(use[4], sheet.level)
          - constitution_hp_bonus(snapshot.player.stat_use[4], sheet.level))
    sheet = replace(sheet, rows=tuple(rows), max_hp=hp, armor_class=ac)
    snapshot = replace(snapshot, player=replace(snapshot.player, stat_use=tuple(use),
                                                max_hp=hp, hp=hp, ac=ac))
    symbols = [at_symbol(0 if index == 5 and chr_reset else bonus[index] + tsuyoshi[index])
               for index in range(6)]
    character = dict(character, mutations=list(mutations),
                     ac_bonus=ac - character["base_ac"],
                     stat_modifiers=[{"stat_id": index, "player": {"symbol": symbols[index]}}
                                     for index in range(6)])
    return sheet, snapshot, character, bonus


def with_symbol(character, stat, symbol):
    rows = [dict(row, player={"symbol": symbol}) if row["stat_id"] == stat else row
            for row in character["stat_modifiers"]]
    return dict(character, stat_modifiers=rows)


class DeclaredClassBTest(unittest.TestCase):
    def assert_restored(self, value, plain, bonus, ac_delta=0):
        self.assertEqual(value.natural_stats, plain.natural_stats)
        self.assertEqual(value.stat_cur, plain.stat_cur)
        self.assertEqual(value.base_hp, plain.base_hp)
        self.assertEqual(value.base_ac_bonus, plain.base_ac_bonus + ac_delta)
        self.assertEqual(value.intrinsic_adjustments,
                         tuple(a + b for a, b in zip(plain.intrinsic_adjustments, bonus)))
        self.assertEqual(value.base_stats, tuple(
            modify_stat_value(natural, adjustment)
            for natural, adjustment in zip(value.natural_stats, value.intrinsic_adjustments)))

    def test_every_table_mutation_restores_the_unmutated_calibration(self):
        for mutation in sorted(DESIGN_TABLE):
            with self.subTest(mutation=mutation):
                sheet, snapshot, character, plain, bonus = declared_l28([12, mutation])
                value = derive_equipped_calibration(sheet, snapshot, character)
                self.assertEqual(value.mutation_signature, (12, mutation))
                self.assert_restored(value, plain, bonus, MUTATION_AC.get(mutation, 0))

    def test_iron_skin_ac_goes_to_the_constant_and_its_dex_to_the_adjustment(self):
        sheet, snapshot, character, plain, bonus = declared_l28([85])
        value = derive_equipped_calibration(sheet, snapshot, character)
        self.assertEqual(value.base_ac_bonus, plain.base_ac_bonus + 25)
        self.assertEqual(value.intrinsic_adjustments[3], plain.intrinsic_adjustments[3] - 1)

    def test_several_mutations_and_tsuyoshi_sum_into_the_star_symbol(self):
        effects = frozenset({"tsuyoshi"})
        sheet, snapshot, character, plain, bonus = declared_l28([64, 68, 69], effects)
        self.assertEqual([row["player"]["symbol"] for row in character["stat_modifiers"]],
                         ["8", ".", ".", ".", "*", "."])
        value = derive_equipped_calibration(sheet, snapshot, character, effects=effects)
        self.assert_restored(value, plain, bonus)
        with self.assertRaises(CharacterSheetUnavailable) as raised:
            derive_equipped_calibration(sheet, snapshot, with_symbol(character, 4, "9"),
                                        effects=effects)
        self.assertEqual(str(raised.exception), "mutation-symbol-mismatch")

    def test_symbol_that_contradicts_the_table_is_refused(self):
        sheet, snapshot, character, _plain, _bonus = declared_l28([90])
        self.assertIsNotNone(derive_equipped_calibration(sheet, snapshot, character))
        for symbol in (".", "2", "*", "?"):
            with self.subTest(symbol=symbol):
                with self.assertRaises(CharacterSheetUnavailable) as raised:
                    derive_equipped_calibration(sheet, snapshot,
                                                with_symbol(character, 3, symbol))
                self.assertEqual(str(raised.exception), "mutation-symbol-mismatch")
        # A sustain hides the number; that stat is not compared.
        self.assertIsNotNone(derive_equipped_calibration(
            sheet, snapshot, with_symbol(character, 3, "s")))

    def test_ill_norm_resets_charisma_and_keeps_its_printed_total(self):
        for mutations in ([74], [72, 74], [71, 74]):
            with self.subTest(mutations=mutations):
                sheet, snapshot, character, plain, bonus = declared_l28(mutations)
                self.assertEqual(character["stat_modifiers"][5]["player"]["symbol"], ".")
                value = derive_equipped_calibration(sheet, snapshot, character)
                self.assertEqual(value.intrinsic_adjustments[5], 0)
                self.assertEqual(value.base_stats[5], sheet.rows[5].actual)
                self.assertEqual(value.intrinsic_adjustments[:5], tuple(
                    a + b for a, b in zip(plain.intrinsic_adjustments[:5], bonus[:5])))
                self.assertEqual(value.natural_stats, plain.natural_stats)
                self.assertEqual(value.base_hp, plain.base_hp)
        # ILL_NORM charisma always prints '.'.
        sheet, snapshot, character, _plain, _bonus = declared_l28([74])
        with self.assertRaises(CharacterSheetUnavailable) as raised:
            derive_equipped_calibration(sheet, snapshot, with_symbol(character, 5, "2"))
        self.assertEqual(str(raised.exception), "mutation-symbol-mismatch")
        # Control: without ILL_NORM the charisma loss is printed as '4'.
        sheet, snapshot, character, _plain, _bonus = declared_l28([72])
        with self.assertRaises(CharacterSheetUnavailable) as raised:
            derive_equipped_calibration(sheet, snapshot, with_symbol(character, 5, "."))
        self.assertEqual(str(raised.exception), "mutation-symbol-mismatch")

    def test_vuln_elem_and_unknown_ids_stay_refused(self):
        sheet, snapshot, character, _plain, _bonus = declared_l28([12, 65])
        for mutations, reason in (([12, 65, 93], "unsupported-mutation:93"),
                                  ([93], "unsupported-mutation:93"),
                                  ([65, 96, 93], "unsupported-mutation:93,96")):
            with self.subTest(mutations=mutations):
                with self.assertRaises(CharacterSheetUnavailable) as raised:
                    derive_equipped_calibration(sheet, snapshot,
                                                dict(character, mutations=mutations))
                self.assertEqual(str(raised.exception), reason)

    def test_class_a_sheet_symbols_are_not_compared(self):
        # Control: no table entry is used, so the stage-1 calibration stays
        # exactly as before, whatever the '@' column shows.
        sheet, snapshot, character = recorded_equipped_inputs()
        plain = derive_equipped_calibration(sheet, snapshot, character)
        odd = with_symbol(dict(character, mutations=[12]), 0, "7")
        value = derive_equipped_calibration(sheet, snapshot, odd)
        self.assertEqual(replace(value, mutation_signature=()), plain)

    def test_tables_are_the_design_partition(self):
        self.assertEqual(character_sheet.MUTATION_STAT_BONUS, DESIGN_TABLE)
        self.assertEqual(character_sheet.CHR_RESET_MUTATIONS, frozenset({74}))
        handled = set(character_sheet.MUTATION_STAT_BONUS) | character_sheet.CHR_RESET_MUTATIONS
        self.assertEqual(handled, set(DESIGN_CLASS_B))
        self.assertEqual(handled & character_sheet.SHEET_NEUTRAL_MUTATIONS, set())
        self.assertEqual(character_sheet.SHEET_NEUTRAL_MUTATIONS, DESIGN_CLASS_A)
        self.assertEqual(frozenset(range(96)) - character_sheet.SHEET_NEUTRAL_MUTATIONS - handled,
                         frozenset({93}))


def _game_source_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / "src/mutation/mutation-flag-types.h").is_file():
            return parent / "src"
    return None


class GameSourceTableTest(unittest.TestCase):
    def test_table_matches_the_at_column_compensation(self):
        root = _game_source_root()
        if root is None:
            self.skipTest("game source absent")
        header = (root / "mutation/mutation-flag-types.h").read_text(encoding="utf-8")
        ids = {name: int(value) for name, value in
               re.findall(r"(?m)^\s*([A-Z_]+)\s*=\s*(\d+),", header)}
        text = (root / "view/display-player-stat-info.cpp").read_text(encoding="utf-8")
        body = re.search(r"(?ms)^static int compensation_stat_by_mutation\(.*?\n\}\n", text)[0]
        stat_ids = {"A_STR": 0, "A_INT": 1, "A_WIS": 2, "A_DEX": 3, "A_CON": 4, "A_CHR": 5}
        found, reset, stats, current = {}, set(), (), None
        for line in body.splitlines():
            block = re.search(r"if \((stat == A_\w+(?: \|\| stat == A_\w+)*)\)", line)
            if block:
                stats = tuple(stat_ids[name] for name in re.findall(r"A_\w+", block[1]))
            mutation = re.search(r"PlayerMutationType::(\w+)", line)
            if mutation:
                current = ids[mutation[1]]
            elif "tsuyoshi" in line:
                current = None  # the timed bonus, not a mutation
            amount = re.search(r"compensation ([+-])= (\d+);", line)
            if amount and current is not None:
                vector = list(found.get(current, (0,) * 6))
                for stat in stats:
                    vector[stat] = int(amount[1] + amount[2])
                found[current] = tuple(vector)
            if re.fullmatch(r"\s*compensation = 0;", line):
                reset.add(current)
        self.assertEqual(found, DESIGN_TABLE)
        self.assertEqual(reset, {74})


class Life014RecordedTest(unittest.TestCase):
    """RECORDED life-014 (Lv36, mutations [12, 65]) through the posted-dump lifecycle."""

    KNOWLEDGE = {35: MonraceKnowledge(30, 110, False, False, level=1, rarity=1,
                                      average_hp=30, armor_class=10,
                                      blows=(MonsterBlow("HIT", "HURT", 1, 8),))}

    @staticmethod
    def rows():
        lines = gzip.decompress(LIFE014_STATE.read_bytes()).decode("utf-8").splitlines()
        return json.loads(lines[0]), json.loads(lines[1])

    def published(self, directory, character_row, board_row):
        policy = HengbotPolicy(monrace_knowledge=self.KNOWLEDGE)
        policy._character_dump_path = Path(directory) / "bot-test.txt"
        policy._character_calibration_path = Path(directory) / "constants.json"
        # DECLARED: the ~f shield skill_exp (not in these two rows); it only
        # enters the AC constant, never a stat.
        policy._skill_exp_cache = (0, 0, 36, getattr(policy, "_town_visit_epoch", None))
        policy._prepare_character_sheet_dump()
        self.assertTrue(policy.confirm_key_posted(CHARACTER_DUMP_MACRO))
        policy._character_dump_path.write_bytes(gzip.decompress(LIFE014_DUMP.read_bytes()))
        board = parse_snapshot(board_row, {})
        policy.observe_character_snapshot(character_row["character"], envelope=character_row)
        policy._complete_character_dump(board)
        return policy, board

    def test_recorded_puny_character_calibrates_and_reaches_the_optimizer(self):
        character_row, board_row = self.rows()
        self.assertEqual(character_row["character"]["mutations"], [12, 65])
        with TemporaryDirectory() as directory:
            policy, board = self.published(directory, character_row, board_row)
            self.assertIsNone(policy._calibration_unavailable_reason)
            calibration = policy._character_calibration
            self.assertEqual(calibration.mutation_signature, (12, 65))
            sheet = parse_character_sheet(gzip.decompress(LIFE014_DUMP.read_bytes()))
            printed = [row.race + row.profession + row.personality for row in sheet.rows]
            self.assertEqual(calibration.intrinsic_adjustments[0], printed[0] - 4)
            self.assertEqual(calibration.intrinsic_adjustments[3:5], tuple(printed[3:5]))
            for index in (0, 3, 4):
                with self.subTest(stat=index):
                    equipment = sum(item.pval for item in board.equipment
                                    if index in item.known_flags)
                    predicted = modify_stat_value(calibration.natural_stats[index],
                                                  calibration.intrinsic_adjustments[index]
                                                  + equipment)
                    self.assertEqual(predicted, sheet.rows[index].actual)
                    self.assertEqual(predicted, board.player.stat_use[index])
            board = policy.with_known_skill_exp(board)
            self.assertIsNotNone(policy._validated_character_calibration(board))
            policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
            policy._equipment_catalog.observe_home_page([])
            preparation = policy._prepare_equipment_optimization(board)
            self.assertEqual(preparation.blockers, ())
            self.assertIsNotNone(preparation.result.best.loadout)

    def test_recorded_sheet_needs_the_puny_bonus_and_its_symbol(self):
        character_row, board_row = self.rows()
        for change, reason in (({"mutations": [12]}, "visible-modifier-mismatch"),
                               (with_symbol(character_row["character"], 0, "3"),
                                "mutation-symbol-mismatch"),
                               (with_symbol(character_row["character"], 0, "."),
                                "mutation-symbol-mismatch")):
            with self.subTest(reason=reason, change=str(change)[:40]):
                declared = dict(character_row, character=dict(character_row["character"], **change))
                with TemporaryDirectory() as directory:
                    policy, _board = self.published(directory, declared, board_row)
                    self.assertIsNone(policy._character_calibration)
                    self.assertEqual(policy._calibration_unavailable_reason, reason)


if __name__ == "__main__":
    unittest.main()
