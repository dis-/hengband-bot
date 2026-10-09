"""Recorded pins: buy/sell on the observed shop page; skip shelf-proven stops.

SOL-DESIGN-store-reentry-20261003 (revision 2), user decisions 2026-10-03:
「入り直しの仕組みも含めて見直す」 (+「時間がかかるなら他作業と並行して、
なるべく実機を止めないように」) and the final-spec confirmation
「承認・自宅も段階2で変える」: Phase 0 (log-only shadow) and Phase 1
(ordinary shops, ``--in-store-shop-ops``, default off).  Home (Phase 2, pin
P10) is not part of this change.

Capture: the 10:49:42 bot process (commit c0cb88f6, both enforcement
switches off) of ``town-store-reentry-20261003-1056``, frozen whole by
tests/extract_store_reentry_fixture.py (847 decisions; indices below are
decision indices, equal to ``decision_sequence`` up to 167 and one/two more
after the two duplicated observation-probe rows 167 and 761).  Every one of
its 13 shop transactions was observed in one entry and performed in a second
(design 1.3); the one-shot release keys are the operation bodies an in-store
operation must reproduce.

The current replay stops at its first changed decision, index 18. Commit 628bd90b
added Identify-staff supplier routing: the user decision requires 20 charges,
so after Magic the Black Market is the next supplier. Index 18's recorded
Home-withdraw reason is stale, though its Escape key is unchanged; index 19
continues along the new route rather than the captured walk. Pins at 38, 42,
45, 159, 171, and 209 use DECLARED CONSTRUCTED independent b75db5e9
baseline-policy checkpoints. Later ordinary-shop pins through the old
boundary 802 use
DECLARED CONSTRUCTED independent 3b12a514 checkpoints frozen by
extract_suitefix4_checkpoints.py. The old partial-Home absence-proof boundary
802 and later live-key walls remain checked on independent substrates. Pins
beyond 802 use DECLARED CONSTRUCTED independent baseline-policy checkpoints
from group 2 (90fca3b7), produced by extract_s33_store_checkpoints.py and
frozen with a hash. These are independent operation substrates, not a
continued current trajectory or recovered live checkpoints. Their runtime
files are redirected to this test's temporary directory.

The prefix replay, switch off, is shared by every pin
(setUpClass); checkpoints are pickled before the boards the pins decide, and
every pin continues from its own copy (R4: no recorded board after a changed
key is used, except the DECLARED CONSTRUCTED substitutions named in a pin).
Declared walls, all in ``_step``/``_dump_wall``/``_switch_on``:

- DUMP WALL: the C-sheet dump file is not in the capture; at each posted
  dump's completion the frozen record whose printed stat key matches the
  board is installed (the 07:47 record of
  identify-staff-swap-churn-20261003, the drained-Strength record of
  lethal-unseen-caster-20261003, or the CHR-15 record frozen from
  jsonlog/character-calibration.json as
  store-reentry-20261003.character-calibration.json; their stat fields
  differ only in the printed stats).
- CLI TIMER WALL: the periodic dump/save requests come from the CLI wall
  clock; each is delivered on the board where the live process posted it
  (also when the live row shows it rewritten by the progress invariant).
- UNSEEN-HIT WALL: pre_unseen_scratch_bound_rule restores the capture-era
  unseen-hit threshold (main now ignores immaterial scratches).
- LIVE-KEY WALL 9-12, 17, 159, 171, 219, 267, 273: main-only src reproduces
  these divergences: Home travel/scan/reserve after dumps (9-12), town
  probe versus boxed-breakout travel (17), store observation ownership
  rewriting/suppressing kill-mob approach (171, 219), ranged fire before recall wait (159),
  and strong-fight-speed use (267, 273). The live keys are posted. With the
  walls every other key and reason before 212 is reproduced, switch off
  (pin P0); later wall sites use independent baseline substrates.
- SCREEN WALL: the capture holds no screen.  Phase 1 acts only when the
  executor's slot-by-slot screen check passed on the same board (design 3.1
  condition 3); the CLI supplies it through ``observe_store_screen``.  On a
  recorded STORE board the pins declare it True; the negative is P4.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
import base64
import hashlib
import io
import json
import pickle
import unittest
from contextlib import contextmanager, redirect_stderr
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from hengbot.cli import (
    _ExecutorInputPort,
    _send_new_decision_key,
    SendResult,
    _configure_in_store_shop_ops,
    _consume_response_sequence,
    _store_buy_continuations,
    _town_plan_state,
)
from hengbot.control_client import ControlClient
from hengbot.input_executor import (
    Operation,
    OperationExecutor,
    ScreenKind,
    _PURCHASE_REFUSAL_MESSAGES,
)
from hengbot.model import (
    STORE_ALCHEMIST,
    STORE_BLACK,
    STORE_MAGIC,
    STORE_TEMPLE,
    SV_SCROLL_STAR_IDENTIFY,
    TVAL_SCROLL,
    TVAL_WAND,
    TVAL_STAFF,
    StoreItem,
    StoreState,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.observed_input import compile_observed_input
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import (
    FOOD_TYPE_MANA,
    IN_STORE_BREAKER_FILE_NAME,
    STORE_MAINTENANCE_INTERVAL_TURNS,
    STORE_STUCK_LIMIT,
)
from hengbot.policy_instore import shelf_signature
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_types import StoreVisitPhase
from hengbot.warrior_optimization import load_character_calibration

from unseen_scratch_walls import pre_unseen_scratch_bound_rule
from test_esp_threat_rest_recorded import EDIT, _policy
from test_input_executor import (
    FaithfulHookGame, command_screen, prompt_screen, store_screen,
)
from suitefix4_checkpoints import restore as restore_independent

FIXTURES = Path(__file__).parent / "fixtures"
STEM = "store-reentry-20261003"
FIXTURE = FIXTURES / f"{STEM}.jsonl.gz"
BOUNDARIES = FIXTURES / f"{STEM}.boundaries.json"
CALIBRATION = FIXTURES / f"{STEM}.character-calibration.json"
CALIBRATION_0747 = FIXTURES / "identify-staff-swap-churn-20261003.character-calibration.json"
DRAINED_CALIBRATION = FIXTURES / "lethal-unseen-caster-20261003.character-calibration.json"
# R9: digests of the bytes with CRLF normalized to LF.
SHA256 = {
    FIXTURE: "d08e50cedfa3b122a43fbd360650e7679aace30a89fa49c0e00aca181f27f467",
    BOUNDARIES: "f520c2fbd161847d6c4a6956c2b4c333b276c765385680e78a03be96525b64ee",
    CALIBRATION: "c97a96a0cec90b7fd4f8e2c84898ab4e1455100ca4e07f9b58b122af311ad362",
    CALIBRATION_0747: "5ce8f502589e2d96662f96819b5ec034762a9ee8ba6b1d4e9746ad3824235cbc",
    DRAINED_CALIBRATION: "89681faaab50a350d0994cd790788bb424bd4f8a12f1f7801767c327c7773f4c",
}
# Verified against main-only src at a9767a0e (same divergence indices):
# 9-12: legacy Home travel/scan/identify-staff reserve replay after dumps.
# 17: legacy town probe versus recorded boxed-breakout travel.
# 171, 219: store observation ownership rewrites/suppresses kill-mob approach.
# 159: main ranged-fire precedence replaces return:wait-recall.
# 267, 273: main strong-fight-speed decisions added after capture.
LIVE_KEY_WALL = frozenset({9, 10, 11, 12, 17, 159, 171, 219, 267, 273})
S33_FIRST_CHANGED = 212
PRE_STAR_ID_FIRST_CHANGED = 802
ROUTE_CHECKPOINTS = FIXTURES / "store-reentry.route-independent-checkpoints.json.gz"
ROUTE_CHECKPOINTS_SHA256 = "2b58ac46317daff39ef7fe2e6ea341b2f7910547fa27e7dfe93221435c720e1b"
STAR_ID_CHECKPOINTS = FIXTURES / "store.suitefix4-independent-checkpoints.json.gz"
STAR_ID_CHECKPOINTS_SHA256 = "76859f45c779daf79f2888b26a618f0ecfdff3c8e921a8b1eceeff45a23dd529"
S33_CHECKPOINTS = FIXTURES / "store-reentry.s33-independent-checkpoints.json.gz"
S33_CHECKPOINTS_SHA256 = "3a56680f4c0dcf802b89757ab9e4395d8415a6439745893218da95caf6ccd824"

PERIODIC_REQUESTS = {
    "periodic:character-dump": "request_character_dump",
    "periodic:game-save": "request_game_save",
}
# Observe-and-leave page -> the one-shot release of the same shelf (design P1).
P1_RELEASES = {
    38: 40, 42: 44, 209: 211, 213: 215, 226: 228, 790: 792,
    811: 813, 826: 828, 830: 832, 834: 836, 844: 846,
}
MAGIC_OBSERVE = 817       # seq 815, state row 1060: Magic, 1-charge staff unsold
MAGIC_RELEASE_PAGE = 1064  # state row: the sale's release page (staff tagged {@1})
MAGIC_AFTER_SALE = 1065    # state row: written right after 'd1y', before ESC
MAGIC_BUY_ROW = 60         # state row: written right after 'pi1\r\r' (seq 40)
MAGIC_BUY_EXIT = 61        # state row: the entrance board after that ESC
P5_SKIPS = {45: (STORE_BLACK, "black-market"),
            216: (STORE_ALCHEMIST, "identification-source"),
            795: (STORE_ALCHEMIST, "identification-source")}
P6_KEEPS = {785: STORE_ALCHEMIST, 808: STORE_MAGIC, 821: STORE_ALCHEMIST}
ALCHEMIST_RESTOCK = 822   # seq 820, state row 1069 (row 1021 -> 1069 restock)
CHECKPOINTS = frozenset({
    *P1_RELEASES, *P5_SKIPS, *P6_KEEPS, MAGIC_OBSERVE, ALCHEMIST_RESTOCK,
    796, 786,
})

# Named policy divergences introduced by 628bd90b (identify-staff supplier
# routing). The 2026-09-17 user decision requires 20 Identify-staff charges;
# after Magic is exhausted, the Black Market is the next supplier. At index
# 18 the old Home-withdraw reason is stale, though Escape is still the same
# posted key. Index 19 follows the new Black Market route instead of the
# recording's old walk. Later pins use independent baseline-policy checkpoints.
DECLARED_POLICY_DIVERGENCES = {
    18: "Home withdrawal claim is stale; the recorded Escape has no pending Home item/batch.",
    19: "Identify-staff procurement now routes to the Black Market after Magic (628bd90b; user decision 2026-09-17).",
}

# USER DECISION 2026-10-08: optional Black Market spending must leave the full
# departure resupply reserve intact; base-item prices establish it where known.
DECLARED_OPTIONAL_BLACK_MARKET_BUYS = {42, 834}
DECLARED_OPTIONAL_BLACK_MARKET_REFUSALS = {844}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


_RECORDS = ()


def _recorded_dump(self, pending, character, envelope, board=None):
    """DECLARED WALL (dump): the frozen record for the board's printed stats."""
    key = board.player.printed_stat_cur_key
    matches = [record for record in _RECORDS if record.visible_stat_key == key]
    if len(matches) != 1:
        raise AssertionError(f"no frozen calibration for printed stats {key}")
    self._character_calibration = matches[0]
    self._character_calibration_loaded = True
    self._calibration_unavailable_reason = None
    self._calibration_rejection = None
    self._equipment_optimization_signature = None
    self._confirmed_loadout = None
    self._confirmed_loadout_loaded = True


