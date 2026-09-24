"""The S1 claim register, its ledger, its metric and its lint.

``SOL-DESIGN-ownership-contract.md`` section 6 stage **S1** is attribution
only: every decision is recorded under a declared claim, nothing is enforced,
and no key or reason may change because the register exists.  The pins are the
four this round was given:

S1-1 behaviour neutrality.  Two recorded replays -- the dungeon capture
     ``tests/fixtures/loot-choke-oscillation-20260923.jsonl.gz`` (24 boards of
     the 2026-09-23 06:00 stop) and the town capture
     ``tests/fixtures/calibration-visit-blocked-loop-20260923.jsonl.gz`` (24
     boards of the 03:44 stop) -- produce byte-identical keys and reasons, and
     byte-identical decision rows bar the declared volatiles and the claim
     block itself, with the register enabled and with it disabled.
S1-2 a checkpoint pickled before this change restores and decides: both a
     ``DecisionCandidate`` whose ``__reduce__`` payload carries the five
     pre-S1 arguments, and the real pre-S1 policy checkpoint of
     ``tests/fixtures/home-deferral-absorbing-state.json.gz``.
S1-3 the ledger records a claim for every decision of a recorded replay, and
     the implicit-handoff metric over it matches a hand-checked count on the
     whole 24-decision window (the sequence is written out below).
S1-4 the lint's count is reproducible and its marker detection is correct on
     ``tests/fixtures/ownership_claim_lint_sample.py``, whose every site is
     annotated in the fixture with the verdict asserted here.

Walls: ``tests/__init__`` runtime-file isolation; every ledger, decision log
and report is written inside a ``TemporaryDirectory``.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare runs

import base64
import gzip
import hashlib
import json
import pickle
import tempfile
import unittest
from pathlib import Path

from hengbot import cli
from hengbot.claim_register import (
    CLOSING_EVENTS,
    ClaimOwner,
    ClaimRegister,
    ClaimState,
    claims,
    observe,
    owner_of,
    reach,
    terminal,
)
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.ownership_metrics import (
    OWNERSHIP_CLAIMS_NAME,
    OWNERSHIP_METRICS_NAME,
    OwnershipMetricsLedger,
    implicit_handoffs,
    read_records,
)
from hengbot.policy import HengbotPolicy
from hengbot.policy_types import DecisionCandidate, _restore_decision_candidate
from hengbot.town_arbiter import UNREGISTERED_FAMILY, owner_families

import ownership_claim_lint


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
EDIT = Path("C:/hengband/lib/edit")
DUNGEON = FIXTURES / "loot-choke-oscillation-20260923.jsonl.gz"
DUNGEON_SHA256 = "a6195e5ed8f0c5d947b34f07d287fde139e0fd569ca98950af53ae74e1586442"
TOWN = FIXTURES / "calibration-visit-blocked-loop-20260923.jsonl.gz"
LINT_SAMPLE = FIXTURES / "ownership_claim_lint_sample.py"
LEGACY_CHECKPOINT = FIXTURES / "home-deferral-absorbing-state.json.gz"

# S1-3, hand-checked.  The 24 replayed boards of the 06:00 capture, in order,
# with the owner family the reason's registration gives each one.  **S2a
# re-pinned these**: the families are the same producers as before, named.
# Before S2a (kept so the change is readable):
#   1- 2  explore                 -> misc
#   3- 5  detected:prepare-choke  -> unregistered   (change 1)
#   6     melee                   -> misc           (change 2)
#   7-24  detected:prepare-choke  -> unregistered   (change 3)
# After S2a:
#   1- 2  explore                 -> explore
#   3- 5  detected:prepare-choke  -> positioning    (change 1)
#   6     melee                   -> combat         (change 2)
#   7-24  detected:prepare-choke  -> positioning    (change 3)
# Three owner changes either way; no row before any of them carries a
# ``closed`` and no row after one closes the previous claim, so all three are
# implicit.  The count is unchanged because these three *are* three different
# producers: what S2a removed is the catch-all, not the handoff.
HAND_CHECKED_OWNERS = (
    ["explore"] * 2 + ["positioning"] * 3 + ["combat"] + ["positioning"] * 18
)
HAND_CHECKED_PAIRS = {
    "explore>positioning": 1,
    "positioning>combat": 1,
    "combat>positioning": 1,
}

# S1-4, read off tests/fixtures/ownership_claim_lint_sample.py's own comments.
LINT_SAMPLE_SITES = [
    (16, False, "store-router"),
    (21, False, "town-plan"),
    (26, False, "mixed"),
    (31, False, "unknown"),
    (37, True, "departure"),
    (44, True, "departure"),
    (52, True, "survival"),
    (59, False, "survival"),
    (65, False, "home-visit"),
]


def _volatile_free(record: dict) -> dict:
    """Drop the wall-clock fields two independent runs cannot share.

    The same declared normalisation the S0 neutrality pin uses (``time`` and
    every ``elapsed_seconds``), and nothing else -- except the ``claim`` block,
    which by construction only one of the two runs has.  The comparison of the
    claim block is its own assertion below, so it is not being hidden here.
    """

    def strip(value):
        if isinstance(value, dict):
            return {
                name: strip(item)
                for name, item in value.items()
                if name not in ("elapsed_seconds", "claim")
            }
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value

    return strip({name: value for name, value in record.items() if name != "time"})


def _rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class _Replay:
    """One recorded capture, replayed through the driver's decision writer."""

    monrace = None

    @classmethod
    def knowledge(cls):
        if cls.monrace is None:
            cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        return cls.monrace

    @classmethod
    def dungeon_boards(cls):
        with gzip.open(DUNGEON, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        skill = next(r for r in records if r["role"] == "skill-knowledge")["board"]
        return skill, [r["board"] for r in records if r["role"] == "decision-input"]

    @classmethod
    def town_boards(cls):
        with gzip.open(TOWN, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        return None, [
            r["board"] for r in records if r["role"] == "blocked-window"
        ]

    @classmethod
    def run(cls, root: Path, skill, boards, *, register: bool, ledger=False):
        """Replay the boards; return the trajectory and the decision log path."""
        monrace = cls.knowledge()
        log = root / "bot-decisions.jsonl"
        metrics = (
            OwnershipMetricsLedger(
                root / OWNERSHIP_METRICS_NAME, progress_interval_seconds=1e9
            )
            if ledger
            else None
        )
        if metrics is not None:
            metrics.note_session_start({"time": "2026-09-24T06:00:00+0900"}, pid=1)
        policy = HengbotPolicy(monrace_knowledge=monrace)
        if not register:
            # The seam the neutrality pin needs: with no register there is no
            # declaration, no claim block and no ledger record.
            policy._claim_register = None
        if skill is not None:
            policy.consume_skill_knowledge(skill)
        trajectory = []
        for raw in boards:
            board = parse_snapshot(raw, monrace)
            key = policy.choose_key(board)
            key = policy.validate_read_key(board, key)
            cli._write_decision(
                log, board, key, policy.last_reason, policy,
                ownership_ledger=metrics,
            )
            trajectory.append((key, policy.last_reason))
            if skill is not None:
                policy.confirm_key_posted(key)
        return trajectory, log


class ClaimOwnerDerivationTest(unittest.TestCase):
    """The owner enum is the arbiter's registrations; nothing is invented."""

    def test_the_enum_is_exactly_the_families_that_exist_today(self):
        self.assertEqual(
            [owner.value for owner in ClaimOwner],
            [*owner_families(), UNREGISTERED_FAMILY],
        )
        # S2a: 20 arbitrating registrations + 10 census-only families of
        # design 6/S2a + ``unregistered``.
        self.assertEqual(len(ClaimOwner), 31)

    def test_an_unknown_family_lands_on_unregistered_rather_than_raising(self):
        self.assertEqual(owner_of("no-such-family"), ClaimOwner.UNREGISTERED)
        self.assertEqual(owner_of(None), ClaimOwner.UNREGISTERED)
        self.assertEqual(owner_of(ClaimOwner.SURVIVAL), ClaimOwner.SURVIVAL)

    def test_goals_and_claims_are_plain_data(self):
        register = ClaimRegister()
        claim = register.declare(ClaimOwner.STORE_ROUTER, reach((3, 4)))
        restored = pickle.loads(pickle.dumps(claim))
        self.assertEqual(restored, claim)
        self.assertEqual(restored.goal.cell, (3, 4))
        self.assertEqual(
            json.loads(json.dumps(claim.as_dict(distance=2)))["goal"],
            {"kind": "Reach", "cell": [3, 4]},
        )
        self.assertEqual(
            observe(("gold", "floor"), 10).as_dict(),
            {"kind": "Observe", "expectation": ["floor", "gold"], "within": 10},
        )
        self.assertEqual(
            terminal("wait").as_dict(), {"kind": "Terminal", "effect": "wait"}
        )

    def test_the_same_owner_and_goal_keep_one_id_until_the_claim_closes(self):
        register = ClaimRegister()
        first = register.declare(ClaimOwner.STORE_ROUTER, reach((3, 4)))
        again = register.declare(ClaimOwner.STORE_ROUTER, reach((3, 4)))
        self.assertEqual(again.claim_id, first.claim_id)
        moved = register.declare(ClaimOwner.STORE_ROUTER, reach((3, 5)))
        self.assertEqual(moved.claim_id, first.claim_id + 1)
        register.complete()
        self.assertEqual(register.current.state, ClaimState.COMPLETE)
        after = register.declare(ClaimOwner.STORE_ROUTER, reach((3, 5)))
        self.assertEqual(after.claim_id, first.claim_id + 2)
        self.assertIsNone(after.closed)

    def test_the_marker_returns_the_producer_unchanged(self):
        def producer():
            return "6"

        marked = claims(ClaimOwner.SURVIVAL)(producer)
        self.assertIs(marked, producer)
        self.assertIs(producer.__hengbot_claim_owner__, ClaimOwner.SURVIVAL)


class NeutralityTest(unittest.TestCase):
    """S1-1: the register changes no key, no reason and no other row field."""

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(DUNGEON.read_bytes()).hexdigest() == DUNGEON_SHA256

    def _compare(self, skill, boards):
        with tempfile.TemporaryDirectory(prefix="claim-off-") as off, \
                tempfile.TemporaryDirectory(prefix="claim-on-") as on:
            without, plain = _Replay.run(
                Path(off), skill, boards, register=False
            )
            with_, noted = _Replay.run(Path(on), skill, boards, register=True)
            self.assertEqual(len(without), len(boards))
            self.assertEqual(
                json.dumps(without, ensure_ascii=False),
                json.dumps(with_, ensure_ascii=False),
            )
            plain_rows, noted_rows = _rows(plain), _rows(noted)
            self.assertEqual(
                [_volatile_free(row) for row in plain_rows],
                [_volatile_free(row) for row in noted_rows],
            )
            return plain_rows, noted_rows

    def test_the_dungeon_capture_decides_identically(self):
        skill, boards = _Replay.dungeon_boards()
        plain_rows, noted_rows = self._compare(skill, boards)
        self.assertFalse([row for row in plain_rows if "claim" in row])
        self.assertEqual(
            len([row for row in noted_rows if "claim" in row]), len(boards)
        )

    def test_the_town_capture_decides_identically(self):
        skill, boards = _Replay.town_boards()
        plain_rows, noted_rows = self._compare(skill, boards)
        self.assertFalse([row for row in plain_rows if "claim" in row])
        self.assertEqual(
            len([row for row in noted_rows if "claim" in row]), len(boards)
        )

    def test_two_runs_with_the_register_allocate_the_same_ids(self):
        skill, boards = _Replay.dungeon_boards()
        with tempfile.TemporaryDirectory(prefix="claim-a-") as first, \
                tempfile.TemporaryDirectory(prefix="claim-b-") as second:
            _, one = _Replay.run(Path(first), skill, boards, register=True)
            _, two = _Replay.run(Path(second), skill, boards, register=True)
            self.assertEqual(
                [row["claim"] for row in _rows(one)],
                [row["claim"] for row in _rows(two)],
            )


class PreS1CheckpointTest(unittest.TestCase):
    """S1-2: what was pickled before this change still restores and decides."""

    def test_a_pre_s1_decision_candidate_payload_still_loads(self):
        identity = object()
        decision_identity = object()
        # Exactly the five-argument payload ``DecisionCandidate.__reduce__``
        # produced before ``claim_id`` existed, rebuilt through the same
        # callable a pickle from that build names.
        legacy = pickle.dumps(
            _LegacyCandidate("6", "explore", decision_identity, None, identity)
        )
        restored = pickle.loads(legacy)
        self.assertIsInstance(restored, DecisionCandidate)
        self.assertEqual(str(restored), "6")
        self.assertEqual(restored.reason, "explore")
        self.assertIsNone(restored.claim_id)
        # And the current payload round-trips with its declaration intact.
        current = DecisionCandidate(
            "6", reason="explore", decision_identity=decision_identity,
            claim_id=7,
        )
        self.assertEqual(pickle.loads(pickle.dumps(current)).claim_id, 7)

    def test_a_pre_s1_policy_checkpoint_restores_and_decides(self):
        with gzip.open(LEGACY_CHECKPOINT, "rt", encoding="utf-8") as stream:
            capture = json.load(stream)
        producer = capture["sequence"][0]
        snapshot = pickle.loads(
            base64.b64decode(capture["snapshots_pickle_b64"][producer["snapshot_id"]])
        )
        state = pickle.loads(
            base64.b64decode(capture["producer_checkpoint_pickle_b64"])
        )
        # The capture genuinely predates S1; assert that rather than assume it.
        self.assertNotIn("_claim_register", state)
        self.assertNotIn("decision_claim", state)

        restored = restore_checkpoint(
            HengbotPolicy, capture["producer_checkpoint_pickle_b64"]
        )
        self.assertIsInstance(restored._claim_register, ClaimRegister)
        self.assertIsNone(restored.decision_claim)
        self.assertEqual(
            (restored.choose_key(snapshot), restored.last_reason),
            (producer["expected_key"], producer["expected_reason"]),
        )
        # Restoring gave it a register, so the restored decision is attributed.
        self.assertEqual(restored.decision_claim["claim_id"], 1)
        self.assertEqual(
            restored.decision_claim["decision_sequence"],
            restored._decision_sequence,
        )


class _LegacyCandidate:
    """Reproduces the pre-S1 five-argument ``DecisionCandidate`` payload."""

    def __init__(self, key, reason, decision_identity, route, identity):
        self._payload = (key, reason, decision_identity, route, identity)

    def __reduce__(self):
        return (_restore_decision_candidate, self._payload)


class ClaimLedgerTest(unittest.TestCase):
    """S1-3: a claim for every decision, and the metric on a checked window."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="claim-ledger-"))
        skill, boards = _Replay.dungeon_boards()
        self.boards = boards
        self.trajectory, self.log = _Replay.run(
            self.root, skill, boards, register=True, ledger=True
        )
        self.claims = read_records(self.root / OWNERSHIP_CLAIMS_NAME)

    def test_the_ledger_is_a_sibling_file_of_the_session_ledger(self):
        self.assertTrue((self.root / OWNERSHIP_METRICS_NAME).exists())
        self.assertTrue((self.root / OWNERSHIP_CLAIMS_NAME).exists())
        session = read_records(self.root / OWNERSHIP_METRICS_NAME)
        # The session file keeps its own record kinds; the 24 claims are not
        # in it.  (The first decision always writes one heartbeat.)
        self.assertEqual(
            {record["kind"] for record in session},
            {"session-start", "decision-progress"},
        )
        self.assertEqual(len(session), 2)
        # The heartbeat carries the running claim counts of design 5.1/5.2, so
        # a killed session leaves them behind even if the claim file is gone.
        self.assertEqual(session[-1]["claims"], 1)  # the first decision
        self.assertEqual(session[-1]["implicit_handoffs"], 0)

    def test_every_decision_of_the_replay_carries_a_claim(self):
        rows = _rows(self.log)
        self.assertEqual(len(rows), len(self.boards))
        self.assertEqual(len(self.claims), len(self.boards))
        self.assertEqual(
            [row["claim"]["claim_id"] for row in rows],
            [record["claim_id"] for record in self.claims],
        )
        for record in self.claims:
            with self.subTest(sequence=record["decision_sequence"]):
                self.assertIsNotNone(record["claim_id"])
                self.assertIn(record["owner"], {owner.value for owner in ClaimOwner})
                self.assertIn(
                    record["state"], {state.value for state in ClaimState}
                )
                self.assertIn(record["goal"]["kind"],
                              {"Reach", "Observe", "Terminal"})
                self.assertIn(record["closed"], {None, *CLOSING_EVENTS})

    def test_a_candidate_key_carries_the_declaration_token(self):
        """Design 5.4: the token rides the existing candidate, not a new type.

        The 24 boards of this capture all emit plain ``str`` keys -- only the
        quest producers build a ``DecisionCandidate`` -- so the declaration
        point is driven directly, on a real board, with a candidate built by
        the real constructor.  ``_record_decision_claim`` is the method under
        test; nothing about its answer is supplied here.
        """
        skill, boards = _Replay.dungeon_boards()
        self.assertFalse(
            [key for key, _reason in self.trajectory
             if isinstance(key, DecisionCandidate)]
        )
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        policy.consume_skill_knowledge(skill)
        board = parse_snapshot(boards[0], _Replay.knowledge())
        policy.choose_key(board)
        candidate = DecisionCandidate(
            "6", reason="quest:enter:approach", decision_identity=object()
        )
        self.assertIsNone(candidate.claim_id)

        policy.last_reason = "quest:enter:approach"
        policy._record_decision_claim(board, candidate)

        self.assertEqual(policy.decision_claim["owner"], "quest-request")
        self.assertEqual(candidate.claim_id, policy.decision_claim["claim_id"])
        self.assertEqual(
            pickle.loads(pickle.dumps(candidate)).claim_id, candidate.claim_id
        )

    def test_a_reach_goal_records_its_measured_distance(self):
        reaching = [
            record for record in self.claims
            if record["goal"]["kind"] == "Reach"
        ]
        self.assertTrue(reaching)
        for record in reaching:
            with self.subTest(sequence=record["decision_sequence"]):
                self.assertIsInstance(record["distance"], int)
                self.assertGreaterEqual(record["distance"], 0)

    def test_the_metric_matches_the_hand_checked_window(self):
        self.assertEqual(
            [record["owner"] for record in self.claims], HAND_CHECKED_OWNERS
        )
        self.assertFalse([record for record in self.claims if record["closed"]])
        self.assertFalse(
            [record for record in self.claims if record["closed_claim"]]
        )
        measured = implicit_handoffs(self.claims)
        self.assertEqual(measured["rows"], len(self.boards))
        self.assertEqual(measured["implicit_handoffs"], 3)
        self.assertEqual(measured["pairs"], HAND_CHECKED_PAIRS)

    def test_the_producer_breakdown_separates_the_catch_all_family(self):
        """The family breakdown cannot see seek-loot from melee; this can.

        After S2a the two answers coincide on this capture, because the
        family now *is* the producer: ``producer_identity`` only refines a
        reason that landed in a catch-all, and none of these do.
        """
        measured = implicit_handoffs(self.claims, by="producer")
        self.assertEqual(measured["implicit_handoffs"], 3)
        self.assertEqual(
            measured["pairs"],
            {
                "explore>positioning": 1,
                "positioning>combat": 1,
                "combat>positioning": 1,
            },
        )

    def test_a_closed_claim_is_not_an_implicit_handoff(self):
        """The negative control for the metric, on constructed rows."""
        def row(session, claim_id, owner, closed=None, closed_claim=None):
            return {
                "kind": "claim", "session": session, "claim_id": claim_id,
                "owner": owner, "producer": owner, "closed": closed,
                "closed_claim": closed_claim,
            }

        rows = [
            row("s", 1, "store-router"),
            row("s", 2, "home-visit"),                      # implicit
            row("s", 2, "home-visit", closed="retired"),
            row("s", 3, "departure"),                       # explicit: retired
            row("s", 4, "survival", closed_claim={
                "claim_id": 3, "owner": "departure", "closed": "complete",
            }),                                             # explicit: arrived
            row("other", 5, "misc"),                        # another session
        ]
        measured = implicit_handoffs(rows)
        self.assertEqual(measured["implicit_handoffs"], 1)
        self.assertEqual(measured["pairs"], {"store-router>home-visit": 1})

    def test_the_report_prints_the_metric_and_writes_nothing_else(self):
        import ownership_metrics_report

        before = sorted(path.name for path in self.root.iterdir())
        output = self.root / "report.txt"
        self.assertEqual(
            ownership_metrics_report.main(
                [str(self.root / OWNERSHIP_METRICS_NAME),
                 "--output", str(output)]
            ),
            0,
        )
        text = output.read_text(encoding="utf-8")
        self.assertIn("implicit handoffs by owner", text)
        self.assertIn("implicit handoffs by producer", text)
        self.assertIn("explore>positioning", text)
        self.assertIn("claim rows     24", text)
        self.assertEqual(
            sorted(path.name for path in self.root.iterdir()),
            sorted([*before, "report.txt"]),
        )


class ClaimLintTest(unittest.TestCase):
    """S1-4: the count is reproducible and the marker detection is correct."""

    def test_every_site_of_the_fixture_is_classified_as_annotated(self):
        sites = ownership_claim_lint.scan([LINT_SAMPLE])
        self.assertEqual(
            [(site["line"], site["covered"], site["family"]) for site in sites],
            LINT_SAMPLE_SITES,
        )

    def test_the_summary_of_the_fixture_is_the_one_the_sites_imply(self):
        summary = ownership_claim_lint.summarise(
            ownership_claim_lint.scan([LINT_SAMPLE])
        )
        self.assertEqual(summary["sites"], 9)
        self.assertEqual(summary["covered"], 3)
        self.assertEqual(summary["uncovered"], 6)
        self.assertEqual(summary["covered_by_family"],
                         {"departure": 2, "survival": 1})
        self.assertEqual(
            summary["uncovered_by_family"],
            {
                "home-visit": 1, "mixed": 1, "store-router": 1,
                "survival": 1, "town-plan": 1, "unknown": 1,
            },
        )

    def test_the_count_over_the_package_is_reproducible(self):
        first = ownership_claim_lint.summarise(
            ownership_claim_lint.scan(
                sorted((ROOT / "src" / "hengbot").glob("*.py"))
            )
        )
        second = ownership_claim_lint.summarise(
            ownership_claim_lint.scan(
                sorted((ROOT / "src" / "hengbot").glob("*.py"))
            )
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first["sites"], first["covered"] + first["uncovered"]
        )
        # Producers really are marked, so a regression that drops the marker
        # (or the lint's reading of it) cannot pass unnoticed.
        self.assertGreater(first["covered"], 0)

    def test_the_lint_reports_rather_than_failing_the_build(self):
        with tempfile.TemporaryDirectory(prefix="claim-lint-") as raw:
            output = Path(raw) / "lint.json"
            self.assertEqual(
                ownership_claim_lint.main(
                    ["--path", str(LINT_SAMPLE), "--json",
                     "--output", str(output)]
                ),
                0,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["uncovered"], 6)


if __name__ == "__main__":
    unittest.main()
