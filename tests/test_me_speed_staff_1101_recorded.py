"""#47 owner 2026-11-01: the absorbed Staff of Speed replaces the Potion of Speed.

Owner (verbatim): 「スピードの薬の購入ルールについて。スピードの杖の取り込み後、成功率が
80%以上なら以降スピードの薬の購入、持ち歩きをやめる。スピードの薬を使用する場面では代わりに
取り込んだ杖を試みる。」  Built like 「*破壊*の杖のみ、成功率が80%以上なら…」: the
me_capability.REPLACES row (``reliable``: the displayed success rate) and the use half
in speed_dose.

Recorded boards (every decision is the public ``choose_key``; posted keys go through
the production executor port):

- n1-c life-085 (tests/fixtures/me-speed-staff-life085-1101.json.gz,
  tests/extract_me_speed_staff_1101_fixture.py): Lv18 zombie Magic-Eater in the Black
  Market at turn 1444679, Q2 untaken; the Q2 force asked two Potions of Speed
  (measured 0, required 2) and decision 9047 bought them (``shop:in-store-buy``
  ``pg2``).  The life had absorbed the Staff of Speed (its 08:50 capture's record:
  ``staff:22`` 8).
- n1-c life-083 (tests/fixtures/d57-n1c-083-1101.json.gz): at turn 1187014 the
  Magic Missile answered nothing (a same-turn second decision) and the strong-fight
  rung quaffed a Potion of Speed (decision 5317, ``item:strong-fight-speed`` ``qb``).

DECLARED RECONSTRUCTED: life-085's staff record is the death capture's
``_me_staff_sequence`` (stage 3; the 09:24 record lacks ``staff:22``), the Black
Market visit and errand plan are the recorded ones of decisions 9046/9047
(``store_visit`` town-errand/acquire, stops Black Market then Temple) and the shelf
screen was on the page (the recorded in-store preconditions); the Home and
skill-proficiency rows are the ring's last ones before the turn.
DECLARED CONSTRUCTED: the displayed staff power list with the Speed row
(cmd-magiceat.cpp prints the failure percent; charges 8/8, fail 20 or 21 per case);
for life-083 the empty Magic Missile of the second decision is the executor's
``_magic_eater_wand_charges`` 0 (the recorded same-turn re-decision), the replies to
posted keys (the staff list screen, the failure message 「呪文をうまく唱えられなかった！」,
cmd-magiceat.cpp:521-531) and the purchase reply.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import io
import json
from pathlib import Path
import time
import unittest

from hengbot import me_staff_sequence
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_decision_key_with_prompt_chain
from hengbot.me_device_attacks import observe_lists
from hengbot.model import STORE_BLACK, STORE_TEMPLE, _parse_items, parse_snapshot
from hengbot.policy_types import StoreVisit, StoreVisitPhase, TownErrandPlan
from tests import test_d57_nav_depth_1101_recorded as nav
from tests import test_input_executor as executor_pins
from tests import test_classA_observed_input as follow_harness
from tests import test_me_staff_loops_1031_recorded as loops
from tests import test_q2_tower_recharge_recorded as q2_town
from tests import test_lv7_town_stop_recorded as lv7
from tests import test_me_mining_death_recorded as mining_death
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_stage2_powers import TYPE_PROMPT


with gzip.open(Path(__file__).with_name("fixtures") / "me-speed-staff-life085-1101.json.gz",
               "rt", encoding="utf-8") as _stream:
    LIFE085 = json.load(_stream)
SPEED = "スピード"
STRONG_TURN = 1187014
STRONG_REASON = "item:strong-fight-speed"
CAST_REASON = STRONG_REASON + ":absorbed-power"
FAILED = "呪文をうまく唱えられなかった！"


def staff_list(fail):
    """DECLARED CONSTRUCTED: the displayed staff list's Speed row."""
    return {"kind": "staff", "rows": [
        {"name": SPEED, "current": 8, "max": 8, "fail": fail, "success": 100 - fail}]}


