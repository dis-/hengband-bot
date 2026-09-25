"""Recorded pin: a Home reached this visit is not declared unreachable.

Live incident 2026-09-25 10:22:13 (one bot process resumed at 10:11:24 onto
the running game, 3,782 logged decisions): back in the Outpost after a
recall (sequence 3695), the town visit sold, bought, quaffed Restore
Constitution, ran the equipment calibration and restored its supplies, then
the equipment transaction deposited the Ring of Free Action at Home
(sequence 3778 'do\\r', observed on 3779: pack 17 -> 16).  The next decision
(3780) stopped the run with ``town:blocked:overweight-home-unreachable``
while standing on the Home entrance (45, 123).

Root cause (the ``home_route_projection`` telemetry of every recorded
decision, reproduced by the replay below): the verdict was
``_town_store_blocked_under_applicable_bound(STORE_HOME)``; nothing ever
failed to approach (``home_approach_fails`` 0 throughout).  The block was
installed by the unsuccessful-pass count, which only a stop pass reported as
``operation_completed`` resets (user decision 2026-09-16).  Every other
observed Home effect left it charged:

- 3713 +1 ``home:leave-after-one-operation`` (0 -> 1);
- 3735 +1 ``home:store-context-exit`` (-> 2); then the atomic deposits
  3736-3741 took effect (pack 18 -> 10 -> 2 -> 1) with no reset;
- 3769 +1 ``home:store-context-exit`` (-> 3); then the calibration restore
  withdrawals 3770-3775 took effect (pack 1 -> 13 -> 15 -> 16) with no
  reset;
- 3775 +1 equipment-transaction approach charge (-> 4);
- 3776 reset by the identify-staff withdrawal's own pass (the one observed
  withdrawal that reported ``operation_completed``), then +1 approach (-> 1);
- 3777 +1 approach (-> 2);
- 3779 +1 ``home:leave-after-one-operation`` after the confirmed Ring
  deposit, reported with ``operation_completed`` False because the
  equipment transaction's confirmation never reached the StoreVisit (-> 3).
  The same deposit finished the outstanding equipment work, so the Home
  bound fell from 300 to 3 on that pass, and 3 >= 3 installed the block.

Fix: one seam, ``_observe_home_operation_effect``, called wherever a posted
Home deposit or withdrawal's effect is confirmed (atomic deposit, atomic
withdrawal, calibration restore batch, equipment-transaction deposit or
withdrawal), resets the unsuccessful passes and the failed approaches and
releases a block they installed.  Only passes and approaches after the last
observed effect can exhaust the bound.

Substrate: every recorded decision of the process, replayed through the
public response path on one policy (tests/extract_overweight_home_
unreachable_fixture.py; the calibration file is the one the process loaded).
Walls, each declared:
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them;
- Home history/disposal files and the calibration file live in a temporary
  directory;
- the board of every decision that follows a posted key carries the live
  input executor's ``_completed_operation_sequence``/``_owner`` (the
  previous decision's sequence and reason), as the executor adds them after
  an accepted operation;
- DECLARED DIVERGENCE (not a wall): three decisions of the store-4 purchase
  loop, sequence 3701, 3705 and 3706, are decided differently by the
  replay (the progress-invariant wrapper names the wander/await it wraps
  instead of ``shop:approach``, and on 3705 it awaits the store entry '5'
  instead of the live ``probe`` '8').  The replay decides them identically
  with and without the fix, before any Home pass of the visit, and every
  later recorded board is decided as live -- the pre-fix code reproduces
  every other decision of the process, the stop included.
No wall touches the Home ledger, the equipment transaction or the terminal.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import hengbot.policy as policy_module
from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_HOME, TOWN_STOP_PASS_LIMIT

from test_esp_threat_rest_recorded import EDIT, _policy
import test_policy_home  # WeightOverloadTownTest's overweight town board


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "overweight-home-unreachable-20260925.jsonl.gz"
CALIBRATION = FIXTURES / (
    "guardian-recall-pingpong-20260925.character-calibration.json"
)
FIXTURE_SHA256 = "f0eee9ea489edb276f7deed60696140ace323c301a465ec88201a89d5f8dae9a"
BOUNDARIES_SHA256 = (
    "df03223131b213afe99980b3c2bbfb4590e6912d7743bcda1735e7118a3df278"
)
CALIBRATION_SHA256 = (
    "a90e4700854b1b3cf839a278a846078c7f9d768c82c058551c6f52173660016b"
)
# Decisions are addressed by log index; the landing reuses sequence 3695.
VISIT_START = 3697  # sequence 3696: the first town decision, ledger reset
DIVERGENT = (3702, 3706, 3707)  # sequence 3701, 3705, 3706 (declared above)
DEPOSITS_OBSERVED = (3739, 3741, 3743)  # sequence 3738, 3740, 3742
RESTORES_OBSERVED = (3772, 3774, 3776)  # sequence 3771, 3773, 3775
STAFF_OBSERVED = 3777  # sequence 3776
RING_DEPOSIT = 3779  # sequence 3778, 'do\r'
RING_OBSERVED = 3780  # sequence 3779, home:leave-after-one-operation
STOP = 3781  # sequence 3780, town:blocked:overweight-home-unreachable
HOME_ENTRANCE = (45, 123)


class OverweightHomeUnreachableRecordedTest(unittest.TestCase):
    replay = None

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        assert hashlib.sha256(CALIBRATION.read_bytes()).hexdigest() == (
            CALIBRATION_SHA256
        )
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        cls.recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(boundaries["input_rows"])
        assert len(cls.recorded) == STOP + 1
        cls.starts = [0]
        for count in boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    @classmethod
    def _board_lines(cls, index):
        segment = cls.lines[cls.starts[index] : cls.starts[index + 1]]
        previous = cls.recorded[index - 1] if index else None
        if index and previous["key"]:
            # Wall (executor binding): see the module docstring.
            row = json.loads(segment[-1])
            row["_completed_operation_sequence"] = previous["decision_sequence"]
            row["_completed_operation_owner"] = previous["reason"]
            segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
        return segment

    @classmethod
    def _replay(cls):
        """Replay the whole recorded process on one policy."""
        if cls.replay is not None:
            return cls.replay
        replay = []
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            policy = _policy(directory, cls.monrace)
            policy._character_calibration_path.write_bytes(
                CALIBRATION.read_bytes()
            )
            for index in range(STOP + 1):
                _decoded, snapshots = _consume_response_sequence(
                    cls._board_lines(index), policy, lambda _key: True,
                    cls.monrace,
                    knowledge_ledger_path=directory / "knowledge.jsonl",
                )
                recorded_reason = cls.recorded[index]["reason"]
                if recorded_reason == "periodic:game-save":
                    policy.request_game_save()
                elif recorded_reason == "periodic:character-dump":
                    policy.request_character_dump()
                snapshot = snapshots[-1]
                key = policy.choose_key(snapshot)
                ledger = policy._town_visit_ledger
                here = snapshot.grid_at(snapshot.player.position)
                replay.append({
                    "key": str(key),
                    "reason": policy.last_reason,
                    "passes": ledger.unsatisfied_passes[STORE_HOME],
                    "approach_fails": ledger.approach_fails[STORE_HOME],
                    "blocked": STORE_HOME in ledger.blocked_stores,
                    "limit": policy._town_store_visit_limit(STORE_HOME),
                    "blocked_reason": policy._town_blocked_reason,
                    "claims": tuple(
                        getattr(policy, "_town_claim_categories", ()) or ()
                    ),
                    "position": (
                        snapshot.player.position.y, snapshot.player.position.x
                    ),
                    "store_number": (
                        here.store_number if here is not None else None
                    ),
                    "overweight": (
                        snapshot.in_town and policy._inventory_overweight(snapshot)
                    ),
                    # S2b.2: the bar table's record (record-only, switch off)
                    **{
                        name: (policy.decision_claim or {}).get(name)
                        for name in (
                            "would_bar", "bars_set", "bars_lifted",
                            "bar_skipped",
                        )
                    },
                })
                policy.confirm_key_posted(key)
        cls.replay = replay
        return replay

    # ------------------------------------------------------------ recorded
    def test_recorded_home_passes_outlived_observed_home_effects(self):
        recorded = self.recorded
        stop = recorded[STOP]
        self.assertEqual(
            (stop["decision_sequence"], stop["key"], stop["reason"]),
            (3780, "9", "town:blocked:overweight-home-unreachable"),
        )
        self.assertEqual((stop["y"], stop["x"]), HOME_ENTRANCE)
        visit = recorded[VISIT_START : STOP + 1]
        # Nothing ever failed to approach Home in this visit.
        self.assertEqual({row["home_approach_fails"] for row in visit}, {0})
        # Home operations took effect (pack size on the confirming board) ...
        self.assertEqual(
            [recorded[index]["inventory_used"] for index in (
                DEPOSITS_OBSERVED[0] - 1, *DEPOSITS_OBSERVED,
            )],
            [18, 10, 2, 1],
        )
        self.assertEqual(
            [recorded[index]["inventory_used"] for index in (
                RESTORES_OBSERVED[0] - 1, *RESTORES_OBSERVED, STAFF_OBSERVED,
            )],
            [1, 13, 15, 16, 17],
        )
        self.assertEqual(recorded[RING_DEPOSIT]["key"], "do\r")
        self.assertEqual(
            [recorded[RING_DEPOSIT]["inventory_used"],
             recorded[RING_OBSERVED]["inventory_used"]],
            [17, 16],
        )
        # ... while the unsuccessful-pass count kept climbing through them.
        self.assertEqual(
            [
                recorded[index]["home_unsatisfied_passes"]
                for index in (
                    VISIT_START, 3714, 3736, *DEPOSITS_OBSERVED, 3770,
                    *RESTORES_OBSERVED, STAFF_OBSERVED, 3778, RING_OBSERVED,
                )
            ],
            [0, 1, 2, 2, 2, 2, 3, 3, 3, 4, 1, 2, 3],
        )
        # The Ring deposit finished the equipment work: the bound fell from
        # 300 to 3 on the very pass that made the count 3, and blocked Home.
        self.assertEqual(
            [
                (
                    recorded[index]["home_visit_limit"],
                    recorded[index]["outstanding_equipment_work"],
                    recorded[index]["home_blocked"],
                )
                for index in (RING_DEPOSIT, RING_OBSERVED, STOP)
            ],
            [(300, True, False), (3, False, True), (3, False, True)],
        )
        self.assertEqual(TOWN_STOP_PASS_LIMIT, 3)

    # ------------------------------------------------------------ H1
    def test_replay_reproduces_every_recorded_decision_before_the_stop(self):
        replay = self._replay()
        self.assertEqual(
            [
                index
                for index in range(STOP + 1)
                if (replay[index]["key"], replay[index]["reason"])
                != (self.recorded[index]["key"], self.recorded[index]["reason"])
            ],
            [*DIVERGENT, STOP],
        )

    def test_s2b2_the_bar_table_records_the_hunts_it_would_bar(self):
        # S2b.2 (record-only, switch off; the decisions are pinned above).
        # Seven hunts lost their monster (``target-lost``) and were barred
        # until it is unseen for the 50-turn clock; four of those bars lifted
        # inside the window, and three later hunts of a still-barred monster
        # are recorded as would-bars.  Nothing was skipped.
        replay = self._replay()
        bars_set = [
            (entry["owner"], entry["kind"], entry["ending"])
            for row in replay for entry in (row["bars_set"] or ())
        ]
        self.assertEqual(
            bars_set, [("hunt", "threat", "release:target-lost")] * 7
        )
        self.assertEqual(
            [entry["owner"] for row in replay
             for entry in (row["bars_lifted"] or ())],
            ["hunt"] * 4,
        )
        would = [row for row in replay if row["would_bar"] is not None]
        self.assertEqual(len(would), 3)
        for row in would:
            self.assertEqual(row["would_bar"]["owner"], "hunt")
            self.assertTrue(row["reason"].startswith("hunt"), row["reason"])
            self.assertEqual(
                row["would_bar"]["goal"]["monster"],
                row["would_bar"]["triggers"][0],
            )
        self.assertEqual(
            [row for row in replay if row["bar_skipped"] is not None], []
        )

    def test_h1_stop_board_proceeds_to_the_home_deposit(self):
        replay = self._replay()
        stop = replay[STOP]
        # The stop board stands on the Home entrance, overweight.
        self.assertEqual(stop["position"], HOME_ENTRANCE)
        self.assertEqual(stop["store_number"], STORE_HOME)
        self.assertTrue(stop["overweight"])
        # It enters Home for the surplus deposit instead of the terminal.
        self.assertEqual(
            (stop["key"], stop["reason"]), ("5", "home:weight-overload-deposit")
        )
        self.assertIsNone(stop["blocked_reason"])
        self.assertFalse(stop["blocked"])
        self.assertIn("weight-overload", stop["claims"])
        for row in replay[VISIT_START : STOP + 1]:
            self.assertNotEqual(
                row["blocked_reason"], "overweight-home-unreachable", row
            )

    def test_h1_every_observed_home_effect_resets_the_pass_count(self):
        replay = self._replay()
        recorded = self.recorded
        # Until the first observed effect the count is the recorded one.
        self.assertEqual(
            [row["passes"] for row in replay[VISIT_START : DEPOSITS_OBSERVED[0]]],
            [
                row["home_unsatisfied_passes"]
                for row in recorded[VISIT_START : DEPOSITS_OBSERVED[0]]
            ],
        )
        # Each confirmed deposit/withdrawal clears the passes charged before
        # it; a later pass counts from there.
        self.assertEqual(
            [
                replay[index]["passes"]
                for index in (
                    3736, *DEPOSITS_OBSERVED, 3770, *RESTORES_OBSERVED,
                    STAFF_OBSERVED, 3778, RING_DEPOSIT, RING_OBSERVED,
                )
            ],
            [2, 0, 0, 0, 1, 0, 0, 1, 1, 2, 2, 1],
        )
        # The Ring deposit still finishes the equipment work and drops the
        # bound to 3, but one pass after an observed effect blocks nothing.
        ring = replay[RING_OBSERVED]
        self.assertEqual(
            (ring["key"], ring["reason"], ring["limit"], ring["blocked"]),
            ("\x1b", "home:leave-after-one-operation", 3, False),
        )
        self.assertEqual(
            {row["approach_fails"] for row in replay[VISIT_START : STOP + 1]},
            {0},
        )


class HomeSuccessResetsTheVisitBoundTest(unittest.TestCase):
    """H2 (class): observed Home effects, not visits, decide the bound.

    User decision 2026-09-16: a Home operation that succeeded resets the
    unsuccessful-pass count (the 300/3 limits stay).  User decision
    2026-09-03 (overweight handling, 5): a deposit that really fails, or a
    Home the character really cannot approach, is a visible stop.

    Each successful Home operation is confirmed by a production observer,
    ``_observe_calibration_restore_batch`` (the outside board of an
    entrance-composed Home take, the observer of the recorded 3770-3775
    restores), on a board whose pack shows the taken item.  The unsuccessful
    passes are charged by the ledger producer the recorded visit's
    store-context exits and transaction approaches used.  The verdict is the
    public claim evaluation that set the recorded terminal.
    """

    def setUp(self):
        self.snapshot = test_policy_home.WeightOverloadTownTest()._snapshot()
        self.policy = HengbotPolicy()
        self.policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=None
        )
        self.remains = next(
            item for item in self.snapshot.inventory if item.slot == "r"
        )
        self.assertTrue(self.policy._inventory_overweight(self.snapshot))

    def _unsuccessful_home_pass(self):
        self.policy._town_errand_plan = policy_module.TownErrandPlan(
            [STORE_HOME], {STORE_HOME: ("equipment-work",)}
        )
        self.policy._report_town_stop_pass(
            self.snapshot, STORE_HOME, goal_satisfied=False
        )

    def _observed_home_take(self):
        """One posted Home take whose item the next outside board carries."""
        signature = self.policy._item_signature(self.remains)
        entry = (signature, 0, self.remains, 1, 0)
        self.policy._home_atomic_withdraw_pending = (*entry[:4], (entry,))
        self.policy._observe_calibration_restore_batch(
            self.snapshot, self.policy._home_atomic_withdraw_pending
        )
        self.assertIsNone(self.policy._home_atomic_withdraw_pending)

    def _successful_home_operations(self, rounds):
        """Two unsuccessful passes under the equipment work's 300 bound,
        then one observed Home operation, ``rounds`` times."""
        policy = self.policy
        ledger = policy._town_visit_ledger
        charged = []
        with patch.object(policy, "_outstanding_equipment_work", return_value=True):
            self.assertEqual(policy._town_store_visit_limit(STORE_HOME), 300)
            for _round in range(rounds):
                self._unsuccessful_home_pass()
                self._unsuccessful_home_pass()
                charged.append(ledger.unsatisfied_passes[STORE_HOME])
                self._observed_home_take()
                charged.append(ledger.unsatisfied_passes[STORE_HOME])
        return charged

    def _weight_claim(self):
        self.policy._town_claims_active(self.snapshot)
        return (
            "weight-overload" in self.policy._town_claim_categories,
            self.policy._town_blocked_reason,
            STORE_HOME in self.policy._town_visit_ledger.blocked_stores,
        )

    def _equipment_work_over(self):
        # No equipment work outstanding: the ordinary bound of 3 applies.
        return patch.object(
            self.policy, "_outstanding_equipment_work", return_value=False
        )

    def test_successful_home_operations_leave_the_bound_to_a_later_need(self):
        policy = self.policy
        ledger = policy._town_visit_ledger
        charged = self._successful_home_operations(3)
        # Six unsuccessful passes were charged; each observed operation
        # cleared the ones before it.
        self.assertEqual(charged, [2, 0, 2, 0, 2, 0])
        with self._equipment_work_over():
            self.assertEqual(policy._town_store_visit_limit(STORE_HOME), 3)
            # One more unsuccessful pass (live 3779's leave) is 1 of 3 ...
            self._unsuccessful_home_pass()
            self.assertEqual(ledger.unsatisfied_passes[STORE_HOME], 1)
            # ... and the overweight deposit, a different Home need, keeps
            # its visit.
            self.assertEqual(self._weight_claim(), (True, None, False))

    def test_an_observed_effect_releases_the_block_its_passes_installed(self):
        policy = self.policy
        with self._equipment_work_over():
            for _pass in range(policy._town_store_visit_limit(STORE_HOME)):
                self._unsuccessful_home_pass()
            self.assertIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)
            self._observed_home_take()
            self.assertEqual(self._weight_claim(), (True, None, False))

    def test_approach_failures_before_an_observed_effect_are_released(self):
        policy = self.policy
        ledger = policy._town_visit_ledger
        with self._equipment_work_over():
            limit = policy._town_store_visit_limit(STORE_HOME)
            ledger.approach_fails[STORE_HOME] = limit - 1
            self._observed_home_take()
            self.assertEqual(ledger.approach_fails[STORE_HOME], 0)
            ledger.approach_fails[STORE_HOME] += 1
            self.assertEqual(self._weight_claim(), (True, None, False))

    def test_a_genuinely_failing_approach_still_reaches_the_terminal(self):
        policy = self.policy
        ledger = policy._town_visit_ledger
        self._successful_home_operations(2)
        with self._equipment_work_over():
            for _failure in range(policy._town_store_visit_limit(STORE_HOME)):
                ledger.approach_fails[STORE_HOME] += 1
            self.assertEqual(
                self._weight_claim(),
                (False, "overweight-home-unreachable", False),
            )

    def test_passes_without_an_observed_effect_still_exhaust_the_bound(self):
        policy = self.policy
        self._successful_home_operations(2)
        with self._equipment_work_over():
            for _pass in range(policy._town_store_visit_limit(STORE_HOME)):
                self._unsuccessful_home_pass()
            self.assertEqual(
                self._weight_claim(),
                (False, "overweight-home-unreachable", True),
            )


if __name__ == "__main__":
    unittest.main()
