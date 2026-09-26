"""Stage S2b.2: the bar table, recorded; the switch that enforces it, off.

``SOL-DESIGN-ownership-contract.md`` sections 3.2 (the bar key ``(owner, goal,
trigger monsters)``, lifted after 50 game turns with none of the trigger
monsters perceived; survival exempt), 3.3 (errand owners: the retirement
clearance key re-arms them; the ladder skips barred owners), 5.4.1 (the key is
a pure function of the board), "Rev 10: S2b specified" item S2b.2 and "Rev
10.1" items 3, 4 and 9.  User decision 2026-09-26: the bar that changes
behaviour is switched on only after a live measurement; this round builds it
and records what it *would* do.

What is built
-------------
* ``claim_register.Bar`` and the register's bar table ``_bars`` (plain data,
  pickled with the policy), with ``_ended``: every claim a closing call ended
  since the last declaration.
* ``policy._claim_bar_for``: which endings bar.  The preemptors of design 3.2
  are the threat-triggered owners (``claim_ladder.TRIGGER_FAMILIES``); their
  Reach/Observe claim is barred when it ends without its goal (released,
  expired, retired, dropped by a violation, displaced from the stack), except
  when survival replaced it or a floor change ended it while suspended.  Any
  other owner is barred by retirement only (design 3.3, an errand).  Survival
  claims and Terminal claims never.
* The lift pass at the exit (``_claim_bar_lift``, pure ``bar_after_board``):
  threat bars after ``DETECTED_THREAT_HOLD_MAX_GAME_TURNS`` game turns (the
  existing 50-turn clock) with none of the ``(index, race_id)`` triggers
  perceived; errand bars (round 2, user decision 2026-09-26) when the
  *durable* part of the retirement clearance key changes -- never by the
  player's own movement, no clock (``policy._claim_durable_clearance``).
* ``would_bar`` on the decision row at the ``choose_key`` exit, plus
  ``bars_set`` / ``bars_lifted`` / ``bars_active`` / ``bar_skipped``; the
  ledger counts would-bars; ``ownership_metrics.bar_numbers`` and the report
  print would-bar events per owner and bar lifetimes.
* The switch ``HengbotPolicy._claim_bar_enforced`` (a policy attribute,
  default False, never set by shipped code) and its plumbing
  ``_claim_bar_skips``, asked by ``_decide`` *before* it calls a gated rung
  (round 2): the rung is not called while a bar a claim of that rung earned
  stands, so a barred producer spends none of its own state.  The gated rungs
  (``claim_ladder.BAR_GATED_RUNGS``) are the threat-triggered rungs a bar can
  carry that cannot answer survival -- whether an answer is survival is known
  only after the rung has run.  Because the decision is taken before the
  rung chooses its goal, the switch skips by rung; ``would_skip`` records
  exactly that on the row, beside ``would_bar``'s owner-and-goal match.

The pins
--------
P1  class tests on the register and the policy's exit: a threat bar set on a
    positioning release, kept by a perceived trigger, lifted exactly after
    the 50-turn clock -- and a monster that reuses a trigger's index under
    another race does not keep it (revert-proof: index-only identity would);
    a walking errand bar survives the player's own steps (while the full
    clearance key and the arbiter's retirement both change -- revert-proof)
    and lifts on a gold or inventory change; survival is never barred
    (neither by a bar set nor a would-bar, and no gated rung can answer
    survival); the endings that bar nothing.
P2  the recorded 2026-09-23 06:00 loot <-> prepare-choke capture:
    switch OFF -- keys and reasons byte-identical to the pre-S2b.2 replay and
    to the register-off replay, and the positioning owner's would-bar is
    recorded on every decision after its release; switch ON -- seek-loot
    owns every decision after the bar and the positioning rung is skipped.
    Round 2: ON with a barred choke rung does not call the rung, so the choke
    plan's counters are untouched (revert-proof: OFF, the same board spends
    them).
P3  metrics: the ledger's would-bar count and ``bar_numbers`` / the report
    over the same replay.
P4  restored checkpoints: a register without ``_bars`` / ``_ended`` and a
    policy without ``_claim_bar_enforced`` / ``_decision_bar_skips`` restore
    and decide.
P5  the three 2026-09-25 captures that still replay are pinned in their own
    modules, on the replays those modules already run (no second replay):
    ``test_guardian_recall_pingpong_recorded``,
    ``test_town_approach_retired_recorded`` and
    ``test_overweight_home_unreachable_recorded`` each keep their
    every-recorded-decision pin with the switch off and add a
    ``test_s2b2_*`` pin of what the bar table recorded (nothing, nothing, and
    seven ``target-lost`` hunt bars with three would-bars).

Attributes S2b.2 adds (P4 covers each): ``ClaimRegister._bars``,
``ClaimRegister._ended``; ``Bar.rung`` / ``Bar.reason`` (round 2, class
defaults); ``HengbotPolicy._claim_bar_enforced`` (``__init__``,
``restore_checkpoint`` default False) and the per-decision slot
``_decision_bar_skips`` (reset at every ``choose_key`` entry, ``getattr`` in
the writer, ``restore_checkpoint`` default).

Walls: ``tests/__init__`` runtime-file isolation; every ledger and report is
written inside a ``TemporaryDirectory``.
"""

from __future__ import annotations

import tests  # noqa: F401  -- live runtime-file isolation, also for bare runs

