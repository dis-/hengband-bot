"""Recorded pins: the cured-curse calibration deferral was an absorbing state.

2026-09-23 03:42-03:44 (protocol 3, HEAD 075b92c).  The town visit started a
character calibration, stripped everything removable and reached the capture
phase still wearing ``☆軟革ブーツ『ヴェアファナ』`` — a cursed artifact the
strip cannot take off.  Decision 560 therefore aborted with
``calibration:abort:unremovable-cursed-equipment``, which latches
``_calibration_blocked_this_visit`` and records the deferral cause.  While that
curse stayed worn, ``_equipment_departure_ready`` granted the matching
mechanical exemption, so departure was open.  "Unremovable" names the strip,
not the curse: the boots carried no HEAVY_CURSE tag and the pack simply held
no Remove Curse scroll at that moment.

Decision 628 then read a Remove Curse scroll (``town:remove-curse``, key
``rh``) and decision 629 observed the board uncursed.  The exemption vanished
with the curse, but the deferral stayed latched: calibration entry kept
answering ``visit-blocked`` while ``departure_block.failed`` stayed
``["equipment_departure_ready"]``.  Decisions 639-662 are the recorded
consequence — 24 identical ``town:blocked:equipment-calibration-required``
rows, ``passes_since_progress`` counting 1..23, the arbiter retired at tenure
24 — and the driver stopped with ``loop-detected``.  No key the bot could post
left that state.

Fixture: tests/fixtures/calibration-visit-blocked-loop-20260923.jsonl.gz,
written by tests/extract_calibration_visit_blocked_loop_fixture.py.

pin_vacuity: the capture holds boards, Home catalogues and decision facts, not
a restorable policy.  Each pin therefore rebuilds the deferral by running the
PRODUCTION owner of the recorded abort (``_calibration_observe`` on the
recorded decision-560 board, entered in the ``strip`` phase that decision 559
recorded) and then runs the production owners of the recorded refusal —
``_calibration_observe`` + ``_calibration_town_key`` +
``_equipment_departure_ready``, in the order ``_choose_key`` calls them — on
every recorded input board of the loop.  The control reproduces the recorded
``calibration.entry_blocker`` and ``departure_block.failed`` of all 24 rows.
Public ``choose_key`` is NOT used as the verdict here: the reconstructed policy
has no live town plan, procurement ledger or arbiter tenure, so its emitted
reason is its own, not the recorded one.

Declared walls: the reconstruction enters the abort in the recorded ``strip``
phase instead of replaying the recorded Home deposits, so it carries no
calibration restore queue; its phase therefore settles at None where decision
560 recorded ``restore-supplies``.  Both agree from decision 602 on, which is
the state every board of the frozen loop window recorded.
"""

from __future__ import annotations

import ast
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import tests  # noqa: F401  -- live runtime-file isolation, also for bare runs
from hengbot.cli import _parse_items, snapshot_protocol_version
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_STUCK_LIMIT


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    ROOT / "tests" / "fixtures" /
    "calibration-visit-blocked-loop-20260923.jsonl.gz"
)
FIXTURE_SHA256 = (
    "a7e6389d6fd161ef4bd4ce5564eb115d0fa232de7b0cea21e19176a81a1d7fc8"
)
EDIT = Path("C:/hengband/lib/edit")
ABORT = "calibration:abort:unremovable-cursed-equipment"
CURSED_BOOTS = "☆軟革ブーツ『ヴェアファナ』 [2,+4] (+4加速) {呪われている, +速器隠r冷獄}"
BLOCKED_REASON = "town:blocked:equipment-calibration-required"
PRE_SCAN_TURN = 4_734_609
POST_SCAN_TURN = 4_741_084


def _records():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


class CalibrationVisitBlockedLoopRecordedPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        records = _records()
        cls.knowledge = {
            record["turn"]: record["board"]
            for record in records if record["role"] == "home-knowledge"
        }
        cls.inputs = {
            record["decision"]["decision_sequence"]: record
            for record in records if record["role"] == "decision-input"
        }
        cls.window = [
            record for record in records if record["role"] == "blocked-window"
        ]

    def _home_catalogue(self, turn):
        row = self.knowledge[turn]
        return tuple(_parse_items(
            row["knowledge"]["items"], protocol=snapshot_protocol_version(row)
        ))

    def _board(self, sequence):
        return parse_snapshot(self.inputs[sequence]["board"], self.monrace)

    def _deferred_policy(self):
        """Rebuild the recorded deferral through the production abort path."""
        board = self._board(560)
        policy = HengbotPolicy(monrace_knowledge=self.monrace)
        policy.prime(board)
        policy.consume_home_knowledge(self._home_catalogue(PRE_SCAN_TURN))
        policy._refresh_carried_equipment_catalog(board)
        # The phase this decision was entered with is a recorded fact: it is
        # decision 559's telemetry, not a value this test chooses.
        policy._calibration_phase = (
            self.inputs[559]["decision"]["calibration"]["phase"]
        )
        policy._calibration_observe(board)
        # The Home catalogue the live bot held once the loop began.
        policy.consume_home_knowledge(self._home_catalogue(POST_SCAN_TURN))
        return policy, board

    def _drive_recorded_window(self, policy):
        """Run the recorded loop boards through the production town owners."""
        observed = []
        for record in self.window:
            board = parse_snapshot(record["board"], self.monrace)
            policy._refresh_carried_equipment_catalog(board)
            policy._calibration_observe(board)
            entry = policy.calibration_entry_state(board)
            calibration_key = policy._calibration_town_key(board)
            observed.append({
                "entry_blocker": entry["entry_blocker"],
                "phase": entry["phase"],
                "posted": calibration_key is not None,
                "departure_ready": policy._equipment_departure_ready(board),
            })
        return observed

    # ---- substrate fidelity ------------------------------------------------

    def test_fixture_freezes_the_recorded_absorbing_loop(self):
        self.assertEqual(
            hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), FIXTURE_SHA256
        )
        self.assertEqual(sorted(self.knowledge), [PRE_SCAN_TURN, POST_SCAN_TURN])
        self.assertEqual(sorted(self.inputs), [559, 560, 628, 629])
        self.assertEqual(len(self.window), 24)

        stripping = self.inputs[559]["decision"]
        self.assertEqual(stripping["calibration"]["phase"], "strip")
        self.assertIsNone(stripping["calibration"].get("last_abort"))
        aborted = self.inputs[560]["decision"]
        self.assertEqual(aborted["calibration"]["last_abort"], ABORT)
        self.assertEqual(
            [(item["slot"], item["name"])
             for item in self.inputs[560]["board"]["equipment"]],
            [("feet", CURSED_BOOTS)],
        )

        cure = self.inputs[628]["decision"]
        self.assertEqual((cure["key"], cure["reason"]), ("rh", "town:remove-curse"))
        self.assertEqual(
            [item["name"] for item in self.inputs[628]["board"]["equipment"]
             if item["is_cursed"]],
            [CURSED_BOOTS],
        )
        cured = self.inputs[629]["decision"]
        self.assertEqual(cured["calibration"]["entry_blocker"], "visit-blocked")
        self.assertEqual(
            [item["name"] for item in self.inputs[629]["board"]["equipment"]
             if item["is_cursed"]],
            [],
        )
        self.assertEqual(len(self.inputs[629]["board"]["equipment"]), 11)

        self.assertEqual(
            {record["decision"]["reason"] for record in self.window},
            {BLOCKED_REASON},
        )
        self.assertEqual(
            [record["decision"]["key"] for record in self.window],
            ["1"] + ["5"] * 23,
        )
        self.assertEqual(
            {record["decision"]["calibration"]["entry_blocker"]
             for record in self.window},
            {"visit-blocked"},
        )
        self.assertEqual(
            {tuple(record["decision"]["departure_block"]["failed"])
             for record in self.window},
            {("equipment_departure_ready",)},
        )
        self.assertEqual(
            [record["decision"]["departure_block"]["town_ledger"][
                "passes_since_progress"]
             for record in self.window],
            [1] + list(range(1, 24)),
        )
        self.assertEqual(
            self.window[-1]["decision"]["arbiter"],
            {
                "budget_remaining_estimate": 0,
                "decision_attribution": "town-plan",
                "owner": "town-plan",
                "producer_owner": "town-plan",
                "progress": False,
                "retired": True,
                "retirement_set": ["town-plan"],
                "tenure": 24,
                "would_retire": True,
            },
        )

    def test_recorded_strip_end_reproduces_the_deferral_and_its_exemption(self):
        policy, cursed = self._deferred_policy()

        self.assertEqual(policy._calibration_last_abort, ABORT)
        self.assertEqual(
            policy._calibration_deferral_cause, "unremovable-cursed-equipment"
        )
        self.assertEqual(policy._calibration_aborts_this_visit, 1)
        self.assertTrue(policy._calibration_blocked_this_visit)
        entry = policy.calibration_entry_state(cursed)
        recorded = self.inputs[560]["decision"]["calibration"]
        self.assertEqual(entry["last_abort"], recorded["last_abort"])
        self.assertEqual(entry["entry_blocker"], "visit-blocked")
        # Declared wall: the reconstruction never ran the recorded Home
        # deposits, so it has no restore queue and the abort settles the phase
        # at None, where decision 560 recorded "restore-supplies".  The live
        # queue drained to the same None by decision 602, which is the state
        # every board of the loop window recorded.
        self.assertIsNone(entry["phase"])
        self.assertEqual(recorded["phase"], "restore-supplies")
        self.assertEqual(
            {record["decision"]["calibration"]["phase"]
             for record in self.window},
            {None},
        )
        # C3 half one: while the curse is worn the recorded departure
        # exemption stands, and the deferral is not released.
        self.assertTrue(policy._equipment_departure_ready(cursed))

    # ---- C1 ---------------------------------------------------------------

    def test_c1_cured_curse_reopens_calibration_on_every_recorded_board(self):
        policy, _cursed = self._deferred_policy()

        observed = self._drive_recorded_window(policy)

        self.assertEqual(
            {row["entry_blocker"] for row in observed}, {None},
            "calibration is still refused after its deferral cause is cured",
        )
        self.assertFalse(policy._calibration_blocked_this_visit)
        self.assertIsNone(policy._calibration_deferral_cause)
        self.assertIsNone(policy._calibration_deferral_reason)
        # The visit's abort budget is NOT refunded by the release.
        self.assertEqual(policy._calibration_aborts_this_visit, 1)
        # The bot is doing the calibration again instead of repeating a
        # refusal: the phase machine advances on the recorded boards.
        self.assertEqual(
            [row["phase"] for row in observed], [None] + ["deposit"] * 23
        )
        self.assertEqual(policy._calibration_phase, "deposit")

    def test_c1_revert_returns_the_recorded_absorbing_state(self):
        with patch.object(
            HengbotPolicy,
            "_release_cured_calibration_deferral",
            lambda self, snapshot: None,
        ):
            policy, _cursed = self._deferred_policy()
            observed = self._drive_recorded_window(policy)

            self.assertTrue(policy._calibration_blocked_this_visit)
            self.assertIsNone(policy._calibration_phase)

        # Exactly the recorded refusal, on every recorded row of the loop, with
        # no calibration key to post and departure still gated: the state the
        # driver stopped in.
        self.assertEqual(
            [row["entry_blocker"] for row in observed],
            [record["decision"]["calibration"]["entry_blocker"]
             for record in self.window],
        )
        self.assertEqual({row["entry_blocker"] for row in observed}, {"visit-blocked"})
        self.assertEqual({row["posted"] for row in observed}, {False})
        self.assertEqual({row["departure_ready"] for row in observed}, {False})

    # ---- C2 ---------------------------------------------------------------

    def test_c2_reopened_calibration_still_gates_departure(self):
        policy, _cursed = self._deferred_policy()

        observed = self._drive_recorded_window(policy)

        # Releasing the deferral does not open the departure conjunction: the
        # calibration is now performable, so it must still be performed.
        self.assertEqual({row["departure_ready"] for row in observed}, {False})
        final = parse_snapshot(self.window[-1]["board"], self.monrace)
        preparation = policy._prepare_equipment_optimization(final)
        self.assertEqual(preparation.blockers, ("calibration-required",))
        self.assertEqual(
            tuple(self.window[-1]["decision"]["equipment_blockers"]),
            preparation.blockers,
        )

    # ---- C3 ---------------------------------------------------------------

    def test_c3_worn_curse_keeps_the_deferral_and_its_exemption(self):
        policy, cursed = self._deferred_policy()

        # The recorded cursed board, observed as many times as the recorded
        # loop ran: the deferral never releases while the curse is worn.
        for _ in range(len(self.window)):
            policy._calibration_observe(cursed)
            self.assertTrue(policy._calibration_blocked_this_visit)
            self.assertEqual(
                policy.calibration_entry_state(cursed)["entry_blocker"],
                "visit-blocked",
            )
        self.assertEqual(
            policy._calibration_deferral_cause, "unremovable-cursed-equipment"
        )
        self.assertTrue(policy._equipment_departure_ready(cursed))

    def test_c3_release_is_bounded_by_the_visit_abort_budget(self):
        policy, _cursed = self._deferred_policy()
        cured = self._board(629)
        policy._calibration_aborts_this_visit = STORE_STUCK_LIMIT

        policy._calibration_observe(cured)

        self.assertTrue(policy._calibration_blocked_this_visit)
        self.assertEqual(
            policy.calibration_entry_state(cured)["entry_blocker"],
            "visit-blocked",
        )

    def test_c3_other_deferral_causes_are_untouched(self):
        policy, _cursed = self._deferred_policy()
        cured = self._board(629)
        policy._calibration_deferral_cause = "capture-invalid"
        policy._calibration_deferral_reason = "calibration:deferred:capture-invalid"

        policy._calibration_observe(cured)

        self.assertTrue(policy._calibration_blocked_this_visit)
        self.assertEqual(policy._calibration_deferral_cause, "capture-invalid")

    def test_restored_checkpoint_releases_the_deferral_identically(self):
        """restore_checkpoint rebuilds __dict__ without __init__."""
        policy, _cursed = self._deferred_policy()
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        cured = self._board(629)

        self.assertTrue(restored._calibration_blocked_this_visit)
        self.assertEqual(
            restored._calibration_deferral_cause, "unremovable-cursed-equipment"
        )

        restored._calibration_observe(cured)
        policy._calibration_observe(cured)

        self.assertFalse(restored._calibration_blocked_this_visit)
        self.assertIsNone(restored._calibration_deferral_cause)
        self.assertEqual(
            restored.calibration_entry_state(cured)["entry_blocker"],
            policy.calibration_entry_state(cured)["entry_blocker"],
        )
        self.assertNotEqual(
            restored.calibration_entry_state(cured)["entry_blocker"],
            "visit-blocked",
        )

    # ---- structural -------------------------------------------------------

    def test_release_runs_at_decision_entry_for_the_latch_it_owns(self):
        source_root = ROOT / "src" / "hengbot"
        methods = {}
        clearers = set()
        for path in sorted(source_root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for member in node.body:
                        if isinstance(member, ast.FunctionDef):
                            methods.setdefault(member.name, member)
                if not isinstance(node, ast.FunctionDef):
                    continue
                for statement in ast.walk(node):
                    if (
                        isinstance(statement, ast.Assign)
                        and isinstance(statement.value, ast.Constant)
                        and statement.value.value is False
                        and any(
                            isinstance(target, ast.Attribute)
                            and target.attr == "_calibration_blocked_this_visit"
                            for target in statement.targets
                        )
                    ):
                        clearers.add((path.name, node.name))
        # Exactly one owner clears the latch during a visit: this release.  The
        # other two writers are the constructor default and the fresh-visit
        # reset that needs a town departure the latch itself used to forbid.
        self.assertEqual(
            clearers,
            {
                ("policy.py", "__init__"),
                ("policy_observation.py", "_observe"),
                ("policy_calibration.py", "_release_cured_calibration_deferral"),
            },
        )

        release = methods["_release_cured_calibration_deferral"]
        observe = methods["_calibration_observe"]
        self.assertEqual(
            ast.unparse(observe.body[1]),
            "self._release_cured_calibration_deferral(snapshot)",
        )
        self.assertIn(
            "self._calibration_observe(snapshot)",
            ast.unparse(methods["_choose_key"]),
        )
        # The only writer that clears the latch outside the fresh-visit reset
        # names the cause it releases and the budget that bounds it.
        release_source = ast.unparse(release)
        self.assertIn("unremovable-cursed-equipment", release_source)
        self.assertIn("STORE_STUCK_LIMIT", release_source)
        self.assertIn("_calibration_blocked_this_visit = False", release_source)


if __name__ == "__main__":
    unittest.main()
