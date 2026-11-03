"""n1-a life-472 (2026-11-03 11:49): the Home *Remove Curse* was never fetched.

The worn ロング・ソード {呪われている} waited for *Identify*, which this visit
could not supply.  The Home *Remove Curse* binder waited for every carried or
worn identification candidate, the cursed weapon itself included, so the
scroll the supply ledger counted stayed at Home and the town end stopped
under town:blocked:survival:identify_staff_ready (remove_curse_ready unmet
as well).  Owner 2026-11-03 「先に解呪する」: remove the curse first,
identification waits; Home is entered again within its pass bound.  The
pack held 19 of 23 slots, at the 4-slot reserve: owner 2026-11-03 「取り置き
を使ってよい」, the take is read at once, so it may use one reserve slot
(town_pack_budget.used_at_once) and nothing is sold or shelved for it.

Recorded: the capture's arrival checkpoint and journal
(tests/extract_curse_first_fixture.py).  Rows 0-26 replay unchanged through
the public chooser; the stop board (row 27) now travels Home.  The boards
after it are constructed (marked), the Home page being the recorded page of
row 17 of the same visit; the read is posted through the production executor.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import town_pack_headroom
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import STORE_HOME, parse_snapshot
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
from tests import test_input_executor as executor_pins
from town_work_corpus import replay_window


FIXTURE = Path(__file__).with_name("fixtures") / "curse-first-20261103"
READ_PROMPT = "どの巻物を読みますか? "


def board_of(row):
    return json.loads(row["line"] or row["inputs"][-1])


class CurseFirstRecordedTest(executor_pins.ProductionHarness):
    def test_home_remove_curse_is_fetched_and_read_first(self):
        with TemporaryDirectory() as raw:
            visit = Path(raw) / "town-arrival"
            visit.mkdir()
            (visit / POLICY_FILE).write_bytes(
                lzma.decompress((FIXTURE / "policy.pkl.xz").read_bytes()))
            (visit / JOURNAL_FILE).write_bytes(gzip.compress(
                lzma.decompress((FIXTURE / "journal.jsonl.xz").read_bytes())))
            rows = journal(visit)
            self.assertEqual(rows[-1]["reason"], "town:blocked:survival:identify_staff_ready")
            scratch = Path(raw) / "scratch"
            scratch.mkdir()
            policy = restore(visit, scratch)
            steps = list(decisions(policy, visit, scratch))
            result = replay_window("n1-a-472-1149", policy, iter(steps[:-1]))
            self.assertIsNone(result.first_divergence)
            self.assertEqual(result.matched_rows, 27)
            board = steps[-1][1]()
            key = policy.choose_key(board)

        cursed = next(item for item in board.equipment if item.is_cursed)
        self.assertEqual(cursed.slot, "main_hand")
        self.assertEqual(len(board.inventory), 19)
        self.assertEqual((key, policy.last_reason), ("\x1b`n(.", "shop:travel"))
        self.assertEqual(policy._home_pending_item[0], "*解呪*の巻物")
        self.assertFalse(town_pack_headroom.organizing(policy, board))
        policy.confirm_key_posted(key)

        # DECLARED CONSTRUCTED: the travel enters Home; its page is the
        # recorded Home page of row 17 of this visit.
        raw_board = board_of(rows[-1])
        home_page = board_of(rows[17])["store"]
        self.assertEqual(home_page["store_type"], STORE_HOME)
        entrance = next(grid.position for grid in board.grids.values()
                        if grid.store_number == STORE_HOME)
        inside = copy.deepcopy(raw_board)
        inside["turn"] += 50
        inside["player"]["y"], inside["player"]["x"] = entrance.y, entrance.x
        inside["store"] = home_page
        inside_board = parse_snapshot(inside, policy._monrace_knowledge)
        self.assertEqual(policy.choose_key(inside_board), "\x1b")
        self.assertEqual(policy.last_reason, "home:leave-for-pending-withdraw")
        policy.confirm_key_posted("\x1b")

        outside = copy.deepcopy(inside)
        outside.pop("store")
        outside["turn"] += 1
        letter = next(item["letter"] for item in home_page["items"]
                      if (item["tval"], item["sval"]) == (70, 15))
        take = policy.choose_key(parse_snapshot(outside, policy._monrace_knowledge))
        self.assertEqual((take, policy.last_reason),
                         ("5p" + letter + "\x1b", "home:atomic-withdraw"))
        policy.confirm_key_posted(take)

        # DECLARED CONSTRUCTED: the take's effect, the scroll in the pack.
        after = copy.deepcopy(outside)
        after["turn"] += 5
        ware = next(item for item in home_page["items"] if item["letter"] == letter)
        used = {item["slot"] for item in after["inventory"]}
        scroll = {name: value for name, value in ware.items() if name not in ("letter", "price")}
        scroll.update(count=1, slot=next(c for c in "abcdefghijklmnopqrstuvw" if c not in used))
        after["inventory"].append(scroll)
        after_board = parse_snapshot(after, policy._monrace_knowledge)
        read = policy.choose_key(after_board)
        self.assertEqual((read, policy.last_reason), ("r" + scroll["slot"], "town:remove-curse"))

        game = executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(after)
        game.screen = executor_pins.command_screen(after["turn"])
        # DECLARED CONSTRUCTED: the read prompt and the following board.
        uncursed = copy.deepcopy(after)
        uncursed["turn"] += 10
        game.screens = [executor_pins.prompt_screen(READ_PROMPT),
                        executor_pins.command_screen(uncursed["turn"])]
        game.states = [copy.deepcopy(after), uncursed]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", read, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=after_board, posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        self.assertEqual(game.accepted, ["r", scroll["slot"]])


if __name__ == "__main__":
    unittest.main()
