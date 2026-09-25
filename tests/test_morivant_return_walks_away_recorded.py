"""Recorded pin: the Morivant return walk heads for Morivant's Inn and arrives.

Live incident 2026-09-25 20:38-20:41 (the 19:39 bot process): back in the
Outpost by Word of Recall (sequence 16522), the *Identify* expedition walked to
the Outpost Inn (16677..16711) and '3mc' teleported it to Morivant.  After
Home and shop errands there (16712..16730) nothing was left to identify, so the
expedition returned: ``town:morivant-full-identify:return`` (16731..16739)
walks to Morivant's teleport building, the Inn at (43,92), and declares that
Reach cell.  The nine steps '6','3','3','3','6','6','6','9','3' went from
(33,115) east to (35,123), the claim distance rose 23 -> 31, the arbiter scored
no progress on eight of nine decisions (budget 8 -> 0), retired ``cross-town``
and 16740 stopped with ``town:blocked:owner-retired``.

Root cause (reproduced below, on the recorded boards).  The declared goal was
right; the steps were wrong, and the arbiter had no measure for the walk:

1. Every surface map shares floor_key (0, 0, 0), so the per-floor terrain
   reset never ran between the Outpost and Morivant.  The router kept the
   Outpost's remembered terrain in Morivant's graph -- the recorded map memory
   grows 10619 -> 11167 known cells across the teleport and keeps the Outpost
   '>' (31,150) as a down staircase in Morivant -- and the static Morivant
   layout fills only cells not already known.  The Outpost walls at
   (37..40, 114..125) closed Morivant's open street south of the store, so the
   route to (43,92) went round them: 53 edges instead of 27, its first steps
   east, away from the Inn.  On the pre-fix code the observation replay below
   reproduces all nine live keys and the arbiter trace (progress on 16731
   only, budget 8 -> 0, retired on 16739); on the fixed code, with only the
   forgetting disabled, it still reproduces the nine keys, the 53-edge route
   and the recorded map memory of every Morivant board (fidelity test).
2. The progress vector registered the route distance for the outbound walk
   (``travel-``) and the walk-in return, not for this return walk, so even a
   correct walk read as no progress after its first step and would retire
   nine cells in; the real route is 27 edges.

Fix: a change of known town id under the same floor key (an Inn teleport)
forgets the routing terrain of the town left behind
(``_forget_left_town_terrain``); the return
walk (and the Library walk, the same producer's third walk) register their
route distance like the outbound walk.  Class tests:
tests/test_surface_map_walks.py.

Substrate (tests/extract_morivant_return_walks_away_fixture.py): the recorded
boards from the landing (16522, the floor change that last reset the terrain)
through the stop.  Walls, each declared:
- observation-only replay: the process began before the capture (the
  decision copy starts at 20:15), so its decisions cannot be replayed.  Each
  board passes the public response path and then the steps choose_key runs on
  every board before any producer (``_emitted_t``, ``_with_grid_memory``,
  ``_begin_map_predicate_cache``, ``_observe``, ``_build_grid_index``); no
  producer runs before 16731.  The routing terrain is built from the boards
  alone after the landing; its recorded size matches the replay on every
  board from 16552 on (checked);
- the expedition at the return is constructed as the live one stood: origin
  town 0 (the walk out left from the Outpost Inn; the recorded trigger town is
  0), no Home targets, returning; the carried *Identify* targets are read from
  the boards (none remained);
- on 16731..16739 the Morivant producer is asked directly, and the policy's
  own arbiter observes each of its decisions with the inputs choose_key's
  accounting call gives it (reason, progress vector, retirement keys);
- continuation (constructed, after the fixed decision on 16731): the 16731
  board with only the player moved to the cell each key steps to and the turn
  advanced; the lit cells stay as recorded.  The walking policy is a pickle
  round trip of the policy after that decision, i.e. a restored checkpoint;
- the fidelity test's replay replaces ``_forget_left_town_terrain`` with a
  no-op on its policy (the pre-fix terrain scope); no pin of the fix uses it.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs
import pickle
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import Position
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import TOWN_TRAVEL_STALL_LIMIT
from hengbot.policy_types import MorivantFullIdentifyExpedition

from test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "morivant-return-walks-away-20260925.jsonl.gz"
FIXTURE_SHA256 = "58c64d58e129cf6da0cba5c81f16826cb5f292bc05f3639851e1dd9a871da2a1"
BOUNDARIES_SHA256 = (
    "e9ba914b047705537055c4f0c09f3f941aed1964a092ff2aa3d65e1e12efb1cf"
)
FIRST = 16522  # the first board after the landing
LAST_OUTPOST = 16711  # '3mc': the Outpost Inn teleports to Morivant
FIRST_MORIVANT = 16712
RETURN = 16731  # the first ``town:morivant-full-identify:return``
RETIRED = 16739
STOP = 16740
RETURN_REASON = "town:morivant-full-identify:return"
INN = Position(43, 92)  # Morivant's teleport building (type 4)
OUTPOST_ENTRANCE = Position(31, 150)  # the Outpost's '>'; Morivant has none
OUTPOST_WALL = (40, 114)  # an Outpost wall; Morivant's street there is open
LIVE_KEYS = ["6", "3", "3", "3", "6", "6", "6", "9", "3"]
# Decisions whose recorded map summary lags the board (their path returned
# before the grid index; the next board's summary catches up).
SUMMARY_LAGS = [16522, 16525, 16526, 16531, 16532, 16544, 16551]


def _observe(policy, raw):
    """The steps choose_key runs on every board before any producer."""
    policy._emitted_t = {(position.y, position.x) for position in raw.grids}
    board = policy._with_grid_memory(raw)
    policy._begin_map_predicate_cache(board)
    policy._observe(board, observation=raw)
    policy._build_grid_index(board)
    return board


def _restored(policy):
    """A checkpoint round trip of the policy (how restored checkpoints load)."""
    return pickle.loads(pickle.dumps(policy))


def _account(policy, board):
    """choose_key's accounting call for the decision the producer just made."""
    arbiter = policy._town_turn_arbiter
    reason = policy.last_reason
    arbiter.observe(
        in_town=True,
        reason=reason,
        progress_vector=policy._town_arbiter_progress_vector(board, reason),
        retirement_key=policy._town_retirement_clearance_key(
            board, arbiter.owner_for_reason(reason), reason
        ),
        retirement_key_for=lambda owner: policy._town_retirement_clearance_key(
            board, owner, reason
        ),
    )
    return dict(arbiter.telemetry)


