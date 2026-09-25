"""Recorded pin: an observed wield no longer silences weight shedding in town.

Live incident 2026-09-26 02:52:28 (one bot process attached at 02:51:39 to
the running game while the character waited for the recall out of Orc cave
23F, 117 logged decisions): the town visit stopped with
``town:blocked:departure-unsatisfiable`` ("no state-changing owner can
satisfy the remaining departure conjunct"); ``departure_block.failed`` was
``["inventory_weight_ready"]`` alone.

Weight (tenth-pounds, pack plus worn, from the frozen boards): the limit is
ADJ_STR_WEIGHT_LIMIT[26] * 50 = 1650 (STR index 26).  The landing board
carried 2224; the weight-overload deposit (sequence 53 'dt2\\rdsdrdp\\x1b',
the (聖戦者)クレイモア among them) brought it to 1554.  The identification-
catalog errand then took the Claymore (200) back out of Home to *identify*
it (sequence 102, 1409 -> 1609); the required identify-staff purchase
(sequence 108, +50) made the pack 1654 > 1650 and the recall purchase
(sequence 114, +5) 1659.  The Claymore, an unreserved spare 200 heavy, was
a legal Home deposit that clears the 9 excess by itself.

Root cause (reproduced by the replay below): the equipment transaction's
ring swap posted ``wm)`` at sequence 60; the next board (sequence 61)
showed the ring worn, but ``EquipmentMutationExecutor.observe`` ran only
inside ``_begin``, i.e. when a *later* wield/takeoff was requested.  None
was, so the executor stayed POSTED for the rest of the visit.  Every reader
of that in-flight gate kept treating the character as mid-mutation;
``_overweight_home_deposit`` returns None unless the executor is IDLE, so
from sequence 109 (the first overweight board) the weight-overload need
never existed, the departure supplier counterfactual found no owner for the
failing ``inventory_weight_ready`` leaf and the terminal fired.  No budget,
reachability or protection refused the deposit (Home was reachable, never
blocked, no rejected deposit, the Claymore unreserved).

Fix: the decision entry observes the posted wield/takeoff on every board,
so an observed worn change releases the gate before any owner reads it.

Substrate: every recorded decision of the process, replayed through the
public response path on one policy (tests/extract_departure_unsatisfiable_
weight_fixture.py; the calibration file is the one the process loaded).
Walls, each declared:
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them (none occurs in this window; kept for parity);
- Home history/disposal files and the calibration file live in a temporary
  directory;
- the board of every decision that follows a posted key carries the live
  input executor's ``_completed_operation_sequence``/``_owner`` (the
  previous decision's sequence and reason), as the executor adds them after
  an accepted operation.
The pre-fix code reproduces every one of the 117 recorded decisions, the
stop included.  With the fix every decision up to the first overweight
board (sequence 108) is decided as live; that board then travels to Home
for the weight-overload deposit instead of the Black Market.  DECLARED
DIVERGENCE: the later recorded boards follow the live route the fixed
policy no longer takes (Black Market page, the Alchemist page and its
purchase); on them the fixed policy heads back to Home (sequence 111), buys
from the page it was handed (sequence 114), and the stop board heads to
Home instead of the terminal.  Only those boards differ.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from hengbot.cli import _consume_response_sequence
from hengbot.equipment_mutation import EquipmentMutationState
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import STORE_HOME

from test_esp_threat_rest_recorded import EDIT, _policy
import test_policy_home  # WeightOverloadTownTest's overweight town board


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "departure-unsatisfiable-weight-20260926.jsonl.gz"
CALIBRATION = FIXTURES / (
    "departure-unsatisfiable-weight-20260926.character-calibration.json"
)
FIXTURE_SHA256 = "60871339b4bae18e554ff25005f470ca524881489e9505af27396dff8f333cee"
BOUNDARIES_SHA256 = (
    "7605c030c3882b395e9c7f28b2861ba019e2343e7c26badb9c12dd1a30bb26d3"
)
CALIBRATION_SHA256 = (
    "570b4d994decb0bc7d9fa5d0acca6602a1a530bf1c27904809cc8dd1ae0ea82b"
)
# Decisions are addressed by log index; the first town decision reuses the
# countdown's last sequence (46 twice), so index = sequence + 1 from there.
WEIGHT_DEPOSIT = 54  # sequence 53, 'dt2\rdsdrdp\x1b'
RING_TAKEOFF = 60  # sequence 59, 'te'
RING_EQUIP = 61  # sequence 60, 'wm)'
RING_OBSERVED = 62  # sequence 61, the board that shows the ring worn
CLAYMORE_WITHDRAW = 103  # sequence 102, '5  pd\x1b'
CLAYMORE_OBSERVED = 104  # sequence 103
STAFF_BUY = 109  # sequence 108, 'pk\r\x1b'
FIRST_OVERWEIGHT = 110  # sequence 109, the first overweight board
RECALL_BUY = 115  # sequence 114, 'pi1\r\r\x1b'
STOP = 116  # sequence 115, town:blocked:departure-unsatisfiable
DIVERGENT = (FIRST_OVERWEIGHT, 112, RECALL_BUY, STOP)
HOME_TRAVEL = "\x1b`n(."
WEIGHT_LIMIT = 1650
CLAYMORE = "(聖戦者)クレイモア"


def _board_weight(row: dict) -> int:
    return sum(
        max(0, item["weight"]) * max(1, item["count"])
        for item in (*row["inventory"], *row["equipment"])
    )


class DepartureUnsatisfiableWeightRecordedTest(unittest.TestCase):
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
    def _board(cls, index):
        return json.loads(cls.lines[cls.starts[index + 1] - 1])

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
                deposit = (
                    policy._overweight_home_deposit(snapshot)
                    if snapshot.in_town
                    else None
                )
                replay.append({
                    "key": str(key),
                    "reason": policy.last_reason,
                    "mutation": policy._equipment_mutation.state,
                    "overweight": (
                        snapshot.in_town and policy._inventory_overweight(snapshot)
                    ),
                    "deposit": deposit.name if deposit is not None else None,
                    "blocked_reason": policy._town_blocked_reason,
                    "claims": tuple(
                        getattr(policy, "_town_claim_categories", ()) or ()
                    ),
                    "home_blocked": (
                        STORE_HOME in policy._town_visit_ledger.blocked_stores
                    ),
                })
                policy.confirm_key_posted(key)
        cls.replay = replay
        return replay

    # ------------------------------------------------------------ recorded
    def test_recorded_weight_and_the_stop(self):
        recorded = self.recorded
        stop = recorded[STOP]
        self.assertEqual(
            (stop["decision_sequence"], stop["key"], stop["reason"]),
            (115, "9", "town:blocked:departure-unsatisfiable"),
        )
        self.assertEqual(stop["departure_failed"], ["inventory_weight_ready"])
        self.assertEqual(stop["need_attempts"]["weight-overload"], 1)
        self.assertEqual(stop["home_blocked"], False)
        self.assertEqual(
            recorded[WEIGHT_DEPOSIT]["key"], "dt2\rdsdrdp\x1b"
        )
        self.assertEqual(recorded[RING_EQUIP]["key"], "wm)")
        self.assertTrue(
            any("を装備した" in message
                for message in recorded[RING_OBSERVED]["messages"])
        )
        self.assertTrue(
            any(CLAYMORE in message and "を取った" in message
                for message in recorded[CLAYMORE_OBSERVED]["messages"])
        )
        # Pack plus worn weight on each decision's board (limit 1650).
        self.assertEqual(
            [
                _board_weight(self._board(index))
                for index in (
                    WEIGHT_DEPOSIT, WEIGHT_DEPOSIT + 1, CLAYMORE_WITHDRAW,
                    CLAYMORE_OBSERVED, STAFF_BUY, FIRST_OVERWEIGHT,
                    RECALL_BUY, STOP,
                )
            ],
            [2224, 1554, 1409, 1609, 1604, 1654, 1654, 1659],
        )
        board = self._board(STOP)
        self.assertEqual(board["player"]["stats"]["str"]["index"], 26)
        claymore = [
            item for item in board["inventory"] if CLAYMORE in item["name"]
        ]
        self.assertEqual([item["weight"] for item in claymore], [200])

    # ------------------------------------------------------------ H1
    def test_replay_decides_as_live_until_the_first_overweight_board(self):
        replay = self._replay()
        self.assertEqual(
            [
                index
                for index in range(STOP + 1)
                if (replay[index]["key"], replay[index]["reason"])
                != (self.recorded[index]["key"], self.recorded[index]["reason"])
            ],
            list(DIVERGENT),
        )
        self.assertEqual(
            [row["overweight"] for row in replay[STAFF_BUY : STOP + 1]],
            [False] + [True] * (STOP - STAFF_BUY),
        )

    def test_h1_the_observed_ring_swap_releases_the_mutation_gate(self):
        replay = self._replay()
        self.assertEqual(
            [row["mutation"] for row in replay[RING_TAKEOFF : RING_OBSERVED + 1]],
            [
                EquipmentMutationState.PREPARED,
                EquipmentMutationState.PREPARED,
                EquipmentMutationState.IDLE,
            ],
        )
        self.assertEqual(
            {row["mutation"] for row in replay[RING_OBSERVED : STOP + 1]},
            {EquipmentMutationState.IDLE},
        )

    def test_h1_the_first_overweight_board_sheds_weight_at_home(self):
        replay = self._replay()
        board = replay[FIRST_OVERWEIGHT]
        self.assertEqual(
            (board["key"], board["reason"]), (HOME_TRAVEL, "shop:travel")
        )
        self.assertIn("weight-overload", board["claims"])
        self.assertIn(CLAYMORE, board["deposit"])
        self.assertIsNone(board["blocked_reason"])

    def test_h1_the_stop_board_heads_home_instead_of_the_terminal(self):
        replay = self._replay()
        stop = replay[STOP]
        self.assertEqual((stop["key"], stop["reason"]), (HOME_TRAVEL, "shop:travel"))
        self.assertIn("weight-overload", stop["claims"])
        self.assertIn(CLAYMORE, stop["deposit"])
        self.assertIsNone(stop["blocked_reason"])
        self.assertFalse(stop["home_blocked"])
        for row in replay[FIRST_OVERWEIGHT : STOP + 1]:
            self.assertNotEqual(row["blocked_reason"], "departure-unsatisfiable")
            self.assertIsNotNone(row["deposit"])


class ObservedMutationReleasesTownOwnersTest(unittest.TestCase):
    """H2 (class): a posted wield/takeoff gates town owners only while in flight.

    User decision 2026-09-03 (overweight handling, 2 and 5): the surplus goes
    to Home; only a deposit that really fails is a visible stop.  The
    equipment executor's POSTED state is an in-flight gate, and the board that
    shows the worn change is its completion evidence -- whichever owner reads
    the gate first on that board.

    The posted operation is produced by the production takeoff composer and
    confirmed by the public post confirmation; the next board goes through
    the public decision entry; the verdict is the overweight deposit selector
    and the claim evaluation that feed the departure supplier.
    """

    def setUp(self):
        self.after = test_policy_home.WeightOverloadTownTest()._snapshot()
        ring = replace(
            test_policy_home.item("main_ring", 45, 8, is_equipment=True),
            weight=2,
        )
        self.before = replace(
            self.after, equipment=[*self.after.equipment, ring]
        )
        self.policy = HengbotPolicy()
        self.policy._equipment_optimization_preparation = SimpleNamespace(
            blockers=(), result=None
        )
        self.assertTrue(self.policy._inventory_overweight(self.after))
        key = self.policy._equipment_takeoff(
            self.before, "transaction-apply", "c"
        )
        self.assertEqual(key, "tc")
        self.policy.confirm_key_posted(key)
        self.assertEqual(
            self.policy._equipment_mutation.state, EquipmentMutationState.POSTED
        )
        # While posted, the weight-shedding owner stands aside.
        self.assertIsNone(self.policy._overweight_home_deposit(self.after))

    def test_the_board_showing_the_worn_change_releases_weight_shedding(self):
        policy = self.policy
        policy.choose_key(self.after)
        self.assertEqual(
            policy._equipment_mutation.state, EquipmentMutationState.IDLE
        )
        deposit = policy._overweight_home_deposit(self.after)
        self.assertIsNotNone(deposit)
        policy._town_claims_active(self.after)
        self.assertIn("weight-overload", policy._town_claim_categories)
        self.assertIsNone(policy._town_blocked_reason)

    def test_a_board_without_the_worn_change_keeps_the_gate(self):
        policy = self.policy
        policy.choose_key(self.before)
        self.assertEqual(
            policy._equipment_mutation.state, EquipmentMutationState.POSTED
        )
        self.assertIsNone(policy._overweight_home_deposit(self.before))


if __name__ == "__main__":
    unittest.main()
