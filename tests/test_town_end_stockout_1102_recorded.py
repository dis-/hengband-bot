"""town-end-stockout-1102: a store stockout is a purchase gap (2026-11-02 21:11/21:14).

Owner 2026-11-02 「品切れも採掘に回す」: a departure supply that is short, not
in Home, and not buyable because every store known to sell it is out of it
this visit (or sells it above the gold) is a purchase gap, so the town end
runs its one mining cycle (store time passes for a restock) instead of
stopping.  A supplier not yet visited this visit is visited first.

n1-c life-109 (Magic-Eater Lv16) came back from its Yeek Cave 1F mining run
at 21:11 one Cure Critical Wounds potion short of the departure's ten and
stopped two boards later under town:blocked:survival:cure_critical_ready
without entering a store: the Temple and Alchemist pages remembered from the
visit before the run made the supply ledger read both suppliers as empty
(procurement_requirements: blocked_reason no-actionable-supplier).

n1-a life-464 (Warrior Lv42) came back from its Identify-staff stockout run
at 21:14 with four 2-charge Identify staves (8 of the 20 charges a 10F+
departure needs; the four-staff cap of 2026-10-03 holds), saw the Magic shop
sell only 1- and 2-charge staves, and stopped under
town:blocked:survival:identify_staff_ready.  The requirement applies to every
class at 10F+ (STAFF_IDENTIFY_MIN_DEPTH); no shelf staff could raise the
charges, which is a stockout of a staff that helps.

Fixture: tests/fixtures/town-end-stockout-1102.json.gz
(tests/extract_town_end_stockout_1102_fixture.py).
DECLARED CONSTRUCTED: n1-c's remembered Temple/Alchemist pages before the
run (empty of the potion; the capture does not hold the earlier visit), the
same stores seen this visit without the potion for the stockout test, and an
empty Home list (n1-c's capture holds no Home row); n1-a's Black Market
attempted this visit.
DECLARED RECONSTRUCTED: n1-c's staff sequence complete with every sequence
staff absorbed (the recorded departure had identify_staff_ready true) and its
mining set ended on the return (the recorded decision 1603 has
fundraising.mode null); n1-a's visit attempts are its recorded Magic and
Alchemist pages.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_capability, me_staff_sequence, town_end_mining, town_terminal
from hengbot.model import StoreState, _parse_items, parse_snapshot
from hengbot.policy import ConservativePolicy
from hengbot.quest_strategies import load_quest_strategies


FIXTURE = Path(__file__).with_name("fixtures") / "town-end-stockout-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
STRATEGIES = Path(__file__).parents[1] / "strategy" / "quests"
TEMPLE, ALCHEMIST, BLACK_MARKET = 3, 4, 6
CURE_SUPPLIERS = (TEMPLE, ALCHEMIST)


def new_policy(first, skill):
    policy = ConservativePolicy(quest_strategies=load_quest_strategies(STRATEGIES))
    policy.prime(parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(skill), turn=first["turn"],
        player=dict(skill["player"], level=first["player"]["level"])))
    return policy


def board_of(policy, raw):
    return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)


def see_page(policy, board, page, turn):
    """The visit saw ``page`` (an attempted store with its observed shelf)."""
    policy._town_supplier_stock[page.store_type] = page
    policy._town_supplier_stock_observations[page.store_type] = (
        policy._effective_town_id(board), turn)
    policy._set_town_store_attempted(page.store_type, turn, "visited")


class N1cCureStockoutTest(unittest.TestCase):
    def arrive(self):
        """Climb out of the 1F run with the earlier visit's pages remembered."""
        case = CASE["n1c"]
        policy = new_policy(case["dungeon"], case["skill"])
        policy._fundraising_mode, policy._planned_mining_runs = "mine", 1
        policy._mining_runs_completed = 0
        for store in CURE_SUPPLIERS:
            policy._town_supplier_stock[store] = StoreState(store_type=store, items=[])
            policy._town_supplier_stock_observations[store] = (0, case["dungeon"]["turn"] - 5000)
        arrival = board_of(policy, case["arrival"])
        policy.confirm_key_posted(policy.choose_key(arrival))
        return policy, arrival

    def test_stockout_at_every_supplier_starts_the_mining_cycle(self):
        policy, _arrival = self.arrive()
        policy.consume_home_knowledge(())
        record = me_staff_sequence.state(policy)
        for sval in me_staff_sequence.SEQUENCE_SVALS:
            record.absorbed[me_capability.record_key("staff", sval)] = 1
        record.stage = len(me_staff_sequence.STAGES) + 1
        policy._fundraising_mode = None
        stop = CASE["n1c"]["stop"]
        board = board_of(policy, stop)
        for store in CURE_SUPPLIERS:
            see_page(policy, board, StoreState(store_type=store, items=[]), stop["turn"] - 50)
        self.assertEqual(policy._departure_block_state(board)["failed"], ["cure_critical_ready"])
        material = town_terminal.gather_town_end(policy, board)
        self.assertEqual(material.purchase_gaps, ("cure_critical_ready",))
        self.assertEqual(town_terminal.verdict_town_end(material).kind, "mine")
        town_terminal.town_end_key(policy, board)
        # Not town:blocked:survival:cure_critical_ready: one mining cycle.
        self.assertEqual(policy.last_reason, town_end_mining.START_REASON)
        self.assertTrue(town_end_mining.outstanding(policy))


class N1aIdentifyStaffStockoutTest(unittest.TestCase):
    def setUp(self):
        case = CASE["n1a"]
        self.policy = policy = new_policy(case["stop"], case["skill"])
        policy.consume_home_knowledge(
            tuple(_parse_items(case["home"]["knowledge"]["items"], protocol=3)))
        self.board = board_of(policy, case["stop"])
        for name in ("magic", "alchemist"):
            see_page(policy, self.board, board_of(policy, case[name]).store, case[name]["turn"])

    def test_unvisited_black_market_is_visited_first(self):
        policy, board = self.policy, self.board
        self.assertEqual(policy._departure_block_state(board)["failed"], ["identify_staff_ready"])
        self.assertNotIn("identify_staff_ready",
                         town_terminal.gather_town_end(policy, board).purchase_gaps)
        self.assertEqual(str(policy.choose_key(board)), "\x1b`n'.")
        self.assertEqual(policy.last_reason, "shop:travel")

    def test_low_charge_shelves_everywhere_are_a_purchase_gap(self):
        policy, board = self.policy, self.board
        policy._set_town_store_attempted(BLACK_MARKET, board.turn - 9, "visited")
        material = town_terminal.gather_town_end(policy, board)
        self.assertIn("identify_staff_ready", material.purchase_gaps)
        self.assertNotIn("identify_staff_ready", town_terminal.verdict_town_end(material).conditions)


if __name__ == "__main__":
    unittest.main()
