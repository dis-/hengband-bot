"""Recorded pins (issue #66): the fundraising kit is routed to its supplier.

Live soak 2026-10-18 (c4-a life-013, Level 27, bot d102aaf8 = main 99c2fa87).

(a) 12:38 (capture 20261018-123828-town-blocked-shop-required-operation-
uncomposable): Home was full; fundraising mode None with 19,146 gold.  The
Home-full relief chose to withdraw and sell all 5 Treasure Detection scrolls
(``5pj5\\r\\x1b`` home-errand:atomic-withdraw:full-home-sale).  Treasure
Detection was protected only while mining was planned, although the scrolls
are the fundraising kit's requirement (``_mining_detection_scroll_target``).

(b) 14:01 (capture 20261018-140156-town-blocked-owner-retired-burst): the
fundraising prepare stage needed Treasure Detection 0/5.  Home held one
scroll, so the Alchemist ("fundraising-detection") was not a claim.  After
Home was closed by ``home:identify-staff-reserve-unavailable`` (row 44) and
Magic was visited (rows 45-49), no claim was left: 30 ``stuck:wander``
decisions, then ``town:blocked:owner-retired-burst``.

Substrate: the recorded raw state rows (only the windows below) replayed
through the public response path (``_consume_response_sequence``,
``choose_key``, ``confirm_key_posted``) on one fresh policy, with the live
argv flags (cross-area fundraising, in-store shop operations).

DECLARED CONSTRUCTED walls (the live process state before the capture windows
is not in the logs):
  both: the ``~f`` skill list of the same character (20261018-074006 state
  row 7) is consumed on every board.
  (a) planned depth 20 (as in tests/test_sale_inscribe_buy_recorded.py; it
  reproduces the captured Recall target 10).
  (b) on the first board: fundraising mode "prepare" (recorded on every row);
  the complete Home list of the same visit (state row 28 of the capture, turn
  1746652: one Treasure Detection scroll); planned depth 19 (the logged
  last over-extended depth; it reproduces the captured Recall target 9 and
  the logged departure_block.failed set); Home marked attempted
  ("identify-staff-reserve-terminal", recorded row 44); Magic marked
  attempted (the recorded Magic visit, rows 45-49).
Under these walls 99c2fa87 replays (b) a decision with no actionable claim
(``town:blocked:no-actionable-claim-owner``; live posted ``stuck:wander`` from
the same empty claim set).

Window (a) is kept as the measured substrate of the Home-full sale choice
(``test_captured_sale_rows``).  Its behaviour pin is not here: keeping the
kit's detection out of the Home-full sale changes the existing #67 pin
tests/test_sale_inscribe_buy_recorded.py (its 12:38 capture is that sale);
see LUNA-REPORT-fundraise-kit-route.txt.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import _parse_items
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import (
    MINING_RUNS_PER_SET, STORE_ALCHEMIST, STORE_HOME, STORE_MAGIC,
)
from hengbot.protocol import snapshot_protocol_version
from test_esp_threat_rest_recorded import EDIT, _policy
from test_supply_shortfall_owner_recorded import _segments

FIXTURE = Path(__file__).parent / "fixtures/fundraise-kit-route-20261018.json.gz"
SHA256 = "8f286015a59c866d8077983fe47639975eed1ba70adcd12fe71acfa0792eef2f"
ROUTE_PIN = 55


class FundraiseKitRouteRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.skill = json.loads(cls.pin["skill_line"])
        cls.home = json.loads(cls.pin["route_home_line"])
        assert cls.skill["knowledge"]["category"] == "skill_exp"
        assert cls.home["knowledge"]["category"] == "home"
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def replay(self, name, setup, stop):
        """Replay a window; return (policy, (key, reason) by row)."""
        window = self.pin[name]
        lines, decisions = window["lines"], window["decisions"]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        policy = _policy(root, self.monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        ledger = root / "knowledge.jsonl"
        primed = False
        previous = None
        results = {}
        for index, start, end in _segments(lines, decisions):
            recorded = decisions[index]
            segment = lines[start:end]
            if previous is not None and previous["key"]:
                row = json.loads(segment[-1])
                row["_completed_operation_sequence"] = previous["decision_sequence"]
                row["_completed_operation_owner"] = previous["reason"]
                segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
            _, boards = _consume_response_sequence(
                segment, policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=ledger)
            board = boards[-1]
            if not primed:
                primed = True
                policy.prime(board)
                setup(policy, board)
            policy.consume_skill_knowledge(
                {**self.skill, "player": {"level": board.player.level}})
            board = policy.with_known_skill_exp(board)
            self.board = board
            key = policy.choose_key(board)
            results[recorded["row"]] = (str(key), policy.last_reason)
            policy.confirm_key_posted(key)
            previous = recorded
            if recorded["row"] == stop:
                return policy, results
        raise AssertionError("replay end not reached")

    # (a) Home-full sale substrate ------------------------------------------

    def test_captured_sale_rows(self):
        window = self.pin["sale"]
        self.assertEqual(
            [(d["row"], d["key"], d["reason"]) for d in window["decisions"][-3:]],
            [(158, "~9\x1b\x1b", "home:request-knowledge-scan"),
             (159, "1", "home:request-knowledge-scan"),
             (160, "\x1b", "policy:none-store-exit")],
        )
        board = json.loads(window["lines"][-1])
        self.assertEqual(board["store"]["store_type"], STORE_HOME)
        self.assertEqual(board["player"]["gold"], 19146)

    # (b) fundraising prepare route -----------------------------------------

    def _route_walls(self, runs_completed=0):
        home = tuple(_parse_items(
            self.home["knowledge"]["items"],
            protocol=snapshot_protocol_version(self.home)))

        def setup(policy, board):
            policy._fundraising_mode = "prepare"
            policy.consume_home_knowledge(home)
            policy._equipment_optimization_last_depth = 19
            policy._set_town_store_attempted(
                STORE_HOME, board.turn, "identify-staff-reserve-terminal")
            policy._set_town_store_attempted(STORE_MAGIC, board.turn, "visited")
            policy._mining_runs_completed = runs_completed
        return setup

    def test_captured_route_rows(self):
        window = self.pin["route"]
        self.assertEqual(
            [(d["row"], d["key"], d["reason"]) for d in window["decisions"]],
            [(55, "7", "stuck:wander"), (56, "4", "stuck:wander")],
        )
        detection = [item["count"] for item in self.home["knowledge"]["items"]
                     if item["tval"] == 70 and item["sval"] == 26]
        self.assertEqual(detection, [1])

    def test_prepare_routes_missing_detection_to_the_alchemist(self):
        policy, results = self.replay("route", self._route_walls(), ROUTE_PIN)
        requirements = {
            entry["item"]: (entry["current"], entry["target"])
            for entry in policy.procurement_requirements(self.board)
        }
        # The captured shortfalls (decision rows): Recall 7/9, detection 0/5.
        self.assertEqual(requirements["Word of Recall scrolls"], (7, 9))
        self.assertEqual(requirements["Treasure Detection scrolls"], (0, 5))
        # 99c2fa87: ("5", "town:blocked:no-actionable-claim-owner") -- no
        # claim; live posted stuck:wander.
        self.assertEqual(results[ROUTE_PIN][:2], ("\x1b`n%.", "shop:travel"))
        plan = policy._town_errand_plan
        self.assertIn(STORE_ALCHEMIST, plan.stops)
        self.assertEqual(plan.need_categories[STORE_ALCHEMIST],
                         ("fundraising-detection",))

    def test_control_home_covering_the_requirement_adds_no_supplier(self):
        # Control (constructed): with four of the five runs completed the kit
        # needs one scroll, which Home holds; no Alchemist claim is added
        # and the closed Home leaves no route, as on 99c2fa87.
        _, results = self.replay(
            "route", self._route_walls(MINING_RUNS_PER_SET - 1), ROUTE_PIN)
        self.assertEqual(
            results[ROUTE_PIN][:2],
            ("5", "town:blocked:no-actionable-claim-owner"))


if __name__ == "__main__":
    unittest.main()
