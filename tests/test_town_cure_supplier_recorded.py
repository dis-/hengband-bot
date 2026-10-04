"""Recorded pins: a departure shortage is not routed to a shelf seen without it.

Live stop 2026-10-03 12:04:21 (``town:blocked:owner-retired``, turn 6484634,
commit 155e2829, ``--enforce-crossarea-fundraising``).  The 11:59:45 bot
process is frozen whole by tests/extract_town_cure_supplier_fixture.py (1391
decisions; indices below are decision indices of that process):

- 101-1354: a five-run Yeek Cave 1F mining set (gold 473 -> 11932).  Each run
  wields the digger and reads 財宝感知の巻物 on the cave floor
  (``fundraise:detect-treasure`` at 112, 501, 919, 1081 and 1314, dungeon 2
  level 1), ascends, and restores the combat weapon in town.  No treasure
  detection is read in town (``test_detection_is_read_on_yeek_cave_one``).
- 1367: the set ends by run count; the departure now needs 致命傷の治療の薬
  6/10 (gold 11068 after 1384).
- 1381-1384: the Alchemist page shows no 致命傷の治療の薬; the bot buys
  腕力復活の薬 there, so the Alchemist is never marked attempted.  The Temple
  page (observed at 1364, now older than the restock turnover) held 18 of
  them at 144 gold.
- 1386-1387: Home (plan stop 0) has no composable work
  (``home:route-claim-unfulfilled``).
- 1388: the plan's cure-critical stop is still the Alchemist (policy_town.py
  ``_town_need_candidates``: a supply store is a supplier while "not
  attempted", whatever this visit's page showed).  The travel Home->Alchemist
  scores the same arbiter vector as Alchemist->Home at 1386 (no durable change,
  equal distances), so ``store-router`` retires.
- 1389-1390: the Alchemist page again has nothing wanted; the rebuilt plan's
  next stop is refused for the retired router and nobody owns the decision:
  ``town:blocked:owner-retired``.

Fix (policy_town.py ``_town_need_candidates`` with
``_shortage_supplier_visit_page``): a shop whose page was observed in this
town visit is a supplier of a departure shortage only when that page passes
the supply ledger's own predicate (policy_supply.py ``_supply_page_offers``:
a matching ware -- a charged device for a MANA eater's food -- within gold or
on a store not yet attempted).  Without a page of this visit the earlier
rule stands.  The two DECLARED CONSTRUCTED variants of board 1388 pin that
parity (review F1/F2: MANA food at the Magic shop, an unaffordable ware on
an unattempted store).  Board 1388
then travels to the Temple (``$``).  That key differs from live, so no later
board is the effect of the fixed key (R4); the pin stops at 1388.

One replay of the process through ``CHECKPOINT`` is shared by every pin
(setUpClass); each pin continues from a deep copy.  Declared walls:

- LIVE-KEY WALL 0-``CHECKPOINT``: the live process held the C-sheet
  calibration of its 11:59:55 dump and ran equipment transactions on it; the
  dump file is not in the capture, so the replay has no calibration and
  decides differently on the boards listed in ``PREFIX_DIVERGENCES``
  (9-73: the Home equipment work; 1057: the transaction's stale-identity
  label; 1377-1378: the live ``town:kill-mob-approach`` the replay reads as
  ``store:entry-await-observation`` -- not explained).  The live key is posted
  on every prefix board, so every later board is the one live observed.
  DECLARED DIVERGENCE (89543e80, SOL-REPORT-homefull3.txt section 1 C):
  the filed identification Home errand requests its stale catalogue at 15
  (turn 6453654), replacing the base replay's home:weight-overload-deposit
  ('5'; live had an equipment entry wait). On that board no atomic
  operation is pending and no physical hostile is present. The command is
  now '~9 ESC', owned and declared by home-errand. This is inside the existing
  LIVE-KEY WALL: every old key is still posted, so the later 16-53 boards are
  historical substrates, not effects of this new scan. The added divergences
  19-25, 27-33, 35-36 and 53, and restored parity at 51-52, belong to that
  declared wall. The complete exact divergence set remains pinned; the first
  new request's prerequisite facts, command, claim and declaration are pinned
  separately. The supplier fix itself changes no prefix decision (1388 is
  its first changed key).
- CLI TIMER WALL: the periodic dump/save requests come from the CLI wall
  clock; each is delivered on the board where the live process posted it.
- PRE-FIX WALL (``_pre_fix_supply_rule``): ``_shortage_supplier_visit_page``
  answers None, which is exactly the rule before the fix; under it the
  replay reproduces the live stop.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import copy
import gzip
import hashlib
import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.model import (
    DUNGEON_YEEK_CAVE,
    STORE_ALCHEMIST,
    STORE_HOME,
    STORE_MAGIC,
    STORE_TEMPLE,
    SV_POTION_CURE_CRITICAL,
    StoreItem,
    StoreState,
    TVAL_POTION,
    TVAL_WAND,
)
from hengbot.policy_constants import FOOD_TYPE_MANA
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import TOWN_TRAVEL_STORE_SYMBOLS

from test_esp_threat_rest_recorded import EDIT, _policy

FIXTURES = Path(__file__).parent / "fixtures"
STEM = "town-cure-supplier-20261003"
FIXTURE = FIXTURES / f"{STEM}.jsonl.gz"
BOUNDARIES = FIXTURES / f"{STEM}.boundaries.json"
# R9: digests of the bytes with CRLF normalized to LF.
SHA256 = {
    FIXTURE: "87ebcb785112844337c6d7b78e0a9ae0dbea535f50ac48795e335136196b8a88",
    BOUNDARIES: "2d7bc580efc7b664973ddcf077e00866c4e4578ae73d401a2239e2f23a09e834",
}
CHECKPOINT = 1380
ALCHEMIST_BUY = 1384
HOME_UNFULFILLED = 1387
FIRST_CHANGED = 1388
STOP = 1390
PREFIX_DIVERGENCES = (
    9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
    27, 28, 29, 30, 31, 32, 33, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 53,
    69, 70, 71, 72, 73, 1057, 1377, 1378,
)
PERIODIC_REQUESTS = {
    "periodic:character-dump": "request_character_dump",
    "periodic:game-save": "request_game_save",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@contextmanager
def _no_wall():
    yield


@contextmanager
def _mana_food_short():
    """DECLARED CONSTRUCTED: the Zombie's carried MANA food charges are 0.

    The live character is a MANA eater (food_type 4); with no carried
    charges its food is a departure shortage supplied by the Magic shop.
    """
    with patch.object(
        HengbotPolicy, "_count_mana_food_uses", lambda self, snapshot: 0,
    ):
        yield


@contextmanager
def _pre_fix_supply_rule():
    """DECLARED WALL: the pre-fix rule (no visit page answers a supplier)."""
    with patch.object(
        HengbotPolicy, "_shortage_supplier_visit_page",
        lambda self, snapshot, store_type: None,
    ):
        yield


class _RecordedProcess(unittest.TestCase):
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
        cls._tmp = TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        policy = _policy(cls.directory, cls.monrace)
        policy._crossarea_fundraising_enforced = True  # live argv
        cls.prefix = []
        cls.detect_boards = {}
        cls.home_knowledge_boundary = {}

        def inspect_knowledge(index, policy, board):
            if index != 15:
                return
            cls.home_knowledge_boundary = dict(
                turn=board.turn, needs_knowledge=policy._home_errand.needs_knowledge,
                purpose=policy._home_errand.request.purpose,
                knowledge_current=policy._home_knowledge_current,
                deposit_pending=policy._home_atomic_deposit_pending is not None,
                withdraw_pending=policy._home_atomic_withdraw_pending is not None,
                physical_hostiles=bool(policy._physical_hostiles(board)),
                hp=(board.player.hp, board.player.max_hp), food=board.player.food_state,
                adverse_status=bool(board.player.poisoned or board.player.cut
                                    or board.player.confused or board.player.blind),
                claim=copy.deepcopy(policy.decision_claim))

        for index in range(CHECKPOINT + 1):
            key, reason, board = cls._step(
                policy, index, live_key=True, inspect=inspect_knowledge)
            cls.prefix.append((key, reason))
            if cls.recorded[index]["reason"] == "fundraise:detect-treasure":
                cls.detect_boards[index] = (
                    board.floor_key[0], board.dungeon_level, board.in_town)
        cls.files = {path: path.read_bytes()
                     for path in cls.directory.rglob("*") if path.is_file()}
        cls.checkpoint = copy.deepcopy(policy, {id(cls.monrace): cls.monrace})

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def _step(cls, policy, index, *, live_key=False, inspect=None,
              prepare=None):
        _decoded, snapshots = _consume_response_sequence(
            cls.segments[index], policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=cls.directory / "knowledge.jsonl",
        )
        board = snapshots[-1]
        if prepare is not None:
            prepare(index, policy, board)
        live = cls.recorded[index]
        request = PERIODIC_REQUESTS.get(live["reason"])
        if request is not None:
            # DECLARED WALL (CLI timer): delivered where live posted it.
            getattr(policy, request)()
        key = str(policy.choose_key(board))
        reason = policy.last_reason
        if inspect is not None:
            inspect(index, policy, board)
        posted = live["key"] if live_key else key
        policy.confirm_key_posted(posted)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, posted):
            policy.commit_staged_prompt_chain(
                {"outcome": "released", "posted": str(posted)})
        return key, reason, board

    def _resume(self):
        """A fresh copy of the policy (and its files) after ``CHECKPOINT``."""
        for path in self.directory.rglob("*"):
            if path.is_file() and path not in self.files:
                path.unlink()
        for path, data in self.files.items():
            path.write_bytes(data)
        return copy.deepcopy(self.checkpoint, {id(self.monrace): self.monrace})

    def _continue(self, last, *, inspect=None, prepare=None):
        policy = self._resume()
        return [
            self._step(policy, index, inspect=inspect, prepare=prepare)[:2]
            for index in range(CHECKPOINT + 1, last + 1)
        ]

    @staticmethod
    def _observe_page(policy, board, store_type, items):
        """DECLARED CONSTRUCTED: a shelf of ``store_type`` seen this visit.

        Recorded exactly as the in-store observation records a page
        (policy.py ``_decide``: ``_town_supplier_stock`` and its
        ``(town, turn)`` observation), one turn before the board.
        """
        policy._town_supplier_stock[store_type] = StoreState(store_type, items)
        policy._town_supplier_stock_observations[store_type] = (
            policy._effective_town_id(board), board.turn - 1,
        )

    def _planned_stops(self, prepare, *, wall=None):
        """The real ``choose_key`` plan on board ``FIRST_CHANGED``."""
        seen = {}

        def inspect(index, policy, board):
            if index == FIRST_CHANGED:
                plan = policy._town_errand_plan
                seen["stops"] = {
                    category: sorted(
                        store for store, categories in plan.need_categories.items()
                        if category in categories)
                    for category in ("cure-critical", "food")
                }
                ledger = policy._supply_ledger(board, policy._planned_depth())
                seen["ledger"] = {
                    kind: (status.obtainable, status.stores)
                    for kind, status in ledger.items()
                    if status.count < status.required_departure
                }

        def staged(index, policy, board):
            if index == FIRST_CHANGED:
                prepare(policy, board)

        with (wall() if wall is not None else _no_wall()):
            rows = self._continue(FIRST_CHANGED, inspect=inspect, prepare=staged)
        self.assertEqual(
            rows[:-1],
            [self._live(index) for index in range(CHECKPOINT + 1, FIRST_CHANGED)])
        return seen, rows[-1]

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]


class TownCureSupplierRecordedTest(_RecordedProcess):
    def test_walled_prefix_reproduces_live_except_declared_boards(self):
        divergent = tuple(
            index for index in range(CHECKPOINT + 1)
            if self.prefix[index] != self._live(index)
        )
        self.assertEqual(divergent, PREFIX_DIVERGENCES)
        self.assertEqual(self._live(15),
                         ("5", "equipment-transaction:travel-home:await-entry"))
        self.assertEqual(self.prefix[15],
                         ("~9\x1b", "home-errand:request-knowledge:identification"))
        boundary = dict(self.home_knowledge_boundary)
        claim = boundary.pop("claim")
        self.assertEqual(boundary, dict(
            turn=6453654, needs_knowledge=True, purpose="identification",
            knowledge_current=False, deposit_pending=False, withdraw_pending=False,
            physical_hostiles=False, hp=(731, 731), food="normal", adverse_status=False))
        self.assertEqual((claim["owner"], claim["goal"]["kind"], claim["goal"]["source"]),
                         ("home-errand", "Observe", "knowledge"))
        self.assertEqual(claim["rung"], "_home_errand_knowledge_key")
        execution = claim["execution"]
        self.assertEqual((execution["producer"], execution["next_step"],
                          execution["expected_effect"], execution["continuation"]),
                         ("home-errand", "home.knowledge.request",
                          "catalogue-adopted", "home.knowledge.observe"))
        for field in ("violation", "declaration_mismatch", "claim_verdict_conflict"):
            self.assertIsNone(claim[field], field)

    def test_recorded_stay_ends_without_an_owner(self):
        self.assertEqual(TOWN_TRAVEL_STORE_SYMBOLS[STORE_ALCHEMIST], "%")
        self.assertEqual(TOWN_TRAVEL_STORE_SYMBOLS[STORE_TEMPLE], "$")
        self.assertEqual(TOWN_TRAVEL_STORE_SYMBOLS[STORE_HOME], "(")
        self.assertEqual(self._live(ALCHEMIST_BUY),
                         ("pa1\r\r\x1b", "shop:one-shot-buy"))
        self.assertEqual(self._live(HOME_UNFULFILLED),
                         ("\x1b", "home:route-claim-unfulfilled"))
        self.assertEqual(self._live(FIRST_CHANGED), ("\x1b`n%.", "shop:travel"))
        arbiter = self.detail[str(FIRST_CHANGED)]["arbiter"]
        self.assertEqual((arbiter["progress"], arbiter["retirement_set"]),
                         (False, ["store-router"]))
        self.assertEqual(self.detail[str(STOP - 1)]["store_type"], STORE_ALCHEMIST)
        self.assertEqual(self._live(STOP), ("7", "town:blocked:owner-retired"))
        stop = self.detail[str(STOP)]
        self.assertEqual(stop["procurement_requirements"], [{
            "item": "Cure Critical Wounds potions",
            "current": 6, "target": 10, "missing": 4,
        }])
        self.assertEqual(stop["gold"], 11068)

    def test_pre_fix_rule_reproduces_the_live_stop(self):
        with _pre_fix_supply_rule():
            rows = self._continue(STOP)
        self.assertEqual(
            rows, [self._live(index) for index in range(CHECKPOINT + 1, STOP + 1)])

    def test_visit_page_without_the_ware_routes_to_the_stocked_temple(self):
        seen = {}

        def inspect(index, policy, board):
            if index != FIRST_CHANGED:
                return
            gold = board.player.gold

            def cure_offers(store_type, *, remembered=False):
                page = (
                    policy._town_supplier_stock.get(store_type) if remembered
                    else policy._shortage_supplier_visit_page(board, store_type)
                )
                return None if page is None else [
                    (item.count, item.price) for item in page.items
                    if item.tval == TVAL_POTION
                    and item.sval == SV_POTION_CURE_CRITICAL
                    and item.price <= gold
                ]

            seen["alchemist"] = cure_offers(STORE_ALCHEMIST)
            seen["temple"] = cure_offers(STORE_TEMPLE)
            seen["temple_remembered"] = cure_offers(STORE_TEMPLE, remembered=True)
            cure = policy._supply_ledger(board, policy._planned_depth())["cure"]
            seen["cure"] = (cure.count, cure.required_departure, cure.obtainable)
            plan = policy._town_errand_plan
            seen["cure_stops"] = sorted(
                store for store, categories in plan.need_categories.items()
                if "cure-critical" in categories)
            telemetry = policy._town_turn_arbiter.telemetry
            seen["arbiter"] = (telemetry["progress"], telemetry["retirement_set"])

        rows = self._continue(FIRST_CHANGED, inspect=inspect)
        self.assertEqual(
            rows[:-1],
            [self._live(index) for index in range(CHECKPOINT + 1, FIRST_CHANGED)])
        # This visit's Alchemist page (1382) has none; the Temple page (1364)
        # is older than the restock turnover, so the Temple stays a candidate
        # (and its remembered page shows the stock).
        self.assertEqual(seen["alchemist"], [])
        self.assertIsNone(seen["temple"])
        self.assertEqual(seen["temple_remembered"], [(18, 144)])
        self.assertEqual(seen["cure"], (6, 10, True))
        self.assertEqual(seen["cure_stops"], [STORE_TEMPLE])
        self.assertEqual(seen["arbiter"], (True, []))
        # First changed key versus live (Alchemist travel): stop here (R4).
        self.assertEqual(rows[-1], ("\x1b`n$.", "shop:travel"))


    def test_visit_page_of_unattempted_store_counts_an_unaffordable_ware(self):
        """DECLARED CONSTRUCTED board 1388 (review F2): ledger parity.

        This visit's Alchemist page shows 致命傷の治療の薬 above the carried
        gold on a store not yet attempted; the Temple is attempted with an
        empty page of this visit.  The ledger names the Alchemist as the
        supplier (``_supply_page_offers``: not attempted), so the planner keeps
        its cure-critical stop there instead of dropping every cure stop.
        """
        def prepare(policy, board):
            gold = board.player.gold
            self._observe_page(policy, board, STORE_ALCHEMIST, [StoreItem(
                letter="a", name="致命傷の治療の薬", count=5,
                tval=TVAL_POTION, sval=SV_POTION_CURE_CRITICAL,
                price=gold + 1,
            )])
            self._observe_page(policy, board, STORE_TEMPLE, [])
            policy._town_store_attempted[STORE_TEMPLE] = board.turn - 1
            self.assertNotIn(STORE_ALCHEMIST, policy._town_store_attempted)

        seen, row = self._planned_stops(prepare)
        self.assertEqual(seen["ledger"]["cure"], (True, (STORE_TEMPLE, STORE_ALCHEMIST)))
        self.assertEqual(seen["stops"]["cure-critical"], [STORE_ALCHEMIST])

    def test_visit_magic_page_supplies_mana_food_with_a_charged_device(self):
        """DECLARED CONSTRUCTED board 1388 (review F1): MANA food parity.

        With no carried MANA food charges (``_mana_food_short``) the ledger's
        food supplier is the Magic shop, and a charged wand on its page of
        this visit is the ware (pval > 0).  The planner keeps the Magic food
        stop; reading the page with the ordinary food predicate dropped it.
        """
        def prepare(policy, board):
            self.assertEqual(board.player.food_type, FOOD_TYPE_MANA)
            self._observe_page(policy, board, STORE_MAGIC, [StoreItem(
                letter="a", name="マジック・ミサイルの魔法棒", count=1,
                tval=TVAL_WAND, sval=15, price=443, pval=13,
            )])
            self.assertNotIn(STORE_MAGIC, policy._town_store_attempted)

        seen, row = self._planned_stops(prepare, wall=_mana_food_short)
        # Home holds charged devices too, so it leads the ledger's suppliers.
        self.assertEqual(seen["ledger"]["food"], (True, (STORE_HOME, STORE_MAGIC)))
        self.assertIn(STORE_MAGIC, seen["stops"]["food"])

    def test_detection_is_read_on_yeek_cave_one(self):
        """The reported 'detect treasure read in town': it was not.

        Every ``fundraise:detect-treasure`` of the set replays the live key on
        a Yeek Cave 1F board, and each ``town:restore-combat-weapon`` follows
        the run's ``fundraise:ascend`` back in town.
        """
        self.assertEqual(sorted(self.detect_boards), [112, 501, 919, 1081, 1314])
        for index, (dungeon, level, in_town) in self.detect_boards.items():
            self.assertEqual((dungeon, level, in_town),
                             (DUNGEON_YEEK_CAVE, 1, False), index)
            self.assertEqual(self.recorded[index]["floor"], [DUNGEON_YEEK_CAVE, 1])
            self.assertEqual(self.prefix[index], self._live(index), index)
        restores = [index for index, row in enumerate(self.recorded)
                    if row["reason"] == "town:restore-combat-weapon"]
        for index in restores:
            self.assertEqual(self.recorded[index]["floor"], [0, 0], index)
            ascend = max(i for i in range(index)
                         if self.recorded[i]["reason"] == "fundraise:ascend")
            self.assertTrue(all(
                self.recorded[i]["floor"] == [0, 0]
                for i in range(ascend + 1, index + 1)), index)


if __name__ == "__main__":
    unittest.main()
