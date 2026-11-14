"""Home's freed slot is not an unreachable Home (n1-b life-397 2026-11-14 22:40:42).

n1-b life-397 (Magic-Eater Lv47, build e897edf2d) came back to the Outpost
overweight.  At Home (240/240 after the deposits) the deposits that did not land
were recorded as refused (``_home_rejected_deposits``; in the record the
首切りソード's), the equipment transaction closed with its Home-full tombstone
and Home's full relief began: it sold surplus potions at the Alchemist, took the
溶解のヘヴィ・フレイル out of Home and sold it at the Armoury (rows 62-99), which
left Home one slot and filed the relief's retry deposit (the 革製スケイル・メイル).
On the first outside board after that sale (row 101) the closing-equipment-weight
transition read the refused deposits as Home's failed weight gate and, Home no
longer full, stopped under town:blocked:overweight-home-unreachable - over the
retry deposit Home could take, with Home's approach/pass/visit bounds unused.

Fix: a deposit refused by a full Home is not a failed weight gate once Home has
room and a deposit is left for it; the transition gives the board to Home's weight
route, under Home's own bounds.  An exhausted Home bound still stops by name.

Recorded: the incident capture's town-arrival checkpoint and its whole journal
(tests/extract_n1b_397_overweight_home_1114_fixture.py), rows 0-100 decided
through the public choose_key and compared with the record.  Row 7 is FORCED: the
checkpoint does not keep the equipment optimizer's prepared result, so the
recorded bot's signature-cache hit (a loadout prepared before the arrival, which
kept the crossbow and the ring) is a fresh search here whose deposit batch also
names them; the recorded key is posted.  The character dump of row 0 was written
to the dump file the journal does not hold; the calibration it produced is the
recorded one of the next checkpoint (``calibration-after-dump.json.xz``).

DECLARED CONSTRUCTED: the Home knowledge answering row 101's scan is row 28's
recorded Home list without the sold 溶解のヘヴィ・フレイル (rows 62-63 took only
it), with row 101's pack; the Home page is row 62's recorded page with row 101's
pack and the one free slot (239/240).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.latch_onset_capture import checkpoint_bytes, restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_HOME, TOWN_TRAVEL_STORE_SYMBOLS
from replay_town_arrival import adopt_calibration
from support.town_arrival_fixture import load

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-397-overweight-home-1114"
FORCED = {7}
STOP_ROW = 101
STOP = "town:blocked:overweight-home-unreachable"
KNOWLEDGE_ROW = 28
HOME_PAGE_ROW = 62
SOLD = "溶解のヘヴィ・フレイル"
RETRY = ("革製スケイル・メイル [11]", 36, 11)


class N1b397OverweightHome1114RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        scratch = Path(cls.scratch.name)
        policy, cls.journal, steps = load(FIXTURE, scratch)
        dumped = scratch / "calibration-after-dump.json"
        dumped.write_bytes(lzma.decompress(
            (FIXTURE / "calibration-after-dump.json.xz").read_bytes()))
        cls.replayed = []
        for recorded, supply in steps[:STOP_ROW]:
            key = policy.choose_key(supply())
            cls.replayed.append((recorded["row"], (key, policy.last_reason),
                                 (recorded["key"], recorded["reason"])))
            policy.confirm_key_posted(recorded["key"])
            if recorded["row"] == 0:
                adopt_calibration(policy, dumped, scratch / "runtime")
        cls.board = steps[STOP_ROW][1]()
        cls.checkpoint = checkpoint_bytes(policy)
        cls.knowledge_ledger = scratch / "knowledge.jsonl"

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        for row, decided, recorded in self.replayed:
            if row not in FORCED:
                self.assertEqual(decided, recorded, row)
        self.policy = restore_checkpoint_bytes(HengbotPolicy, self.checkpoint)
        self.addCleanup(lambda: self.policy._home_disposal.history_path.unlink(missing_ok=True))

    def raw(self, row):
        entry = self.journal[row]
        return json.loads(entry["line"] if entry["line"] is not None else entry["inputs"][-1])

    def test_the_stop_board_scans_home_instead_of_stopping(self):
        self.assertEqual((self.journal[STOP_ROW]["key"], self.journal[STOP_ROW]["reason"]),
                         ("1", STOP))
        policy, board = self.policy, self.board
        self.assertIsNone(board.store)
        self.assertTrue(policy._inventory_overweight(board))
        self.assertFalse(policy._home_is_full(board))
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        self.assertTrue(policy._home_rejected_deposits)
        self.assertFalse(policy._overweight_home_bound_exhausted())
        self.assertEqual(policy._home_full_retry_deposits, ((RETRY, 1, 1),))
        self.assertEqual(policy._item_signature(policy._find_home_deposit(board)), RETRY)

        key = policy.choose_key(board)

        self.assertEqual((key, policy.last_reason), ("~9\x1b", "home:request-knowledge-scan"))
        self.assertIsNone(policy._town_blocked_reason)

    def test_home_is_reached_and_takes_a_deposit(self):
        policy = self.policy
        key = policy.choose_key(self.board)
        policy.confirm_key_posted(key)
        line = self.raw(STOP_ROW)
        # DECLARED CONSTRUCTED (module docstring): the scan's Home list.
        knowledge = copy.deepcopy(next(
            record for record in map(json.loads, self.journal[KNOWLEDGE_ROW]["inputs"])
            if record.get("type") == "knowledge"
            and record["knowledge"].get("category") == "home"))
        items = knowledge["knowledge"]["items"]
        self.assertEqual(sum(item["name"].startswith(SOLD) for item in items), 1)
        knowledge["knowledge"]["items"] = [
            item for item in items if not item["name"].startswith(SOLD)]
        for field in ("turn", "inventory", "equipment", "player"):
            knowledge[field] = line[field]
        _consume_response_sequence(
            [json.dumps(record, ensure_ascii=False) + "\n" for record in (knowledge, line)],
            policy, lambda _key: True, policy._monrace_knowledge, parse_snapshots=False,
            knowledge_ledger_path=self.knowledge_ledger)

        key = policy.choose_key(parse_snapshot(copy.deepcopy(line), policy._monrace_knowledge))

        self.assertEqual((key, policy.last_reason),
                         (f"\x1b`n{TOWN_TRAVEL_STORE_SYMBOLS[STORE_HOME]}.", "shop:travel"))
        self.assertEqual(policy._shopping_approach_store_type, STORE_HOME)
        policy.confirm_key_posted(key)
        # DECLARED CONSTRUCTED (module docstring): Home's page with its free slot.
        page = copy.deepcopy(self.raw(HOME_PAGE_ROW))
        self.assertEqual((page["store"]["store_type"], page["store"]["stock_num"],
                          page["store"]["capacity"]), (STORE_HOME, 240, 240))
        for field in ("inventory", "equipment", "player"):
            page[field] = line[field]
        page["turn"] = line["turn"] + 10
        page["store"]["stock_num"] = 239
        policy.observe_store_screen(True)

        key = policy.choose_key(parse_snapshot(page, policy._monrace_knowledge))

        self.assertTrue(key.startswith("d"), (key, policy.last_reason))
        self.assertIsNone(policy._town_blocked_reason)

    def test_an_exhausted_home_bound_still_stops_by_name(self):
        policy = self.policy
        policy._town_visit_ledger.approach_fails[STORE_HOME] = (
            policy._town_store_visit_limit(STORE_HOME))

        key = policy.choose_key(self.board)

        self.assertEqual((key, policy.last_reason), ("1", STOP))


if __name__ == "__main__":
    unittest.main()