import ast
import base64
import inspect
import textwrap
import gzip
import json
import pickle
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.claim_goal_typing import (
    SURVIVAL_REASON_PREFIXES,
    SURVIVAL_RETURN_PREFIX,
)
from hengbot.claim_ladder import (
    BAR_GATED_RUNGS,
    CLAIM_LADDER,
    TRIGGER_FAMILIES,
    rung_named,
)
from hengbot.claim_register import (
    BAR_ERRAND,
    BAR_THREAT,
    Bar,
    Claim,
    ClaimOwner,
    ClaimRegister,
    bar_after_board,
    observe,
    reach,
    terminal,
)
from hengbot.latch_onset_capture import restore_checkpoint
from hengbot.model import Position, parse_snapshot
from hengbot.ownership_metrics import (
    OWNERSHIP_CLAIMS_NAME,
    OWNERSHIP_METRICS_NAME,
    bar_numbers,
    read_records,
)
from hengbot.policy import DETECTED_THREAT_HOLD_MAX_GAME_TURNS, HengbotPolicy
from hengbot.policy_types import ChokeEngagementPlan

from test_ownership_claims import LEGACY_CHECKPOINT, _Replay
from test_ownership_s2a1_closure import _fresh_policy, _town_board
from test_ownership_s2b1b_close_pairs import _quiet_dungeon_board

import ownership_metrics_report


ROOT = Path(__file__).resolve().parents[1]
POLICY_SOURCE = ROOT / "src" / "hengbot" / "policy.py"
HOLD = DETECTED_THREAT_HOLD_MAX_GAME_TURNS

# Round 2: the rungs ``_decide`` asks ``_claim_bar_skips`` about before it
# calls them, in source order.
GATED = (
    "_detected_threat_preparation_key",
    "_breeder_breakthrough_key",
    "_choke_engagement_key",
    "_breeder_breakthrough_escape_key",
)
SKIPPED_PREPARATION = {
    "rung": "_detected_threat_preparation_key",
    "owner": "positioning",
    "goal": {"kind": "Reach", "cell": [2, 102]},
    "bar_since_turn": 4828338,
}

# P2: the 24 replayed boards of the 06:00 capture, as the pre-S2b.2 policy
# (6de8446a) decided them -- keys and reasons, in order.
PRE_S2B2_TRAJECTORY = (
    [("4", "explore"), ("1", "explore")]
    + [("9", "detected:prepare-choke"), ("6", "detected:prepare-choke"),
       ("6", "detected:prepare-choke")]
    + [("1", "melee")]
    + [("6", "detected:prepare-choke")] * 18
)
MELEE_ROW = 5  # the melee decision: a hostile became visible
BAR_TURN = 4828338  # its game turn, where the positioning release is barred
CHOKE_CELL = [2, 102]  # the positioning goal (the covered cell it chose)
# claim 3's look-ahead set (the positioning claim released on the melee row)
CLAIM_3_TRIGGERS = [
    [43, 1105], [45, 1105], [46, 1105], [47, 1105], [48, 1105], [74, 111],
]
LAST_TURN = 4828473


def _dungeon_boards():
    skill, raws = _Replay.dungeon_boards()
    return skill, [parse_snapshot(raw, _Replay.knowledge()) for raw in raws]


class _Run:
    """Drive ``_record_decision_claim`` directly, one decision at a time."""

    def __init__(self, board):
        self.board = board
        self.policy = _fresh_policy(board)

    def decide(
        self, reason, *, cell=None, triggers=None, board=None, key="k"
    ) -> dict:
        policy = self.policy
        board = board or self.board
        policy._decision_sequence += 1
        policy._decision_goal = None
        policy._decision_expectation = None
        policy._decision_triggers = None
        policy._decision_bar_skips = None
        policy.last_reason = reason
        family = policy._claim_family_of(reason)
        if cell is not None:
            policy._decision_goal = (family, reach(cell), None)
        if triggers is not None:
            policy._decision_triggers = (
                family, tuple(sorted(tuple(pair) for pair in triggers))
            )
        policy._record_decision_claim(board, key)
        return dict(policy.decision_claim)

    @property
    def register(self) -> ClaimRegister:
        return self.policy._claim_register


def _board_with(board, *, turn, monsters):
    return replace(
        board, turn=turn, visible_monsters=[], detected_monsters=list(monsters)
    )


# -- P1 ----------------------------------------------------------------------


