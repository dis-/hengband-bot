"""Recorded pin: an unfulfilled Home pass closes its unbindable catalogue work.

Live soak 2026-10-18 07:13 and 07:40 (issue #63): a Level 22 warrior in town
cycled about 20 times through ``home:route-claim-unfulfilled`` (inside Home),
a step away and ``shop:approach`` back to Home.  The stall report named the
Home claims ``identification-withdrawal``, ``equipment-catalog`` and
``equipment-work``.  The Home catalogue held incomplete items (a cursed
shield, unknown {special}/{good}/{excellent} weapons) but the pack carried
only identify staffs, so the catalogue binder, which requires a reliable
(scroll) source, never bound a withdrawal and no Home producer acted.

Fixture rows (raw lines of the captured state log): the complete ``~9`` Home
list (turn 872965), the approach board (turn 873529, (44,124)), the Home page
(turn 873529) and the next outside board (turn 873540).

DECLARED CONSTRUCTED: a fresh policy primed on the captured boards; the Home
list is consumed as the requested ``~9`` response; ``_home_candidate_waiting``
is set as recorded on every loop row (the process state before the capture
window is not in the logs); the skill-exp cache is filled.  The control rows
add an Identify scroll to the captured pack and bind a pending withdrawal.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _parse_items
from hengbot.model import SV_SCROLL_IDENTIFY, TVAL_SCROLL, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_HOME
from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURE = Path(__file__).parent / "fixtures" / "home-ident-withdraw-20261018.jsonl.gz"
HOME_CLAIMS = {"identification-withdrawal", "equipment-catalog", "equipment-work"}
AXE = ("焼棄のブロード・アックス (2d6) (+6,+6)", 22, 11)


class HomeIdentWithdrawRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            (cls.home9, cls.approach, cls.inside, cls.after,
             cls.approach2, cls.inside2) = [
                json.loads(line) for line in stream
            ]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy_for(self, board):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        snapshot = parse_snapshot(board, self.monrace)
        policy.prime(snapshot)
        policy._skill_exp_cache = (
            0, 0, snapshot.player.level, policy._town_visit_epoch
        )
        policy.consume_home_knowledge(tuple(_parse_items(
            self.home9["knowledge"]["items"],
            protocol=self.home9.get("protocol_version"),
        )))
        policy._home_candidate_waiting = True
        return policy, snapshot

    def _home_needs(self, policy, snapshot):
        return sorted(
            need.category for need in policy._town_need_candidates(snapshot)
            if need.store_type == STORE_HOME
        )

    def _decide(self, policy, board):
        snapshot = parse_snapshot(board, self.monrace)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        return snapshot, str(key), policy.last_reason

    def test_captured_boards(self):
        self.assertEqual(
            (self.home9["turn"], self.home9["knowledge"]["category"],
             len(self.home9["knowledge"]["items"])),
            (872965, "home", 139),
        )
        self.assertEqual(
            [(row["turn"], row["player"]["y"], row["player"]["x"],
              (row.get("store") or {}).get("store_type"), len(row["inventory"]))
             for row in (self.approach, self.inside, self.after,
                         self.approach2, self.inside2)],
            [(873529, 44, 124, None, 17), (873529, 45, 123, STORE_HOME, 17),
             (873540, 45, 123, None, 17), (873549, 44, 124, None, 17),
             (873549, 45, 123, STORE_HOME, 17)],
        )

    def test_unfulfilled_home_pass_does_not_route_back_to_home(self):
        policy, snapshot = self._policy_for(self.approach)
        self.assertEqual(
            self._home_needs(policy, snapshot),
            ["equipment-catalog", "identification-withdrawal"],
        )
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        self.assertEqual((str(key), policy.last_reason), ("1", "shop:approach"))

        # First unfulfilled pass: unchanged from 73e94383, Home stays a need,
        # so the captured boards cycle back to Home.
        inside, key, reason = self._decide(policy, self.inside)
        self.assertEqual((key, reason), ("", "home:route-claim-unfulfilled"))
        self.assertEqual(
            self._home_needs(policy, inside),
            ["equipment-catalog", "identification-withdrawal"],
        )
        self.assertEqual(policy._deferred_home_items, set())
        self._decide(policy, self.after)
        self._decide(policy, self.approach2)

        # The repeated pass closes the unbindable work for this stay.
        # 73e94383: the Home needs were still
        # ["equipment-catalog"] here (the router returned to Home).
        inside, key, reason = self._decide(policy, self.inside2)
        self.assertEqual((key, reason), ("", "home:route-claim-unfulfilled"))
        self.assertEqual(self._home_needs(policy, inside), [])
        self.assertEqual(len(policy._deferred_home_items), 6)
        self.assertIn(AXE, policy._deferred_home_items)
        self.assertEqual(
            policy._deferred_home_item_sites[AXE], "home-route-claim-unfulfilled"
        )
        policy._town_claims_active(inside)
        self.assertFalse(
            HOME_CLAIMS & set(getattr(policy, "_town_claim_categories", ()) or ())
        )

    def test_deferred_home_suppression_target_is_not_a_home_claim(self):
        policy, snapshot = self._policy_for(self.approach)
        axe = next(
            owned for owned in policy._equipment_catalog.items
            if owned.origin == "home" and policy._item_signature(owned.item) == AXE
        )
        with patch.object(
            HengbotPolicy, "_selected_random_teleport_suppressions",
            lambda _self, _preparation: (axe,),
        ):
            self.assertTrue(
                policy._has_selected_home_random_teleport_suppression(snapshot)
            )
            policy._defer_home_item(AXE, "constructed")
            self.assertFalse(
                policy._has_selected_home_random_teleport_suppression(snapshot)
            )
            self.assertIsNone(
                policy._random_teleport_suppression_producer_action(snapshot, axe)
            )

    def test_control_identification_withdrawal_that_fits_still_binds(self):
        board = copy.deepcopy(self.approach)
        scroll = copy.deepcopy(next(
            item for item in board["inventory"] if item["tval"] == TVAL_SCROLL
        ))
        scroll.update({"name": "鑑定の巻物", "sval": SV_SCROLL_IDENTIFY,
                       "count": 5})
        board["inventory"].insert(
            next(index for index, item in enumerate(board["inventory"])
                 if item["tval"] == TVAL_SCROLL), scroll)
        policy, snapshot = self._policy_for(board)
        self.assertEqual(18, len(snapshot.inventory))
        policy._bind_catalogued_home_identification_withdrawal(snapshot)
        self.assertTrue(policy._home_errand.active)
        self.assertEqual(policy._home_errand.request.purpose, "identification-catalog")
        self.assertEqual(policy._deferred_home_items, set())

    def test_control_home_visit_with_bound_withdrawal_leaves_to_compose_it(self):
        policy, _snapshot = self._policy_for(self.approach)
        target = policy._item_signature(policy._home_knowledge_items[0])
        policy._home_pending_item = target
        _inside, key, reason = self._decide(policy, self.inside)
        self.assertEqual((key, reason), ("\x1b", "home:leave-for-pending-withdraw"))
        self.assertEqual(policy._deferred_home_items, set())


if __name__ == "__main__":
    unittest.main()
