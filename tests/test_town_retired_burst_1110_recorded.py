"""The town:blocked:owner-retired-burst stops of 2026-11-10 (n1-a life-508, n1-b life-364).

Recorded: each capture's town-arrival checkpoint, visit journal and sidecar files
(tests/extract_town_retired_burst_1110_fixture.py).  The rows before the fixed
decision replay through the public chooser; where the live CLI rewrote a key
(the owner-retirement entrance), the rows go through the same CLI functions
(``validate_read_key``, ``_handle_owner_retirement`` with --owner-retired-log-only,
as the viewing bots run) and the rewritten key is the one posted.

n1-a life-508 (21:05): after a Home withdrawal invalidated the Home list, the
router's Home visit held the Home scan out inside Home (the page left as
home:scan-incomplete-open-page) and outside (the router stepped off and walked
back in); later the outside ``~9`` replaced an entrance step-off the approach
had decided, the step-off latch stayed armed on the unchanged board and refused
the bound Home take, so the router re-entered Home and the page left for the
take again.  Three retirements without progress: owner-retired-burst.

n1-a life-508 (2026-11-11 00:40): Recall short by one (10 carried, 11 for the
departure) with both suppliers sold out started the one-run stock-out
time-pass.  Its mining mode zeroes the Recall target, so the Home deposit
stowed the 10 scrolls; back on the next board the Home list showed them, the
stock-out check took them for a supplier and the gold-target end closed the
set before the run.  The mining kit went back into Home, the now-stale Home
list read as no supplier and the stock-out restarted, the scrolls came out
again: the deposit/withdraw ping-pong that ran the owner budget out.

n1-b life-364 (10:18): the torch thrown at a dog in the Outpost's one-cell east
gate lay in the gate under the name of the carried torches; with 19 carried
items the floor-step budget counted it one slot and refused the gate, and the
walk to the Magic shop went round the outside of the town wall until
owner-retired-burst.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import base64
import copy
import gzip
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

from hengbot.cli import _handle_owner_retirement
from hengbot.model import STORE_HOME, Position
from hengbot.policy import staged_prompt_chain_matches
from hengbot.policy_constants import HOME_KNOWLEDGE_MACRO
from hengbot import town_hold
from hengbot.town_arrival_checkpoint import (
    JOURNAL_FILE, POLICY_FILE, SIDECAR_DIRECTORY, SIDECAR_MANIFEST,
)
from hengbot import town_pack_budget
from replay_town_arrival import adopt_calibration, decisions, journal, restore
from town_work_corpus import replay_window


FIXTURES = Path(__file__).with_name("fixtures") / "town-retired-burst-1110"
# The viewing bots' CLI flag (owner retirements logged and forgiven).
LOG_ONLY = SimpleNamespace(owner_retired_log_only=True, decision_log=None)
PICKAXE = ("つるはし (1d3) (+0,+0) (+1) {+掘}", 20, 4)
GATE_TORCH = Position(33, 130)


def pre_fix_home_route_opened_for(policy, family):
    """DECLARED WALL: the Home hold's route exemption before the Home scan's.

    The n1-a step-off pin replays rows 55-72 as the live process decided them;
    the Home-scan exemption (town_hold.home_route_opened_for) changes row 55
    on, so it is walled off for that pin only.  Its own pin is
    test_n1a_home_scan_runs_inside_the_router_s_home_visit.
    """
    holder = town_hold.errand_hold(policy, "__none__", enforced=True)
    visit = getattr(policy, "_store_visit", None)
    return bool(holder is not None and holder.owner.value == "store-router"
                and town_hold.home_catalogue_work_holder(policy) is None
                and visit is not None and visit.store_type == STORE_HOME
                and visit.opened_for_family == family)


class TownRetiredBurst1110RecordedTest(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)

    def load(self, stop):
        """The stop's arrival policy, its journal rows and its board suppliers."""
        visit = self.scratch / stop / "town-arrival"
        (visit / SIDECAR_DIRECTORY).mkdir(parents=True)
        fixture = FIXTURES / stop
        (visit / POLICY_FILE).write_bytes(
            lzma.decompress((fixture / "policy.pkl.xz").read_bytes()))
        (visit / JOURNAL_FILE).write_bytes(gzip.compress(
            lzma.decompress((fixture / "journal.jsonl.xz").read_bytes())))
        sidecars = json.loads(lzma.decompress((fixture / "sidecars.json.xz").read_bytes()))
        (visit / SIDECAR_MANIFEST).write_text(
            json.dumps(sidecars["manifest"], ensure_ascii=False), encoding="utf-8")
        for role, data in sidecars["files"].items():
            (visit / SIDECAR_DIRECTORY / role).write_bytes(base64.b64decode(data))
        runtime = self.scratch / stop / "runtime"
        runtime.mkdir()
        policy = restore(visit, runtime)
        adopt_calibration(policy, visit / SIDECAR_DIRECTORY / "_character_calibration_path",
                          runtime)
        return policy, journal(visit), list(decisions(policy, visit, runtime))

    def replay(self, name, policy, steps):
        """Replay ``steps`` unchanged through the public chooser."""
        result = replay_window(name, policy, iter(steps))
        self.assertIsNone(result.first_divergence)
        self.assertEqual(result.matched_rows, len(steps))

    def replay_live(self, policy, recorded, steps):
        """Replay ``steps`` as the live CLI decided and posted them."""
        posted = []
        for (row, supply) in steps:
            board = supply()
            visit_before = copy.copy(policy._store_visit)
            chosen = policy.choose_key(board)
            self.assertEqual((chosen, policy.last_reason),
                             (recorded[row["row"]]["key"], recorded[row["row"]]["reason"]),
                             row["row"])
            key = policy.validate_read_key(board, chosen)
            key = _handle_owner_retirement(LOG_ONLY, board, key, policy, visit_before)
            posted.append(key)
            if key:
                policy.confirm_key_posted(key)
                chain = policy.peek_staged_prompt_chain()
                if chain is not None and staged_prompt_chain_matches(chain, key):
                    policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
        return posted

    def test_n1a_home_scan_runs_inside_the_router_s_home_visit(self):
        """Row 55 (decision 17440): the Home page after the shovel withdrawal.

        Live: ``ESC`` home:scan-incomplete-open-page, the scan held out by the
        router's Home visit (holder store-router), then the step-off and the
        re-entry that the arbiter retired twice.
        """
        policy, recorded, steps = self.load("n1a-508")
        self.replay("before-the-page", policy, steps[:55])
        self.assertEqual((recorded[55]["key"], recorded[55]["reason"]),
                         ("\x1b", "home:scan-incomplete-open-page"))
        board = steps[55][1]()
        self.assertEqual(board.store.store_type, STORE_HOME)
        self.assertEqual((board.store.stock_num, len(board.store.items)), (59, 52))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        self.assertFalse(policy._town_turn_arbiter.pending_retirement_owners)

    def test_n1a_bound_home_take_composes_after_the_outside_scan(self):
        """Row 73 (decision 17458): the Home entrance after the outside ``~9``.

        Live: ``5`` shop:travel:await-entry (the step-off latch of row 72 refused
        the composer), the Home page left again for the take, and the third
        retirement made the burst.  The pickaxe take is bound since row 65.
        """
        with mock.patch("hengbot.policy.town_home_route_opened_for",
                        pre_fix_home_route_opened_for):
            policy, recorded, steps = self.load("n1a-508")
            self.replay("before-the-home-loop", policy, steps[:55])
            posted = self.replay_live(policy, recorded, steps[55:73])
            # The live CLI's rewrites at the two forgiven retirements.
            self.assertEqual((recorded[58]["key"], posted[58 - 55]), ("~9\x1b", "\x1b"))
            self.assertEqual(policy._owner_retired_no_progress_count, 2)
            self.assertEqual((recorded[72]["key"], recorded[72]["reason"]),
                             ("~9\x1b", "home:request-knowledge-scan"))
            self.assertEqual(policy._home_pending_item, PICKAXE)
            board = steps[73][1]()
            self.assertEqual(board.grid_at(board.player.position).store_number, STORE_HOME)
            self.assertEqual(recorded[73]["reason"], "shop:travel:await-entry")
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5 pd1\r\x1b", "home:atomic-withdraw"))
        self.assertEqual(policy._home_atomic_withdraw_pending[0], PICKAXE)

    def test_n1a_2243_home_scan_runs_after_the_deposit(self):
        """22:43, row 47 (decision 11981): the Home page after an atomic deposit.

        The same Home visit shape one visit later (build bot-49436da51): live
        ``ESC`` home:scan-incomplete-open-page, the step-off and re-entry.
        """
        policy, recorded, steps = self.load("n1a-508-2243")
        self.replay_live(policy, recorded, steps[:47])
        self.assertEqual((recorded[45]["reason"], recorded[47]["key"], recorded[47]["reason"]),
                         ("home:atomic-deposit", "\x1b", "home:scan-incomplete-open-page"))
        board = steps[47][1]()
        self.assertEqual(board.store.store_type, STORE_HOME)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason),
                         (HOME_KNOWLEDGE_MACRO, "home:request-knowledge-scan"))
        self.assertFalse(policy._town_turn_arbiter.pending_retirement_owners)

    def test_n1a_2243_bound_home_take_composes_after_the_outside_scan(self):
        """22:43, row 74 (decision 12008): the Home entrance after the outside ``~9``.

        Live: ``5`` shop:travel:await-entry, the page left for the take again and
        the third retirement made the burst (the 21:05 shape, one visit later).
        """
        with mock.patch("hengbot.policy.town_home_route_opened_for",
                        pre_fix_home_route_opened_for):
            policy, recorded, steps = self.load("n1a-508-2243")
            self.replay_live(policy, recorded, steps[:74])
            self.assertEqual(policy._owner_retired_no_progress_count, 2)
            self.assertEqual((recorded[73]["key"], recorded[73]["reason"]),
                             ("~9\x1b", "home:request-knowledge-scan"))
            pending = policy._home_pending_item
            self.assertIsNotNone(pending)
            board = steps[74][1]()
            self.assertEqual(board.grid_at(board.player.position).store_number, STORE_HOME)
            self.assertEqual(recorded[74]["reason"], "shop:travel:await-entry")
            key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("5 pp1\r\x1b", "home:atomic-withdraw"))
        self.assertEqual(policy._home_atomic_withdraw_pending[0], pending)

    def test_n1a_0040_stowed_recall_does_not_end_the_stockout_run(self):
        """00:40, row 44 (decision 27291): the Home list after the deposit of row 39.

        Live: ``ESC `n(.`` shop:travel, the stock-out set ended at the gold
        target (Home's 10 scrolls taken for a supplier), then the kit deposit
        and the restart of the stock-out (rows 45-47).  The Home scan
        exemption is walled off (declared) to replay rows 24-43 as decided.
        """
        with mock.patch("hengbot.policy.town_home_route_opened_for",
                        pre_fix_home_route_opened_for):
            policy, recorded, steps = self.load("n1a-508-0040")
            self.replay_live(policy, recorded, steps[:44])
        self.assertEqual((recorded[13]["reason"], recorded[39]["key"], recorded[39]["reason"]),
                         ("town:recall-stockout-mining", "df10\r\x1b", "home:atomic-deposit"))
        self.assertEqual(policy._fundraising_mode, "mine")
        board = steps[44][1]()
        self.assertEqual(sum(item.count for item in policy._home_knowledge_items
                             if item.is_recall_scroll), 10)
        self.assertEqual(recorded[44]["reason"], "shop:travel")
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), (">\ry", "descend"))
        self.assertEqual((policy._fundraising_mode, policy._recall_stockout_mining_plan),
                         ("mine", True))

    def test_n1b_detour_round_the_wall_is_store_router_progress(self):
        """Rows 8-59: the walk round the town wall to the Magic shop.

        Live: the router's straight-line distance stayed flat at row 31
        ((13,130) after (14,131)) and came back to a value it had at row 56
        ((1,105)): two retirements in the walk.  The pile fix of row 3 is
        walled off (declared: stacking_pile_objects counts nothing, as the
        live build did) so that the live detour is the route the walk takes.
        """
        with mock.patch("hengbot.town_pack_budget.stacking_pile_objects",
                        lambda snapshot, grid: 0):
            policy, recorded, steps = self.load("n1b-364")
            self.replay_live(policy, recorded, steps[:31])
            progress = []
            for row, supply in steps[31:60]:
                board = supply()
                key = policy.choose_key(board)
                self.assertEqual((key, policy.last_reason),
                                 (recorded[row["row"]]["key"], "shop:approach"), row["row"])
                arbiter = policy._town_turn_arbiter.telemetry
                progress.append((row["row"], arbiter["producer_owner"], arbiter["progress"]))
                policy.confirm_key_posted(key)
        self.assertEqual(progress, [(row, "store-router", True) for row in range(31, 60)])
        self.assertEqual(policy._owner_retired_no_progress_count, 0)

    def test_n1b_walk_through_the_gate_holding_its_own_torch(self):
        """Row 3 (decision 1611): the board after the thrown torch killed the dog.

        Live: periodic:game-save, then the walk east out of the gate and round
        the town wall (the travel was refused by the same pile estimate).
        """
        policy, recorded, steps = self.load("n1b-364")
        self.replay("the-kill", policy, steps[:3])
        self.assertEqual((recorded[3]["reason"], recorded[8]["key"], recorded[8]["reason"]),
                         ("periodic:game-save", "6", "shop:approach"))
        board = steps[3][1]()
        self.assertEqual((board.grids[GATE_TORCH].object_count, len(board.inventory)), (1, 19))
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ("\x1b`n&.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_goal, Position(38, 106))
        # The gate cell itself: the torch joins the carried 松明(1700ターンの寿命) stack.
        self.assertEqual(board.found_item_names[GATE_TORCH],
                         ("松明(1700ターンの寿命) {明, @v0=g}",))
        self.assertTrue(town_pack_budget.floor_step_fits(board, GATE_TORCH))


if __name__ == "__main__":
    unittest.main()
