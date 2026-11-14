"""n1-b life-397 (Magic-Eater Lv45) 2026-11-14: the Q25 gate undervalued the absorbed powers.

Owner 2026-11-14 on n1-b's Q25 evaluation: 「ドラゴンの火炎の魔法棒ならもっと威力があるし成功率も
担保できている。比較方法が怠惰ではないか？」 and 「取り込んだ魔法棒の成功率の出し方がおかしい。
95%じゃないのか」.

Recorded: tests/fixtures/n1b-397-q25-gate-1114/ (tests/extract_n1b_397_q25_gate_1114_fixture.py),
the town-arrival checkpoint of the 15:56:00 visit (turn 4259464), restored through
support.town_arrival_fixture; row 0's board is the arrival board.  The Q25 ranged gate
(quest_ranged_force, condition 1: 180 a turn) read 衰弱 (wand, 125 against イプシシマス, race
571) x 75% = 93.75 as the best absorbed power:

- Defect A: Dragon's Flame (wand sval 26, 7 charges, all spent; 200 fire) and Dragon's Frost
  (5, spent; 180) did not count, only charged powers did; the inn's stay refills them all
  (cmd-building/cmd-inn.cpp charge_magic_eating_energy).
- Defect B: the wand list (turn 4259460) was shown while stunned NORMAL, so every wand read
  25% fail; the rod list (4259418) under SLIGHT read 15%; the staff list (4259180, unstunned)
  5%.  The game adds the stun penalty to the displayed rate (cmd-magiceat.cpp:258-274,
  timed-effect/player-stun.cpp get_magic_chance_penalty); unstunned, the Lv45 Dragon's Flame
  is at the 5% floor.

DECLARED CONSTRUCTED (each named at its test): Q25 marked TAKEN (the visit never accepted
it: the gate refused), the player moved beside the inn or onto the Q25 entrance, a list row's
charge changed, the board's stun cleared or its stat index removed.  The quest dispatcher
(``_fixed_quest_key``) is asked directly after the public ``choose_key`` of row 0: at the
arrival the survival rest (stunned) and the shopping come first in ``choose_key``.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import dataclasses
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import me_device_attacks, me_inn_refill, me_power_success, me_powers, quest_ranged_force
from hengbot.input_executor import ScreenKind
from hengbot.model import Position, QuestState
from hengbot.observed_input import compile_observed_input
from hengbot.policy_constants import QUEST_STATUS_TAKEN
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-397-q25-gate-1114"
IPSISSIMUS = 571
DRAGONS_FLAME, DRAGONS_FROST, ACID_BOLT, TELEPORT_OTHER = 26, 27, 16, 3
INN = Position(37, 119)          # the Outpost inn (building 0) on the town map
BESIDE_INN = Position(38, 119)   # its step north enters it
Q25_ENTRANCE = Position(44, 72)


class MePowerScoring1114RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.policy, _, steps = load(FIXTURE, Path(scratch.name))
        self.board = steps[0][1]()
        self.ranged = self.policy._strategy_force_for_snapshot(
            self.board, self.policy.approved_quest_strategy(25))["ranged"]

    # -- helpers

    def row(self, kind, sval):
        names = me_device_attacks.POWERS[(kind, sval)].names
        return next(row for row in self.policy._me_device_lists[kind][1] if row["name"] in names)

    def unstunned(self, board=None):
        """DECLARED CONSTRUCTED: the board with its stun ended (as the inn's stay ends it)."""
        board = board or self.board
        return dataclasses.replace(board, player=dataclasses.replace(
            board.player, stunned=False, stun_rank=0))

    @staticmethod
    def taken(board, position=None):
        """DECLARED CONSTRUCTED: Q25 taken; the player at ``position``."""
        quests = dict(board.quests)
        quests[25] = QuestState(25, name="幽霊屋敷", status=QUEST_STATUS_TAKEN, type=1, fixed=True)
        board = dataclasses.replace(board, quests=quests)
        if position is not None:
            board = dataclasses.replace(board, player=dataclasses.replace(board.player, position=position))
        return board

    # -- the recording

    def test_the_recorded_lists_and_board(self):
        player = self.board.player
        self.assertEqual((player.level, player.stun_rank, player.stat_index[1]), (45, 2, 18))
        self.assertEqual({kind: turn for kind, (turn, _) in self.policy._me_device_lists.items()},
                         {"staff": 4259180, "wand": 4259460, "rod": 4259418})
        flame = self.row("wand", DRAGONS_FLAME)
        self.assertEqual((flame["fail"], flame["current"], flame["max"]), (25, 0, 7))
        frost = self.row("wand", DRAGONS_FROST)
        self.assertEqual((frost["fail"], frost["current"], frost["max"]), (25, 0, 5))

    def test_the_game_formula_reproduces_every_displayed_rate_under_its_stun(self):
        # The stun each list was shown under: staff none, rod SLIGHT, wand NORMAL.
        shown_under = {"staff": 0, "rod": 1, "wand": 2}
        checked = 0
        for power, row in me_device_attacks.held_powers(self.policy):
            fail = me_power_success.fail_percent(self.policy, self.board, power.kind, power.level,
                                                 stun=shown_under[power.kind])
            self.assertEqual(fail, row["fail"], (power.kind, power.sval))
            checked += 1
        self.assertGreater(checked, 25)

    # -- defect B: the success rate

    def test_a_wand_power_succeeds_95_percent_unstunned_and_the_stun_adds_its_penalty(self):
        rate = lambda stun: me_power_success.success_percent(  # noqa: E731
            self.policy, self.board, "wand", me_device_attacks.POWERS[("wand", DRAGONS_FLAME)].level,
            stun=stun)
        self.assertEqual(rate(0), 95)
        self.assertEqual((rate(1), rate(2), rate(3), rate(4)), (85, 75, 65, 45))
        self.assertEqual(rate(5), 5)        # +100, capped at 95% fail
        self.assertEqual(rate(None), 75)    # the board's own stun: NORMAL

    def test_combat_reads_the_rate_under_the_current_stun_not_the_list_stun(self):
        board = self.unstunned()
        acid = dict(me_device_attacks.usable_powers(self.policy, board))[
            me_device_attacks.POWERS[("wand", ACID_BOLT)]]
        self.assertAlmostEqual(acid, 0.95)  # its row read 25% fail, shown while stunned
        stunned = dict(me_device_attacks.usable_powers(self.policy, self.board))[
            me_device_attacks.POWERS[("wand", ACID_BOLT)]]
        self.assertAlmostEqual(stunned, 0.75)

    def test_the_stunned_escape_rate_is_not_counted_twice(self):
        # me_powers.stunned_success (the absorbed Teleport Other against the scroll): its row
        # read 25% fail under the list's stun; unstunned it is 95%, stunned NORMAL 75%.
        self.assertEqual(me_powers.stunned_success(self.policy, self.unstunned(), ("wand", TELEPORT_OTHER)), 95)
        self.assertEqual(me_powers.stunned_success(self.policy, self.board, ("wand", TELEPORT_OTHER)), 75)

    def test_a_list_shown_on_these_inputs_reads_its_rate_less_the_stun_it_was_shown_under(self):
        # DECLARED CONSTRUCTED: the wand list shown again on this (stunned NORMAL) board with
        # Dragon's Flame at 35% fail, 10 above the formula (as a worn HARD_SPELL curse, which
        # the board does not export, would show it).
        rows = [dict(row, fail=35, success=65) if row["name"] in me_device_attacks.POWERS[
            ("wand", DRAGONS_FLAME)].names else dict(row) for row in self.policy._me_device_lists["wand"][1]]
        me_device_attacks.observe_lists(self.policy, dataclasses.replace(
            self.board, turn=self.board.turn + 1,
            magic_eater_power_list={"kind": "wand", "rows": rows}))
        flame = self.row("wand", DRAGONS_FLAME)
        level = me_device_attacks.POWERS[("wand", DRAGONS_FLAME)].level
        rate = lambda board, stun: me_power_success.success_percent(  # noqa: E731
            self.policy, board, "wand", level, row=flame, stun=stun)
        self.assertEqual((rate(self.board, 0), rate(self.board, None), rate(self.board, 3)), (85, 65, 55))
        # DECLARED CONSTRUCTED: INT one index higher than when it was shown: the formula.
        player = self.board.player
        index = list(player.stat_index)
        index[1] += 1
        smarter = dataclasses.replace(self.board, player=dataclasses.replace(
            player, stat_index=tuple(index)))
        self.assertEqual(rate(smarter, 0), 95)

    def test_without_the_stat_index_the_displayed_row_loses_the_stun_it_was_shown_under(self):
        # DECLARED CONSTRUCTED: an emitter without stat_index; the wand list shown again on
        # this (stunned NORMAL) board, so its stun is recorded with it.
        board = dataclasses.replace(self.board, player=dataclasses.replace(
            self.board.player, stat_index=()))
        rows = self.policy._me_device_lists["wand"][1]
        me_device_attacks.observe_lists(self.policy, dataclasses.replace(
            board, turn=self.board.turn + 1,
            magic_eater_power_list={"kind": "wand", "rows": [dict(row) for row in rows]}))
        flame = self.row("wand", DRAGONS_FLAME)
        level = me_device_attacks.POWERS[("wand", DRAGONS_FLAME)].level
        self.assertEqual(me_power_success.success_percent(
            self.policy, board, "wand", level, row=flame, stun=0), 95)
        self.assertEqual(me_power_success.success_percent(
            self.policy, board, "wand", level, row=flame, stun=1), 85)

    # -- defect A: the gate counts the refillable capacity

    def test_the_q25_gate_counts_dragons_flame_at_its_capacity(self):
        found = quest_ranged_force.score(self.policy, self.board, self.ranged)
        self.assertAlmostEqual(found.turn, 200 * 0.95)
        self.assertGreaterEqual(found.turn, 120)  # condition 2
        self.assertGreaterEqual(found.turn, 180)  # condition 1
        self.assertGreaterEqual(found.shots, 40)
        flags = self.policy._monrace_knowledge.get(IPSISSIMUS).flags
        best = max(quest_ranged_force._absorbed(self.policy, self.board, flags))
        self.assertEqual(best, (190.0, 7))  # Dragon's Flame: its 7 charges once refilled

    def test_the_policy_readiness_passes_its_ranged_row(self):
        self.policy._evaluate_fixed_quest_readiness(self.board, 25, require_target_town=False)
        force = self.policy._fixed_quest_readiness["strategy_force"]
        self.assertEqual(force["hp"]["required"], 850)  # condition 1's row
        self.assertEqual(force["ranged"]["turn"], {"measured": 190.0, "required": 180.0})
        self.assertNotIn("ranged", force["failed"])
        # What remains are carries the shops sell.
        self.assertEqual(force["failed"], ["required_potions.restore_exp", "required_potions.restore_str"])

    def test_combat_still_refuses_a_power_without_a_charge(self):
        usable = {(power.kind, power.sval) for power, _ in me_device_attacks.usable_powers(
            self.policy, self.unstunned())}
        self.assertNotIn(("wand", DRAGONS_FLAME), usable)
        self.assertNotIn(("wand", DRAGONS_FROST), usable)
        self.assertIn(("wand", ACID_BOLT), usable)

    # -- defect A: the inn's night before the entry

    def test_the_entry_stays_at_the_inn_first_then_enters(self):
        policy = self.policy
        self.assertEqual(policy.choose_key(self.board), "Cf\ry\x1b\x1b")  # recorded row 0
        self.assertTrue(quest_ranged_force.absorbed_short(policy, self.board, self.ranged))
        # On the Q25 entrance itself the walk turns to the inn.
        key = policy._fixed_quest_key(self.taken(self.board, Q25_ENTRANCE), [])
        self.assertEqual(policy.last_reason, me_inn_refill.APPROACH_REASON)
        self.assertNotEqual(key, ">")
        # Beside the inn: the step in carries the night and the leave.
        key = policy._fixed_quest_key(self.taken(self.board, BESIDE_INN), [])
        self.assertEqual((key, policy.last_reason), ("8r\x1b", me_inn_refill.REST_REASON))
        self.assertEqual(me_inn_refill.state(policy).posted_turn, self.board.turn)
        first, steps = compile_observed_input(key, ScreenKind.COMMAND, {}, policy.last_reason, [])
        self.assertEqual(first, "8")
        self.assertEqual([(step.kinds, step.keys) for step in steps],
                         [(frozenset({ScreenKind.BUILDING}), "r"),
                          (frozenset({ScreenKind.BUILDING}), "\x1b")])
        # The night is posted once: the entrance then enters.
        key = policy._fixed_quest_key(self.taken(self.board, Q25_ENTRANCE), [])
        self.assertEqual((key, policy.last_reason), (">", "quest:enter"))
        # A quest floor starts a new stay in town.
        policy.choose_key(dataclasses.replace(self.unstunned(), floor_key=(0, 0, 25)))
        self.assertIsNone(getattr(policy, "_me_inn_refill_stay", None))

    def test_counter_full_powers_enter_without_the_inn(self):
        # DECLARED CONSTRUCTED: every counted wand and rod at its capacity.
        for kind, (turn, rows) in list(self.policy._me_device_lists.items()):
            full = tuple(dict(row, current=row["max"]) if "current" in row else dict(row, charging=0)
                         for row in rows)
            self.policy._me_device_lists[kind] = (turn, full)
        self.assertFalse(quest_ranged_force.absorbed_short(self.policy, self.board, self.ranged))
        self.policy.choose_key(self.board)
        key = self.policy._fixed_quest_key(self.taken(self.board, Q25_ENTRANCE), [])
        self.assertEqual((key, self.policy.last_reason), (">", "quest:enter"))


if __name__ == "__main__":
    unittest.main()