class ThreatBarTest(unittest.TestCase):
    """P1: a positioning release is barred; the 50-turn rule lifts it."""

    @classmethod
    def setUpClass(cls):
        _skill, boards = _dungeon_boards()
        cls.board = boards[2]  # the first detected:prepare-choke board
        cls.monster = next(
            monster for monster in cls.board.detected_monsters
            if (monster.index, monster.race_id) == (47, 1105)
        )

    def _barred_run(self):
        run = _Run(self.board)
        start = self.board.turn
        opened = run.decide(
            "detected:prepare-choke", cell=CHOKE_CELL, triggers=[(47, 1105)],
            board=_board_with(self.board, turn=start, monsters=[self.monster]),
        )
        self.assertEqual(opened["trigger_monsters"], [[47, 1105]])
        # the producer gives the retreat up (its own release, not a goal met)
        run.register.release("choke-threat-dispersed")
        dropped = run.decide(
            "explore", cell=(5, 5),
            board=_board_with(self.board, turn=start + 1, monsters=[self.monster]),
        )
        return run, start, opened, dropped

    def test_a_released_positioning_claim_is_barred(self):
        run, start, opened, dropped = self._barred_run()
        (entry,) = dropped["bars_set"]
        self.assertEqual(
            {name: entry[name] for name in (
                "owner", "goal", "kind", "since_turn", "triggers", "claim_id",
                "ending", "last_perceived_turn", "rung",
            )},
            {
                "rung": "_detected_threat_preparation_key",
                "owner": "positioning",
                "goal": {"kind": "Reach", "cell": CHOKE_CELL},
                "kind": BAR_THREAT,
                "since_turn": start + 1,
                "triggers": [[47, 1105]],
                "claim_id": opened["claim_id"],
                "ending": "release:choke-threat-dispersed",
                "last_perceived_turn": start + 1,
            },
        )
        self.assertEqual(dropped["bars_active"], 1)
        self.assertIsNone(dropped["would_bar"])
        # the same owner and goal again: recorded, not enforced
        again = run.decide(
            "detected:prepare-choke", cell=CHOKE_CELL,
            board=_board_with(self.board, turn=start + 2, monsters=[self.monster]),
        )
        self.assertEqual(
            again["would_bar"],
            {
                "owner": "positioning",
                "goal": {"kind": "Reach", "cell": CHOKE_CELL},
                "bar_since_turn": start + 1,
                "triggers": [[47, 1105]],
            },
        )
        # another goal of the same owner is not barred
        other = run.decide(
            "detected:prepare-choke", cell=(9, 9),
            board=_board_with(self.board, turn=start + 3, monsters=[self.monster]),
        )
        self.assertIsNone(other["would_bar"])

    def test_the_fifty_turn_rule_with_index_and_race_identity(self):
        run, start, _opened, _dropped = self._barred_run()
        seen = start + HOLD
        kept = run.decide(
            "explore", cell=(5, 5),
            board=_board_with(self.board, turn=seen, monsters=[self.monster]),
        )
        self.assertIsNone(kept["bars_lifted"])
        self.assertEqual(run.register.bars[0].last_perceived_turn, seen)
        # Hengband reuses the index of a dead monster: index 47 now holds
        # another race.  It is not a trigger, so it keeps nothing.
        impostor = replace(self.monster, race_id=self.monster.race_id + 1)
        still = run.decide(
            "explore", cell=(5, 5),
            board=_board_with(self.board, turn=seen + HOLD, monsters=[impostor]),
        )
        self.assertIsNone(still["bars_lifted"])
        self.assertEqual(still["bars_active"], 1)
        self.assertEqual(run.register.bars[0].last_perceived_turn, seen)
        lifted = run.decide(
            "explore", cell=(5, 5),
            board=_board_with(self.board, turn=seen + HOLD + 1, monsters=[impostor]),
        )
        (entry,) = lifted["bars_lifted"]
        self.assertEqual(
            (entry["owner"], entry["since_turn"], entry["lifted_turn"],
             entry["last_perceived_turn"]),
            ("positioning", start + 1, seen + HOLD + 1, seen),
        )
        self.assertEqual(lifted["bars_active"], 0)
        # once lifted, the owner and goal are free again
        free = run.decide(
            "detected:prepare-choke", cell=CHOKE_CELL,
            board=_board_with(self.board, turn=seen + HOLD + 2, monsters=[]),
        )
        self.assertIsNone(free["would_bar"])

    def test_revert_proof_index_only_identity_keeps_the_bar(self):
        bar = Bar(
            owner=ClaimOwner.POSITIONING, goal=reach(CHOKE_CELL),
            kind=BAR_THREAT, triggers=((47, 1105),), since_turn=100,
            last_perceived_turn=100,
        )
        pairs = frozenset({(47, 1106)})
        indices = frozenset({(47, 1105)})  # what an index-only reading sees
        turn = 100 + HOLD + 1
        self.assertIsNone(bar_after_board(
            bar, turn=turn, perceived=pairs, hold=HOLD
        ))
        self.assertIsNotNone(bar_after_board(
            bar, turn=turn, perceived=indices, hold=HOLD
        ))

    def test_nothing_but_the_clock_lifts_it(self):
        run, start, _opened, _dropped = self._barred_run()
        # another floor, another position, a changed trigger set: still barred
        floor = self.board.floor_key
        elsewhere = replace(
            _board_with(self.board, turn=start + HOLD, monsters=[]),
            floor_key=(floor[0], floor[1] + 1, floor[2]),
        )
        row = run.decide(
            "detected:prepare-choke", cell=CHOKE_CELL, triggers=[(1, 2)],
            board=elsewhere,
        )
        self.assertIsNotNone(row["would_bar"])
        self.assertEqual(row["bars_active"], 1)


