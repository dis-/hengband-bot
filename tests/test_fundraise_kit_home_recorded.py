"""Recorded pin (issue #64): the fundraising kit at Home is withdrawn.

Live soak 2026-10-18 09:15 (c4-a, capture
20261018-091516-town-blocked-owner-retired-burst): a Level 22 character with
2,134 gold was preparing the gold-triggered fundraising (Treasure Detection
0/5, digging tool 0/2).  Home held the kit (4 Treasure Detection scrolls and
two shovels), so the plan was Home only ("fundraising-kit", home-first).
Every Home page ended in ``home:identify-staff-reserve-unavailable``: Home was
left and marked attempted without withdrawing the kit, the plan was
exhausted, the bot wandered, came back (decision row 92) and stopped in
``owner-retired-burst``.

Substrate: the recorded state rows (tests/extract_fundraise_kit_poor_fixture.py)
replayed through the public response path on one policy from decision row 91
(``\\x1b`n(.`` travel to Home) to row 93 (the outside board after the Home
page).  DECLARED WALLS (constructed context; the live process state before the
capture window is not in the logs): (1) the ``~f`` skill list and (2) the
complete Home list of the same character from earlier captures, as in
tests/test_supply_shortfall_owner_recorded.py; (3) ONE wall for the live Home
visit state on the Home page: the filed visit request is a DEPOSIT (both live
kit visits followed an equipment-transaction deposit at Home), which refuses
the ordinary catalogue binder.  Under these walls 37f66a8c posts the recorded
``\\x1b`` home:identify-staff-reserve-unavailable on row 92; the replay starts
with a fresh town plan, so row 91 posts the recorded key under the reason
``shop:travel`` (the live repetition state is not reconstructed).
"""

import tests  # noqa: F401 -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.home_visit import HomeVisitKind, HomeVisitRequest
from hengbot.model import _parse_items
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STORE_HOME
from hengbot.protocol import snapshot_protocol_version
from test_esp_threat_rest_recorded import EDIT, _policy
from test_supply_shortfall_owner_recorded import _segments

FIXTURE = Path(__file__).parent / "fixtures/fundraise-kit-poor-20261018.json.gz"
SHA256 = "2946264183960f7193e5914e9c7f81489682a26c0cdd67a467d9d54252e5e924"
START, PIN, AFTER = 91, 92, 93
DETECTION = ("財宝感知の巻物", 70, 26)
SHOVEL = ("シャベル (1d2) (+0,+0) (+1) {+掘}", 20, 1)


class FundraiseKitHomeRecordedTest(unittest.TestCase):
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

    def _home_items(self):
        return tuple(_parse_items(
            self.home["knowledge"]["items"],
            protocol=snapshot_protocol_version(self.home)))

    def replay(self, at_pin=None):
        """Replay rows START..AFTER; return (policy, results by row)."""
        lines, decisions = self.pin["lines"], self.pin["decisions"]
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
            if index < START:
                continue
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
                policy.consume_home_knowledge(self._home_items())  # Wall (2).
            policy.consume_skill_knowledge(  # Wall (1).
                {**self.skill, "player": {"level": board.player.level}})
            board = policy.with_known_skill_exp(board)
            if index == PIN:
                # Wall (3): the filed Home visit request is a deposit.
                deposited = policy._item_signature(policy._home_knowledge_items[0])
                policy._home_visit.request = HomeVisitRequest(
                    HomeVisitKind.DEPOSIT, "equipment-transaction",
                    item_identity=deposited)
                if at_pin is not None:
                    at_pin(policy)
            key = policy.choose_key(board)
            results[recorded["row"]] = (
                str(key), policy.last_reason, recorded["key"], recorded["reason"])
            policy.confirm_key_posted(key)
            previous = recorded
            if index == AFTER:
                return policy, results
        raise AssertionError("replay end not reached")

    def test_captured_rows(self):
        decisions = self.pin["decisions"]
        self.assertEqual(
            [(d["row"], d["key"], d["reason"]) for d in decisions[START:AFTER + 1]],
            [(91, "\x1b`n(.", "town:repetition-required-shopping"),
             (92, "\x1b", "home:identify-staff-reserve-unavailable"),
             (93, "9", "town:blocked:repetition")],
        )
        kit = {self._signature(item): item.count for item in self._home_items()
               if self._signature(item) in {DETECTION, SHOVEL}}
        self.assertEqual(kit, {DETECTION: 4, SHOVEL: 2})

    @staticmethod
    def _signature(item):
        return (item.name, item.tval, item.sval)

    def test_home_page_binds_the_fundraising_kit_before_closing(self):
        policy, results = self.replay()
        # Row 91: recorded key, reason from the fresh plan (see docstring).
        self.assertEqual(results[91][:2], ("\x1b`n(.", "shop:travel"))
        # 37f66a8c: ("\x1b", "home:identify-staff-reserve-unavailable"),
        # Home marked attempted and the Home-only plan exhausted.
        self.assertEqual(results[92][:2], ("\x1b", "home:queue-catalogue-shortage"))
        # 37f66a8c: ("9", "town:blocked:no-actionable-claim-owner").
        self.assertEqual(results[93][:2], ("5pn4\r\x1b", "home:atomic-withdraw"))
        self.assertNotIn(STORE_HOME, policy._town_store_attempted)
        self.assertEqual(policy._home_pending_batch, [SHOVEL])

    def test_control_without_a_home_kit_the_terminal_still_closes_home(self):
        # Control (constructed): with the Home kit deferred for this stay on
        # the pinned page (no Home shortage it can supply), the identify-staff
        # terminal closes Home exactly as recorded.
        def defer_kit(policy):
            policy._deferred_home_items.update({DETECTION, SHOVEL})

        policy, results = self.replay(at_pin=defer_kit)
        self.assertEqual(
            results[92][:2], ("\x1b", "home:identify-staff-reserve-unavailable"))
        self.assertIn(STORE_HOME, policy._town_store_attempted)
        self.assertIsNone(policy._home_pending_item)


if __name__ == "__main__":
    unittest.main()
