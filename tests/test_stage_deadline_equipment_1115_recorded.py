"""A Home relief's ware put back on the shelf ends the relief's entry (n1-c life-214, 2026-11-15).

Recorded: n1-c life-214 (Magic-Eater Lv41, build 744f140d4) stopped at
town:blocked:stage-deadline:equipment at 18:03:56.  The Home junk sweep chose the rank 21+
麻痺知らずの指輪 {麻} to sell (home:junk-sweep-withdraw, row 40) and took it out
(home-errand:atomic-withdraw:full-home-sale, row 41).  The equipment transaction took the
next decisions and deposited the unworn ring again (equipment-transaction:deposit, row 43)
before the relief saw the ring carried.  On the Home page the relief then found its ware on
the shelf, re-filed the take (row 44), and the take and the deposit alternated (rows 41-108):
the pack and the gold showed only the two states the visit had already seen, so the
equipment stage's count never restarted (town_visit_plan.note_observed_progress) and its
deadline stopped the loop (row 109).  The deadline was right; the loop was the relief's.

When the relief sees the ware held by another owner it ends the entry retained and skipped
(home:full-skip:sale-item-held, n1-a life-492 2026-11-07; n1-a life-525 2026-11-15 row 40
of tests/test_n1a_525_kill_mob_1115_recorded).  Now a take that was done (its errand DONE)
with the ware back on the shelf is that case too.

The town-arrival checkpoint, journal rows and sidecar files
(tests/extract_stage_deadline_equipment_1115_fixture.py) replay through the public
choose_key with the recorded keys posted: rows 0-43 decide as recorded.  On row 44 the relief
ends its entry (and the sweep for the stay) instead of re-filing the take; the production
executor port posts that key on the recorded Home page.  The visit then leaves Home and
goes on to its next shop.

DECLARED CONSTRUCTED: the character dump the game wrote for rows 0 and 31
(periodic:character-dump) is not in the capture.  The fixture's character-dump-row0.txt is
the arrival's dump (the capture's sidecar, written before the visit) with the strength row
raised to the board's (base 18/91 -> 18/97, total 18/191 -> 18/197, stat_max 115); without
it the calibration is stale (visible-base-epoch-mismatch) and row 4 asks for the Home scan
instead of the recorded deposit.  The screens around the posted key; the boards after it
(row 44's Home page and row 45's outside board, their turns advanced).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import copy
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins

FIXTURE = Path(__file__).with_name("fixtures") / "stage-deadline-equipment-1115" / "n1c214"
STOP = "town:blocked:stage-deadline:equipment"
STOP_ROW = 109
FIXED_ROW = 44
RING = "麻痺知らずの指輪 {麻}"
TAKE = "home-errand:atomic-withdraw:full-home-sale"
LOOP = {TAKE, "home-errand:request-knowledge:full-home-sale",
        "equipment-transaction:travel-home:await-entry", "equipment-transaction:deposit"}


def store_page_screen(store):
    """DECLARED CONSTRUCTED: the Home page with the recorded stock and the menu rows
    (the recorded page's 52 rows need a taller terminal than the harness's)."""
    screen = executor_pins.store_screen()
    menu = screen["lines"][20:22]
    screen["lines"] = screen["lines"][:6] + [""] * 56
    screen["height"] = len(screen["lines"])
    for index, item in enumerate(store["items"][:52]):
        screen["lines"][6 + index] = f"{item['letter']}) {item['name']}"
    screen["lines"][58:60] = menu
    screen["cursor"] = {"visible": True, "y": 58, "x": 0}
    return screen


class StageDeadlineEquipment1115RecordedTest(executor_pins.ProductionHarness):
    def test_n1c_214_relief_ends_when_its_ware_is_back_on_the_shelf(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        policy, recorded, steps = load(FIXTURE, Path(scratch.name))
        self.assertEqual(len(steps), STOP_ROW + 1)
        self.assertEqual(recorded[STOP_ROW]["reason"], STOP)
        self.assertEqual(recorded[FIXED_ROW]["reason"], "policy:none-store-exit")
        self.assertEqual(recorded[FIXED_ROW + 2]["reason"], TAKE)
        for index, (row, supply) in enumerate(steps[:FIXED_ROW]):
            with contextlib.redirect_stdout(io.StringIO()):
                key = policy.choose_key(supply())
            self.assertEqual((key, policy.last_reason), (row["key"], row["reason"]), index)
            policy.confirm_key_posted(key)
            chain = policy.peek_staged_prompt_chain()
            if chain is not None and staged_prompt_chain_matches(chain, key):
                policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})
            if row["reason"] == "periodic:character-dump":
                # DECLARED CONSTRUCTED: the sheet the game writes for this dump.
                dump = Path(policy._character_dump_path)
                dump.write_bytes((FIXTURE / "character-dump-row0.txt").read_bytes())
                os.utime(dump, ns=(time.time_ns(), time.time_ns()))
        board = steps[FIXED_ROW][1]()
        # The take was done and the ring is back on the shelf.
        self.assertEqual(policy._home_errand.state.value, "done")
        self.assertEqual(policy._home_errand.request.signature[0], RING)
        self.assertFalse(any(item.name == RING for item in board.inventory))
        self.assertTrue(any(item.name == RING for item in board.store.items))

        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)

        self.assertEqual(policy.last_reason, "home:full-skip:sale-item-held")
        self.assertIsNone(policy._home_full_relief)
        policy.confirm_key_posted(key)
        raw = json.loads(recorded[FIXED_ROW]["line"] or recorded[FIXED_ROW]["inputs"][-1])
        self.assert_posts(policy, raw, board, key)
        # DECLARED CONSTRUCTED: the Home page again, then the outside board.
        page = parse_snapshot(dict(copy.deepcopy(raw), turn=raw["turn"] + 10),
                              policy._monrace_knowledge)
        self.assertEqual(self.decide(policy, page), ("\x1b", "home:leave-after-one-operation"))
        outside = json.loads(recorded[FIXED_ROW + 1]["line"] or recorded[FIXED_ROW + 1]["inputs"][-1])
        self.assertIsNone(outside.get("store"))
        reasons = [self.decide(policy, parse_snapshot(
            dict(copy.deepcopy(outside), turn=outside["turn"] + 10 * n),
            policy._monrace_knowledge))[1] for n in range(1, 4)]
        self.assertEqual(reasons[0], "shop:travel")
        self.assertFalse(LOOP & set(reasons), reasons)
        self.assertFalse(any(reason.startswith("town:blocked:") for reason in reasons))

    @staticmethod
    def decide(policy, board):
        with contextlib.redirect_stdout(io.StringIO()):
            key = policy.choose_key(board)
        if key:
            policy.confirm_key_posted(key)
        return key, policy.last_reason

    def assert_posts(self, policy, raw, board, key):
        """The production executor posts ``key`` on the recorded Home page."""
        self.assertIsNotNone(raw.get("store"))
        game = executor_pins.FaithfulHookGame()
        game.state, game.jsonl = copy.deepcopy(raw), [copy.deepcopy(raw)]
        game.screen = store_page_screen(raw["store"])
        game.screens = [store_page_screen(raw["store"])]
        game.states = [dict(copy.deepcopy(raw), turn=raw["turn"] + 10)]
        _game, _client, executor = self.make(game)
        result = executor.observe_boundary(deadline=9999999999)
        self.assertEqual(result.outcome, "ready", result)
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-home-page", key, None, set(), in_store=True,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, [key])


if __name__ == "__main__":
    unittest.main()