class ErrandBarTest(unittest.TestCase):
    """P1, round 2: a walking errand bar lifts on its durable key only.

    User decision 2026-09-26: a town-errand bar lifts only when the durable
    part of the retirement clearance key changes (inventory, gold, equipment,
    the quest and departure tuples), never by the player's own movement, and
    no clock.  A store-router walk's clearance key is its progress vector,
    whose locomotion part is the distance to the entrance: one step changes
    the full key.
    """

    def _retired_walk(self):
        board = _town_board()
        run = _Run(board)
        policy = run.policy
        family = policy._claim_family_of("shop:approach")
        self.assertEqual(family, "store-router")
        self.assertNotIn(family, TRIGGER_FAMILIES)
        arbiter = policy._town_turn_arbiter
        arbiter.acquire_store_visit(
            owner="store-router", purpose="s2b2-walk", store_type=1,
            opened_sequence=policy._decision_sequence,
            close_visit=policy._close_store_visit,
        )
        here = board.player.position
        entrance = Position(here.y + 6, here.x + 2)
        policy._shopping_approach_goal = entrance
        cell = (entrance.y, entrance.x)
        full = policy._town_retirement_clearance_key(
            board, family, "shop:approach"
        )
        arbiter._retired = {family: full}
        arbiter.telemetry = {"retired": True, "producer_owner": family}
        retired = run.decide("shop:approach", cell=cell)
        arbiter.telemetry = {"retired": False, "producer_owner": family}
        self.assertEqual(retired["state"], "retired")
        (entry,) = retired["bars_set"]
        self.assertEqual(
            (entry["owner"], entry["kind"], entry["ending"], entry["triggers"]),
            (family, BAR_ERRAND, "retired", []),
        )
        self.assertEqual(run.register.bars[0].reason, "shop:approach")
        self.assertEqual(
            run.register.bars[0].clearance,
            policy._claim_durable_clearance(full),
        )
        return run, board, family, cell

    @staticmethod
    def _stepped(board, steps=1):
        here = board.player.position
        return replace(
            board,
            turn=board.turn + 10 * steps,
            player=replace(board.player, position=Position(here.y + steps, here.x)),
        )

    def test_a_walking_errand_bar_survives_the_players_own_steps(self):
        run, board, family, cell = self._retired_walk()
        policy = run.policy
        for steps in (1, 2, 3):
            walked = self._stepped(board, steps)
            with self.subTest(steps=steps):
                # revert-proof: the full clearance key changed with the step,
                # and the arbiter no longer holds the owner retired (both are
                # what round 1 lifted on)
                self.assertNotEqual(
                    policy._town_retirement_clearance_key(
                        walked, family, "shop:approach"
                    ),
                    policy._town_retirement_clearance_key(
                        board, family, "shop:approach"
                    ),
                )
                policy._town_turn_arbiter._retired = {}
                row = run.decide("shop:approach", cell=cell, board=walked)
                self.assertIsNone(row["bars_lifted"])
                self.assertEqual(row["bars_active"], 1)
                self.assertEqual(row["would_bar"]["owner"], family)
        # no clock: a long wait on the same durable facts lifts nothing
        later = replace(board, turn=board.turn + 100 * HOLD)
        self.assertIsNone(run.decide("explore", cell=(1, 1), board=later)["bars_lifted"])

    def test_it_lifts_on_a_gold_or_inventory_change(self):
        for name, change in (
            ("gold", lambda board: replace(
                board, player=replace(board.player, gold=board.player.gold + 1)
            )),
            ("inventory", lambda board: replace(
                board, inventory=list(board.inventory)[1:]
            )),
        ):
            with self.subTest(change=name):
                run, board, family, cell = self._retired_walk()
                walked = self._stepped(board)
                self.assertIsNone(
                    run.decide("shop:approach", cell=cell, board=walked)[
                        "bars_lifted"]
                )
                row = run.decide("shop:approach", cell=cell, board=change(walked))
                (gone,) = row["bars_lifted"]
                self.assertEqual((gone["owner"], gone["kind"]), (family, BAR_ERRAND))
                self.assertEqual(row["bars_active"], 0)
                self.assertIsNone(row["would_bar"])

    def test_the_durable_part_of_each_key_shape(self):
        policy = _Run(_town_board()).policy
        durable = policy._claim_durable_clearance
        # departure: the last element is the locomotion clearance
        departure = ("departure", (0, 0, 0), True, 0, 5, (("hp_full", True),),
                     ("locomotion", "departure", (0, 0, 0), 6, 8))
        self.assertEqual(durable(departure), departure[:-1])
        self.assertEqual(
            durable(departure[:-1] + (("locomotion", "departure", (0, 0, 0), 5, 7),)),
            durable(departure),
        )
        self.assertEqual(durable(departure[:-1] + (None,)), durable(departure))
        # the quest route-unavailable tuples are durable already
        quest = (("quest-enter-approach-route-unavailable", 3, 1), None, None)
        self.assertEqual(durable(quest), quest)
        # the progress vector: the locomotion part goes, the rest stays
        vector = ("facts", ("locomotion", "store-router", (0, 0, 0), 6, 8))
        self.assertEqual(durable(vector), ("facts",))

    def test_an_errand_released_without_retirement_is_not_barred(self):
        board = _town_board()
        run = _Run(board)
        cell = (board.player.position.y + 3, board.player.position.x)
        run.decide("shop:approach", cell=cell)
        run.register.release("store-visit:abandoned")
        row = run.decide("explore", cell=(1, 1))
        self.assertIsNone(row["bars_set"])

    def test_the_pure_rule_has_no_clock(self):
        bar = Bar(
            owner=ClaimOwner.STORE_ROUTER, goal=reach((1, 1)), kind=BAR_ERRAND,
            clearance=("durable", 1), since_turn=5,
        )
        for turn in (5, 5 + HOLD + 1, 5 + 1000 * HOLD):
            with self.subTest(turn=turn):
                self.assertIs(
                    bar_after_board(
                        bar, turn=turn, perceived=frozenset(), hold=HOLD,
                        clearance_of=lambda _bar: ("durable", 1),
                    ),
                    bar,
                )
        self.assertIsNone(bar_after_board(
            bar, turn=6, perceived=frozenset(), hold=HOLD,
            clearance_of=lambda _bar: ("durable", 2),
        ))


