"""n1-b life-322 (2026-11-06 02:37): the Q14 reward Light Crossbow was sold.

The reward, an unidentified ライト・クロスボウ (x3), was picked up at 02:37:07
and sold to the Weapon Smith six seconds later for $57 (decisions 13949
shop:in-store-inscribe {o@0, 13950 shop:in-store-sell d0y).  The optimizer
cannot judge an unidentified launcher, so spare_gear released it as spare,
and the town organization sold every Home candidate that had a buyer: the
owner's ranking (item_fate: the top 10 of a slot are kept, an unranked piece
is kept) was never asked.  Identified, it was (1.20turn) (+1,+2): 12.5 per
turn with plain bolts against the worn Sling's 7.5, and the owner's launcher
rule (2026-10-02) puts a Light Crossbow above an ordinary Sling.  Wearing it
needs bolts the optimizer can see: the Smith page this town already saw, a
look at the Smith, and a Smith stop reopened when the new launcher is worn
with none (launcher_upgrade).

Recorded: the 02:37:31 arrival checkpoint of the same life (the sale visit's
own checkpoint was pruned), its calibration, and the recorded boards of the
sale and of the same stay after identification
(tests/extract_launcher_sale_1106_fixture.py).  Changes to boards and
policy state are marked DECLARED.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import launcher_upgrade, spare_gear
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import (
    STORE_HOME, STORE_MAGIC, STORE_TEMPLE, STORE_WEAPON, TVAL_BOW, TVAL_DIGGING, parse_snapshot,
)
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import POLICY_FILE
from replay_town_arrival import adopt_calibration, restore
from tests.support import recorded as executor_pins


FIXTURE = Path(__file__).with_name("fixtures") / "launcher-sale-1106"
LETTERS = "abcdefghijklmnopqrstuvw"
WIELD_PROMPT = "どれを装備しますか? "
# The game's own description of the reward when the sale identified it.
IDENTIFIED = {"name": "ライト・クロスボウ (x3) (1.20turn) (+1,+2)", "to_h": 1, "to_d": 2}
# The next arrival's gold (02:52), above the fundraising start.
NEXT_STAY_GOLD = 13631


def relettered(board: dict) -> dict:
    for letter, item in zip(LETTERS, board["inventory"]):
        item["slot"] = letter
    return board


class LauncherSale1106RecordedTest(executor_pins.ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.boards = json.loads(lzma.decompress((FIXTURE / "boards.json.xz").read_bytes()))

    def policy(self, fundraising):
        raw = TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        visit = Path(raw.name) / "town-arrival"
        visit.mkdir()
        (visit / POLICY_FILE).write_bytes(lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
        scratch = Path(raw.name) / "scratch"
        scratch.mkdir()
        policy = restore(visit, scratch)
        adopt_calibration(policy, FIXTURE / "calibration.json", scratch)
        # DECLARED CONSTRUCTED: the arrival had requested the ~f skill list;
        # the Magic-Eater's two-weapon and shield skills are unused (0).
        policy.consume_skill_knowledge({"knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
                                        "player": {"level": 14}})
        # DECLARED RECONSTRUCTED: the fundraising mode of the stay (decision
        # 13949 fundraising.mode "prepare"; None for the next, richer stay).
        policy._fundraising_mode = fundraising
        return policy

    def board(self, name, turn=None, **changes):
        board = copy.deepcopy(self.boards[name])
        if turn is not None:
            board["turn"] = turn
        board["player"].update(changes)
        return board

    @staticmethod
    def decide(policy, board):
        snapshot = parse_snapshot(board, policy._monrace_knowledge)
        policy.observe_store_screen(bool(board.get("store")))
        key = policy.choose_key(snapshot)
        if key:
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        return snapshot, key, policy.last_reason

    def crossbow(self):
        """DECLARED CONSTRUCTED: the reward as identified (the sold row's text)."""
        sling = next(item for item in self.boards["smith-page"]["equipment"] if item["tval"] == TVAL_BOW)
        crossbow = copy.deepcopy(sling)
        crossbow.update(IDENTIFIED, sval=23, weight=110, slot="")
        return crossbow

    def next_stay(self, turn):
        """The identified stay with the next arrival's gold, the shovel shelved.

        DECLARED CONSTRUCTED: the crossbow kept (identified) before the shots;
        the shovel is the Home deposit an equipment plan takes first.
        """
        board = self.board("after-identify", turn, gold=NEXT_STAY_GOLD)
        pack = [item for item in board["inventory"] if item["tval"] != TVAL_DIGGING]
        shots = next(index for index, item in enumerate(pack) if item["tval"] == 16)
        pack.insert(shots, self.crossbow())
        board["inventory"] = pack
        return relettered(board)

    def test_unidentified_reward_launcher_is_not_sold(self):
        policy = self.policy("prepare")
        outside = self.board("outside-smith")
        self.decide(policy, outside)
        # DECLARED RECONSTRUCTED: the stops this stay had finished (Home 13923,
        # Magic Shop 13933); the Temple one keeps the checkpoint's later
        # surplus Heroism potion, no candidate at 13949, off the first slot.
        for store_type in (STORE_HOME, STORE_MAGIC, STORE_TEMPLE):
            policy._set_town_store_attempted(store_type, outside["turn"], "recorded-plan")
        snapshot, _key, _reason = self.decide(policy, self.board("outside-smith", outside["turn"] + 1))
        crossbow = next(item for item in snapshot.inventory if item.tval == TVAL_BOW)
        self.assertFalse(crossbow.known)
        self.assertIsNone(policy._find_town_organization_surplus(snapshot))
        _snapshot, key, reason = self.decide(policy, self.board("smith-page"))
        self.assertEqual((key, reason), ("\x1b", "shop:observe-and-leave"))

    def test_identified_crossbow_is_worn_on_the_seen_smith_page(self):
        policy = self.policy(None)
        board = self.next_stay(943500)
        snapshot, key, reason = self.decide(policy, board)
        self.assertEqual((key, reason), ("tc", "equipment-transaction:takeoff"))
        plan = policy._equipment_transaction_session.plan.actions
        self.assertEqual([(action.kind, action.target_slot) for action in plan],
                         [("takeoff", "bow"), ("equip", "bow"), ("deposit", None)])

        # DECLARED CONSTRUCTED: the take-off's effect, the Sling in the pack.
        taken = copy.deepcopy(board)
        taken["turn"] += 1
        sling = next(item for item in taken["equipment"] if item["tval"] == TVAL_BOW)
        taken["equipment"].remove(sling)
        index = next(index for index, item in enumerate(taken["inventory"]) if item["tval"] == TVAL_BOW)
        taken["inventory"].insert(index, sling)
        relettered(taken)
        letter = next(item["slot"] for item in taken["inventory"] if item["sval"] == 23)
        taken_board, key, reason = self.decide(policy, taken)
        self.assertEqual((key, reason), ("w" + letter, "equipment-transaction:equip"))

        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(taken)
        game.screen = executor_pins.command_screen(taken["turn"])
        worn = copy.deepcopy(taken)
        worn["turn"] += 10
        game.screens = [executor_pins.prompt_screen(WIELD_PROMPT),
                        executor_pins.command_screen(worn["turn"])]
        game.states = [copy.deepcopy(taken), worn]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": reason},
            snapshot=taken_board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, ["w", letter])

    def test_unseen_smith_is_visited_for_the_waiting_launcher(self):
        policy = self.policy(None)
        board = self.next_stay(943500)
        # DECLARED RECONSTRUCTED: a stay that has not seen the Smith's page.
        policy._in_store_attribute("_shelf_evidence").get("pages", {}).clear()
        policy._town_supplier_stock.clear()
        snapshot, _key, _reason = self.decide(policy, board)
        crossbow = next(item for item in snapshot.inventory if item.tval == TVAL_BOW)
        self.assertIs(launcher_upgrade.waiting_launcher(policy, snapshot), crossbow)
        self.assertFalse(spare_gear.released(policy, snapshot, crossbow))
        self.assertIn(launcher_upgrade.CATEGORY, policy._town_errand_plan.need_categories[STORE_WEAPON])

    def test_new_launcher_worn_empty_reopens_the_smith(self):
        policy = self.policy(None)
        sling_worn = self.next_stay(943500)
        sling_worn["inventory"] = [item for item in sling_worn["inventory"] if item["tval"] != TVAL_BOW]
        relettered(sling_worn)
        self.decide(policy, sling_worn)
        # DECLARED RECONSTRUCTED: this stay finished Home (the Sling shelved)
        # and the Smith (its page seen) before the crossbow was worn.
        for store_type in (STORE_HOME, STORE_WEAPON):
            policy._set_town_store_attempted(store_type, sling_worn["turn"], "recorded-plan")
        # DECLARED CONSTRUCTED: the crossbow worn, the Sling at Home.
        worn = copy.deepcopy(sling_worn)
        worn["equipment"] = [item for item in worn["equipment"] if item["tval"] != TVAL_BOW]
        worn["equipment"].insert(1, dict(self.crossbow(), slot="bow"))
        for turn in (943510, 943511):
            worn["turn"] = turn
            snapshot, key, reason = self.decide(policy, worn)
        self.assertNotIn(STORE_WEAPON, policy._town_store_attempted)
        self.assertIn(launcher_upgrade.CATEGORY, policy._town_errand_plan.need_categories[STORE_WEAPON])
        self.assertEqual(policy._count_matching_ammo(snapshot), 0)

        # DECLARED CONSTRUCTED: at the Smith's door, then its recorded page.
        page = self.boards["smith-page"]
        door = copy.deepcopy(worn)
        door["turn"] = 943570
        door["player"]["y"], door["player"]["x"] = page["player"]["y"], page["player"]["x"]
        self.decide(policy, door)
        inside = copy.deepcopy(door)
        inside["turn"] += 1
        inside["store"] = page["store"]
        inside["type"] = "store"
        bolts = next(item["letter"] for item in page["store"]["items"] if item["tval"] == 18)
        _snapshot, key, reason = self.decide(policy, inside)
        self.assertEqual((key, reason), ("p" + bolts + "99\r\r", "shop:in-store-buy"))


if __name__ == "__main__":
    unittest.main()
