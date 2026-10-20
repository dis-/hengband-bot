"""Recorded pin: the Home-full sale keeps the one *Remove Curse* reserve.

Live soak c4-a life-014 2026-10-20 (Level 30-31): the Temple purchase owner
(``curse:star-reserve`` / ``_affordable_star_remove_curse``, no cursed worn
item: the Light Crossbow curse became known only at 13:48) bought
``*解呪*の巻物`` for 6,028 G at 10:30:55 (seq 17 ``pn1\\r\\r``); Home's reserve
deposit stored it at 10:31:21 (seq 38 ``home:atomic-deposit`` ``de\\x1b``).
At 10:35:45 the Home-full relief withdrew it
(``home-errand:atomic-withdraw:full-home-sale`` ``5pH\\x1b``), inscribed it
``{@0}`` and sold it for 1,944 G (seq 2397 ``home:scan-leave-store``).  The
same buy / deposit / sell cycle repeated at 11:15, 11:29, 11:44 and 11:55
(6,116 G each, sold for 1,872 G).

Fixture rows: the issue #67 capture B (2026-10-18 12:38, the same soak
character, Level 26, gold 19,146 >= the reserve's purchase gate) -- the Home
``~9`` list, the outside approach board and the Home page board.

DECLARED CONSTRUCTED: the 2026-10-20 boards carry no inventory.  The Home's
Summon Monster stack (3) becomes the one ``*解呪*の巻物`` the reserve
deposited, on the list and on the Home page.  For the pack-reserve control the
carried Door/Stair Location staff becomes two ``*解呪*の巻物``.  The junk wall
of the issue #68 pin is reused so the relief chooses among sale stock.
"""

from __future__ import annotations

import tests  # noqa: F401 -- isolate runtime state for standalone module runs
import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _parse_items
from hengbot.model import (SV_SCROLL_STAR_REMOVE_CURSE, TVAL_SCROLL,
                           parse_snapshot)
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_esp_threat_rest_recorded import EDIT, _policy
from test_home_full_sale_keeps_recall_recorded import _without_home_junk
import test_oneshot_inflight_recorded as oneshot


FIXTURE = Path(__file__).parent / "fixtures" / "sale-inscribe-buy-20261018.jsonl.gz"
STAR_REMOVE_CURSE_NAME = "*解呪*の巻物"
SUMMON_NAME = "サモン・モンスターの巻物"
DETECTION_NAME = "財宝感知の巻物"
CARRIED_STAFF_NAME = "ドア/階段感知の杖 (15回分)"


def _reserve_at_home(row):
    """Return ``row`` with the Home Summon Monster stack made the reserve."""
    row = copy.deepcopy(row)
    items = (row["knowledge"]["items"] if "knowledge" in row
             else row["store"]["items"])
    item = next(item for item in items if item["name"] == SUMMON_NAME)
    item.update(name=STAR_REMOVE_CURSE_NAME, tval=TVAL_SCROLL,
                sval=SV_SCROLL_STAR_REMOVE_CURSE, count=1, is_broken=False)
    return row


def _reserve_carried(board, count=1):
    """Return ``board`` with ``count`` *Remove Curse* in the pack."""
    board = copy.deepcopy(board)
    item = next(item for item in board["inventory"]
                if item["name"] == CARRIED_STAFF_NAME)
    item.update(name=STAR_REMOVE_CURSE_NAME, tval=TVAL_SCROLL,
                sval=SV_SCROLL_STAR_REMOVE_CURSE, count=count, charges=0,
                pval=0, aware=True, known=True, is_broken=False)
    return board


class StarRemoveCurseReserveSaleRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream]
        cls.home, cls.approach, cls.inside = rows[4], rows[5], rows[6]
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def _policy_on(self, home, approach):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy._in_store_ops_enabled = True
        policy._equipment_optimization_last_depth = 20
        snapshot = parse_snapshot(approach, self.monrace)
        policy.prime(snapshot)
        policy._skill_exp_cache = (
            0, 0, snapshot.player.level, policy._town_visit_epoch
        )
        home = _without_home_junk(home)
        policy.consume_home_knowledge(tuple(_parse_items(
            home["knowledge"]["items"], protocol=home.get("protocol_version"),
        )))
        return policy

    def _relief_pick(self, home, approach, inside):
        """Replay the Home page board; return the picked relief stack."""
        policy = self._policy_on(home, approach)
        snapshot = parse_snapshot(inside, self.monrace)
        policy.observe_store_screen(True)
        key = policy.choose_key(snapshot)
        policy.confirm_key_posted(key)
        relief = policy._home_full_relief or {}
        sale = relief.get("sale")
        return (sale[0][0] if sale else None), relief.get("mode"), (
            str(key), policy.last_reason)

    def _home_stack(self, policy, name):
        return next(item for item in policy._home_knowledge_items
                    if item.name == name)

    def test_home_reserve_is_neither_sold_nor_destroyed(self):
        home, approach, inside = (_reserve_at_home(self.home), self.approach,
                                  _reserve_at_home(self.inside))
        policy = self._policy_on(home, approach)
        snapshot = parse_snapshot(inside, self.monrace)
        self.assertFalse(any(item.is_cursed for item in snapshot.equipment))
        self.assertEqual(policy._carried_star_remove_curse_count(snapshot), 0)
        stack = self._home_stack(policy, STAR_REMOVE_CURSE_NAME)
        # 838e185b: both selectors offered the reserve.
        self.assertIsNone(policy._home_full_sale_candidate(snapshot, stack))
        self.assertIsNone(policy._home_full_discard_candidate(snapshot, stack))

    def test_home_full_relief_sells_other_stock_not_the_reserve(self):
        # 838e185b picked the reserve here (the live 10:35:45 withdrawal).
        # Control: the relief still makes room, from the other sale stock
        # (the Treasure Detection stack no mining kit target holds).
        self.assertEqual(
            self._relief_pick(_reserve_at_home(self.home), self.approach,
                              _reserve_at_home(self.inside)),
            (DETECTION_NAME, "sale",
             ("\x1b", "home:full-queue-surplus-withdraw")),
        )

    def test_control_scroll_beyond_the_reserve_is_still_surplus(self):
        # No cursed target: of two carried scrolls only the one-scroll
        # reserve is retained; the second stays sellable surplus.
        approach = _reserve_carried(self.approach, count=2)
        inside = _reserve_carried(self.inside, count=2)
        policy = self._policy_on(self.home, approach)
        snapshot = parse_snapshot(inside, self.monrace)
        self.assertFalse(any(item.is_cursed for item in snapshot.equipment))
        carried = next(item for item in snapshot.inventory
                       if item.sval == SV_SCROLL_STAR_REMOVE_CURSE
                       and item.tval == TVAL_SCROLL)
        self.assertEqual(carried.count, 2)
        self.assertEqual(policy._retention_surplus(snapshot, carried), 1)

    def test_control_treasure_detection_outside_mining_is_still_surplus(self):
        # No mining kit target is live: the Home Treasure Detection stack is
        # still offered to the Home-full sale.
        policy = self._policy_on(_reserve_at_home(self.home), self.approach)
        snapshot = parse_snapshot(_reserve_at_home(self.inside), self.monrace)
        stack = self._home_stack(policy, DETECTION_NAME)
        self.assertEqual(stack.count, 5)
        self.assertIsNotNone(policy._home_full_sale_candidate(snapshot, stack))


class OneShotReserveSaleWallTest(unittest.TestCase):
    """Non-vacuity of the declared wall in test_oneshot_inflight_recorded."""

    def test_without_the_wall_the_recorded_reserve_sale_is_not_composed(self):
        # The 2026-10-20 08:28 capture withdrew the *Remove Curse* reserve
        # for the Home-full sale; without the wall it is retained, so the
        # outside board no longer composes ("5", "shop:one-shot-sell").
        recorded = oneshot.OneShotInFlightRecordedTest
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        holder = type("Replay", (), {})
        holder.lines = gzip.decompress(
            oneshot.FIXTURE.read_bytes()).decode("utf-8").splitlines()
        holder.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        holder.directory = Path(directory.name)
        holder.policy = _policy(holder.directory, holder.monrace)
        holder.policy._crossarea_fundraising_enforced = True
        holder.policy._in_store_ops_enabled = True
        holder._await_recorded_knowledge = staticmethod(
            recorded._await_recorded_knowledge)
        decision = None
        for index in range(oneshot.COMPOSE_BOARD + 1):
            decision = recorded._feed.__func__(holder, holder.lines[index])
        self.assertIsNotNone(decision)
        self.assertNotEqual(decision[1:], ("5", "shop:one-shot-sell"))
        self.assertIn("*解呪*の巻物 {@0}", [
            item.name for item in decision[0].inventory])


if __name__ == "__main__":
    unittest.main()