class SurvivalAndEndingsTest(unittest.TestCase):
    """P1: survival is never barred; the endings that bar nothing."""

    @classmethod
    def setUpClass(cls):
        _skill, boards = _dungeon_boards()
        cls.board = boards[2]

    def test_a_survival_claim_released_is_not_barred(self):
        run = _Run(self.board)
        opened = run.decide("emergency:seek-upstairs", cell=(4, 4))
        self.assertTrue(opened["survival"])
        self.assertEqual(opened["owner"], "escape")
        run.register.release("gave-up")
        row = run.decide("explore", cell=(5, 5))
        self.assertIsNone(row["bars_set"])

    def test_a_survival_decision_meets_no_would_bar(self):
        run = _Run(self.board)
        run.register.set_bar(Bar(
            owner=ClaimOwner.ESCAPE, goal=reach((4, 4)), kind=BAR_THREAT,
            triggers=((47, 1105),), since_turn=self.board.turn,
            last_perceived_turn=self.board.turn,
        ))
        row = run.decide("emergency:seek-upstairs", cell=(4, 4))
        self.assertTrue(row["survival"])
        self.assertIsNone(row["would_bar"])
        self.assertIsNone(row["would_skip"])
        # the same goal under a non-survival escape reason is recorded
        other = run.decide("breeder-breakthrough:seek-upstairs", cell=(4, 4))
        self.assertFalse(other["survival"])
        self.assertEqual(other["would_bar"]["owner"], "escape")

    def test_no_gated_rung_can_answer_survival(self):
        prefixes = (*SURVIVAL_REASON_PREFIXES, SURVIVAL_RETURN_PREFIX)
        for name in sorted(BAR_GATED_RUNGS):
            rung = rung_named(name)
            with self.subTest(rung=name):
                self.assertIsNotNone(rung)
                self.assertIn(rung.family, TRIGGER_FAMILIES)
                # a bar can carry it: ``rung_of`` reaches it by a reason
                self.assertTrue(rung.ordinary or rung.reasons)
                source = textwrap.dedent(
                    inspect.getsource(getattr(HengbotPolicy, rung.producer))
                )
                literals = {
                    node.value for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                self.assertEqual(
                    sorted(text for text in literals if text.startswith(prefixes)),
                    [],
                )
                self.assertNotIn("_esp_threat_leave_key", source)

    def test_the_endings_that_bar_nothing(self):
        run = _Run(self.board)
        policy = run.policy
        base = Claim(
            claim_id=9, owner=ClaimOwner.POSITIONING, goal=reach((2, 2)),
            trigger_monsters=((47, 1105),),
        )
        cases = {
            "complete": replace(base, closed="complete", closed_reason="reached"),
            "survival": replace(base, closed="release", survival=True),
            "survival-displaced": replace(
                base, closed="release", closed_reason="survival-displaced"
            ),
            "suspended-expired": replace(
                base, closed="release", closed_reason="suspended-expired"
            ),
            "terminal": replace(
                base, goal=terminal("melee"), owner=ClaimOwner.COMBAT,
                closed="release",
            ),
            "non-trigger release": replace(
                base, owner=ClaimOwner.FLOOR_LOOT, closed="release"
            ),
        }
        for name, claim in cases.items():
            with self.subTest(ending=name):
                self.assertIsNone(
                    policy._claim_bar_for(self.board, claim, claim.closed)
                )
        # and the ones that do, for a threat owner
        for ending, claim in (
            ("release", replace(base, closed="release", closed_reason="x")),
            ("expired", replace(
                base, goal=observe(("floor",), 3), closed="expired"
            )),
            ("retired", replace(base, closed="retired")),
            ("abandoned", base),
            ("release", replace(
                base, closed="release", closed_reason="resume-displaced"
            )),
        ):
            with self.subTest(ending=ending, reason=claim.closed_reason):
                bar = policy._claim_bar_for(self.board, claim, ending)
                self.assertIsNotNone(bar)
                self.assertEqual(bar.kind, BAR_THREAT)

    def test_a_retarget_violation_bars_the_goal_it_dropped(self):
        run = _Run(self.board)
        first = run.decide(
            "detected:prepare-choke", cell=(2, 2), triggers=[(47, 1105)]
        )
        second = run.decide("detected:prepare-choke", cell=(3, 3))
        self.assertEqual(second["violation"]["kind"], "retarget")
        (entry,) = second["bars_set"]
        self.assertEqual(
            (entry["claim_id"], entry["ending"], entry["goal"]["cell"]),
            (first["claim_id"], "abandoned", [2, 2]),
        )


class SwitchTest(unittest.TestCase):
    """The switch: an attribute, off, and the pre-call question answers False."""

    def test_the_switch_is_off_and_nothing_is_skipped(self):
        _skill, boards = _dungeon_boards()
        board = boards[2]
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        self.assertIs(policy._claim_bar_enforced, False)
        policy._claim_register.set_bar(Bar(
            owner=ClaimOwner.POSITIONING, goal=reach(CHOKE_CELL),
            kind=BAR_THREAT, since_turn=board.turn,
            last_perceived_turn=board.turn,
            rung="_detected_threat_preparation_key",
        ))
        for name in GATED:
            self.assertIs(policy._claim_bar_skips(board, name), False)
        self.assertIsNone(getattr(policy, "_decision_bar_skips", None))
        policy._claim_bar_enforced = True
        self.assertIs(
            policy._claim_bar_skips(board, "_detected_threat_preparation_key"),
            True,
        )
        self.assertIs(policy._claim_bar_skips(board, "_choke_engagement_key"), False)

    def test_the_shipped_sources_never_turn_it_on(self):
        for path in (ROOT / "src" / "hengbot").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == "_claim_bar_enforced"
                    ):
                        with self.subTest(path=path.name, line=node.lineno):
                            self.assertIsInstance(node.value, ast.Constant)
                            self.assertIs(node.value.value, False)

    def test_the_gated_rungs_are_asked_before_they_run(self):
        tree = ast.parse(POLICY_SOURCE.read_text(encoding="utf-8"))
        decide = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_decide"
        )
        gated = []
        for node in ast.walk(decide):
            if not isinstance(node, ast.IfExp):
                continue
            test = node.test
            if not (
                isinstance(test, ast.Call)
                and isinstance(test.func, ast.Attribute)
                and test.func.attr == "_claim_bar_skips"
            ):
                continue
            name = test.args[1].value
            # skipped means "not called": the rung is only in the else branch
            self.assertIsInstance(node.body, ast.Constant)
            self.assertIsNone(node.body.value)
            self.assertEqual(node.orelse.func.attr, name)
            gated.append((node.lineno, name))
        self.assertEqual([name for _line, name in sorted(gated)], list(GATED))
        self.assertEqual(set(GATED), BAR_GATED_RUNGS)
        # no call anywhere asks after the rung has run
        self.assertNotIn("_claim_bar_gate", POLICY_SOURCE.read_text(encoding="utf-8"))


