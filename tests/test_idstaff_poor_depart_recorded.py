"""Recorded pin (issue #76): a remembered Magic page must not hard-stop town.

Live soak 2026-10-19 08:04 (c4-a life-014, Level 22, bot 35b1cf2d, capture
20261019-080433-town-blocked-departure-unsatisfiable): gold-triggered
fundraising prepare, 2,708 gold after three sales, Identify staff charges
13/20, departure_block.failed ``["identify_staff_ready"]`` only.  Decision row
150 posted ``("1", "town:blocked:departure-unsatisfiable")`` and the A0
keep-running fallback printed ``hard_stop ... method=none``.  The Magic Shop
page of the same stay (state row 28, turn 658699) offered an 18-charge staff
for 936 gold; the purchase was ``preempted`` (decision row 97) and Magic was
not routed again.

Substrate: the recorded raw state rows of decision row 150
(tests/extract_idstaff_poor_depart_fixture.py) replayed through the public
response path (``_consume_response_sequence``, ``choose_key``) on one fresh
policy, with the live argv flags (cross-area fundraising, in-store shop
operations), the recorded ``~f`` skill list (state row 10) and the recorded
complete Home list (state row 79, turn 659988).

DECLARED CONSTRUCTED walls (the live process state before the window is not
replayable): fundraising mode "prepare" (recorded on the row); the stay's
store-attempted latches for Home, Magic Shop and Black Market (constructed:
Home 9 and Magic 1 visits are in the recorded ledger; the plan dropped Black
Market at decision row 109 without a visit); the recorded Magic page of state
row 28 held as remembered supplier stock without this town's observation
provenance (constructed: provenance is not logged).  Under these walls
35b1cf2d replays the recorded ``("1", "town:blocked:departure-unsatisfiable")``
on row 150.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import (
    SV_STAFF_IDENTIFY, STORE_BLACK, STORE_HOME, STORE_MAGIC, TVAL_STAFF,
    _parse_items, parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.protocol import snapshot_protocol_version
from test_esp_threat_rest_recorded import EDIT, _policy
from test_supply_shortfall_owner_recorded import _segments

FIXTURE = Path(__file__).parent / "fixtures/idstaff-poor-depart-20261019.json.gz"
SHA256 = "ae7249a2196a70db3a2801be24b6c9a5be61ad59041b86811e80e59c188912eb"
PIN = 150


class IdstaffPoorDepartRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = FIXTURE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == SHA256
        cls.pin = json.loads(gzip.decompress(raw))
        cls.skill = json.loads(cls.pin["skill_line"])
        cls.home = json.loads(cls.pin["home_line"])
        assert cls.skill["knowledge"]["category"] == "skill_exp"
        assert cls.home["knowledge"]["category"] == "home"
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.magic = parse_snapshot(
            json.loads(cls.pin["magic_line"]), cls.monrace).store

    def replay(self, attempted):
        """Replay the board of PIN; return (policy, (key, reason))."""
        lines, decisions = self.pin["lines"], self.pin["decisions"]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        policy = _policy(root, self.monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
        home = tuple(_parse_items(
            self.home["knowledge"]["items"],
            protocol=snapshot_protocol_version(self.home)))
        for index, start, end in _segments(lines, decisions):
            if decisions[index]["row"] != PIN:
                continue
            _, boards = _consume_response_sequence(
                lines[start:end], policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=root / "knowledge.jsonl")
            board = boards[-1]
            policy.prime(board)
            policy._fundraising_mode = "prepare"
            policy.consume_home_knowledge(home)
            for store_type in attempted:
                policy._set_town_store_attempted(store_type, board.turn, "visited")
            policy._town_supplier_stock[STORE_MAGIC] = self.magic
            policy.consume_skill_knowledge(
                {**self.skill, "player": {"level": board.player.level}})
            board = policy.with_known_skill_exp(board)
            key = policy.choose_key(board)
            return policy, (str(key), policy.last_reason)
        raise AssertionError("pinned row not reached")

    def test_captured_rows(self):
        self.assertEqual(
            [(d["row"], d["key"], d["reason"]) for d in self.pin["decisions"][-3:]],
            [(148, "\x13", "periodic:game-save"),
             (149, "Cf\ry\x1b\x1b", "periodic:character-dump"),
             (150, "1", "town:blocked:departure-unsatisfiable")],
        )
        recorded = self.pin["recorded"]
        self.assertEqual(recorded["departure_block"]["failed"],
                         ["identify_staff_ready"])
        self.assertEqual(recorded["fundraising"]["mode"], "prepare")
        self.assertTrue(recorded["fundraising"]["gold_trigger"])
        self.assertEqual(recorded["player"]["gold"], 2708)
        staves = [(item.charges, item.price) for item in self.magic.items
                  if item.tval == TVAL_STAFF and item.sval == SV_STAFF_IDENTIFY]
        self.assertEqual(staves, [(18, 936), (14, 873)])

    def test_unrouted_remembered_page_starts_the_stockout_mining_run(self):
        policy, result = self.replay((STORE_HOME, STORE_MAGIC, STORE_BLACK))
        # 35b1cf2d: ("1", "town:blocked:departure-unsatisfiable") -- the
        # remembered 936-gold page kept procurement "possible" while no
        # identify-staff need routed to it, so no owner was left.
        self.assertIsNone(policy._town_blocked_reason)
        self.assertTrue(policy._identify_staff_mining_plan)
        self.assertEqual(policy._planned_mining_runs, 1)
        self.assertEqual(policy._fundraising_mode, "prepare")
        # The one-run time-pass re-arms the suppliers: Magic is retried first.
        self.assertEqual(result, ("\x1b`n&.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_MAGIC)

    def test_control_unlatched_magic_still_buys_the_staff(self):
        # Control (constructed): with Magic not yet attempted this stay the
        # ordinary identify-staff need routes to the Magic Shop; no stockout
        # mining run is installed.
        policy, result = self.replay((STORE_HOME, STORE_BLACK))
        self.assertEqual(result, ("\x1b`n&.", "shop:travel"))
        self.assertEqual(policy._town_errand_plan.need_categories,
                         {STORE_MAGIC: ("identify-staff",)})
        self.assertFalse(policy._identify_staff_mining_plan)
        self.assertIsNone(policy._planned_mining_runs)


if __name__ == "__main__":
    unittest.main()
