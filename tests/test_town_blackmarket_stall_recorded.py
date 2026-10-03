"""Recorded pin: the town router and the departure seam read one departure verdict.

Live stops 2026-10-02 17:00:27, 17:01:07 and 17:01:48
(``town:blocked:owner-retired``; commit 35a18252,
``--enforce-crossarea-fundraising``, S3.3 switch off).  The 17:01:12 process
of the 17:01:48 stop is frozen by tests/extract_town_blackmarket_stall_fixture.py:

- 0..3: knowledge request, Home knowledge scan, approach and observe-and-leave
  of store 6 (Black Market); the plan ``[Black Market]`` is then complete.
- 4..6: ``town:blocked:no-actionable-claim-owner``; 7: ``owner-retired``.
  The records carry no ``departure_block``.

Mechanism (replayed below, production code): Home holds 鑑定の巻物, so
policy_observation.py ``_observe`` re-derives ``_home_candidate_waiting``
True on every in-town board (policy_home.py
``_home_identification_candidate_pending``: ``known_source``), with no
candidate, need or pending Home item.  In ``_decide`` the town claim registry
(``_town_claims_active``) then sees departure NOT ready
(``home_candidate_resolved`` False), so the optional ``launcher-enchant``
claim (ライト・クロスボウ (+7,+9), both enchant svals wanted) is not
registered and the router has no stop.  The departure seam
(``_town_special_key``) first releases the stale latch
(``_release_stale_home_candidate_waiting``), so there departure IS ready, the
same registry now keeps ``launcher-enchant`` active, and the unsafe-Angband
branch (landing 21 needs resist_conf; no alternate landing) returns None
because a claim is active.  Nobody owns the decision.

Fix: when the stale latch is the only failing departure leaf, release it
before the router's claim evaluation as well, so both seams read the same
verdict.  With another leaf failing both seams already read "not ready" and
the latch is left as it was (tests/test_oneshot_preempt_recorded.py board 8
keeps its live Home step-off).  Board 4 then routes to the Alchemist
(store 4, ``%``) for the live claim.  That key differs from live, so no
later board is the effect of the fixed key (R4); the pin stops at 4.
The fix pin runs under the recorded five-staff Identify cap
(tests/identify_staff_cap_walls.py); the 2026-10-03 four-staff cap's first
changed key on this board (index 2) is pinned unwalled in
IdentifyStaffCapDivergenceTest.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.model import STORE_ALCHEMIST, STORE_BLACK, STORE_MAGIC, TVAL_SCROLL
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS

from test_esp_threat_rest_recorded import EDIT, _policy
from identify_staff_cap_walls import pre_four_staff_cap_rule

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "town-blackmarket-stall-20261002.jsonl.gz"
BOUNDARIES = FIXTURES / "town-blackmarket-stall-20261002.boundaries.json"
CALIBRATION = FIXTURES / "town-blackmarket-stall-20261002.character-calibration.json"
SHA256 = {
    FIXTURE: "28e85c0ef9d52cdfd76dc2c8d99ceefe28484a520925e69e44f23db9cc74cd36",
    BOUNDARIES: "bd70eb5ace54e75aa4748dcba1857861c9318d2e9221c5b2e927b8936af1e96e",
    CALIBRATION: "78ba2af16831a9a9211784eacedc74599c53de6a9dfffe68dbb5f7ae88af6220",
}
BLACK_MARKET_LEAVE = 3
FIRST_NO_OWNER = 4
STOP = 7


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


class TownBlackMarketStallRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        cls.detail = boundaries["detail"]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            lines = stream.read().splitlines(keepends=True)
        assert len(lines) == sum(boundaries["input_rows"])
        cls.segments = []
        start = 0
        for count in boundaries["input_rows"]:
            cls.segments.append(lines[start:start + count])
            start += count
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _replay(self, last, *, inspect=None):
        rows = []
        with TemporaryDirectory() as raw:
            directory = Path(raw)
            policy = _policy(directory, self.monrace)
            policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
            policy._crossarea_fundraising_enforced = True  # live argv
            for index in range(last + 1):
                _decoded, snapshots = _consume_response_sequence(
                    self.segments[index], policy, lambda _key: True, self.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                board = snapshots[-1]
                key = policy.choose_key(board)
                rows.append((str(key), policy.last_reason))
                if inspect is not None:
                    inspect(index, policy, board)
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain(
                        {"outcome": "released", "posted": str(key)})
        return rows

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]

    # ------------------------------------------------------------ recorded
    def test_recorded_process_ends_without_an_owner(self):
        # R1: the travel symbol names the store the fix routes to.
        self.assertEqual(TOWN_TRAVEL_STORE_SYMBOLS[STORE_ALCHEMIST], "%")
        self.assertEqual(self.detail[str(BLACK_MARKET_LEAVE)]["store_type"], STORE_BLACK)
        self.assertEqual(self._live(BLACK_MARKET_LEAVE),
                         ("\x1b", "shop:observe-and-leave"))
        for index in range(FIRST_NO_OWNER, STOP):
            self.assertEqual(self._live(index)[1],
                             "town:blocked:no-actionable-claim-owner", index)
        self.assertEqual(self._live(STOP), ("5", "town:blocked:owner-retired"))
        self.assertEqual(self.detail[str(STOP)]["procurement_requirements"], [])

    # ------------------------------------------------------------ fix
    @pre_four_staff_cap_rule()  # declared wall: recorded five-staff cap, 「鑑定の杖」 x5 (tests/identify_staff_cap_walls.py)
    def test_router_and_departure_seam_agree_and_route_the_live_claim(self):
        seen = {}

        def inspect(index, policy, board):
            if index == FIRST_NO_OWNER:
                home = policy._home_knowledge_items[
                    : policy._home_knowledge_valid_before]
                seen["home_identify_scroll"] = any(
                    item.tval == TVAL_SCROLL and item.name == "鑑定の巻物"
                    for item in home)
                seen["claims"] = list(policy._town_claim_categories)
                seen["departure_ready"] = policy._town_departure_ready(board)
                plan = policy._town_errand_plan
                seen["plan"] = (list(plan.stops), plan.index) if plan else None

        rows = self._replay(FIRST_NO_OWNER, inspect=inspect)
        for index in range(FIRST_NO_OWNER):
            self.assertEqual(rows[index], self._live(index), index)
        self.assertTrue(seen["home_identify_scroll"])
        self.assertTrue(seen["departure_ready"])
        self.assertEqual(seen["claims"], ["launcher-enchant"])
        self.assertEqual(seen["plan"], ([STORE_ALCHEMIST], 0))
        # First changed key versus live (no-actionable-claim-owner): stop here.
        self.assertEqual(rows[FIRST_NO_OWNER], ("\x1b`n%.", "shop:travel"),
                         self._live(FIRST_NO_OWNER))


class IdentifyStaffCapDivergenceTest(unittest.TestCase):
    """The same recorded process, without the cap wall, under the 10-03 cap.

    User 2026-10-03 「鑑定の杖の所持数を4本以内にしたい」 / 「4本を超えた分は回数の
    少ない杖から売る（売れなければ自宅に預ける）」: the board carries five staves
    「鑑定の杖」 j (18), k (5) and l (3x 4), 35 charges.  One 4-charge staff of
    l is above the cap, so the first changed key is index 2: travel to the
    Magic shop to sell it (shop-sell) instead of the live Black Market
    approach.
    """

    # The same frozen process and replay as the walled pin above.
    setUpClass = TownBlackMarketStallRecordedTest.__dict__["setUpClass"]
    _replay = TownBlackMarketStallRecordedTest._replay
    _live = TownBlackMarketStallRecordedTest._live

    def test_fewest_charges_staff_above_the_cap_goes_to_the_magic_shop(self):
        first_changed = 2
        seen = {}
        original = HengbotPolicy.choose_key

        def choose_key(policy, board):
            if len(seen.setdefault("keys", [])) == first_changed:
                staves = policy._carried_identify_staves(board)
                seen["staves"] = [(item.slot, item.count, item.charges)
                                  for item in staves]
                seen["charges"] = policy._total_identify_staff_charges(board)
                seen["release"] = policy._identify_staff_release_plan(board)
                sale = policy._find_device_sale(board)
                seen["sale"] = sale and (sale.slot, sale.count, sale.charges)
            key = original(policy, board)
            seen["keys"].append(key)
            if len(seen["keys"]) == first_changed + 1:
                seen["requesters"] = (policy.decision_claim or {}).get(
                    "requester_families")
            return key

        with patch.object(HengbotPolicy, "choose_key", choose_key):
            rows = self._replay(first_changed)
        self.assertEqual(rows[:first_changed],
                         [self._live(index) for index in range(first_changed)])
        self.assertEqual(seen["staves"], [("j", 1, 18), ("k", 1, 5), ("l", 3, 4)])
        self.assertEqual(seen["charges"], 35)
        self.assertEqual(seen["release"], {"l": 1})
        self.assertEqual(seen["sale"], ("l", 3, 4))
        # First changed key versus live (Black Market approach): stop here (R4).
        self.assertEqual(self._live(first_changed), ("9", "shop:approach"))
        self.assertEqual(rows[first_changed], ("`n&.", "shop:travel"))
        self.assertEqual(TOWN_TRAVEL_STORE_SYMBOLS.index("&"), STORE_MAGIC)
        self.assertIn("shop-sell", seen["requesters"])


if __name__ == "__main__":
    unittest.main()