class ChokePlanTest(unittest.TestCase):
    """Round 2: ON, a barred choke rung is not called; its plan is untouched."""

    COUNTERS = ("decisions_consumed", "sight_loss_decisions", "no_progress_decisions")

    def _policy(self, *, enforced, barred=True):
        board = _quiet_dungeon_board()
        policy = _fresh_policy(board)
        policy.consume_skill_knowledge(_Replay.dungeon_boards()[0])
        destination = Position(board.player.position.y, board.player.position.x - 4)
        policy._choke_engagement_plan = ChokeEngagementPlan(
            floor=board.floor_key, phase="reposition", destination=destination,
            covered_retreat_direction=(0, 1), trigger_last_seen={},
            start_exp=board.player.exp, start_gold=board.player.gold,
            start_breeder_count=0, last_player_hp=board.player.hp,
            closest_destination_distance=4,
        )
        if barred:
            policy._claim_register.set_bar(Bar(
                owner=ClaimOwner.POSITIONING,
                goal=reach((destination.y, destination.x)),
                kind=BAR_THREAT, since_turn=board.turn,
                last_perceived_turn=board.turn, rung="_choke_engagement_key",
            ))
        policy._claim_bar_enforced = enforced
        return policy, board

    def _counters(self, policy):
        plan = policy._choke_engagement_plan
        return {name: getattr(plan, name) for name in self.COUNTERS}

    def test_on_a_barred_choke_rung_spends_nothing(self):
        policy, board = self._policy(enforced=True)
        before = self._counters(policy)
        policy.choose_key(board)
        self.assertEqual(self._counters(policy), before)
        self.assertIsNone(policy._choke_engagement_plan.release_cause)
        self.assertFalse((policy.last_reason or "").startswith("melee:choke"))
        self.assertIn(
            "_choke_engagement_key",
            [entry["rung"] for entry in policy.decision_claim["bar_skipped"]],
        )

    def test_revert_proof_off_the_same_board_spends_the_plan(self):
        policy, board = self._policy(enforced=False)
        before = self._counters(policy)
        policy.choose_key(board)
        self.assertNotEqual(self._counters(policy), before)
        self.assertIsNone(policy.decision_claim["bar_skipped"])
        # and ON without a bar on the rung runs it exactly as OFF does
        unbarred, same = self._policy(enforced=True, barred=False)
        unbarred.choose_key(same)
        self.assertEqual(self._counters(unbarred), self._counters(policy))
        self.assertEqual(unbarred.last_reason, policy.last_reason)


# -- P2 ----------------------------------------------------------------------


class LootChokeRecordedTest(unittest.TestCase):
    """P2: the 2026-09-23 06:00 capture, switch off and switch on."""

    @classmethod
    def setUpClass(cls):
        cls.skill, cls.boards = _dungeon_boards()
        cls.off = cls._replay(enforced=False)
        cls.on = cls._replay(enforced=True)

    @classmethod
    def _replay(cls, *, enforced):
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        policy._claim_bar_enforced = enforced
        policy.consume_skill_knowledge(cls.skill)
        rows = []
        for board in cls.boards:
            key = policy.choose_key(board)
            key = policy.validate_read_key(board, key)
            rows.append((str(key), policy.last_reason, dict(policy.decision_claim)))
            policy.confirm_key_posted(key)
        return rows

    def test_off_decides_exactly_as_before(self):
        self.assertEqual(
            [(key, reason) for key, reason, _claim in self.off],
            PRE_S2B2_TRAJECTORY,
        )
        with tempfile.TemporaryDirectory(prefix="s2b2-") as raw:
            off, _log = _Replay.run(
                Path(raw), self.skill,
                [board for board in _Replay.dungeon_boards()[1]],
                register=False,
            )
        self.assertEqual(
            [(str(key), reason) for key, reason in off], PRE_S2B2_TRAJECTORY
        )

    def test_off_records_the_positioning_would_bar(self):
        melee = self.off[MELEE_ROW][2]
        (entry,) = melee["bars_set"]
        self.assertEqual(
            (entry["owner"], entry["goal"], entry["kind"], entry["since_turn"],
             entry["triggers"], entry["ending"]),
            ("positioning", {"kind": "Reach", "cell": CHOKE_CELL}, BAR_THREAT,
             BAR_TURN, CLAIM_3_TRIGGERS, "release:choke-hostile-visible"),
        )
        would = [
            (index, claim["would_bar"])
            for index, (_key, _reason, claim) in enumerate(self.off)
            if claim["would_bar"] is not None
        ]
        self.assertEqual(
            [index for index, _would in would],
            list(range(MELEE_ROW + 1, len(self.boards))),
        )
        for _index, entry in would:
            self.assertEqual(
                entry,
                {
                    "owner": "positioning",
                    "goal": {"kind": "Reach", "cell": CHOKE_CELL},
                    "bar_since_turn": BAR_TURN,
                    "triggers": CLAIM_3_TRIGGERS,
                },
            )
        # recorded only: no rung was skipped, the bar never lifted; the rung
        # the switch would have skipped is recorded on the same rows
        for index, (_key, _reason, claim) in enumerate(self.off):
            self.assertIsNone(claim["bar_skipped"])
            self.assertIsNone(claim["bars_lifted"])
            self.assertEqual(
                claim["would_skip"],
                SKIPPED_PREPARATION if index > MELEE_ROW else None,
            )

    def test_on_the_oscillation_does_not_recur(self):
        # identical up to and including the decision that set the bar
        self.assertEqual(
            [(key, reason) for key, reason, _claim in self.on[:MELEE_ROW + 1]],
            PRE_S2B2_TRAJECTORY[:MELEE_ROW + 1],
        )
        after = self.on[MELEE_ROW + 1:]
        self.assertEqual({reason for _key, reason, _claim in after}, {"seek-loot"})
        self.assertEqual(len({claim["claim_id"] for *_rest, claim in after}), 1)
        goal = after[0][2]["goal"]
        self.assertEqual(goal["kind"], "Reach")
        target = Position(*goal["cell"])
        for (key, _reason, claim), board in zip(after, self.boards[MELEE_ROW + 1:]):
            with self.subTest(turn=board.turn):
                self.assertEqual(claim["bar_skipped"], [SKIPPED_PREPARATION])
                self.assertIsNone(claim["would_bar"])
                self.assertIsNone(claim["violation"])
                # every loot step closes on the loot walk's goal
                origin = board.player.position
                stepped = next(
                    Position(origin.y + dy, origin.x + dx)
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if (dy or dx) and HengbotPolicy._direction_key(
                        None, origin, Position(origin.y + dy, origin.x + dx)
                    ) == key
                )
                self.assertLess(
                    stepped.distance_to(target), origin.distance_to(target)
                )

    def test_revert_proof_without_the_gate_on_changes_nothing(self):
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        policy._claim_bar_enforced = True
        policy._claim_bar_skips = lambda _snapshot, _rung: False
        policy.consume_skill_knowledge(self.skill)
        decided = []
        for board in self.boards:
            key = policy.choose_key(board)
            key = policy.validate_read_key(board, key)
            decided.append((str(key), policy.last_reason))
            policy.confirm_key_posted(key)
        self.assertEqual(decided, PRE_S2B2_TRAJECTORY)


