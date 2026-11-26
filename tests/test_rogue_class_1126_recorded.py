"""The Rogue (盗賊, class 3) played as the Warrior (owner 2026-11-26, supervisor's choice).

Owner 2026-11-26 (verbatim): 「n1-aとn1-bは自由なキャラクタと戦略で勝利を目指すこと。」
「1体は魔道具術師以外にして」.  The Rogue is played exactly like the Warrior (melee, a launcher,
the carried devices; no spell): class_roles.plays_as_warrior drives the Warrior's rules, and the
class-table numbers that differ are the game's (equipment_class_profile):

* src/player-info/class-info.cpp :97-100: num 5, wgt 40, mul 3 (the Warrior's 6, 70, 5);
* src/player/player-status.cpp :1463-1469 calc_num_blow: a Rogue's weapon under 5.0 lb at DEX
  stat_index 30+ gives one more blow (the Warrior's lev/40 is not the Rogue's), and :1443 the
  two-handed bonus is 1 (the Warrior's lev/23 + 1);
* src/player/player-status.cpp :983-989 calc_num_fire: a Rogue's sling gets lev*4 shots of 100,
  its bow nothing (the Warrior's every launcher lev*2).

Recorded: the 00:58:36 town-arrival checkpoint of n1-a life-535 (Warrior Lv40,
tests/fixtures/n1a-535-deep-arrival-1123, its 148 town rows), replayed as recorded and again as a
Rogue.

DECLARED CONSTRUCTED:
* the Rogue replay: every recorded line's ``player.class_id`` is 3, and the recorded calibration
  (the C sheet constants of that Warrior) is kept with its ``class_id`` 3 (nothing else on the
  sheet depends on the class: skills, stats and HP are the board's);
* the replay runs under the recall gates it was recorded with (deep_fall_guard
  ``landing_refused`` answers False, as tests/test_n1a_535_deep_arrival_1123_recorded.py);
* after the first divergence the recorded boards answer the Warrior's keys, so the rest of the
  Rogue replay only proves the policy decides on every board without an exception.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from hengbot import class_roles, equipment_target
from hengbot.cli import _consume_response_sequence
from hengbot.equipment_class_profile import EQUIPMENT_CLASS_PROFILES, class_shots_bonus
from hengbot.equipment_optimizer import Loadout, OwnedEquipment
from hengbot.model import InventoryItem, parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.quest_strategies import (acceptance_dps_floor, acceptance_hp_floor,
                                      load_quest_strategies)
from hengbot.warrior_equipment_evaluator import (
    ADJ_DEX_BLOW, ADJ_STR_BLOW, ADJ_STR_HOLD, BLOWS_TABLE, WarriorCombatInputs, _warrior_blows)
from hengbot.warrior_loadout_evaluator import warrior_ranged_offense_dps
from replay_town_arrival import journal
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1a-535-deep-arrival-1123"
STRATEGIES = Path(__file__).resolve().parents[1] / "strategy" / "quests"
ROGUE = class_roles.PLAYER_CLASS_ROGUE


def _weapon(weight):
    item = InventoryItem(slot="a", name="weapon", count=1, tval=23, sval=1, aware=True,
                         known=True, fully_known=True, is_equipment=True, weight=weight,
                         damage_dice_num=1, damage_dice_sides=4)
    return OwnedEquipment("weapon", item, "home")


def _launcher(sval, weight):
    item = InventoryItem(slot="b", name="launcher", count=1, tval=19, sval=sval, aware=True,
                         known=True, fully_known=True, is_equipment=True, weight=weight)
    return Loadout((("bow", OwnedEquipment("launcher", item, "home")),), "one_handed")


def _replay(scratch: Path, class_id: int):
    """(policy, [(row, matched, key, reason)], last board) of the visit replayed as ``class_id``."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        policy, _journal, _steps = load(FIXTURE, scratch)
    runtime = scratch / "runtime"

    def rewrite(line):
        raw = json.loads(line)
        if isinstance(raw.get("player"), dict):
            raw["player"]["class_id"] = class_id
        return json.dumps(raw, ensure_ascii=False)

    rows, board = [], None
    with mock.patch("hengbot.deep_fall_guard.landing_refused", return_value=False):
        for index, entry in enumerate(journal(scratch / "town-arrival")):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                _consume_response_sequence(
                    [rewrite(line) + "\n" for line in entry["inputs"]], policy,
                    lambda _key: True, policy._monrace_knowledge, parse_snapshots=False,
                    knowledge_ledger_path=runtime / "knowledge.jsonl")
            for name, value in entry["cli_latches"].items():
                setattr(policy, name, tuple(value) if isinstance(value, list) else value)
            policy.observe_store_screen(entry["store_screen_verified"])
            line = entry["line"] if entry["line"] is not None else entry["inputs"][-1]
            board = parse_snapshot(json.loads(rewrite(line)), policy._monrace_knowledge)
            if index == 0:
                recorded = policy._validated_character_calibration(
                    replace(board, player=replace(board.player, class_id=0)))
                # DECLARED CONSTRUCTED (module docstring): the sheet constants, as class_id.
                policy._character_calibration = replace(recorded, class_id=class_id)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                key = policy.choose_key(board)
            rows.append((index, (key, policy.last_reason) == (entry["key"], entry["reason"]),
                         key, policy.last_reason))
            if index == 12:
                policy._rogue_test_target = equipment_target.loadout_target_result(policy)
                policy._rogue_test_calibration = policy._validated_character_calibration(board)
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
    return policy, rows, board