def show(policy, raw, fail):
    """The policy saw the staff list on a board just before ``raw``."""
    shown = dict(copy.deepcopy(raw), _magic_eater_power_list=staff_list(fail))
    shown["turn"] -= 1
    observe_lists(policy, parse_snapshot(shown, policy._monrace_knowledge))


class SpeedPotionPurchaseRecordedTest(executor_pins.ProductionHarness):
    """life-085: the Black Market page where Q2's Speed potions were bought."""

    # The production construction (cli.py main) of the Q2 recorded tests.
    _town = q2_town.Q2TowerRechargeRecordedTest
    setUpClass = classmethod(_town.setUpClass.__func__)
    policy = _town.policy
    decide = _town.decide

    def visit(self, fail=None):
        board, page = LIFE085["boards"][0], LIFE085["boards"][1]
        policy = self.policy(board)
        policy.consume_skill_knowledge(LIFE085["skill"])
        policy.consume_home_knowledge(tuple(_parse_items(LIFE085["home"]["knowledge"]["items"],
                                                         protocol=3)))
        record = me_staff_sequence.state(policy)
        record.powers_read = True
        record.absorbed = {(int(key) if key.isdigit() else key): count
                           for key, count in LIFE085["sequence"]["absorbed"].items()}
        record.stage = LIFE085["sequence"]["stage"]
        if fail is not None:
            show(policy, board, fail)
        policy._town_errand_plan = TownErrandPlan([STORE_BLACK, STORE_TEMPLE], index=0)
        policy._store_visit = StoreVisit("town-errand", "shopping", STORE_BLACK,
                                         phase=StoreVisitPhase.ENTERING, opened_sequence=9046,
                                         visit_origin="acquire")
        policy._decision_sequence = 9046
        policy.observe_store_screen(True)
        raw = copy.deepcopy(page)
        key = self.decide(policy, raw)
        return policy, raw, key

    def speed_force(self, policy, raw):
        """The Q2 force's Speed row (the recorded ``fixedquest_readiness``)."""
        policy._approved_strategy_force_ready(parse_snapshot(copy.deepcopy(raw), self.monraces),
                                              policy.approved_quest_strategy(2))
        return policy._fixed_quest_readiness["strategy_force"]["speed_potions"]

    def post_buy(self, policy, raw, key):
        """The purchase through the executor (purchase-order.cpp prompts)."""
        ware = next(item for item in raw["store"]["items"] if item["letter"] == key[1])
        following = copy.deepcopy(raw)
        following["turn"] += 10
        following["player"]["gold"] -= ware["price"]
        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.jsonl = [copy.deepcopy(raw)]
        shelf = lv7.Lv7TownStopRecordedTest.shelf_screen
        game.screen = shelf(raw)
        # The recorded item prompt (live-screen-cap-05), the price question
        # (store/purchase-order.cpp prompt_to_buy), the shelf again.
        game.screens = [follow_harness.recorded("live-screen-cap-05-alchemist-buy-p.json"),
                        executor_pins.prompt_screen(f"買値 ${ware['price']} で買いますか？[Y/n]"),
                        shelf(following)]
        game.states = [copy.deepcopy(raw), copy.deepcopy(raw), copy.deepcopy(following)]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=time.monotonic() + 10).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _, _, _ = _send_decision_key_with_prompt_chain(
            port, "speed-staff-replay", key, None, set(), policy=policy,
            shadow_client=None, file=io.StringIO(), deadline=time.monotonic() + 10,
            poll_interval=0, prompt_japanese=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), self.monraces),
            posting_contract=PostingContract(), in_store=True)
        self.assertTrue(sent, getattr(port.last_result, "reason", None))
        self.assertEqual(port.last_result.outcome, "completed")
        return game

    def test_recorded_rows(self):
        rows = {row["decision_sequence"]: row for row in LIFE085["decisions"]}
        self.assertEqual((rows[9047]["reason"], rows[9047]["key"]), ("shop:in-store-buy", "pg2\r\r"))
        self.assertEqual(rows[9047]["shop_selector"]["wanted_purchase"]["category"], "speed")
        self.assertEqual(rows[9047]["fixedquest_readiness"]["strategy_force"]["speed_potions"],
                         {"measured": 0, "required": 2})

    def test_control_unlisted_or_unreliable_staff_buys_the_recorded_potions(self):
        for fail in (None, 21):
            with self.subTest(fail=fail):
                policy, raw, key = self.visit(fail)
                self.assertEqual((key, policy.last_reason), ("pg2\r\r", "shop:in-store-buy"))
                self.assertEqual(self.speed_force(policy, raw), {"measured": 0, "required": 2})

    def test_reliable_staff_waives_the_speed_potions_through_the_executor(self):
        for fail in (20, 15):
            with self.subTest(fail=fail):
                policy, raw, key = self.visit(fail)
                # Q2's next potion, the Potion of Healing; no Speed potion is asked.
                self.assertEqual((key, policy.last_reason), ("ph\r", "shop:in-store-buy"))
                self.assertEqual(self.speed_force(policy, raw), {"measured": 0, "required": 0})
                board = parse_snapshot(copy.deepcopy(raw), self.monraces)
                speed = next(item for item in board.store.items if item.name == "スピードの薬")
                self.assertEqual(policy._matching_live_purchase_rungs(board, speed), ())
                game = self.post_buy(policy, raw, key)
                self.assertEqual("".join(game.accepted), key)


