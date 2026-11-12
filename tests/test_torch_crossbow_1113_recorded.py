"""The owner's two answers on the crossbow torch rule (2026-11-13), on n1-c life-202's board.

Owner 2026-11-12 「ライトクロスボウを装備したあと松明を持っているなら全て自宅に仕舞うようにして。」
(torch_release), and 2026-11-13:
「ヘヴィ・クロスボウなど他の射撃武器を装備した時も、松明を全て自宅に仕舞いますか？」 ->
「クロスボウ2種だけ」;
「クロスボウを装備した時に、付けている光源が松明だったらどうしますか？」 ->
「松明は装備しない。装備していたら停止して報告。」

Recorded: the town-arrival checkpoint of n1-c life-202's 2026-11-12 17:18 stop visit
(tests/fixtures/town-weight-torch-1112, tests/extract_town_weight_torch_1112_fixture.py),
replayed through the public chooser and the live CLI's owner-retirement entrance up to row 137:
the light crossbow (sval 23) worn after the swap, the brass lantern worn, seventeen torches in
the pack.  Row 137 is the board where the owner's release shelves every torch at Home.

DECLARED CONSTRUCTED parts (each test names its own):
- the worn launcher's sval on row 137's JSONL board: 24 (heavy crossbow, sv-bow-types.h) or 13
  (long bow); name and weight stay the recorded crossbow's, so the pack weight is unchanged;
- the worn light on row 137's board: the pack's torch (one of the seventeen) in place of the
  lantern; or no worn light (the lantern taken out of the equipment list);
- an open equipment transaction whose remaining action puts a light on;
- the loadout search's catalogue: the row 137 board's crossbow, lantern and torch, with a flat
  evaluator that scores the torch above the lantern.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import json
import lzma
import pickle
import unittest

from hengbot import torch_release
from hengbot.cli import (
    PostingContract, _ExecutorInputPort, _policy_final_stop_banner, _policy_final_stop_required,
    _send_new_decision_key,
)
from hengbot.equipment_optimizer import LoadoutMetrics, OwnedEquipment, optimize_loadout
from hengbot.equipment_transaction_planner import (
    PHASE_EQUIP, EquipmentTransaction, EquipmentTransactionPlan,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession
from hengbot.model import SV_BOW_HEAVY_XBOW, SV_BOW_LIGHT_XBOW, SV_BOW_LONG, parse_snapshot
from tests.support.recorded import FaithfulHookGame, ProductionHarness, command_screen
from tests import test_town_weight_torch_1112_recorded as weight_1112
from tests.test_town_weight_torch_1112_recorded import FIXTURE, STASH_ROW, TORCHES

DEPOSIT = ("5", "equipment-transaction:atomic-deposit")


def _row_line(row):
    rows = [json.loads(line) for line in lzma.decompress(
        (FIXTURE / "journal.jsonl.xz").read_bytes()).decode("utf-8").splitlines() if line.strip()]
    entry = rows[row]
    return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])


class TorchCrossbow1113RecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        # The 11-12 test's replay (its load and live CLI posting), run once for every pin here.
        replay = weight_1112.TownWeightTorch1112RecordedTest("test_worn_light_crossbow_shelves_every_torch")
        replay.setUp()
        try:
            policy, recorded, steps = replay.load()
            replay.replay_live(policy, recorded, steps[:STASH_ROW])
            steps[STASH_ROW][1]()   # the row's inputs reach the policy as live
            cls.policy_bytes = pickle.dumps(policy)
        finally:
            replay.doCleanups()
        cls.raw = _row_line(STASH_ROW)

    def setUp(self):
        self.policy = pickle.loads(self.policy_bytes)

    def board(self, *, bow_sval=None, light="lantern"):
        """Row 137's JSONL board with the declared constructed equipment."""
        raw = copy.deepcopy(self.raw)
        bow = next(item for item in raw["equipment"] if item["slot"] == "bow")
        self.assertEqual(bow["sval"], SV_BOW_LIGHT_XBOW)
        if bow_sval is not None:
            bow["sval"] = bow_sval
        index = next(i for i, item in enumerate(raw["equipment"]) if item["slot"] == "light")
        if light == "torch":
            torch = next(item for item in raw["inventory"] if item["tval"] == 39)
            raw["equipment"][index] = dict(copy.deepcopy(torch), count=1, slot="light")
        elif light is None:
            del raw["equipment"][index]
        return raw, parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge)

    def post(self, raw, key):
        """Post ``key`` through the production executor's input port."""
        game = FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = command_screen(raw["turn"])
        following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[])
        game.screens = [command_screen(following["turn"])]
        game.states = [following]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": self.policy._decision_sequence,
                      "reason": self.policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge),
            posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(port.last_result.outcome, "completed", port.last_result.reason)
        return game.accepted

    # ----------------------------------------------------------- 「クロスボウ2種だけ」

    def test_heavy_crossbow_shelves_every_torch(self):
        """DECLARED CONSTRUCTED: the worn launcher is a heavy crossbow (sval 24)."""
        raw, board = self.board(bow_sval=SV_BOW_HEAVY_XBOW)
        self.assertTrue(torch_release.released(self.policy, board))
        torch = next(item for item in board.inventory if item.is_torch)
        self.assertEqual(self.policy._retention_reservation(board, torch), 0)
        self.assertTrue(self.policy._home_deposit_candidate(torch, board))
        key = self.policy.choose_key(board)
        self.assertEqual((key, self.policy.last_reason), DEPOSIT)
        deposit = self.policy._home_atomic_deposit_pending[0]
        self.assertEqual([(entry[0][1:], entry[1], entry[2]) for entry in deposit],
                         [((39, 0), TORCHES, TORCHES)])
        self.assertEqual(self.post(raw, key), [key])

    def test_light_crossbow_still_shelves_every_torch(self):
        """Recorded row 137 as it is (the 11-12 rule, unchanged)."""
        raw, board = self.board()
        self.assertTrue(torch_release.released(self.policy, board))
        key = self.policy.choose_key(board)
        self.assertEqual((key, self.policy.last_reason), DEPOSIT)

    def test_bow_keeps_the_torches(self):
        """DECLARED CONSTRUCTED: the worn launcher is a long bow (sval 13)."""
        raw, board = self.board(bow_sval=SV_BOW_LONG)
        self.assertFalse(torch_release.released(self.policy, board))
        torch = next(item for item in board.inventory if item.is_torch)
        self.assertGreater(self.policy._retention_reservation(board, torch), 0)
        self.assertFalse(self.policy._home_deposit_candidate(torch, board))
        key = self.policy.choose_key(board)
        self.assertNotEqual(self.policy.last_reason, DEPOSIT[1])
        self.assertFalse(self.policy._home_atomic_deposit_pending)
        self.assertNotEqual(self.policy.last_reason, torch_release.STOP_REASON)
        self.assertIsNotNone(key)

    # ----------------------------------------------- 「装備していたら停止して報告」

    def test_torch_worn_with_crossbow_stops_by_name(self):
        """DECLARED CONSTRUCTED: a torch worn in place of the lantern, both crossbows."""
        for sval in (SV_BOW_LIGHT_XBOW, SV_BOW_HEAVY_XBOW):
            with self.subTest(sval=sval):
                policy = pickle.loads(self.policy_bytes)
                _raw, board = self.board(bow_sval=sval, light="torch")
                self.assertTrue(policy._worn_light(board).is_torch)
                key = policy.choose_key(board)
                self.assertEqual((key, policy.last_reason),
                                 (None, "light:torch-worn-with-crossbow"))
                # The driver's final stop: nothing is sent, the runner reads the marker.
                self.assertTrue(_policy_final_stop_required(policy))
                self.assertTrue(_policy_final_stop_banner(policy.last_reason).startswith(
                    "<light:torch-worn-with-crossbow> "))

    def test_torch_worn_with_a_bow_plays_on(self):
        """DECLARED CONSTRUCTED: a torch worn with a long bow is no stop (no crossbow)."""
        _raw, board = self.board(bow_sval=SV_BOW_LONG, light="torch")
        self.policy.choose_key(board)
        self.assertNotEqual(self.policy.last_reason, torch_release.STOP_REASON)
        self.assertFalse(torch_release.torch_worn_with_crossbow(self.policy, board))

    def test_open_transaction_putting_a_light_on_is_no_stop(self):
        """DECLARED CONSTRUCTED: the planner wears the bow before the light (``_EQUIP_ORDER``)."""
        _raw, board = self.board(light="torch")
        lantern = EquipmentTransaction(PHASE_EQUIP, "equip", "lantern", "light")
        self.policy._equipment_transaction_session = EquipmentTransactionSession(
            EquipmentTransactionPlan((lantern,), (), 0))
        self.assertFalse(torch_release.torch_worn_with_crossbow(self.policy, board))
        self.policy._equipment_transaction_session = None
        self.assertTrue(torch_release.torch_worn_with_crossbow(self.policy, board))

    # ------------------------------------------------------ 「松明は装備しない」

    def test_no_light_chooser_picks_a_torch_beside_a_crossbow(self):
        """DECLARED CONSTRUCTED: no worn light; seventeen torches in the pack.

        Also constructed: the same board off the town (``town_flag`` False) with the torches
        unidentified, for ``_find_light``'s fallback to an unknown light.
        """
        for sval, wears_torch in ((SV_BOW_LIGHT_XBOW, False), (SV_BOW_HEAVY_XBOW, False),
                                  (SV_BOW_LONG, True)):
            with self.subTest(sval=sval):
                policy = pickle.loads(self.policy_bytes)
                _raw, board = self.board(bow_sval=sval, light=None)
                self.assertIsNone(policy._worn_light(board))
                choices = (policy._find_light(board), policy._light_to_wield(board),
                           policy._darkness_torch(board))
                # The dungeon fallback for unidentified lights (fuel hidden, reads 0).
                unknown = replace(board, town_flag=False, inventory=[
                    replace(item, known=False, fuel=0) if item.is_torch else item
                    for item in board.inventory])
                choices += (policy._find_light(unknown),)
                self.assertEqual(torch_release.released(policy, board), not wears_torch)
                if wears_torch:
                    self.assertTrue(all(choice is not None and choice.is_torch
                                        for choice in choices), choices)
                else:
                    self.assertEqual(choices, (None, None, None, None))
                    key = policy.choose_key(board)
                    self.assertNotIn(policy.last_reason, ("wield-light", "fundraise:wield-light"))
                    self.assertNotEqual(key and key[:1], "w")

    def test_loadout_search_never_wears_a_torch_beside_a_crossbow(self):
        """DECLARED CONSTRUCTED catalogue (row 137's items) and a flat evaluator.

        The evaluator scores the torch above the lantern and the crossbow above no launcher:
        without the rule the search wears the crossbow with the torch.
        """
        _raw, board = self.board()
        crossbow = next(item for item in board.equipment if item.slot == "bow")
        lantern = next(item for item in board.equipment if item.slot == "light")
        torch = next(item for item in board.inventory if item.is_torch)
        bow = OwnedEquipment("bow", crossbow, "equipped", "bow")
        lit = OwnedEquipment("lantern", lantern, "pack")
        lamp = OwnedEquipment("torch", torch, "equipped", "light")

        def flat(loadout):
            light = loadout.item_at("light")
            return LoadoutMetrics(
                expected_dps=10.0, survival_turns=100.0, combat_margin=90.0,
                ranged_dps=5.0 if loadout.item_at("bow") is not None else 0.0, speed_bonus=0,
                secondary_value=2 if light is not None and light.item.is_torch else 1,
                relevant_traits=frozenset())

        def best(catalog):
            result = optimize_loadout(catalog, flat, depth=None,
                                      current_item_ids=frozenset({"bow", "torch"}))
            slots = dict(result.best.loadout.slots)
            return (slots.get("bow") and slots["bow"].id, slots.get("light") and slots["light"].id)

        self.assertEqual(best((bow, lit, lamp)), ("bow", "lantern"))
        self.assertNotEqual(best((bow, lamp)), ("bow", "torch"))
        long_bow = OwnedEquipment("bow", replace(crossbow, sval=SV_BOW_LONG), "equipped", "bow")
        self.assertEqual(best((long_bow, lit, lamp)), ("bow", "torch"))


if __name__ == "__main__":
    unittest.main()
