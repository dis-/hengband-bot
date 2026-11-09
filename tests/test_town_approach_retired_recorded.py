"""Recorded pin: a town approach whose claimed distance falls is not retired.

Live incident 2026-09-25 06:15:50-06:23:14 (one bot process, 2,052 logged
decisions, resumed onto the running game): back in the Outpost after a
guardian-kit-insufficient return from the Orc cave, a town fight interrupted
native travel to the Black Market (store 7).  ``shop:approach`` then walked
single steps ('9', '6') toward the entrance at (45, 123).  The S2a.1 claim
ledger shows one Reach claim (claim 925) whose distance fell on every
decision, 33 -> 20, yet the arbiter scored ``progress: False`` on 11 of those
14 decisions, spent the store-router budget 8 -> 0, retired the owner on
sequence 2046 and the next decision stopped the run with
``town:blocked:owner-retired``.

Root cause: the arbiter's locomotion part measured the walk with the
Manhattan sum |dy| + |dx|.  Above the goal's row a '9' step closes |dx| and
opens |dy|, so the sum stayed flat (32, 32, 32 ...) on every such step while
the eight-way step distance the policy and the claim ledger use
(``Position.distance_to``) fell by one.  The same flat sum also made the
first walk board (sequence 2032, (47, 89)) repeat the vector of sequence 2024
((46, 88), both 36) and retire the owner at once by recurrence.  User
decision 2026-09-23 (ownership contract): progress is distance plus the
expected observation, and a strictly falling distance to the claimed goal is
progress.

DECLARED DIVERGENCE (89543e80, Home relief fix C; SOL-REPORT-homefull3.txt
section 1 C): the current prefix stops at 1180 (sequence 1178, turn 5363502).
Board 1179 filed a combat-weapon Home errand after a deposit invalidated the
catalogue. On 1180 no atomic operation is pending, the character is healthy,
and no physical hostile is present. The filed errand now requests its missing
catalogue with '~9 ESC' (home-errand:request-knowledge:combat-weapon) instead
of live's '5' equipment-transaction:atomic-deposit. Its Observe/knowledge
claim and execution declaration stay with home-errand. No subsequent old
effect board is consumed. The earlier S3.3 boundary at 1183 (seek the partial
Home page rather than asserting absence) is beyond this new changed key.
Later guardian sites
and the walk from 2026 use DECLARED CONSTRUCTED independent baseline-policy
checkpoints from group 2 (90fca3b7), frozen by
extract_s33_town_checkpoints.py. They are independent operation substrates,
not a current continuation or recovered live checkpoints. Every changed-key
site ends before any following historical effect board is consumed.

Original substrate: every recorded decision of the process, replayed through the
public response path on one policy (tests/extract_town_approach_retired_
fixture.py; the calibration file is the one the process loaded).
Walls, each declared:
- the recorded periodic save/dump decisions receive the CLI timer request
  that produced them;
- Home history/disposal files and the calibration file live in a temporary
  directory;
- DECLARED WALL (executor binding): from decision 2027 on, the board of every
  decision that follows a posted key carries the live input executor's
  ``_completed_operation_sequence``/``_owner`` (the previous decision's
  sequence and reason).  The executor adds them to the board it composes
  after an accepted operation and the state log never carries them; without
  them decision 2027 cannot see that the town fight interrupted the native
  travel of 2026 (``store:entry-interrupted-replan`` recorded).  With the
  binding the pre-fix code reproduces all 2,052 recorded decisions, the
  stop included.
- DECLARED WALL (live replay only, orc-cave-residual-path): the live town
  router had no guardian-landing gate, so the replay answers
  ``_recall_landing_guardian_blocked`` with False; otherwise the 06:22:31
  recall to the Orc cave (B below) would be refused and every later recorded
  board, the walk included, would be counterfactual.  B1 decides the 06:22:31
  board without it.
No wall touches the approach producer, the progress vector or the arbiter.

DECLARED DIVERGENCE (2026-09-26 stale equipment-mutation gate fix,
departure-unsatisfiable-weight): the recorded ``town:restore-combat-weapon``
'wnb' (sequence 1917) posted a combat-loadout wield whose worn change the
next board showed, but the executor observed only when a later wield or
takeoff was requested, so it stayed POSTED through the recall.  The Home
knowledge gate read that stale POSTED and held the combat-weapon knowledge
request back.  The decision entry now observes the executor, so the request
runs on the first board that wants it (list index 1944, sequence 1941),
where live walked one more ``shop:approach`` step; the town work that
follows shifts (Home withdrawal of the combat weapon before the character
dump) and the replay follows recorded boards the fixed policy no longer
produced until the recall board (1966).  From 1967 on every recorded
decision, the approach walk included, is decided as live.

B (orc-cave-residual-path, same capture): 06:22:31 ``town:recall-to-alt-
dungeon`` 'rhc' read Word of Recall to the Orc cave (target 3, no alternate,
streak 0), whose landing 23 is its guardian floor; at 06:22:50 the dive came
straight back (``guardian-kit-insufficient``).  The target came from the
conquest latch (``_conquest_target`` / ``_conquest_committed``), committed at
sequence 1890 on a mid-transaction kit that could beat the guardian and kept
after the kit changed (B1 path test).  The town router now refuses a recall
whose landing is a guardian floor the current kit cannot pass
(``_guardian_floor_blocked``) and switches like the guardian valve.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
from hengbot import town_hold
from hengbot.policy import staged_prompt_chain_matches
import copy
import base64
import io
import gzip
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.cli import _consume_response_sequence
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import SHOP_APPROACH_STUCK_LIMIT, TOWN_TRAVEL_STALL_LIMIT

from tests.support.recorded import EDIT, _policy
from recorded_loadout import recorded_loadout_replay
from recorded_equipment_decisions import frozen_equipment_replay
from recorded_floor_knowledge import pre_seen_floor_replay
from extraction_calibration import install_extraction_calibration
from test_store_reentry_recorded import _Unpickler
from hengbot.policy_state import normalize_policy_state

# overweight-home review P2 (USER DECISION 2026-09-20 「帰還の巻物は目標＋出発で
# 読む1枚を買う」): the departure recall scroll is now counted, and bought with
# the target, while the recall target still awaits its safe-landing switch.
# DECLARED WALL for the replays below: the pre-P2 (safety-gated) departure
# count, so they keep proving their own subjects on boards that are the effect
# of the live keys.  A separate test pins the first changed decision.
from hengbot.policy import HengbotPolicy as _P2Policy
_PRODUCTION_RECALL_DESTINATION = _P2Policy._town_recall_destination
_PRODUCTION_FULL_RESUPPLY_RESERVE = _P2Policy._full_departure_resupply_reserve


def _pre_p2_recall_destination(self, snapshot, *, guardian_gate=True,
                               safety_gate=True):
    return _PRODUCTION_RECALL_DESTINATION(
        self, snapshot, guardian_gate=guardian_gate)


def _pre_p2_departure_count():
    return patch.object(_P2Policy, "_town_recall_destination",
                        _pre_p2_recall_destination)


def _pre_full_resupply_reserve(self, snapshot):
    """Wall the 2026-10-08 Black Market reserve rule for this old lifetime."""
    return self._required_departure_supply_reserve(snapshot)


def _recorded_optional_reserve():
    return patch.object(
        _P2Policy, "_full_departure_resupply_reserve",
        _pre_full_resupply_reserve,
    )


def _recorded_junk_pile_loot():
    """DECLARED CONSTRUCTED wall (#70): keep this lifetime's junk-pile loot.

    Owner directive 2026-10-18: worthless piles are not loot.  This 2026-09-25
    lifetime walked to a single skeleton pile at (40,35) during fundraising
    (row 342: recorded '7' fundraise:seek-loot; with the skip, 'T3'
    fundraise:dig-to-treasure), which would end the replay before the town
    decisions this module checks.  The skip is disabled for this replay only.
    """
    return patch.object(_P2Policy, "_floor_pile_is_worthless",
                        staticmethod(lambda _grid: False), create=True)


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "town-approach-retired-20260925.jsonl.gz"
CALIBRATION = FIXTURES / (
    "guardian-recall-pingpong-20260925.character-calibration.json"
)
FIXTURE_SHA256 = "249feeff221d652c51bb8b56d9c4ec021ce17bd309f39b17d9d53f940e106093"
BOUNDARIES_SHA256 = (
    "9706267ad37124770d48b06af6281f8876aed2c3244b66680d0b1de63ea88a20"
)
CALIBRATION_SHA256 = (
    "a90e4700854b1b3cf839a278a846078c7f9d768c82c058551c6f52173660016b"
)
STALE_GATE_FIRST = 1944  # sequence 1941: the combat-weapon knowledge request
STALE_GATE_WINDOW = (1944, 1949, 1950, *range(1959, 1967))  # declared above
BINDING_FROM = 2027  # store:entry-interrupted-replan, the first bound board
WALK_START = 2036  # sequence 2032: the first shop:approach step after the fight
WALK_END = 2050  # sequence 2046: the live retirement
STOP = 2051  # sequence 2047: town:blocked:owner-retired
STORE_7_ENTRANCE = [45, 123]
# B (orc-cave-residual-path): the Orc cave path, by log index.
ORC_CAVE = 3
FOREST = 7
ORC_CAVE_LANDING = 23  # recorded dungeon_recall_depths[3]; its guardian floor
LATCH = 1893  # sequence 1890, 06:21:37: _conquest_target commits the Orc cave
KIT_CHANGED = 1899  # sequence 1896: the shield is on, the guardian unbeatable
RECALL = 1966  # sequence 1963, 06:22:31: 'rhc' town:recall-to-alt-dungeon
BOUNCE = 1991  # sequence 1988, 06:22:50: 'rh' return:recall from (3, 23)
PATH = (LATCH - 1, LATCH, KIT_CHANGED - 1, KIT_CHANGED, RECALL, BOUNCE)


HOME_KNOWLEDGE_FIRST_CHANGED = 1180
S33_CHECKPOINTS = FIXTURES / "town-approach.s33-independent-checkpoints.json.gz"
S33_CHECKPOINTS_SHA256 = "fe64591abd5fc6ecfd7e74f2170d655741544f3673fe2ba470baa4cb6fd6051a"
S33_WALK_BEGIN = WALK_START - 10

P2_FIRST = 52  # first decision changed by the P2 departure recall count
OPTIONAL_RESERVE_FIRST_CHANGED = 53  # recorded Black Market visit, decision 52


class TownApproachRetiredRecordedTest(unittest.TestCase):
    replay = None
    path = None
    fixed_recall = None

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
        assert hashlib.sha256(S33_CHECKPOINTS.read_bytes()).hexdigest() == S33_CHECKPOINTS_SHA256
        independent = json.loads(gzip.decompress(S33_CHECKPOINTS.read_bytes()))
        assert independent["source_revision"] == "90fca3b7"
        assert independent["input_sha256"] == FIXTURE_SHA256
        cls.independent = {int(index): base64.b64decode(data)
                           for index, data in independent["checkpoints"].items()}

    @classmethod
    def _new_policy(cls, directory: Path):
        policy = _policy(directory, cls.monrace)
        policy._character_calibration_path.write_bytes(CALIBRATION.read_bytes())
        install_extraction_calibration(policy)
        return policy

    @classmethod
    def _board_lines(cls, index):
        segment = cls.lines[cls.starts[index] : cls.starts[index + 1]]
        previous = cls.recorded[index - 1] if index else None
        if index >= BINDING_FROM and previous["key"]:
            # DECLARED WALL (executor binding): see the module docstring.
            row = json.loads(segment[-1])
            row["_completed_operation_sequence"] = previous["decision_sequence"]
            row["_completed_operation_owner"] = previous["reason"]
            segment = segment[:-1] + [json.dumps(row, ensure_ascii=False) + "\n"]
        return segment

    @classmethod
    def _consume(cls, policy, index, directory):
        _decoded, snapshots = _consume_response_sequence(
            cls._board_lines(index), policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=directory / "knowledge.jsonl",
        )
        recorded_reason = cls.recorded[index]["reason"]
        if recorded_reason == "periodic:game-save":
            policy.request_game_save()
        elif recorded_reason == "periodic:character-dump":
            policy.request_character_dump()
        return snapshots[-1]

    @staticmethod
    def _decide(policy, snapshot, *, live_gate=True):
        suspended_before = {claim.claim_id for claim in town_hold.suspended_claims(policy)}
        if live_gate:
            # DECLARED WALL (live replay): see the module docstring.
            with patch.object(
                policy, "_recall_landing_guardian_blocked", return_value=False,
                create=True,  # pre-fix code has no gate: fail by assertion
            ):
                key = policy.choose_key(snapshot)
        else:
            key = policy.choose_key(snapshot)
        telemetry = policy._town_turn_arbiter.telemetry or {}
        claim = town_hold.standing_claim(policy)
        decided = {
            "key": str(key),
            "reason": policy.last_reason,
            "producer_owner": telemetry.get("producer_owner"),
            "progress": telemetry.get("progress"),
            "budget_remaining_estimate": telemetry.get(
                "budget_remaining_estimate"
            ),
            "retirement_set": telemetry.get("retirement_set"),
            "claim_id": getattr(claim, "claim_id", None),
            "claim_state": getattr(getattr(claim, "state", None), "value", None),
            "claim_distance": (
                town_hold.claim_goal_distance(policy, snapshot, claim.goal)
                if claim is not None else None
            ),
            "claim": claim,
            "rung": town_hold.decision_rung(policy),
            # S2b.1: a preempted claim resumed under its own id on this row
            "claim_resumed": getattr(claim, "claim_id", None) in suspended_before,
            # S2b.2: the bars standing in the town hold
            "bars": town_hold.hold_bars(policy),
        }
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({
                "outcome": "released", "posted": str(key),
            })
        return decided

    @classmethod
    @pre_seen_floor_replay  # declared wall: board recorded 2026-09-25, before the 2026-10-23 seen-floor rule (tests/recorded_floor_knowledge.py)
    @recorded_loadout_replay
    # fixer-reconcile-prompt.txt STEP 2: approach/ownership/guardian pins must
    # consume capture-time equipment choices, not unconfirmed new loadouts.
    @frozen_equipment_replay("town")
    def _replay(cls):
        """Current prefix plus explicitly independent later operation sites."""
        if cls.replay is not None:
            return cls.replay
        cls.path = {}
        with (TemporaryDirectory() as raw_directory,
              _pre_p2_departure_count(), _recorded_optional_reserve(),
              _recorded_junk_pile_loot()):
            directory = Path(raw_directory)
            policy = cls._new_policy(directory)
            replay = []
            first = None
            for index in range(HOME_KNOWLEDGE_FIRST_CHANGED + 1):
                snapshot = cls._consume(policy, index, directory)
                if index == HOME_KNOWLEDGE_FIRST_CHANGED:
                    cls.first_context = dict(
                        turn=snapshot.turn, in_town=snapshot.in_town,
                        outside=snapshot.store is None,
                        needs_knowledge=policy._home_errand.needs_knowledge,
                        purpose=policy._home_errand.request.purpose,
                        knowledge_current=policy._home_knowledge_current,
                        scan_inflight=policy._home_knowledge_scan_inflight,
                        deposit_pending=policy._home_atomic_deposit_pending is not None,
                        withdraw_pending=policy._home_atomic_withdraw_pending is not None,
                        physical_hostiles=bool(policy._physical_hostiles(snapshot)),
                        hp=(snapshot.player.hp, snapshot.player.max_hp),
                        food=snapshot.player.food_state,
                        adverse_status=bool(snapshot.player.poisoned or snapshot.player.cut
                                            or snapshot.player.confused or snapshot.player.blind),
                    )
                live = cls.recorded[index]
                if index == OPTIONAL_RESERVE_FIRST_CHANGED:
                    # This route replay is not a purchase-mechanics pin. Keep
                    # its historical continuation behind a declared wall, and
                    # separately retain the real new refusal on the same board.
                    observed = copy.deepcopy(policy)
                    with patch.object(
                        _P2Policy, "_full_departure_resupply_reserve",
                        _PRODUCTION_FULL_RESUPPLY_RESERVE,
                    ):
                        changed = cls._decide(observed, snapshot)
                    cls.optional_reserve_divergence = {
                        "recorded": (live["key"], live["reason"]),
                        "current": (changed["key"], changed["reason"]),
                        "gold": snapshot.player.gold,
                        "reserve": _PRODUCTION_FULL_RESUPPLY_RESERVE(
                            observed, snapshot,
                        ),
                    }
                row = cls._decide(policy, snapshot)
                replay.append(row)
                equivalent_quantity = (index == 1178 and row["key"] == "dm"
                                       and live["key"] == "dm\r" and row["reason"] == live["reason"])
                if not equivalent_quantity and (row["key"], row["reason"]) != (live["key"], live["reason"]):
                    first = index
                    break  # No old effect board follows a changed key.
            assert first == HOME_KNOWLEDGE_FIRST_CHANGED, first

            def independent(index):
                policy = _Unpickler(io.BytesIO(cls.independent[index]), cls.monrace).load()
                old_directory = policy._character_calibration_path.parent
                for name, value in tuple(vars(policy).items()):
                    if isinstance(value, Path) and value.is_relative_to(old_directory):
                        setattr(policy, name, directory / value.relative_to(old_directory))
                normalize_policy_state(policy)
                return policy

            for index in PATH:
                policy = independent(index)
                snapshot = cls._consume(policy, index, directory)
                if index == RECALL:
                    fixed = copy.deepcopy(policy)
                    cls.fixed_recall = []
                    for _decision in range(3):
                        row = cls._decide(fixed, snapshot, live_gate=False)
                        row.update(alternate=fixed._alternate_dungeon,
                                   target=fixed._target_dungeon_id,
                                   conquest=fixed._conquest_committed,
                                   mountain_selection=fixed._recall_selection_key(snapshot, 14))
                        cls.fixed_recall.append(row)
                cls._decide(policy, snapshot)
                cls.path[index] = (
                    policy._conquest_committed, policy._target_dungeon_id,
                    policy._alternate_dungeon,
                    policy._guardian_floor_blocked(snapshot, ORC_CAVE,
                                                  snapshot.dungeon_recall_depths[ORC_CAVE]),
                    (snapshot.floor_key[0], snapshot.floor_key[1]))

            policy = independent(S33_WALK_BEGIN)
            cls.walk_replay = {}
            for index in range(S33_WALK_BEGIN, STOP + 1):
                snapshot = cls._consume(policy, index, directory)
                row = cls._decide(policy, snapshot)
                cls.walk_replay[index] = row
                if index < STOP:
                    live = cls.recorded[index]
                    assert (row["key"], row["reason"]) == (live["key"], live["reason"]), index
            cls.replay = replay
        return cls.replay

    # ------------------------------------------------------------ recorded
    def test_recorded_walk_closes_its_claimed_distance_and_is_retired(self):
        walk = self.recorded[WALK_START : WALK_END + 1]
        self.assertEqual(
            [row["decision_sequence"] for row in walk], list(range(2032, 2047))
        )
        self.assertEqual({row["reason"] for row in walk}, {"shop:approach"})
        self.assertEqual({row["key"] for row in walk}, {"9", "6"})
        self.assertEqual(
            {tuple(row["claim_goal"]) for row in walk}, {tuple(STORE_7_ENTRANCE)}
        )
        # The first board's claim (924) was retired with the owner; one claim
        # (925) holds the rest of the walk.  Its distance falls on every
        # decision.
        self.assertEqual(walk[0]["claim_id"], 924)
        self.assertEqual({row["claim_id"] for row in walk[1:]}, {925})
        self.assertEqual(
            [row["claim_distance"] for row in walk], list(range(34, 19, -1))
        )
        self.assertEqual(
            [row["progress"] for row in walk[1:]].count(False), 11
        )
        self.assertEqual(
            [row["budget_remaining_estimate"] for row in walk],
            [0, 8, 8, 7, 6, 5, 8, 7, 6, 5, 4, 3, 2, 1, 0],
        )
        self.assertIn("store-router", walk[0]["retirement_set"])
        self.assertIn("store-router", walk[-1]["retirement_set"])
        stop = self.recorded[STOP]
        self.assertEqual(
            (stop["key"], stop["reason"]), ("5", "town:blocked:owner-retired")
        )
        self.assertEqual(
            min(TOWN_TRAVEL_STALL_LIMIT, SHOP_APPROACH_STUCK_LIMIT), 8
        )

    # ------------------------------------------------------------ B
    def test_recorded_recall_onto_the_orc_cave_guardian_floor(self):
        recorded = self.recorded
        # Angband is the target (no alternate) until the conquest latch.
        self.assertEqual(
            {
                (row["target_dungeon_id"], row["alternate_dungeon_id"])
                for row in recorded[:LATCH]
            },
            {(1, None)},
        )
        self.assertEqual(
            {
                (row["target_dungeon_id"], row["alternate_dungeon_id"])
                for row in recorded[LATCH:RECALL + 1]
            },
            {(ORC_CAVE, None)},
        )
        row = recorded[RECALL]
        self.assertEqual(
            (row["decision_sequence"], row["key"], row["reason"],
             row["over_extended_dive_streak"]),
            (1963, "rhc", "town:recall-to-alt-dungeon", 0),
        )
        row = recorded[BOUNCE]
        self.assertEqual(
            (row["key"], row["reason"], row["dungeon_id"], row["level"],
             row["last_return_trigger"]),
            ("rh", "return:recall", ORC_CAVE, ORC_CAVE_LANDING,
             "guardian-kit-insufficient"),
        )

if __name__ == "__main__":
    unittest.main()