class SpeedStaffCastRecordedTest(nav.RecordedDrive):
    """life-083: the strong-fight rung's Speed dose."""

    post_power = mining_death.MagicEaterMiningDeathRecordedTest.post

    def strong_board(self, fail=None):
        case = nav.CASE_083
        boards = [copy.deepcopy(raw) for raw in case["boards"] if raw["turn"] < STRONG_TURN]
        policy = nav.new_policy(case, boards)
        self.drive_boards(case, boards, policy)
        if fail is not None:
            show(policy, boards[-1], fail)
        strong = copy.deepcopy(next(raw for raw in case["boards"] if raw["turn"] == STRONG_TURN))
        first = loops.decide(policy, copy.deepcopy(strong))
        self.assertEqual((first, policy.last_reason),
                         ("mBp8", "quest-strategy:ranged-fire:magic-eater"))
        # The recorded same-turn second decision: the missile answered nothing.
        strong["_magic_eater_wand_charges"] = 0
        return policy, strong, loops.decide(policy, copy.deepcopy(strong))

    def test_recorded_rows(self):
        rows = [(row["reason"], row["key"]) for row in nav.CASE_083["decisions"]
                if row["turn"] == STRONG_TURN]
        self.assertEqual(rows, [("quest-strategy:ranged-fire:magic-eater", "mBp8"),
                                (STRONG_REASON, "qb")])

    def test_control_unlisted_or_unreliable_staff_quaffs_the_recorded_potion(self):
        for fail in (None, 21):
            with self.subTest(fail=fail):
                policy, _, key = self.strong_board(fail)
                self.assertEqual((key, policy.last_reason), ("qb", STRONG_REASON))

    def cast(self, policy, raw, key, *, failed=False):
        final = executor_pins.command_screen(raw["turn"] + 10)
        if failed:
            final["lines"][0] = FAILED
        game, port = self.post_power(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("staff", [("w", SPEED, 8, 8, 20)]), final])
        self.assertEqual(game.accepted, ["m", "A", "w"])
        return port.last_result.board

    def test_reliable_staff_is_cast_instead_through_the_executor(self):
        policy, raw, key = self.strong_board(20)
        self.assertEqual((key, policy.last_reason), ("mAw", CAST_REASON))
        board = self.cast(policy, raw, key)
        self.assertIsNone(board["_completed_operation_receipt"]["refusal"])

    def test_failed_cast_falls_back_to_the_carried_potion(self):
        policy, raw, key = self.strong_board(20)
        self.assertEqual(key, "mAw")
        board = self.cast(policy, raw, key, failed=True)
        self.assertEqual(board["_completed_operation_receipt"]["refusal"], "failed:magic-eater")
        policy.confirm_key_posted(key)
        following = dict(copy.deepcopy(board), _magic_eater_wand_charges=0)
        self.assertEqual((loops.decide(policy, following), policy.last_reason),
                         ("qb", STRONG_REASON))


if __name__ == "__main__":
    unittest.main()