class RogueClassTableTest(unittest.TestCase):
    def test_rogue_blows_follow_calc_num_blow(self):
        weights = (20, 39, 40, 49, 50, 70, 160)
        for str_idx in range(0, 38, 3):
            for dex_idx in range(0, 38):
                for weight in weights:
                    for two_hand_bonus in (False, True):
                        for level in (1, 40, 50):
                            if ADJ_STR_HOLD[str_idx] < weight // 10:
                                expected = 1
                            else:
                                p = ADJ_STR_BLOW[str_idx] * 3 // max(40, weight) + two_hand_bonus
                                d = min(11, ADJ_DEX_BLOW[dex_idx])
                                expected = (min(5, BLOWS_TABLE[min(11, p)][d])
                                            + (weight < 50 and dex_idx >= 30))
                            self.assertEqual(_warrior_blows(
                                _weapon(weight), str_idx=str_idx, dex_idx=dex_idx, level=level,
                                two_hand_bonus=two_hand_bonus, extra_blows=0, class_id=ROGUE),
                                max(1, expected), (str_idx, dex_idx, weight, level))

    def test_the_class_shots_of_calc_num_fire(self):
        # The sling's ammunition is the shot (16), the bows' the arrow (17), the crossbows' the
        # bolt (18).
        self.assertEqual(class_shots_bonus(ROGUE, level=40, ammo_tval=16), 160)
        self.assertEqual(class_shots_bonus(ROGUE, level=40, ammo_tval=17), 0)
        self.assertEqual(class_shots_bonus(0, level=40, ammo_tval=17), 80)
        self.assertEqual(class_shots_bonus(16, level=40, ammo_tval=16), 0)
        rogue = WarriorCombatInputs(level=40, natural_str=18, natural_dex=18, melee_skill=60,
                                    shooting_skill=80, class_id=ROGUE)
        warrior = replace(rogue, class_id=0)
        sling, bow = _launcher(2, 5), _launcher(12, 30)
        # The Rogue's sling outshoots the Warrior's by 260/180 shots; its bow by none.
        self.assertAlmostEqual(warrior_ranged_offense_dps(sling, rogue)
                               / warrior_ranged_offense_dps(sling, warrior), 260 / 180)
        self.assertLess(warrior_ranged_offense_dps(bow, rogue),
                        warrior_ranged_offense_dps(bow, warrior))
        self.assertIn(ROGUE, EQUIPMENT_CLASS_PROFILES)

    def test_quest_rows_fall_back_to_the_warrior(self):
        quest1 = load_quest_strategies(STRATEGIES)[1].required_force
        for force in (quest1, quest1["no_healing_tier"]):
            self.assertEqual(acceptance_dps_floor(force, ROGUE), acceptance_dps_floor(force, 0))
            self.assertEqual(acceptance_hp_floor(force, ROGUE), acceptance_hp_floor(force, 0))
            # Another class keeps the file's default; the Magic-Eater its own row.
            self.assertEqual(acceptance_dps_floor(force, 1), force["min_expected_dps"])
            self.assertEqual(acceptance_dps_floor(force, 16), 3.6)


class RogueTownVisitReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratches = [TemporaryDirectory(), TemporaryDirectory()]
        cls.warrior, cls.warrior_rows, _ = _replay(Path(cls.scratches[0].name), 0)
        cls.rogue, cls.rogue_rows, cls.rogue_board = _replay(Path(cls.scratches[1].name), ROGUE)

    @classmethod
    def tearDownClass(cls):
        for policy in (cls.warrior, cls.rogue):
            policy._home_disposal.history_path.unlink(missing_ok=True)
        for scratch in cls.scratches:
            scratch.cleanup()

    def test_the_harness_replays_the_warrior_as_recorded(self):
        self.assertEqual(len(self.warrior_rows), 148)
        self.assertTrue(all(matched for _row, matched, _key, _reason in self.warrior_rows))

    def test_the_rogue_decides_every_board_and_searches_its_own_target(self):
        self.assertEqual(len(self.rogue_rows), 148)
        self.assertEqual(self.rogue_board.player.class_id, ROGUE)
        # The search ran on the Rogue's own board (the calibration accepts class 3).
        self.assertEqual(self.rogue._rogue_test_calibration.class_id, ROGUE)
        # The Warrior's town work up to the equipment withdrawal, then the Rogue's own target
        # (5 blows, no bow shots): another Home piece is withdrawn.
        first = next(row for row in self.rogue_rows if not row[1])
        self.assertEqual(first[0], 13)
        self.assertEqual(first[3], "equipment-transaction:withdraw")
        self.assertTrue(all(matched for _row, matched, _key, _reason in self.rogue_rows[:13]))
        rogue = self.rogue._rogue_test_target.best.loadout
        warrior = self.warrior._rogue_test_target.best.loadout
        self.assertNotEqual(
            [(slot, owned.id) for slot, owned in rogue.slots],
            [(slot, owned.id) for slot, owned in warrior.slots])

    def test_the_warrior_rules_read_the_rogue_as_the_warrior(self):
        board = self.rogue_board
        warrior = replace(board, player=replace(board.player, class_id=0))
        policy = self.rogue
        self.assertEqual(policy._home_owner_goal_pending(board),
                         policy._home_owner_goal_pending(warrior))
        for item in (*board.inventory, *board.equipment):
            self.assertEqual(policy._is_disposable_dominated_armour(board, item),
                             policy._is_disposable_dominated_armour(warrior, item), item.name)


if __name__ == "__main__":
    unittest.main()
