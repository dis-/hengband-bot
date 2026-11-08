"""The Magic-Eater hastes at a fight's start with its absorbed Speed (me_powers FIGHT).

Owner 2026-11-04 (verbatim): 「魔道具術師　取り込んだスピードが残10回以上なら、特にピンチでなくても
戦闘時加速する」 and 「成功率8割以上のときに限定して」.

Recorded boards (the public ``choose_key``; the cast goes through the production executor):
- n1-c life-083 (tests/fixtures/d57-n1c-083-1101.json.gz): turn 1187014, the awake hostile the
  recorded build answered with the absorbed Magic Missile (``mBp8``).
- n1-c life-083 (tests/fixtures/d57-me-combat-083-1101.json.gz): turn 1190789, the recorded
  melee blow ``4`` at the adjacent beetle.

DECLARED CONSTRUCTED: the displayed staff list's Speed row (recorded lives show 8/8, so 10 or
more charges has not occurred); the failure percents; the hasted speed field, the sleeping
hostile, the empty board and the low HP of the controls; the replies to the posted keys.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from unittest.mock import patch

from hengbot import me_powers, threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.model import parse_snapshot
from tests import test_d57_me_combat_1101_recorded as combat
from tests import test_d57_nav_depth_1101_recorded as nav
from tests import test_input_executor as executor_pins
from tests import test_me_mining_death_recorded as mining_death
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_stage2_powers import TYPE_PROMPT


SPEED = "スピード"
TURN = 1187014
SPEED_KEY = "mAw"
REASON = "me-power:fight-unhasted:speed"
MISSILE = ("mBp8", "quest-strategy:ranged-fire:magic-eater")
FAILED = "呪文をうまく唱えられなかった！"


def show(policy, raw, charges, fail):
    """The policy saw the staff list on a board just before ``raw``."""
    shown = dict(copy.deepcopy(raw), _magic_eater_power_list={"kind": "staff", "rows": [
        {"name": SPEED, "current": charges, "max": charges, "fail": fail, "success": 100 - fail}]})
    shown["turn"] -= 1
    observe_lists(policy, parse_snapshot(shown, policy._monrace_knowledge))


class FightSpeedRecordedTest(nav.RecordedDrive):
    post_power = mining_death.MagicEaterMiningDeathRecordedTest.post

    def fight(self, *, charges=10, fail=20, edit=lambda raw: None):
        """The policy after the recorded lead-in, and its answer on the fight board.

        DECLARED CONSTRUCTED (threat tiers step 6): the three ogres and the king cobra are T1
        (``test_the_recorded_fight_is_left_at_t1``), which is left; the 11-04 rule is pinned on
        the board taken as a fight the tiers do not decide."""
        tiers_off = patch.object(threat_tiers, "acts_here", return_value=False)
        tiers_off.start()
        self.addCleanup(tiers_off.stop)
        case = nav.CASE_083
        boards = [copy.deepcopy(raw) for raw in case["boards"] if raw["turn"] < TURN]
        policy = nav.new_policy(case, boards)
        self.drive_boards(case, boards, policy)
        show(policy, boards[-1], charges, fail)
        raw = copy.deepcopy(next(raw for raw in case["boards"] if raw["turn"] == TURN))
        edit(raw)
        return policy, raw, loops.decide(policy, copy.deepcopy(raw))

    def cast(self, policy, raw, key, *, failed=False):
        final = executor_pins.command_screen(raw["turn"] + 10)
        if failed:
            final["lines"][0] = FAILED
        game, port = self.post_power(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("staff", [("w", SPEED, 10, 10, 20)]), final])
        self.assertEqual(game.accepted, ["m", "A", "w"])
        return port.last_result.board

    def test_recorded_row(self):
        rows = [(row["reason"], row["key"]) for row in nav.CASE_083["decisions"]
                if row["turn"] == TURN]
        self.assertEqual(rows[0], tuple(reversed(MISSILE)))

    def test_the_recorded_fight_is_left_at_t1(self):
        # Threat tiers step 6 (answer 6 「倒しきれない -> leave」): three ogres and a king cobra at
        # HP 122/171 are not won even with every supply; the flee rung reads Teleportation.
        case = nav.CASE_083
        boards = [copy.deepcopy(raw) for raw in case["boards"] if raw["turn"] < TURN]
        policy = nav.new_policy(case, boards)
        self.drive_boards(case, boards, policy)
        show(policy, boards[-1], 10, 20)
        raw = copy.deepcopy(next(raw for raw in case["boards"] if raw["turn"] == TURN))
        self.assertEqual((loops.decide(policy, copy.deepcopy(raw)), policy.last_reason),
                         ("re", "flee:scroll"))
        board = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual(threat_tiers.assess(policy, board, policy._strategic_hostiles(board)).tier,
                         threat_tiers.T1)

    def test_ten_charges_at_eighty_percent_cast_before_the_attack_through_the_executor(self):
        policy, raw, key = self.fight()
        self.assertEqual((key, policy.last_reason), (SPEED_KEY, REASON))
        board = self.cast(policy, raw, key)
        self.assertIsNone(board["_completed_operation_receipt"]["refusal"])

    def test_the_blow_at_the_adjacent_beetle_waits_for_the_dose(self):
        rows = [copy.deepcopy(raw) for raw in combat.CASE_083["boards"]
                if raw["turn"] == combat.BEETLE_TURN]
        recorded = {row["turn"]: (row["reason"], row["key"])
                    for row in combat.CASE_083["decisions"]}
        self.assertEqual(recorded[combat.BEETLE_TURN], ("melee", "4"))
        policy = combat.d57.new_policy(combat.CASE_083)
        show(policy, rows[0], 10, 20)
        # Threat tiers step 7: with the absorbed Speed listed the beetle is a selected T2 (a reward
        # race, T2 by the Speed dose), so the supply fight casts the same absorbed haste first
        # (D7 「加速を先に」); the 11-04 rung's own cast is pinned with the tiers not acting.
        self.assertEqual((loops.decide(policy, copy.deepcopy(rows[0])), policy.last_reason),
                         (SPEED_KEY, "supply-fight:quaff-speed:absorbed-power"))
        policy = combat.d57.new_policy(combat.CASE_083)
        show(policy, rows[0], 10, 20)
        with patch.object(threat_tiers, "acts_here", return_value=False):
            self.assertEqual((loops.decide(policy, rows[0]), policy.last_reason), (SPEED_KEY, REASON))

    def test_failed_cast_retries_under_the_table_rule_then_attacks(self):
        policy, raw, key = self.fight()
        board = self.cast(policy, raw, key, failed=True)
        self.assertEqual(board["_completed_operation_receipt"]["refusal"], "failed:magic-eater")
        policy.confirm_key_posted(key)
        following = dict(copy.deepcopy(board), _magic_eater_wand_charges=None)
        self.assertEqual((loops.decide(policy, following), policy.last_reason), (SPEED_KEY, REASON))
        memory = policy._me_power_floor
        place = (("staff", 22), "fight-unhasted", parse_snapshot(
            copy.deepcopy(following), policy._monrace_knowledge).player.position)
        self.assertEqual(memory.failed[place], 1)
        policy.confirm_key_posted(SPEED_KEY)
        memory.failed[place] = me_powers.FAILURES_PER_PLACE
        memory.pending = None
        later = dict(copy.deepcopy(following), turn=following["turn"] + 10)
        self.assertNotEqual(loops.decide(policy, later), SPEED_KEY)

    def test_control_nine_charges_keep_the_recorded_attack(self):
        policy, _, key = self.fight(charges=9)
        self.assertEqual((key, policy.last_reason), MISSILE)

    def test_control_ten_charges_below_eighty_percent_keep_the_recorded_attack(self):
        policy, _, key = self.fight(fail=21)
        self.assertEqual((key, policy.last_reason), MISSILE)

    def test_control_already_hasted_keeps_the_recorded_attack(self):
        def hasted(raw):
            raw["player"]["speed_display"] = {"value": 10, "text": "加速(+10)", "color": "yellow",
                                              "riding": False}
        policy, _, key = self.fight(edit=hasted)
        self.assertEqual((key, policy.last_reason), MISSILE)

    def test_control_landed_cast_with_a_blank_speed_field_is_not_repeated(self):
        policy, raw, key = self.fight()
        board = self.cast(policy, raw, key)
        policy.confirm_key_posted(key)
        following = dict(copy.deepcopy(board), _magic_eater_wand_charges=None)
        self.assertNotEqual(loops.decide(policy, following), SPEED_KEY)

    def test_control_no_awake_hostile_does_not_cast(self):
        def asleep(raw):
            for monster in raw["visible_monsters"]:
                monster["asleep"] = True

        def empty(raw):
            raw["visible_monsters"] = []
        for edit in (asleep, empty):
            with self.subTest(edit=edit.__name__):
                policy, _, key = self.fight(edit=edit)
                self.assertNotEqual(key, SPEED_KEY)
                self.assertNotEqual(policy.last_reason, REASON)

    def test_control_a_survival_answer_comes_first(self):
        def low(raw):
            raw["player"]["hp"] = max(1, raw["player"]["max_hp"] // 10)
        policy, _, key = self.fight(edit=low)
        self.assertNotEqual(key, SPEED_KEY)
        self.assertTrue(policy.last_reason.startswith(("emergency:", "item:", "flee", "unseen:")),
                        policy.last_reason)


class FightSpeedTownTest(unittest.TestCase):
    def test_control_a_town_fight_does_not_cast(self):
        from tests import test_town_last_stand_ranged_recorded as d55
        policy = loops.new_policy(d55.CASE, d55.CASE["skill"], record=d55.CASE["sequence"],
                                  monraces=d55.CASE["monraces"])
        rows = d55.boards()
        show(policy, rows[0], 10, 20)
        for raw in rows[1:]:
            self.assertNotEqual(loops.decide(policy, copy.deepcopy(raw)), SPEED_KEY)


if __name__ == "__main__":
    unittest.main()