@contextmanager
def _dump_wall():
    with pre_unseen_scratch_bound_rule(), patch.object(
            HengbotPolicy, "_publish_character_dump", _recorded_dump):
        yield


class _Pickler(pickle.Pickler):
    def __init__(self, stream, monrace):
        super().__init__(stream)
        self.monrace = monrace

    def persistent_id(self, obj):
        return "monrace" if obj is self.monrace else None


class _Unpickler(pickle.Unpickler):
    def __init__(self, stream, monrace):
        super().__init__(stream)
        self.monrace = monrace

    def find_class(self, module, name):
        # Python 3.13 checkpoints moved concrete Path classes into this
        # module; the Codex Python 3.12 runtime exposes the same classes in
        # pathlib. Restore the path value without altering policy state.
        if module == "pathlib._local" and name in {
            "Path", "WindowsPath", "PosixPath", "PurePath",
            "PureWindowsPath", "PurePosixPath",
        }:
            import pathlib
            return getattr(pathlib, name)
        return super().find_class(module, name)

    def persistent_load(self, pid):
        assert pid == "monrace"
        return self.monrace


class StoreReentryRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _RECORDS
        for path, digest in SHA256.items():
            assert _sha(path) == digest, path
        _RECORDS = tuple(load_character_calibration(path) for path in (
            CALIBRATION_0747, DRAINED_CALIBRATION, CALIBRATION))
        boundaries = json.loads(BOUNDARIES.read_text(encoding="utf-8"))
        cls.boundaries = boundaries
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = stream.read().splitlines(keepends=True)
        assert len(cls.lines) == sum(boundaries["input_rows"])
        cls.segments = []
        start = 0
        for count in boundaries["input_rows"]:
            cls.segments.append(cls.lines[start:start + count])
            start += count
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls._tmp = TemporaryDirectory()
        cls.directory = Path(cls._tmp.name)
        policy = _policy(cls.directory, cls.monrace)
        policy._character_calibration_path.write_bytes(CALIBRATION_0747.read_bytes())
        # The CLI sets the dump path; the dump wall supplies its contents.
        policy._character_dump_path = cls.directory / "character-dump.txt"
        cls.checkpoints = {}
        cls.prefix = []
        cls.first_changed = None
        with _dump_wall():
            for index in range(len(cls.segments)):
                if index in CHECKPOINTS:
                    buffer = io.BytesIO()
                    _Pickler(buffer, cls.monrace).dump(policy)
                    cls.checkpoints[index] = buffer.getvalue()
                key, reason, _board = cls._step(policy, index)
                cls.prefix.append((key, reason))
                if (index not in LIVE_KEY_WALL
                        and (key, reason) != (cls.recorded[index]["key"], cls.recorded[index]["reason"])):
                    cls.first_changed = index
                    break  # Never feed an old effect board after this changed key.
        assert cls.first_changed == min(DECLARED_POLICY_DIVERGENCES), cls.first_changed
        assert cls.first_changed in DECLARED_POLICY_DIVERGENCES
        assert hashlib.sha256(ROUTE_CHECKPOINTS.read_bytes()).hexdigest() == ROUTE_CHECKPOINTS_SHA256
        route_data = json.loads(gzip.decompress(ROUTE_CHECKPOINTS.read_bytes()))
        assert route_data["source_revision"] == "b75db5e9"
        assert route_data["input_sha256"] == SHA256[FIXTURE]
        assert route_data["construction"].startswith("DECLARED CONSTRUCTED independent baseline-policy checkpoints")
        cls.route_checkpoints = {int(i): base64.b64decode(data)
                                 for i, data in route_data["checkpoints"].items()}
        assert set(cls.route_checkpoints) == {38, 42, 45, 159, 171, 209}
        cls.checkpoints.update(cls.route_checkpoints)
        cls.route_independent_indices = set(cls.route_checkpoints)
        assert hashlib.sha256(S33_CHECKPOINTS.read_bytes()).hexdigest() == S33_CHECKPOINTS_SHA256
        independent = json.loads(gzip.decompress(S33_CHECKPOINTS.read_bytes()))
        assert independent["source_revision"] == "90fca3b7"
        assert independent["input_sha256"] == SHA256[FIXTURE]
        cls.independent_indices = {int(index) for index in independent["checkpoints"]}
        assert all(index > PRE_STAR_ID_FIRST_CHANGED for index in cls.independent_indices)
        cls.checkpoints.update({int(index): base64.b64decode(data)
                                for index, data in independent["checkpoints"].items()})
        assert hashlib.sha256(STAR_ID_CHECKPOINTS.read_bytes()).hexdigest() == STAR_ID_CHECKPOINTS_SHA256
        substrates = json.loads(gzip.decompress(STAR_ID_CHECKPOINTS.read_bytes()))
        assert substrates["source_revision"] == "3b12a514"
        assert substrates["input_sha256"] == SHA256[FIXTURE]
        cls.star_id_checkpoints = {int(i): record for i, record in substrates["checkpoints"].items()}
        assert all(S33_FIRST_CHANGED < i <= PRE_STAR_ID_FIRST_CHANGED for i in cls.star_id_checkpoints)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def _board(cls, index):
        return cls._parse(cls.segments[index])

    @classmethod
    def _parse(cls, lines, policy=None):
        _decoded, snapshots = _consume_response_sequence(
            lines, policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=cls.directory / "knowledge.jsonl",
        )
        return snapshots[-1]

    @classmethod
    def _step(cls, policy, index, *, board=None):
        if board is None:
            _decoded, snapshots = _consume_response_sequence(
                cls.segments[index], policy, lambda _key: True, cls.monrace,
                knowledge_ledger_path=cls.directory / "knowledge.jsonl",
            )
            board = snapshots[-1]
        live = cls.recorded[index]
        for marker, request in PERIODIC_REQUESTS.items():
            if marker in live["reason"]:
                # DECLARED WALL (CLI timer): delivered where live posted it.
                getattr(policy, request)()
        key = str(policy.choose_key(board))
        reason = policy.last_reason
        # DECLARED WALL (live keys): post what live posted (module docstring).
        posted = live["key"] if index in LIVE_KEY_WALL else key
        cls._post(policy, posted)
        return key, reason, board

    @staticmethod
    def _post(policy, posted, owner=None, outcome=None):
        """The CLI's post-send reconciliation for an accepted key."""
        if owner is not None:
            policy.reconcile_input_operation(owner, outcome)
        policy.confirm_key_posted(posted)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, posted):
            policy.commit_staged_prompt_chain(
                {"outcome": "released", "posted": str(posted)})

    def _resume(self, index):
        if index in self.star_id_checkpoints:
            policy = restore_independent(self.star_id_checkpoints[index], self.monrace, self.directory)
            normalize_policy_state(policy)
            return policy
        policy = _Unpickler(io.BytesIO(self.checkpoints[index]), self.monrace).load()
        if index in self.independent_indices or index in self.route_independent_indices:
            old_directory = policy._character_calibration_path.parent
            for name, value in tuple(vars(policy).items()):
                if isinstance(value, Path) and value.is_relative_to(old_directory):
                    setattr(policy, name, self.directory / value.relative_to(old_directory))
        normalize_policy_state(policy)
        return policy

    def _switch_on(self, policy, breaker_dir=None):
        """``--in-store-shop-ops`` through the CLI's own configuration."""
        directory = Path(breaker_dir or self.directory)
        with redirect_stderr(io.StringIO()):  # the startup banner
            _configure_in_store_shop_ops(policy, SimpleNamespace(
                in_store_shop_ops=True,
                decision_log=directory / "bot-decisions.jsonl",
            ))
        return policy

    def _decide(self, policy, board, *, screen=True):
        # DECLARED WALL (screen): the executor's slot-by-slot check on this
        # recorded STORE board (the capture holds no screen).
        policy.observe_store_screen(screen if board.store is not None else None)
        with _dump_wall():
            key = str(policy.choose_key(board))
        return key, policy.last_reason

    @staticmethod
    def _construct_known_departure_prices(policy, board):
        """DECLARED CONSTRUCTED: price data for purchase-mechanics-only pins."""
        prices = {}
        for status in policy._supply_ledger(
                board, policy._planned_depth()).values():
            if status.required_departure:
                category = "cure-critical" if status.kind == "cure" else status.kind
                prices[category] = (1, 1)
        prices.update({
            "recall": (1, 1), "teleport": (1, 1), "cure-critical": (1, 1),
            "oil": (1, 1), "food": (1, 1), "light": (1, 1),
            "identify-staff": (1, 1), "quest:speed": (1, 1),
            "quest:healing": (1, 1), "remove-curse": (1, 1),
        })
        strategy = policy._carry_procurement_strategy(board)
        if strategy is not None:
            for name, status in policy._quest_carry_status(
                    board, strategy.required_force).items():
                if int(status["required"]):
                    prices[f"quest-carry:{name}"] = (1, 1)
        policy._observed_departure_prices.update(prices)
        return policy._full_departure_resupply_reserve(board)

    def _construct_optional_purchase_board(self, policy, board, index, units):
        reserve = self._construct_known_departure_prices(policy, board)
        self.assertIsNotNone(reserve)
        wanted = self.boundaries["facts"][str(index)][
            "shop_selector"]["wanted_purchase"]
        total = wanted["price"] * units
        constructed = replace(
            board, player=replace(board.player, gold=reserve + total + 1))
        self.assertGreaterEqual(constructed.player.gold - total, reserve)
        return constructed, reserve

    def _row(self, number):
        return self._parse([self.lines[number]])

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]

    def test_identify_staff_supplier_routing_divergences_are_declared(self):
        self.assertEqual(len(self.prefix), min(DECLARED_POLICY_DIVERGENCES) + 1)
        self.assertEqual(set(DECLARED_POLICY_DIVERGENCES), {18, 19})
        self.assertIn("Home withdrawal claim is stale", DECLARED_POLICY_DIVERGENCES[18])
        self.assertIn("628bd90b", DECLARED_POLICY_DIVERGENCES[19])
        self.assertEqual(self.prefix[18][0], self._live(18)[0])
        self.assertNotEqual(self.prefix[18], self._live(18))

    # ------------------------------------------------------------ P0
    def test_p0_switch_off_replay_reproduces_every_recorded_key(self):
        """Flag off: faithful prefix, then named supplier-routing divergences."""
        for index, row in enumerate(self.prefix):
            if index in DECLARED_POLICY_DIVERGENCES:
                self.assertIn(index, DECLARED_POLICY_DIVERGENCES)
            elif index not in LIVE_KEY_WALL:
                self.assertEqual(row, self._live(index), index)
        # The live-key wall is load-bearing.
        for index in LIVE_KEY_WALL:
            if index < len(self.prefix):
                self.assertNotEqual(self.prefix[index], self._live(index), index)
            else:
                with _dump_wall():
                    result = self._step(self._resume(index), index)[:2]
                self.assertNotEqual(result, self._live(index), index)
        # Preserve the original absence-proof assertion on its independent
        # baseline substrate; it is not an effect of the changed Home trip.
        with _dump_wall():
            result = self._step(self._resume(PRE_STAR_ID_FIRST_CHANGED), PRE_STAR_ID_FIRST_CHANGED)[:2]
        self.assertEqual(result, (" ", "equipment-transaction:seek-home-page"))
        self.assertEqual(self._live(PRE_STAR_ID_FIRST_CHANGED),
                         ("\x1b", "equipment-transaction:withdraw-missing"))
        # Every shop transaction of the capture used two entries.
        for observe, release in P1_RELEASES.items():
            self.assertEqual(self._live(observe)[0], "\x1b")
            self.assertEqual(self._live(release)[1], "shop:one-shot-buy")
            # Re-decide the recorded page through the public path as well;
            # this keeps the flag-off pin sensitive to a reverted guard.
            policy = self._resume(observe)
            board = self._board(observe)
            if (observe in DECLARED_OPTIONAL_BLACK_MARKET_BUYS
                    or observe in DECLARED_OPTIONAL_BLACK_MARKET_REFUSALS):
                wanted = self.boundaries["facts"][str(observe)][
                    "shop_selector"]["wanted_purchase"]
                self.assertEqual(board.store.store_type, STORE_BLACK)
                reserve = policy._full_departure_resupply_reserve(board)
                self.assertEqual(
                    reserve, {42: 5168, 834: 4583, 844: 4583}[observe]
                )
                units = {42: 1, 834: 1, 844: 5}[observe]
                remainder = board.player.gold - wanted["price"] * units
                selected = policy._black_market_optional_purchase(board)
                key, reason = self._decide(policy, board)
                if observe in DECLARED_OPTIONAL_BLACK_MARKET_BUYS:
                    self.assertEqual(self._live(observe)[0], "\x1b")
                    self.assertGreaterEqual(remainder, reserve)
                    self.assertIsNotNone(selected)
                    self.assertEqual(selected.letter, wanted["letter"])
                    self.assertEqual(key, "\x1b")
                    self.assertIn(reason, {
                        "shop:observe-and-leave",
                        "town-progress-invariant:continue-observed-shop",
                    })
                else:
                    self.assertEqual(self._live(observe)[0], "\x1b")
                    self.assertLess(remainder, reserve)
                    self.assertIsNone(selected)
                    self.assertEqual(key, "\x1b")
                    self.assertIn(reason, {
                        "shop:observe-and-leave",
                        "town-progress-invariant:continue-observed-shop",
                    })
            else:
                self.assertEqual(self._decide(policy, board), self._live(observe))

    def test_recorded_black_market_optional_gold_respects_full_departure_reserve(self):
        for index in sorted(
            DECLARED_OPTIONAL_BLACK_MARKET_BUYS
            | DECLARED_OPTIONAL_BLACK_MARKET_REFUSALS
        ):
            with self.subTest(index=index):
                board = self._board(index)
                policy = self._switch_on(self._resume(index))
                wanted = self.boundaries["facts"][str(index)][
                    "shop_selector"]["wanted_purchase"]
                if index == 834:
                    # Same declared counterfactual as the mechanics pin:
                    # suppress the separate deferred full-ID retry so this
                    # assertion isolates the recorded optional Healing ware.
                    self.assertIsNone(policy._identification_need)
                    self.assertTrue(policy._unbuyable_full_identify_sigs)
                    policy._unbuyable_full_identify_sigs.clear()
                ware = next(item for item in board.store.items
                            if item.letter == wanted["letter"])
                self.assertEqual(board.store.store_type, STORE_BLACK)
                self.assertEqual(
                    board.player.gold, {42: 13998, 834: 10728, 844: 4585}[index]
                )
                self.assertEqual((ware.name, ware.price),
                                 (wanted["name"], wanted["price"]))
                reserve = policy._full_departure_resupply_reserve(board)
                self.assertEqual(
                    reserve, {42: 5168, 834: 4583, 844: 4583}[index]
                )
                remainder = board.player.gold - wanted["price"] * {
                    42: 1, 834: 1, 844: 5
                }[index]
                selected = policy._black_market_optional_purchase(board)
                if index in DECLARED_OPTIONAL_BLACK_MARKET_BUYS:
                    self.assertGreaterEqual(remainder, reserve)
                    self.assertIsNotNone(selected)
                    self.assertEqual(selected.letter, wanted["letter"])
                else:
                    self.assertLess(remainder, reserve)
                    self.assertIsNone(selected)
                self.assertEqual(
                    self._live(P1_RELEASES[index])[0][:-1],
                    {42: "pj\r", 834: "pi\r", 844: "ph5\r\r"}[index],
                )
                key, reason = self._decide(policy, board)
                if index in DECLARED_OPTIONAL_BLACK_MARKET_BUYS:
                    self.assertEqual((key, reason),
                                     ("\x1b", "shop:observe-and-leave"))
                else:
                    self.assertEqual(key, "\x1b")
                    self.assertIn(reason, {
                        "shop:observe-and-leave",
                        "town-progress-invariant:continue-observed-shop",
                    })

    def test_p0_switch_off_shadow_records_the_would_be_operation(self):
        """Phase 0: the observe-and-leave page logs IST's would-be key only."""
        policy = self._resume(38)
        board = self._board(38)
        key, reason = self._decide(policy, board)
        self.assertEqual((key, reason), self._live(38))
        shadow = policy.in_store_decision_telemetry()["shadow"]
        self.assertEqual(shadow["would_key"], "pi1\r\r")
        self.assertEqual(shadow["expected_confirm"], "買値 $745 で買いますか？[Y/n]")
        self.assertTrue(all(value for name, value in shadow["preconditions"].items()
                            if name not in {"flag"}))
        self.assertFalse(shadow["preconditions"]["flag"])
        self.assertIsNotNone(policy._shop_observation)
        # The stage-2 release of the same shelf agrees with the shadow.
        for index in (39, 40):
            key, reason, _board = self._step(policy, index)
            self.assertEqual((key, reason), self._live(index))
        agreement = policy.in_store_decision_telemetry()["agreement"]
        self.assertEqual(agreement["released_key"], "pi1\r\r\x1b")
        self.assertTrue(agreement["same_body"])
        self.assertTrue(agreement["same_identity"])

    # ------------------------------------------------------------ P1 / P11
    def test_p1_in_store_operation_is_the_recorded_release_body(self):
        for observe, release in P1_RELEASES.items():
            with self.subTest(index=observe):
                policy = self._switch_on(self._resume(observe))
                board = self._board(observe)
                if observe == 834:
                    # DECLARED COUNTERFACTUAL: no deferred full-ID retry
                    # demand. The observed page and all other state remain
                    # recorded. Its healing operation still tests the exact
                    # original release body. The real stocked-*Identify*
                    # selection is pinned separately below (e371f9a6).
                    self.assertIsNone(policy._identification_need)
                    self.assertTrue(policy._unbuyable_full_identify_sigs)
                    policy._unbuyable_full_identify_sigs.clear()
                if (observe in DECLARED_OPTIONAL_BLACK_MARKET_BUYS
                        or observe in DECLARED_OPTIONAL_BLACK_MARKET_REFUSALS):
                    # DECLARED CONSTRUCTED: a complete known price catalog and
                    # enough independent gold to exercise the recorded buy.
                    board, _reserve = self._construct_optional_purchase_board(
                        policy, board, observe,
                        {42: 1, 834: 1, 844: 5}[observe])
                key, reason = self._decide(policy, board)
                body = self._live(release)[0][:-1]
                self.assertEqual(key, body)
                # P11: the progress invariant does not rewrite the operation.
                self.assertEqual(reason, "shop:in-store-buy")
                self.assertEqual(policy._town_progress_invariant_defect, {})
                wanted = self.boundaries["facts"][str(observe)][
                    "shop_selector"]["wanted_purchase"]
                row = next(item for item in board.store.items
                           if item.letter == key[1])
                self.assertEqual((row.letter, row.name, row.price),
                                 (wanted["letter"], wanted["name"], wanted["price"]))
                # P4 (review change 2): no composable observation is left.
                self.assertIsNone(policy._shop_observation)

    def test_visited_restocked_shop_buys_star_identify_for_deferred_candidate(self):
        # DECLARED CONSTRUCTED independent 90fca3b7 substrate at 834, not
        # an effect of current decision 212. State row 1093 stocks *Identify*
        # at letter p; it supersedes the optional Healing buy at letter i.
        policy = self._switch_on(self._resume(834))
        board = self._board(834)
        self.assertIsNone(policy._identification_need)
        self.assertTrue(policy._full_identification_purchase_wanted())
        self.assertIsNone(policy._mandatory_purchase(board))
        key, reason = self._decide(policy, board)
        self.assertEqual((key, reason), ("pp1\r\r", "shop:in-store-buy"))
        scroll = next(item for item in board.store.items if item.letter == "p")
        self.assertEqual((scroll.tval, scroll.sval, scroll.price),
                         (TVAL_SCROLL, SV_SCROLL_STAR_IDENTIFY, 10239))
        self.assertEqual(policy._shop_selector_diagnostics["wanted_purchase"]["category"],
                         "star-identify")
        self.assertIsNone(policy._shop_observation)
        self.assertEqual(policy._town_progress_invariant_defect, {})
        prefix, steps = _store_buy_continuations(key, reason, board)
        compile_observed_input(prefix, ScreenKind.STORE, {}, reason, steps)
        import re
        confirm = steps[-1]
        self.assertEqual(confirm.kinds, frozenset({ScreenKind.CONFIRM}))
        self.assertTrue(any(re.fullmatch(pattern, "買値 $10239 で買いますか？[Y/n]")
                            for pattern in confirm.feature))
        self.assertFalse(any(re.fullmatch(pattern, "買値 $10240 で買いますか？[Y/n]")
                             for pattern in confirm.feature))

    # ------------------------------------------------------------ P2
    def test_p2_confirmation_gate_is_the_exact_total(self):
        for index, total in ((38, 745), (209, 116), (826, 850), (844, 2555)):
            with self.subTest(index=index):
                policy = self._switch_on(self._resume(index))
                board = self._board(index)
                if index == 844:
                    # DECLARED CONSTRUCTED: enough independent gold and known
                    # departure prices to keep this confirmation mechanics pin.
                    board, _reserve = self._construct_optional_purchase_board(
                        policy, board, index, 5)
                key, _reason = self._decide(policy, board)
                prefix, steps = _store_buy_continuations(key, "shop:in-store-buy", board)
                compiled = compile_observed_input(
                    prefix, ScreenKind.STORE, {}, "shop:in-store-buy", steps)
                self.assertEqual(compiled[0], "p")
                confirm = steps[-1]
                self.assertEqual(confirm.kinds, frozenset({ScreenKind.CONFIRM}))
                self.assertEqual(confirm.keys, "\r")
                import re
                self.assertTrue(any(re.fullmatch(pattern, f"買値 ${total} で買いますか？[Y/n]")
                                    for pattern in confirm.feature))
                self.assertFalse(any(re.fullmatch(pattern, f"買値 ${total + 1} で買いますか？[Y/n]")
                                     for pattern in confirm.feature))
                # No trailing Escape continuation (design 3.1).
                self.assertNotIn(ScreenKind.STORE, {kind for step in steps for kind in step.kinds})

    def test_p2_wand_stack_keeps_the_generic_price_gate(self):
        board = self._board(38)
        row = next(item for item in board.store.items if item.letter == "i")
        # DECLARED CONSTRUCTED: the recorded row as a 4-wand stack.
        # DECLARED CONSTRUCTED: a mana eater without carried device food;
        # the observed shop's sole food source is this wand stack.
        wand = replace(board, player=replace(board.player, food_type=FOOD_TYPE_MANA),
                       inventory=[item for item in board.inventory
                                  if item.tval not in {TVAL_STAFF, TVAL_WAND}],
                       store=replace(board.store, items=[
                           replace(row, tval=TVAL_WAND, sval=1, pval=10,
                                   name="マジック・ミサイルの魔法棒 (4x 10回分)")]))
        policy = self._switch_on(self._resume(38))
        # DECLARED CONSTRUCTED: this mana eater's observed Home catalog has
        # no device food either; a catalogued reserve would remove the need.
        policy._home_knowledge_items = [item for item in policy._home_knowledge_items
                                       if item.tval not in {TVAL_STAFF, TVAL_WAND}]
        key, reason = self._decide(policy, wand)
        self.assertEqual(reason, "shop:in-store-buy")
        self.assertTrue(key.startswith("pi"))
        _prefix, steps = _store_buy_continuations(key, reason, wand)
        import re
        self.assertTrue(any(re.fullmatch(pattern, "買値 $743 で買いますか？[Y/n]")
                            for pattern in steps[-1].feature))
        _prefix, steps = _store_buy_continuations("pi1\r\r", "shop:in-store-buy", board)
        self.assertFalse(any(re.fullmatch(pattern, "買値 $743 で買いますか？[Y/n]")
                             for pattern in steps[-1].feature))

    def test_p2_price_mismatch_declines_and_trips_the_breaker(self):
        with TemporaryDirectory() as raw:
            policy = self._switch_on(self._resume(38), raw)
            board = self._board(38)
            key, _reason = self._decide(policy, board)
            # Executor-proven outcome of the confirmation showing another total.
            self._post(policy, key, "shop:in-store-buy", "failed:price-mismatch")
            self.assertIsNone(policy._store_buy_inflight)
            sidecar = json.loads((Path(raw) / IN_STORE_BREAKER_FILE_NAME).read_text(
                encoding="utf-8"))
            self.assertEqual(sidecar["cause"], "price-mismatch")
            # The next page of the same entry only leaves, by its named reason.
            key, reason = self._decide(policy, self._board(38))
            self.assertEqual((key, reason), ("\x1b", "store:in-store-breaker:price-mismatch"))

    # ------------------------------------------------------------ P3 / P9
    def test_p3_sale_then_buy_are_addressed_from_each_observed_page(self):
        """Magic seq 815-826: sale and the 20-charge staff in one entry.

        DECLARED CONSTRUCTED: live inscribed outside (seq 816) and released
        the sale on a re-entered page (state row 1064).  Here the inscription
        is posted in the store on the seq-815 page; row 1064 (same shelf, the
        staff tagged {@1}) stands in for its effect, and row 1065, written
        right after the recorded 'd1y', is the sale's own effect.
        """
        policy = self._switch_on(self._resume(MAGIC_OBSERVE))
        key, reason = self._decide(policy, self._board(MAGIC_OBSERVE))
        self.assertEqual((key, reason), ("{j@1\r", "shop:in-store-inscribe"))
        self._post(policy, key, reason, None)
        page = self._row(MAGIC_RELEASE_PAGE)
        key, reason = self._decide(policy, page)
        self.assertEqual((key, reason), ("d1y", "shop:in-store-sell"))
        self._post(policy, key, reason, None)
        after = self._row(MAGIC_AFTER_SALE)
        names = {item.letter: item.name for item in page.store.items}
        moved = {item.letter: item.name for item in after.store.items}
        self.assertEqual(moved["g"], names["g"])          # 鑑定の杖 (3x 20回分)
        self.assertEqual(moved["j"], names["i"])          # 光の杖 i -> j
        self.assertNotEqual(moved["i"], names["i"])       # the sold staff at i
        key, reason = self._decide(policy, after)
        self.assertEqual((key, reason), ("pg1\r\r", "shop:in-store-buy"))
        self.assertEqual(policy._in_store_entry_ledger["ops"], 2)
        visit = policy._store_visit
        self.assertEqual((visit.store_type, visit.phase), (STORE_MAGIC, StoreVisitPhase.OPERATING))

    def test_p9_visit_operates_in_store_and_closes_outside(self):
        """Magic seq 38-41.

        DECLARED CONSTRUCTED: state row 60 is the store record the same
        'pi1\\r\\r' wrote at the recorded re-entry (seq 40, 13 game turns
        later, same shelf); row 61 is the entrance board after its exit.
        """
        policy = self._switch_on(self._resume(38))
        key, reason = self._decide(policy, self._board(38))
        visit = policy._store_visit
        self.assertEqual((visit.phase, visit.operation_posted, visit.operation_key),
                         (StoreVisitPhase.OPERATING, True, key))
        self._post(policy, key, reason, None)
        key, reason = self._decide(policy, self._row(MAGIC_BUY_ROW))
        self.assertEqual((key, reason), ("\x1b", "shop:in-store-done"))
        self.assertIsNone(policy._store_buy_inflight)
        self.assertEqual(policy._in_store_entry_ledger["ops"], 1)
        self.assertIs(policy._store_visit, visit)
        self.assertFalse(visit.operation_posted)
        self._post(policy, key)
        key, reason = self._decide(policy, self._row(MAGIC_BUY_EXIT))
        # P4: no second one-shot is composed from the page IST acted on.
        self.assertNotIn(reason, {"shop:one-shot-buy", "shop:one-shot-sell"})
        self.assertIsNone(policy._shop_observation)
        self.assertIsNot(policy._store_visit, visit)
        self.assertEqual(visit.phase, StoreVisitPhase.CLOSED)

    # ------------------------------------------------------------ P4
    def test_p4_unverified_page_falls_back_to_observe_and_leave(self):
        board = self._board(38)
        cases = {
            "screen-check-false": (board, False),
            # DECLARED CONSTRUCTED: the recorded page as a second page.
            "page-not-one": (replace(board, store=replace(
                board.store, page_top=board.store.page_size)), True),
            # DECLARED CONSTRUCTED: page index was not emitted.
            "page-unknown": (replace(board, store=replace(board.store, page_top=None)), True),
        }
        for name, (case, screen) in cases.items():
            with self.subTest(case=name):
                policy = self._switch_on(self._resume(38))
                key, reason = self._decide(policy, case, screen=screen)
                self.assertEqual((key, reason), self._live(38))
                self.assertIsNotNone(policy._shop_observation)
                self.assertIsNone(policy._in_store_entry_ledger)
                self.assertIsNone(policy._store_buy_inflight)

    def test_p4_in_store_operation_clears_an_earlier_observation_of_the_shelf(self):
        """Review change 2: no second one-shot from a page IST acted on.

        DECLARED CONSTRUCTED: a restored policy holds an older observation
        of this shelf, with no outstanding leave or old-path transaction.
        The current page is the recorded seq-38 board. Rows 60/61 as in P9.
        """
        policy = self._switch_on(self._resume(38))
        board = self._board(38)
        policy._shop_observation = (board.store, policy._decision_sequence - 1)
        key, reason = self._decide(policy, board)
        self.assertEqual((key, reason), ("pi1\r\r", "shop:in-store-buy"))
        self.assertIsNone(policy._shop_observation)
        self._post(policy, key, reason, None)
        key, reason = self._decide(policy, self._row(MAGIC_BUY_ROW))
        self._post(policy, key)
        key, reason = self._decide(policy, self._row(MAGIC_BUY_EXIT))
        self.assertNotIn(reason, {"shop:one-shot-buy", "shop:one-shot-sell"})
        self.assertNotEqual(key, "5")

    def test_p4_item_absent_from_shown_page_is_never_sent(self):
        board = self._board(38)
        # DECLARED CONSTRUCTED: the wanted 12-charge staff not on this page.
        case = replace(board, store=replace(board.store, items=[
            item for item in board.store.items if item.letter != "i"]))
        policy = self._switch_on(self._resume(38))
        key, _reason = self._decide(policy, case)
        self.assertFalse(key.startswith(("p", "d", "{")))

    def test_unconfirmed_operation_leaves_without_retry(self):
        policy = self._switch_on(self._resume(38))
        board = self._board(38)
        key, reason = self._decide(policy, board)
        self._post(policy, key, reason, None)
        # DECLARED CONSTRUCTED: a fresh barrier with unchanged inventory/gold.
        key, reason = self._decide(policy, replace(board, turn=board.turn + 1))
        self.assertEqual((key, reason), ("\x1b", "shop:in-store-done"))
        self.assertEqual(policy._in_store_entry_ledger["ops"], 0)

    def test_home_first_keeps_the_existing_detour(self):
        policy = self._switch_on(self._resume(786))
        key, reason = self._decide(policy, self._board(786))
        self.assertEqual((key, reason), self._live(786))
        self.assertIsNone(policy._in_store_entry_ledger)
        self.assertIsNone(policy._store_buy_inflight)
        self._post(policy, key)
        with _dump_wall():
            key, reason, board = self._step(policy, 787)
        # e371f9a6 defers the unavailable carried light Helmet (32, 5)
        # and uses Home travel. Stop before feeding old 788/789 effects.
        self.assertEqual((key, reason), ("\x1b`n(.", "shop:travel"))
        self.assertEqual(self._live(787), ("7", "shop:approach"))
        self.assertIsNone(policy._identification_need)
        self.assertEqual(policy._identification_source_obtainability(board, full=True),
                         "unavailable")
        self.assertTrue(any(signature[1:] == (32, 5)
                            for signature in policy._unbuyable_full_identify_sigs))

    # ------------------------------------------------------------ P5 / P6
    def test_p5_shelf_proven_fruitless_stops_are_skipped(self):
        for index, (store, category) in P5_SKIPS.items():
            with self.subTest(index=index):
                off = self._resume(index)
                key, reason = self._decide(off, self._board(index))
                expected = (("\x1b`n(.", "shop:travel")
                            if index in {216, 795} else self._live(index))
                self.assertEqual((key, reason), expected)
                if index in {216, 795}:
                    self.assertIsNone(off._identification_need)
                    self.assertEqual(off._identification_source_obtainability(
                        self._board(index), full=True), "unavailable")
                    self.assertTrue(off._unbuyable_full_identify_sigs)
                would = off.in_store_decision_telemetry()["plan_shadow_would_skip"]
                self.assertIn((store, category),
                              {(entry["store"], entry["category"]) for entry in would})
                on = self._switch_on(self._resume(index))
                key, reason = self._decide(on, self._board(index))
                skips = on.in_store_decision_telemetry()["shelf_evidence_skips"]
                self.assertIn((store, category),
                              {(entry["store"], entry["category"]) for entry in skips})
                # The skipped shelf is not this decision's destination.
                self.assertNotEqual(self._live(index), (key, reason))
                self.assertNotEqual(on._shopping_approach_store_type, store)
                state = _town_plan_state(on)
                names = ("General Store", "Armoury", "Weapon Smiths", "Temple",
                         "Alchemist", "Magic Shop", "Black Market", "Home")
                self.assertIn(names[store], state["skipped_latched"])
                self.assertEqual(state["skipped_reasons"][names[store]], "shelf-evidence")

    def test_p6_stops_are_kept_when_the_shelf_can_supply_or_evidence_expired(self):
        for index, store in P6_KEEPS.items():
            with self.subTest(index=index):
                policy = self._switch_on(self._resume(index))
                key, reason = self._decide(policy, self._board(index))
                self.assertEqual((key, reason), self._live(index))
                telemetry = policy.in_store_decision_telemetry() or {}
                self.assertNotIn(store, {entry["store"] for entry in
                                         telemetry.get("shelf_evidence_skips", ())})
                plan = policy._town_errand_plan
                self.assertEqual(plan.stops[plan.index], store)

    # ------------------------------------------------------------ P7
    def test_p7_restock_is_known_from_observations_only(self):
        # Recorded: the Alchemist shelf of row 1021 (turn 6099617) restocked
        # by the entry of row 1069 (turn 6104902): rule (a).
        policy = self._resume(ALCHEMIST_RESTOCK)
        self._decide(policy, self._board(ALCHEMIST_RESTOCK))
        record = policy._shelf_evidence["pages"][(0, STORE_ALCHEMIST)]
        self.assertEqual((record["restock"], record["window"]), ("changed", 6104902))
        base = self._board(796)
        self.assertEqual(base.store.store_type, STORE_ALCHEMIST)
        # DECLARED CONSTRUCTED: the recorded seq-794 page again after the
        # daily owner change ({売出中}, half price) -- not a restock.
        shuffled = replace(base, turn=base.turn + 100, store=replace(base.store, items=[
            replace(item, name=item.name + " {売出中}", price=max(1, item.price // 2))
            for item in base.store.items]))
        self.assertEqual(shelf_signature(shuffled.store), shelf_signature(base.store))
        policy = self._resume(796)
        self._decide(policy, base)
        self._post(policy, "\x1b")
        window = policy._shelf_evidence["pages"][(0, STORE_ALCHEMIST)]["window"]
        self.assertEqual(window, 6091514)  # rule (a) at the stay-B entry
        self._decide(policy, shuffled)
        record = policy._shelf_evidence["pages"][(0, STORE_ALCHEMIST)]
        self.assertIsNone(record["restock"])
        self.assertEqual(record["window"], window)
        # DECLARED CONSTRUCTED: the same page one maintenance interval later:
        # the game must have restocked at that entry (rule (b)).
        later = replace(base, turn=shuffled.turn + STORE_MAINTENANCE_INTERVAL_TURNS)
        self._post(policy, "\x1b")
        # DECLARED CONSTRUCTED: the observed exit between these entries.
        self._decide(policy, replace(shuffled, store=None))
        self._decide(policy, later)
        record = policy._shelf_evidence["pages"][(0, STORE_ALCHEMIST)]
        self.assertEqual((record["restock"], record["window"]), ("elapsed", later.turn))

    # ------------------------------------------------------------ P8
    def test_p8_store_command_refusal_trips_a_breaker_that_survives_restart(self):
        with TemporaryDirectory() as raw:
            policy = self._switch_on(self._resume(38), raw)
            key, reason = self._decide(policy, self._board(38))
            self._post(policy, key, reason, "refused:store-command")
            key, reason = self._decide(policy, self._board(38))
            self.assertEqual((key, reason),
                             ("\x1b", "store:in-store-breaker:store-command-refused"))
            # Auto-resume restarts with the same flag: the sidecar keeps it off.
            restarted = self._switch_on(self._resume(38), raw)
            self.assertEqual(restarted._in_store_breaker[0], "store-command-refused")
            key, reason = self._decide(restarted, self._board(38))
            self.assertEqual((key, reason), self._live(38))
            self.assertIsNone(restarted._in_store_entry_ledger)

    # ------------------------------------------------------------ P12
    def test_p12_refused_purchase_closes_the_visit(self):
        policy = self._switch_on(self._resume(42))
        board, _reserve = self._construct_optional_purchase_board(
            policy, self._board(42), 42, 1)
        key, reason = self._decide(policy, board)
        visit = policy._store_visit
        self._post(policy, key, reason, "failed:purchase-refused")
        self.assertIsNone(policy._store_buy_inflight)
        self.assertIsNone(policy._in_store_entry_ledger)
        self.assertEqual((visit.phase, visit.outcome),
                         (StoreVisitPhase.CLOSED, "in-store-buy-refused"))

    # ------------------------------------------------------------ P13
    def test_p13_shadow_changes_no_policy_state(self):
        """Rows 38-40: identical state and keys with and without the shadow."""
        names = ("_store_stuck_count", "_town_store_attempted", "_last_buy_sig",
                 "last_reason", "_store_buy_inflight", "_shop_selector_diagnostics",
                 "_store_sell_attempt", "_home_pending_item", "_home_gate_telemetry")
        runs = []
        for shadow in (True, False):
            policy = self._resume(38)
            rows = []
            context = (patch.object(HengbotPolicy, "_in_store_shadow",
                                    lambda _self, _snapshot: None)
                       if not shadow else _nullcontext())
            with context:
                for index in (38, 39, 40):
                    with _dump_wall():
                        key, reason, _board = self._step(policy, index)
                    rows.append((key, reason, {
                        name: repr(getattr(policy, name)) for name in names}))
            runs.append(rows)
        self.assertEqual(runs[0], runs[1])

    def test_a1_shadow_failures_preserve_recorded_decisions(self):
        cases = (("_in_store_shadow", 38), ("_observe_shelf_evidence", 38),
                 ("_in_store_shadow_visit_outcome", 38),
                 ("_in_store_shadow_agreement", 40),
                 ("_shelf_evidence_skips_need", 45),
                 ("_note_shelf_trade", 41))
        for name, index in cases:
            with self.subTest(method=name):
                # DECLARED replay continuation: each board follows the live key.
                policy = self._resume(38 if index in {40, 41} else index)
                if index in {40, 41}:
                    for previous in range(38, index):
                        key, _ = self._decide(policy, self._board(previous))
                        self._post(policy, key)
                def fail(*args, **kwargs):
                    policy.last_reason = "shadow:corrupted-reason"
                    raise RuntimeError("injected advisory failure")
                with patch.object(policy, name, side_effect=fail) as mocked:
                    actual = self._decide(policy, self._board(index))
                self.assertTrue(mocked.called)
                self.assertEqual(actual, self._live(index))
                field = name.removeprefix("_in_store_").lstrip("_") + "_error"
                self.assertEqual(policy.in_store_decision_telemetry()[field], {
                    "type": "RuntimeError", "message": "injected advisory failure"})

    def test_b1_first_page_mismatch_keeps_old_path_purchase_watch(self):
        policy = self._resume(38)
        board = self._board(38)
        key, _ = self._decide(policy, board)
        # DECLARED CONSTRUCTED: pure selection disagrees with the actual shop
        # selection at the emission boundary; the cached old-path buy is real.
        selection = dict(policy._in_store_selection(board), letter="j")
        self.assertIsNone(policy._in_store_emit(board, selection, first=True))
        watch = policy._store_buy_inflight
        self.assertIsNotNone(watch)
        self._post(policy, key)
        for index in (39, 40):
            key, reason = self._decide(policy, self._board(index))
            self.assertEqual((key, reason), self._live(index))
            self.assertIsNotNone(policy._store_buy_inflight)
            self._post(policy, key)
        policy._town_store_attempted[STORE_MAGIC] = board.turn
        self._decide(policy, self._row(MAGIC_BUY_EXIT))
        self.assertIsNone(policy._store_buy_inflight)
        self.assertNotIn(STORE_MAGIC, policy._town_store_attempted)
        self.assertFalse(policy._store_visit.operation_posted)
        self.assertIn(watch[1], policy._town_visit_purchases)

    def test_b5_breaker_disables_shelf_proven_skips(self):
        with TemporaryDirectory() as raw:
            policy = self._switch_on(self._resume(45), raw)
            policy.trip_in_store_breaker("price-mismatch")
            key, reason = self._decide(policy, self._board(45))
            self.assertEqual((key, reason), self._live(45))
            self.assertIn(STORE_BLACK, policy._town_errand_plan.stops)
            self.assertFalse(policy.in_store_decision_telemetry().get("shelf_evidence_skips"))

    def test_b4_unparseable_buy_clears_previous_executor_result(self):
        executor = SimpleNamespace(client=None)
        send = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=1)
        send.last_result = SimpleNamespace(operation=SimpleNamespace(owner="shop:in-store-sell"))
        result, _ = _send_new_decision_key(
            send, "recorded-board", "pxINVALID", None, set(), in_store=True,
            decision={"reason": "shop:in-store-buy"}, snapshot=self._board(38))
        self.assertIs(result, SendResult.TERMINAL)
        self.assertIsNone(send.last_result)

    def test_b8_old_entry_cannot_confirm_on_new_entry_board(self):
        policy = self._switch_on(self._resume(38))
        board = self._board(38)
        key, reason = self._decide(policy, board)
        self._post(policy, key, reason, None)
        policy._decision_sequence += 1
        self.assertTrue(policy._in_store_post_op_board(board))
        # DECLARED CONSTRUCTED: same shop, a fresh entry, stale pending ledger.
        policy._store_visit.opened_sequence += 1
        self.assertFalse(policy._in_store_post_op_board(board))
        watch = policy._store_buy_inflight
        self._decide(policy, self._row(MAGIC_BUY_ROW))
        self.assertEqual(policy._store_buy_inflight, watch)

    # ------------------------------------------------------------ units
    def test_restored_policy_without_the_new_attributes_gets_defaults(self):
        policy = self._resume(38)
        for name in tuple(policy.__dict__):
            if not name.startswith(("_in_store_", "_shelf_evidence", "_plan_shadow_")):
                continue
            del policy.__dict__[name]
        normalize_policy_state(policy, restart=True)
        self.assertFalse(policy._in_store_ops_enabled)
        self.assertIsNone(policy._in_store_breaker)
        self.assertEqual(policy._shelf_evidence, {})
        key, reason = self._decide(policy, self._board(38))
        self.assertEqual((key, reason), self._live(38))

    def test_per_entry_bound_ends_the_entry(self):
        policy = self._switch_on(self._resume(MAGIC_OBSERVE))
        key, reason = self._decide(policy, self._board(MAGIC_OBSERVE))
        self._post(policy, key, reason, None)
        # DECLARED CONSTRUCTED: the entry has already confirmed the bound's
        # number of operations (STORE_STUCK_LIMIT, design 3.1).
        policy._in_store_entry_ledger["ops"] = STORE_STUCK_LIMIT - 1
        # DECLARED CONSTRUCTED: the post-inscription page from P3. A sale
        # is still wanted here, so the bound is what causes this exit.
        key, reason = self._decide(policy, self._row(MAGIC_RELEASE_PAGE))
        self.assertEqual((key, reason), ("\x1b", "shop:in-store-done"))
        self.assertEqual(policy._in_store_entry_ledger["ops"], STORE_STUCK_LIMIT)


@contextmanager
def _nullcontext():
    yield


def _store_record(turn, gold, messages=(), items=None):
    return {
        "turn": turn, "floor": {"dungeon_id": 0, "level": 0},
        "player": {"gold": gold}, "inventory": [], "equipment": [],
        "grid_map": {"runs": []}, "messages": list(messages),
        "store": {"store_type": STORE_BLACK, "items": items or []},
    }


class InStoreExecutorTest(unittest.TestCase):
    """Executor gates of an in-store purchase (design 3.1 prompt gates)."""

    def _executor(self, screens, states):
        game = FaithfulHookGame()
        client = ControlClient(1, request_budget=2, retries=1, backoff=0,
                               socket_factory=game.socket_factory)
        self.addCleanup(client.close)
        executor = OperationExecutor(client, drain=lambda: list(game.jsonl))
        game.screen = store_screen()
        game.state = _store_record(1, 9000)
        game.jsonl.append(dict(game.state))
        executor.observe_boundary(deadline=9999999999)
        game.screens, game.states = screens, states
        return game, executor

    @staticmethod
    def _board():
        # DECLARED CONSTRUCTED: the Black-market rows of state rows 1102/1121
        # (seq 832 体力回復の薬 $6143, seq 842 スピードの薬 x5 $511).
        return SimpleNamespace(store=StoreState(STORE_BLACK, [
            StoreItem("a", "体力回復の薬", 1, 75, 37, 6143),
            StoreItem("b", "スピードの薬", 5, 75, 29, 511),
        ]))

    def _submit(self, executor, key):
        prefix, steps = _store_buy_continuations(key, "shop:in-store-buy", self._board())
        return executor.submit(Operation(
            7, "shop:in-store-buy", prefix, executor.ready_board, steps,
        ), deadline=9999999999)

    def test_black_market_chooser_and_exact_total(self):
        game, executor = self._executor(
            [prompt_screen("(商品:a-b, ESCで中断) どれ? "),
             prompt_screen("いくつですか (1-5): 1"),
             prompt_screen("買値 $1533 で買いますか？[Y/n]"),
             store_screen()],
            [_store_record(1, 9000), _store_record(1, 9000),
             _store_record(1, 9000), _store_record(2, 7467)])
        result = self._submit(executor, "pb3\r\r")
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertIsNone(result.operation.business_outcome)
        self.assertEqual(game.accepted, ["p", "b", "3\r", "\r"])

    def test_price_mismatch_is_declined(self):
        game, executor = self._executor(
            [prompt_screen("(商品:a-b, ESCで中断) どれ? "),
             prompt_screen("買値 $6200 で買いますか？[Y/n]"),
             store_screen()],
            [_store_record(1, 9000), _store_record(1, 9000), _store_record(2, 9000)])
        result = self._submit(executor, "pa\r")
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(result.operation.business_outcome, "failed:price-mismatch")
        self.assertEqual(game.accepted, ["p", "a", "n"])

    def test_refusals_exit_without_the_tail(self):
        for message in ("お金が足りません。", "現在商品の在庫を切らしています。"):
            with self.subTest(message=message):
                self.assertIn(message, _PURCHASE_REFUSAL_MESSAGES)
                game, executor = self._executor(
                    [store_screen(), command_screen(3)],
                    [_store_record(2, 9000, [message]), {
                        "turn": 3, "floor": {"dungeon_id": 0, "level": 0},
                        "player": {"gold": 9000}, "inventory": [],
                        "equipment": [], "grid_map": {"runs": []}}])
                result = self._submit(executor, "pa\r")
                self.assertEqual(result.operation.business_outcome,
                                 "failed:purchase-refused")
                self.assertEqual(game.accepted, ["p", "\x1b"])

    def test_store_command_refusal_is_reported(self):
        message = "そのコマンドは店の中では使えません。"
        game, executor = self._executor(
            [store_screen()], [_store_record(2, 9000, [message])])
        result = executor.submit(Operation(
            8, "shop:in-store-sell", "d01\ry", executor.ready_board,
        ), deadline=9999999999)
        self.assertEqual(result.operation.business_outcome, "refused:store-command")

    def test_unowned_prompt_cancels_and_continues_at_a_fresh_barrier(self):
        game, executor = self._executor(
            [prompt_screen("(商品:a-b, ESCで中断) どれ? "),
             prompt_screen("いくつですか (1-5): 1"), store_screen()],
            [_store_record(1, 9000), _store_record(1, 9000), _store_record(2, 9000)])
        result = self._submit(executor, "pa\r")
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(result.operation.business_outcome, "failed:unowned-screen")
        self.assertEqual(game.accepted, ["p", "a", "\x1b"])

    def test_terminal_operation_cancels_without_reposting_its_transaction(self):
        game, executor = self._executor(
            [prompt_screen("いくつですか (1-5): 1"),
             prompt_screen("いくつですか (1-5): 1")],
            [_store_record(1, 9000), _store_record(1, 9000)])
        result = self._submit(executor, "pa\r")
        self.assertEqual(result.outcome, "stuck-prompt")
        game.screens, game.states = [command_screen(3)], [{
            "turn": 3, "floor": {"dungeon_id": 0, "level": 0},
            "player": {"gold": 9000}, "inventory": [], "equipment": [],
            "grid_map": {"runs": []}}]
        recovered = executor.cancel_in_store_terminal(result, deadline=9999999999)
        self.assertEqual(recovered.outcome, "completed", recovered.reason)
        self.assertEqual(game.accepted, ["p", "\x1b", "\x1b"])

    def test_quantity_gate_only_for_a_stack_and_no_blind_macro(self):
        board = self._board()
        self.assertIsNone(_store_buy_continuations("pa1\r\r", "shop:in-store-buy", board))
        self.assertIsNone(_store_buy_continuations("pb\r", "shop:in-store-buy", board))
        _prefix, steps = _store_buy_continuations("pa\r", "shop:in-store-buy", board)
        self.assertNotIn(ScreenKind.QUANTITY, {kind for step in steps for kind in step.kinds})
        with self.assertRaises(ValueError):
            compile_observed_input("pa\r", ScreenKind.STORE, {}, "shop:in-store-buy", [])
        # The one-shot keeps its trailing Escape (old path unchanged).
        _prefix, steps = _store_buy_continuations("pa\r\x1b", "shop:one-shot-buy")
        self.assertEqual(steps[-1].kinds, frozenset({ScreenKind.STORE}))


if __name__ == "__main__":
    unittest.main()