# -- P3 ----------------------------------------------------------------------


class BarMetricsTest(unittest.TestCase):
    """P3: the ledger counts would-bars; the reader prints them per owner."""

    def test_the_ledger_and_the_report(self):
        skill, raws = _Replay.dungeon_boards()
        with tempfile.TemporaryDirectory(prefix="s2b2-ledger-") as raw:
            root = Path(raw)
            trajectory, _log = _Replay.run(
                root, skill, raws, register=True, ledger=True
            )
            claims = read_records(root / OWNERSHIP_CLAIMS_NAME)
            report = ownership_metrics_report.render(
                [], {
                    "sessions": 0, "runtime_seconds": 0.0, "runtime_hours": 0.0,
                    "runtime_sources": {}, "decisions": 0, "town_decisions": 0,
                    "arbiter_owner_changes": 0, "claims": 0, "claim_share": None,
                    "implicit_handoffs": 0, "implicit_handoffs_per_hour": None,
                    "stops": {}, "stops_total": 0, "stops_per_hour": None,
                    "arbiter_owner_changes_per_hour": None,
                },
                claims,
            )
            metrics = (root / OWNERSHIP_METRICS_NAME).exists()
        self.assertTrue(metrics)
        self.assertEqual(
            [(str(key), reason) for key, reason in trajectory],
            PRE_S2B2_TRAJECTORY,
        )
        numbers = bar_numbers(claims)
        self.assertEqual(
            numbers["would_bar"],
            {"count": 18, "by_owner": {"positioning": {"events": 18, "claims": 1}}},
        )
        self.assertEqual(
            numbers["bars_set"],
            {"count": 1, "by_owner_kind": {"positioning/threat": 1}},
        )
        self.assertEqual(numbers["lifetimes"], {})
        self.assertEqual(
            numbers["still_barred"],
            {"positioning": {"count": 1, "max_age_turns": LAST_TURN - BAR_TURN}},
        )
        self.assertEqual(numbers["skipped"], {"count": 0, "by_owner": {}})
        self.assertEqual(
            numbers["would_skip"],
            {"count": 18, "by_rung": {"_detected_threat_preparation_key": 18}},
        )
        self.assertIn("S2b.2 bar table", report)
        self.assertIn("would-bar events", report)
        self.assertIn("would-skip decisions", report)
        self.assertRegex(report, r"\n    positioning +18 \(1 claim\(s\)\)\n")

    def test_lifetimes_are_read_from_the_lift(self):
        goal = {"kind": "Reach", "cell": [1, 1]}
        rows = [
            {"kind": "claim", "session": "s", "turn": 10, "claim_id": 1,
             "bars_set": [{"owner": "hunt", "goal": goal, "kind": "threat",
                           "since_turn": 10, "since_sequence": 1}]},
            {"kind": "claim", "session": "s", "turn": 20, "claim_id": 2,
             "would_bar": {"owner": "hunt", "goal": goal,
                           "bar_since_turn": 10, "triggers": []}},
            {"kind": "claim", "session": "s", "turn": 700, "claim_id": 2,
             "bars_lifted": [{"owner": "hunt", "goal": goal, "kind": "threat",
                              "since_turn": 10, "since_sequence": 1,
                              "lifted_turn": 700, "lifted_sequence": 9}]},
        ]
        numbers = bar_numbers(rows)
        self.assertEqual(
            numbers["lifetimes"]["hunt"]["turns"],
            {"count": 1, "min": 690, "median": 690, "max": 690},
        )
        self.assertEqual(
            numbers["lifetimes"]["hunt"]["decisions"],
            {"count": 1, "min": 8, "median": 8, "max": 8},
        )
        self.assertEqual(numbers["still_barred"], {})
        self.assertEqual(
            numbers["would_bar"]["by_owner"], {"hunt": {"events": 1, "claims": 1}}
        )


