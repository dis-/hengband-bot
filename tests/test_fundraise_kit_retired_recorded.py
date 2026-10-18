"""Recorded pin (issue #66 recurrence): a retired Home kit route is bought.

Live soak 2026-10-19 00:19-00:50 (c4-a life-013, Level 28, bot c38ec348,
capture 20261019-0050-manual-town-wander): gold-triggered fundraising
prepare (``kit_secured`` false, Treasure Detection 0/5 in the pack) with
Home holding 7 Treasure Detection scrolls (state row 112).  Five Home passes
of the same stay counted ``fundraising-kit`` (town ledger need_attempts 5,
the pass budget is 3) without withdrawing the scrolls, so the claim ledger
retired the Home kit route.  The plan stayed ``["Home"]`` with no live claim
and the Alchemist was never named because Home "held" enough detection:
228 ``stuck:wander`` decisions in 31 minutes, at 1,587 gold while the
Alchemist sold Treasure Detection for 23 gold.

Substrate: the recorded raw state rows of decision rows 2547-2548
(tests/extract_fundraise_kit_retired_fixture.py) replayed through the public
response path (``_consume_response_sequence``, ``choose_key``,
``confirm_key_posted``) on one fresh policy, with the live argv flags
(cross-area fundraising, in-store shop operations).

DECLARED CONSTRUCTED walls (the live process state before the window is not
replayable; the values are the recorded ones of the same capture): on the
first board, fundraising mode "prepare" (recorded on the row), the complete
Home list (state row 112, turn 2945295) and the ``~f`` skill list (state
row 1); the recorded need_attempts of the town ledger (decision row 2544,
the last row before 2547 that logs it).  Under these walls af25b541 replays
the recorded ``("1", "stuck:wander")`` on row 2547.
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import STORE_ALCHEMIST, STORE_HOME, _parse_items
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.protocol import snapshot_protocol_version
from test_esp_threat_rest_recorded import EDIT, _policy
from test_supply_shortfall_owner_recorded import _segments

FIXTURE = Path(__file__).parent / "fixtures/fundraise-kit-retired-20261019.json.gz"
SHA256 = "0733517ead8587c8f20deee080d80477f872d5e540e4277654405730fea8d2db"
PIN = 2547


class FundraiseKitRetiredRecordedTest(unittest.TestCase):
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

    def replay(self, ledger_wall=True):
        """Replay the window to PIN; return (policy, (key, reason))."""
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
            _, boards = _consume_response_sequence(
                lines[start:end], policy, lambda _key: True, self.monrace,
                knowledge_ledger_path=root / "knowledge.jsonl")
            board = boards[-1]
            policy.prime(board)
            policy._fundraising_mode = "prepare"
            policy.consume_home_knowledge(home)
            if ledger_wall:
                policy._town_visit_ledger.need_attempts.update(
                    self.pin["ledger"]["need_attempts"])
            policy.consume_skill_knowledge(
                {**self.skill, "player": {"level": board.player.level}})
            board = policy.with_known_skill_exp(board)
            key = policy.choose_key(board)
            self.assertEqual(decisions[index]["row"], PIN)
            return policy, (str(key), policy.last_reason)
        raise AssertionError("pinned row not reached")

    def test_captured_rows(self):
        self.assertEqual(
            [(d["row"], d["key"], d["reason"]) for d in self.pin["decisions"]],
            [(2547, "1", "stuck:wander"), (2548, "4", "stuck:wander")],
        )
        recorded = self.pin["recorded"]
        self.assertEqual(recorded["fundraising"]["mode"], "prepare")
        self.assertFalse(recorded["fundraising"]["kit_secured"])
        self.assertEqual(recorded["town_plan"]["stops"], ["Home"])
        self.assertEqual(recorded["departure_block"]["town_claims"], [])
        self.assertEqual(recorded["player"]["gold"], 1587)
        self.assertEqual(self.pin["ledger"]["need_attempts"]["fundraising-kit"], 5)
        detection = [item["count"] for item in self.home["knowledge"]["items"]
                     if item["tval"] == 70 and item["sval"] == 26]
        self.assertEqual(detection, [7])

    def test_retired_home_kit_route_travels_to_the_alchemist(self):
        policy, result = self.replay()
        # af25b541: ("1", "stuck:wander") -- Home-only plan, no live claim.
        self.assertEqual(result, ("\x1b`n%.", "shop:travel"))
        plan = policy._town_errand_plan
        self.assertEqual(plan.stops, [STORE_ALCHEMIST])
        self.assertEqual(plan.need_categories,
                         {STORE_ALCHEMIST: ("fundraising-detection",)})

    def test_control_live_home_kit_route_stays_home_first(self):
        # Control (constructed): with a fresh ledger the Home kit route is
        # live, so the 7 scrolls at Home are withdrawn first and no
        # Alchemist purchase is planned.
        policy, result = self.replay(ledger_wall=False)
        self.assertEqual(result, ("\x1b`n(.", "shop:travel"))
        plan = policy._town_errand_plan
        self.assertEqual(plan.stops, [STORE_HOME])
        self.assertNotIn(STORE_ALCHEMIST, plan.stops)


if __name__ == "__main__":
    unittest.main()
