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

One replay of the whole process, switch off, is shared by every pin
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
- LIVE-KEY WALL 9-12, 17, 171, 219: the replay's own decision differs there
  (the Home identify-staff reserve right after the first dumps, and two town
  kill-mob reasons); the cause was not investigated (outside this change),
  so the live keys are posted.  With the walls every other recorded key and
  reason is reproduced, switch off (pin P0).
- SCREEN WALL: the capture holds no screen.  Phase 1 acts only when the
  executor's slot-by-slot screen check passed on the same board (design 3.1
  condition 3); the CLI supplies it through ``observe_store_screen``.  On a
  recorded STORE board the pins declare it True; the negative is P4.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation
import gzip
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

from test_esp_threat_rest_recorded import EDIT, _policy
from test_input_executor import (
    FaithfulHookGame, command_screen, prompt_screen, store_screen,
)

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
LIVE_KEY_WALL = frozenset({9, 10, 11, 12, 17, 171, 219})
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
    with patch.object(HengbotPolicy, "_publish_character_dump", _recorded_dump):
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
        with _dump_wall():
            for index in range(len(cls.segments)):
                if index in CHECKPOINTS:
                    buffer = io.BytesIO()
                    _Pickler(buffer, cls.monrace).dump(policy)
                    cls.checkpoints[index] = buffer.getvalue()
                cls.prefix.append(cls._step(policy, index)[:2])

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
        policy = _Unpickler(io.BytesIO(self.checkpoints[index]), self.monrace).load()
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

    def _row(self, number):
        return self._parse([self.lines[number]])

    def _live(self, index):
        row = self.recorded[index]
        return row["key"], row["reason"]

    # ------------------------------------------------------------ P0
    def test_p0_switch_off_replay_reproduces_every_recorded_key(self):
        """Flag off: the recorded keys and reasons, byte for byte (walls aside)."""
        for index, row in enumerate(self.prefix):
            if index not in LIVE_KEY_WALL:
                self.assertEqual(row, self._live(index), index)
        # The live-key wall is load-bearing.
        for index in LIVE_KEY_WALL:
            self.assertNotEqual(self.prefix[index], self._live(index), index)
        # Every shop transaction of the capture used two entries.
        for observe, release in P1_RELEASES.items():
            self.assertEqual(self._live(observe)[0], "\x1b")
            self.assertEqual(self._live(release)[1], "shop:one-shot-buy")
            # Re-decide the recorded page through the public path as well;
            # this keeps the flag-off pin sensitive to a reverted guard.
            policy = self._resume(observe)
            self.assertEqual(self._decide(policy, self._board(observe)), self._live(observe))

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

    # ------------------------------------------------------------ P2



    # ------------------------------------------------------------ P3 / P9


    # ------------------------------------------------------------ P4





    # ------------------------------------------------------------ P5 / P6


    # ------------------------------------------------------------ P7

    # ------------------------------------------------------------ P8

    # ------------------------------------------------------------ P12

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




if __name__ == "__main__":
    unittest.main()