# -- P4 ----------------------------------------------------------------------


class RestoredCheckpointTest(unittest.TestCase):
    """P4: registers and policies pickled before S2b.2."""

    def test_a_pre_s2b2_register_unpickles_and_bars(self):
        register = ClaimRegister()
        register.declare(ClaimOwner.POSITIONING, reach((3, 4)))
        del register.__dict__["_bars"]
        del register.__dict__["_ended"]
        restored = pickle.loads(pickle.dumps(register))
        self.assertEqual(restored.bars, ())
        self.assertEqual(restored.take_ended(), [])
        self.assertIsNone(restored.barring(ClaimOwner.POSITIONING, reach((3, 4))))
        released = restored.release("gave-up")
        self.assertEqual(restored.take_ended(), [released])
        bar = restored.set_bar(Bar(
            owner=ClaimOwner.POSITIONING, goal=reach((3, 4)), kind=BAR_THREAT,
            triggers=((1, 2),), since_turn=5,
        ))
        self.assertIs(restored.barring("positioning", reach((3, 4))), bar)
        # a bar pickles with the register, clearance and all
        restored.set_bar(Bar(
            owner=ClaimOwner.STORE_ROUTER, goal=reach((1, 1)), kind=BAR_ERRAND,
            clearance=(("vector", Position(1, 2)), 3),
        ))
        again = pickle.loads(pickle.dumps(restored))
        self.assertEqual(again.bars, restored.bars)

    def test_a_round_one_bar_unpickles_and_gates_nothing(self):
        bar = Bar(
            owner=ClaimOwner.POSITIONING, goal=reach((3, 4)), kind=BAR_THREAT,
            since_turn=5, last_perceived_turn=5,
        )
        object.__delattr__(bar, "rung")
        object.__delattr__(bar, "reason")
        restored = pickle.loads(pickle.dumps(bar))
        self.assertIsNone(restored.rung)
        self.assertIsNone(restored.reason)
        _skill, boards = _dungeon_boards()
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        policy._claim_bar_enforced = True
        policy._claim_register.set_bar(restored)
        for name in GATED:
            self.assertIs(policy._claim_bar_skips(boards[2], name), False)

    def test_a_merged_bar_keeps_its_start_and_unites_its_triggers(self):
        register = ClaimRegister()
        first = register.set_bar(Bar(
            owner=ClaimOwner.HUNT, goal=reach((1, 1)), kind=BAR_THREAT,
            triggers=((1, 2),), since_turn=5, last_perceived_turn=5,
        ))
        merged = register.set_bar(Bar(
            owner=ClaimOwner.HUNT, goal=reach((1, 1)), kind=BAR_THREAT,
            triggers=((3, 4),), since_turn=9, last_perceived_turn=9,
        ))
        self.assertEqual(len(register.bars), 1)
        self.assertEqual(merged.since_turn, first.since_turn)
        self.assertEqual(merged.triggers, ((1, 2), (3, 4)))
        self.assertEqual(merged.last_perceived_turn, 9)

    def test_the_legacy_checkpoint_restores_the_switch_off_and_decides(self):
        with gzip.open(LEGACY_CHECKPOINT, "rt", encoding="utf-8") as stream:
            capture = json.load(stream)
        producer = capture["sequence"][0]
        snapshot = pickle.loads(
            base64.b64decode(capture["snapshots_pickle_b64"][producer["snapshot_id"]])
        )
        state = pickle.loads(base64.b64decode(capture["producer_checkpoint_pickle_b64"]))
        register = ClaimRegister()
        register.declare(ClaimOwner.STORE_ROUTER, reach((1, 1)))
        del register.__dict__["_bars"]
        del register.__dict__["_ended"]
        state["_claim_register"] = register
        self.assertNotIn("_claim_bar_enforced", state)
        self.assertNotIn("_decision_bar_skips", state)
        encoded = base64.b64encode(pickle.dumps(state)).decode("ascii")
        restored = restore_checkpoint(HengbotPolicy, encoded)
        self.assertIs(restored.__dict__["_claim_bar_enforced"], False)
        self.assertIsNone(restored.__dict__["_decision_bar_skips"])
        self.assertEqual(restored._claim_register.__dict__["_bars"], [])
        self.assertEqual(restored._claim_register.__dict__["_ended"], [])
        key = restored.choose_key(snapshot)
        self.assertEqual(
            (key, restored.last_reason),
            (producer["expected_key"], producer["expected_reason"]),
        )
        self.assertIn("would_bar", restored.decision_claim)
        self.assertEqual(restored.decision_claim["bars_active"], 0)

    def test_a_policy_without_the_attributes_decides_through_getattr(self):
        skill, boards = _dungeon_boards()
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        policy.consume_skill_knowledge(skill)
        del policy.__dict__["_claim_bar_enforced"]
        del policy._claim_register.__dict__["_bars"]
        del policy._claim_register.__dict__["_ended"]
        self.assertIs(
            policy._claim_bar_skips(boards[0], "_choke_engagement_key"), False
        )
        key = policy.choose_key(boards[0])
        self.assertEqual((str(key), policy.last_reason), PRE_S2B2_TRAJECTORY[0])
        self.assertIsNone(policy.decision_claim["would_bar"])


if __name__ == "__main__":
    unittest.main()