def _decide(policy, board):
    policy._decision_goal = None
    key = policy._morivant_full_identify_key(board)
    slot = policy._decision_goal
    route = policy._town_teleport_route(board, 0).route
    return {
        "position": (board.player.position.y, board.player.position.x),
        "key": key,
        "reason": policy.last_reason,
        "goal": (slot[0], slot[1].kind, slot[1].cell) if slot else None,
        "route": (route.target, route.first_step, route.remaining_edges)
        if route is not None else None,
        "telemetry": _account(policy, board),
    }


class MorivantReturnWalksAwayRecordedTest(unittest.TestCase):
    replays: dict = {}

    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
        boundaries_path = FIXTURE.with_suffix(".boundaries.json")
        assert hashlib.sha256(boundaries_path.read_bytes()).hexdigest() == (
            BOUNDARIES_SHA256
        )
        boundaries = json.loads(boundaries_path.read_text(encoding="utf-8"))
        fields = boundaries["recorded_fields"]
        recorded = [dict(zip(fields, row)) for row in boundaries["recorded"]]
        # Decisions are addressed by log index: the landing reuses 16522.
        assert recorded[0]["decision_sequence"] == FIRST
        assert recorded[-1]["decision_sequence"] == STOP
        cls.recorded = recorded
        cls.by_sequence = {row["decision_sequence"]: row for row in recorded}
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.lines = list(stream)
        assert len(cls.lines) == sum(boundaries["input_rows"])
        cls.starts = [0]
        for count in boundaries["input_rows"]:
            cls.starts.append(cls.starts[-1] + count)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    @classmethod
    def _feed(cls, policy, index, ledger):
        """Deliver decision ``index``'s rows and observe its board."""
        segment = cls.lines[cls.starts[index] : cls.starts[index + 1]]
        # Every row is delivered; only the board (the last row) is parsed
        # into a snapshot, the one choose_key would receive.
        _consume_response_sequence(
            segment[:-1], policy, lambda _key: True, cls.monrace,
            parse_snapshots=False, knowledge_ledger_path=ledger,
        )
        _decoded, (raw,) = _consume_response_sequence(
            segment[-1:], policy, lambda _key: True, cls.monrace,
            knowledge_ledger_path=ledger,
        )
        return raw, _observe(policy, raw)

    @staticmethod
    def _terrain(policy, board):
        return {
            "town_id": board.town_id,
            "outpost_wall": OUTPOST_WALL in policy._remembered_wall_t,
            "outpost_wall_routable": OUTPOST_WALL in policy._floor_t,
            "outpost_entrance": OUTPOST_ENTRANCE in policy._remembered_downstairs,
        }

    @classmethod
    def _replay(cls, *, keep_left_terrain=False):
        """The window on one policy; optionally with the pre-fix terrain scope.

        The Outpost boards are replayed once; from the teleport on, the fixed
        policy and a copy whose ``_forget_left_town_terrain`` is a no-op
        (``keep_left_terrain``: the pre-fix terrain scope, to show that this
        substrate reproduces the live walk when the Outpost terrain stays in
        the graph) each replay the Morivant boards.  Only the fixed policy
        continues the walk.
        """
        if cls.replays:
            return cls.replays[keep_left_terrain]
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            ledger = directory / "knowledge.jsonl"
            policy = _policy(directory, cls.monrace)
            summaries, terrain = {}, {}
            split = next(
                index for index, row in enumerate(cls.recorded)
                if row["decision_sequence"] == FIRST_MORIVANT
            )
            for index in range(split):
                _raw, board = cls._feed(policy, index, ledger)
                sequence = cls.recorded[index]["decision_sequence"]
                summaries[sequence] = (
                    len(policy._remembered_known_t),
                    sorted([p.y, p.x] for p in policy._remembered_downstairs),
                )
            terrain[LAST_OUTPOST] = cls._terrain(policy, board)
            for keep in (True, False):
                branch = _restored(policy)
                if keep:
                    branch._forget_left_town_terrain = lambda: None
                cls.replays[keep] = cls._replay_morivant(
                    branch, split, ledger, dict(summaries), dict(terrain),
                    walk=not keep,
                )
        return cls.replays[keep_left_terrain]

    @classmethod
    def _replay_morivant(cls, policy, split, ledger, summaries, terrain, *, walk):
        capture, continuation = [], []
        walker = return_raw = None
        for index in range(split, len(cls.recorded) - 1):
            sequence = cls.recorded[index]["decision_sequence"]
            raw, board = cls._feed(policy, index, ledger)
            summaries[sequence] = (
                len(policy._remembered_known_t),
                sorted([p.y, p.x] for p in policy._remembered_downstairs),
            )
            if sequence in (FIRST_MORIVANT, RETURN - 1):
                terrain[sequence] = cls._terrain(policy, board)
            if sequence < RETURN:
                continue
            if sequence == RETURN:
                # Wall (expedition): see the module docstring.
                policy._morivant_full_identify = MorivantFullIdentifyExpedition(
                    0, (), returning=True
                )
            capture.append(_decide(policy, board))
            if sequence == RETURN and walk:
                walker, return_raw = _restored(policy), raw
        # Wall (continuation): see the module docstring.  The walker is the
        # policy as the fixed decision on 16731 left it.
        raw, decision = return_raw, capture[0]
        for move in range(1, 8 * TOWN_TRAVEL_STALL_LIMIT if walk else 1):
            if (
                decision["reason"] != RETURN_REASON
                or decision["telemetry"]["retired"]
                or decision["route"] is None
                or decision["route"][1] == INN
            ):
                break
            raw = replace(
                raw,
                player=replace(raw.player, position=decision["route"][1]),
                turn=raw.turn + 10 * move,
            )
            decision = _decide(walker, _observe(walker, raw))
            continuation.append(decision)
        return {
            "summaries": summaries,
            "terrain": terrain,
            "capture": capture,
            "continuation": continuation,
        }

    # ------------------------------------------------------------ recorded
    def test_recorded_return_walk_moved_away_from_its_goal_and_retired(self):
        walk = [
            self.by_sequence[sequence]
            for sequence in range(RETURN, RETIRED + 1)
        ]
        self.assertEqual([row["reason"] for row in walk], [RETURN_REASON] * 9)
        self.assertEqual([row["key"] for row in walk], LIVE_KEYS)
        self.assertEqual(
            [(row["y"], row["x"]) for row in walk],
            [(33, 115), (33, 116), (34, 117), (35, 118), (36, 119),
             (36, 120), (36, 121), (36, 122), (35, 123)],
        )
        self.assertEqual({row["claim_id"] for row in walk}, {13491})
        self.assertEqual(
            {(row["claim_owner"], tuple(row["claim_goal"])) for row in walk},
            {("cross-town", (INN.y, INN.x))},
        )
        self.assertEqual(
            [row["claim_distance"] for row in walk], list(range(23, 32))
        )
        self.assertEqual(
            [(row["progress"], row["budget_remaining_estimate"]) for row in walk],
            [(True, 8)] + [(False, budget) for budget in range(7, -1, -1)],
        )
        self.assertTrue(walk[-1]["retired"])
        self.assertEqual(walk[-1]["retirement_set"], ["cross-town"])
        stop = self.by_sequence[STOP]
        self.assertEqual(
            (stop["key"], stop["reason"]), ("5", "town:blocked:owner-retired")
        )

    def test_recorded_map_memory_kept_the_outpost_in_morivant(self):
        outpost, morivant = self.by_sequence[LAST_OUTPOST], self.by_sequence[FIRST_MORIVANT]
        self.assertEqual(outpost["key"], "3mc")
        self.assertEqual((morivant["y"], morivant["x"]), (INN.y, INN.x))
        self.assertEqual((outpost["known_cells"], morivant["known_cells"]), (10619, 11167))
        self.assertEqual(
            [self.by_sequence[s]["down_stairs"] for s in (LAST_OUTPOST, FIRST_MORIVANT, RETIRED)],
            [[[OUTPOST_ENTRANCE.y, OUTPOST_ENTRANCE.x]]] * 3,
        )

    # ------------------------------------------------------------ fidelity
    def test_replayed_terrain_matches_the_recorded_outpost_memory(self):
        summaries = self._replay()["summaries"]
        lagging = [
            row["decision_sequence"]
            for row in self.recorded[:-1]
            if row["decision_sequence"] <= LAST_OUTPOST
            and summaries[row["decision_sequence"]]
            != (row["known_cells"], row["down_stairs"])
        ]
        self.assertEqual(lagging, SUMMARY_LAGS)
        self.assertEqual(summaries[LAST_OUTPOST], (10619, [[31, 150]]))

    def test_with_the_outpost_terrain_kept_the_replay_walks_the_live_walk(self):
        """Pre-fix terrain scope: the nine live keys, the same goal, 53 edges."""
        replay = self._replay(keep_left_terrain=True)
        self.assertEqual(
            replay["terrain"][RETURN - 1],
            {"town_id": 2, "outpost_wall": True, "outpost_wall_routable": False,
             "outpost_entrance": True},
        )
        capture = replay["capture"]
        self.assertEqual([decision["key"] for decision in capture], LIVE_KEYS)
        self.assertEqual(
            {decision["goal"] for decision in capture},
            {("cross-town", "Reach", (INN.y, INN.x))},
        )
        self.assertEqual(capture[0]["route"], (INN, Position(33, 116), 53))
        # The recorded map memory in Morivant is this replay's.
        summaries = replay["summaries"]
        self.assertEqual(
            [
                summaries[sequence]
                for sequence in range(FIRST_MORIVANT, RETIRED + 1)
            ],
            [
                (self.by_sequence[sequence]["known_cells"],
                 self.by_sequence[sequence]["down_stairs"])
                for sequence in range(FIRST_MORIVANT, RETIRED + 1)
            ],
        )

    # ------------------------------------------------------------ M1
    def test_m1_morivant_boards_hold_no_outpost_terrain(self):
        replay = self._replay()
        terrain, summaries = replay["terrain"], replay["summaries"]
        self.assertEqual(
            terrain[LAST_OUTPOST],
            {"town_id": 0, "outpost_wall": True, "outpost_wall_routable": False,
             "outpost_entrance": True},
        )
        for sequence in (FIRST_MORIVANT, RETURN - 1):
            self.assertEqual(
                terrain[sequence],
                {"town_id": 2, "outpost_wall": False,
                 "outpost_wall_routable": True, "outpost_entrance": False},
            )
        # Recorded: 11167..11199 known cells in Morivant, the Outpost's among
        # them.  Replayed: only what the Morivant boards showed.
        for sequence in range(FIRST_MORIVANT, RETIRED + 1):
            known, down_stairs = summaries[sequence]
            self.assertLess(known, self.by_sequence[LAST_OUTPOST]["known_cells"])
            self.assertEqual(down_stairs, [])

    def test_m1_capture_boards_step_toward_the_inn(self):
        capture = self._replay()["capture"]
        self.assertEqual(
            [decision["position"] for decision in capture],
            [(row["y"], row["x"]) for row in self.recorded
             if RETURN <= row["decision_sequence"] <= RETIRED],
        )
        self.assertEqual(
            {(decision["reason"], decision["goal"]) for decision in capture},
            {(RETURN_REASON, ("cross-town", "Reach", (INN.y, INN.x)))},
        )
        # Live: '6' east, over a 53-edge route round the Outpost's walls.
        first = capture[0]
        self.assertEqual(first["key"], "3")
        self.assertEqual(first["route"], (INN, Position(34, 116), 27))
        # Every recorded position of the old walk now steps back toward the
        # Inn: a real route that grows as the old walk moved east.
        self.assertEqual(
            [decision["key"] for decision in capture],
            ["3", "2", "1", "4", "7", "4", "4", "4", "1"],
        )
        self.assertEqual(
            [decision["route"][2] for decision in capture],
            [27, 27, 26, 26, 27, 28, 29, 30, 31],
        )

    def test_m1_return_walk_arrives_at_the_inn_without_retiring(self):
        replay = self._replay()
        walk = [replay["capture"][0], *replay["continuation"]]
        self.assertEqual({decision["reason"] for decision in walk}, {RETURN_REASON})
        self.assertEqual(
            {decision["goal"] for decision in walk},
            {("cross-town", "Reach", (INN.y, INN.x))},
        )
        # Each step closes the 27-edge route by one edge: 27 decisions, far
        # beyond the nine the owner's budget allows a walk without a measure.
        self.assertEqual(
            [decision["route"][2] for decision in walk], list(range(27, 0, -1))
        )
        self.assertGreater(len(walk), TOWN_TRAVEL_STALL_LIMIT + 1)
        self.assertEqual(
            [
                (decision["telemetry"]["producer_owner"],
                 decision["telemetry"]["progress"],
                 decision["telemetry"]["retired"])
                for decision in walk
            ],
            [("cross-town", True, False)] * len(walk),
        )
        # The last step enters the Inn with the teleport to the Outpost.
        arrival = walk[-1]
        self.assertEqual(arrival["route"][1], INN)
        self.assertTrue(arrival["key"].endswith("ma"), arrival["key"])
        self.assertEqual(max(abs(arrival["position"][0] - INN.y),
                             abs(arrival["position"][1] - INN.x)), 1)


if __name__ == "__main__":
    unittest.main()
