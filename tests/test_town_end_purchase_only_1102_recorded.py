"""town-end-purchase-only-1102: the n1-c life-107 town end (2026-11-02 18:38).

n1-c life-107 (Magic-Eater Lv15, 7,974 gold) restarted at 18:38:33 on the
save of turn 949749 standing on the Alchemist entrance, walked to the Black
Market, saw nothing it wanted and left (decisions 5-6).  On the Black Market
entrance (turn 949982, decision 7) the departure failed only
equipment_departure_ready and home_catalog_ready: the new process had not
read the Home list.  Its reader, the outside ``~9`` (policy ``_choose_key``),
is refused on a store entrance (it keeps the entrance's input ownership), so
on that board nobody answered for the list; the departure judgement
(``_town_special_key`` -> departure-unsatisfiable -> ``force_visit_departure``)
closed the visit and started the town end's mining cycle.  The list was read
two boards later, at the dungeon entrance, with the cycle already open
(decision 9), and the run mined Yeek Cave 1F out.

B. The Home list is read before the departure judgement: a visit closing on
a store entrance while the list is still owed steps off the entrance, and
the next board reads the list.

Fixture: tests/fixtures/town-end-purchase-only-1102.json.gz
(tests/extract_town_end_purchase_only_1102_fixture.py).  Every decision is
the public ``choose_key``; walking keys go through the production executor
port.
DECLARED RECONSTRUCTED: the process restarted on the first board (prime,
the recorded skill row); the staff sequence record (no checkpoint survived)
has every sequence staff and the two carried wands absorbed, stage complete,
which reproduces the recorded decision 5 (shop:travel to the Black Market);
the visit ledger's store visits and need attempts are decision 7's
``departure_block.town_ledger`` and the Black Market is latched as attempted
(decision 6, shelf evidence).
DECLARED CONSTRUCTED: the executor's board after a step is the recorded
board with the player on the stepped cell, ten game turns later; the reply to
``~9`` is the Home row the recorded process read at turn 950629.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path

from hengbot import me_capability, me_staff_sequence, town_end_mining
from hengbot.model import _parse_items, parse_snapshot
from tests import test_d57_nav_depth_1101_recorded as nav
from tests import test_me_staff_loops_1031_recorded as loops
from tests.test_surface_map_walks import _town_maps


FIXTURE = Path(__file__).with_name("fixtures") / "town-end-purchase-only-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
RESTART = CASE["boards"][0]
# The board after the Black Market page: the player on its entrance.
ENTRANCE = next(board for board in CASE["boards"]
                if board["turn"] == 949982 and board["type"] == "player_turn")
BLACK_MARKET = 6
CARRIED_WANDS = ("wand:6", "wand:8")


def recorded(sequence):
    return next(row for row in CASE["decisions"] if row["decision_sequence"] == sequence)


def new_policy():
    policy = loops.new_policy(dict(boards=[RESTART]), CASE["skill"], monraces={})
    record = me_staff_sequence.state(policy)
    for sval in me_staff_sequence.SEQUENCE_SVALS:
        record.absorbed[me_capability.record_key("staff", sval)] = 1
    record.absorbed.update(dict.fromkeys(CARRIED_WANDS, 1))
    record.stage = len(me_staff_sequence.STAGES) + 1
    policy._town_maps = _town_maps()
    policy._town_map = policy._town_maps[0]
    return policy


def board_of(policy, raw):
    return parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)


class HomeListBeforeDepartureTest(nav.RecordedDrive):
    def test_recorded_rows_mined_before_the_home_list(self):
        self.assertEqual(recorded(5)["reason"], "shop:travel")
        self.assertEqual(recorded(6)["reason"], "shop:observe-and-leave")
        block = recorded(7)["departure_block"]
        self.assertEqual(block["failed"], ["equipment_departure_ready", "home_catalog_ready"])
        self.assertEqual(block["town_claims"], [])
        self.assertEqual(recorded(8)["fundraising"]["mode"], "mine")
        self.assertEqual(recorded(9)["reason"], "home:request-knowledge-scan")
        self.assertEqual(CASE["cycle"]["unmet"], ["equipment_departure_ready", "home_catalog_ready"])

    def test_restart_board_routes_as_recorded(self):
        policy = new_policy()
        self.assertEqual(str(policy.choose_key(board_of(policy, RESTART))), recorded(5)["key"])
        self.assertEqual(policy.last_reason, "shop:travel")

    def test_home_list_is_read_before_the_departure_judgement(self):
        policy = new_policy()
        ledger = recorded(7)["departure_block"]["town_ledger"]
        policy._town_visit_ledger.store_visits.update(
            {int(store): count for store, count in ledger["store_visits"].items()})
        policy._town_visit_ledger.need_attempts.update(ledger["need_attempts"])
        policy._set_town_store_attempted(BLACK_MARKET, ENTRANCE["turn"] - 9, "shelf-evidence")
        board = board_of(policy, ENTRANCE)
        self.assertIn("home_catalog_ready", policy._departure_block_state(board)["failed"])
        key = str(policy.choose_key(board))
        # Not the town end's mining cycle: the visit steps off the entrance.
        self.assertEqual(policy.last_reason, "town:entrance-step-off:town:end-step-off")
        self.assertIsNone(policy._fundraising_mode)
        self.assertFalse(town_end_mining.outstanding(policy))
        position = nav.step_of(ENTRANCE, key)
        self.assertIsNotNone(position, key)
        following = copy.deepcopy(ENTRANCE)
        following.update(turn=ENTRANCE["turn"] + 10, messages=[])
        following["player"].update(y=position.y, x=position.x)
        self.send(policy, ENTRANCE, key, following, {})
        policy.confirm_key_posted(key)
        board = board_of(policy, following)
        self.assertEqual(str(policy.choose_key(board)), "~9\x1b\x1b")
        self.assertEqual(policy.last_reason, "home:request-knowledge-scan")
        policy.consume_home_knowledge(
            tuple(_parse_items(CASE["home"]["knowledge"]["items"], protocol=3)))
        # With the list read the departure has nothing unmet: no mining.
        self.assertEqual(policy._departure_block_state(board)["failed"], [])
        policy.choose_key(board)
        self.assertNotEqual(policy.last_reason, town_end_mining.START_REASON)
        self.assertIsNone(policy._fundraising_mode)


if __name__ == "__main__":
    unittest.main()
