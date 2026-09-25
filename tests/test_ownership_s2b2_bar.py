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
  perceived; errand bars when the arbiter no longer holds the owner retired
  under the clearance key it held when the bar was set.
* ``would_bar`` on the decision row at the ``choose_key`` exit, plus
  ``bars_set`` / ``bars_lifted`` / ``bars_active`` / ``bar_skipped``; the
  ledger counts would-bars; ``ownership_metrics.bar_numbers`` and the report
  print would-bar events per owner and bar lifetimes.
* The switch ``HengbotPolicy._claim_bar_enforced`` (a policy attribute,
  default False, never set by shipped code) and its plumbing
  ``_claim_bar_gate``, wired around the trigger-family rungs of ``_decide``
  whose producer writes its own reason and goal (``WIRED`` below).  The step
  rungs whose reason ``_decide`` writes after the call (``_flee_step``,
  ``_hunt_step``, ``_direction_key``) and the errand families (their rungs
  are S3 work, design 3.3; the arbiter's in-gate retirement already keeps a
  retired errand from acting) are not wired.

The pins
--------
P1  class tests on the register and the policy's exit: a threat bar set on a
    positioning release, kept by a perceived trigger, lifted exactly after
    the 50-turn clock -- and a monster that reuses a trigger's index under
    another race does not keep it (revert-proof: index-only identity would);
    an errand bar set on retirement stands while the arbiter's clearance key
    is unchanged and lifts when the arbiter clears it; survival is never
    barred (neither by a bar set, a would-bar, nor the gate); the endings
    that bar nothing.
P2  the recorded 2026-09-23 06:00 loot <-> prepare-choke capture:
    switch OFF -- keys and reasons byte-identical to the pre-S2b.2 replay and
    to the register-off replay, and the positioning owner's would-bar is
    recorded on every decision after its release; switch ON -- seek-loot
    owns every decision after the bar and the positioning rung is skipped.
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
``ClaimRegister._ended``; ``HengbotPolicy._claim_bar_enforced`` (``__init__``,
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
import gzip
import json
import pickle
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.claim_ladder import CLAIM_LADDER, TRIGGER_FAMILIES, decide_rungs
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

from test_ownership_claims import LEGACY_CHECKPOINT, _Replay
from test_ownership_s2a1_closure import _fresh_policy, _town_board

import ownership_metrics_report


ROOT = Path(__file__).resolve().parents[1]
POLICY_SOURCE = ROOT / "src" / "hengbot" / "policy.py"
HOLD = DETECTED_THREAT_HOLD_MAX_GAME_TURNS

# The rungs of ``_decide`` wrapped by ``_claim_bar_gate`` (design 3.3's
# plumbing): the trigger-family producers that write their own reason and goal.
WIRED = (
    "_esp_threat_hunt_key",
    "_summoner_ranged_kill_key",
    "_emergency_item",
    "_paralyzer_prevention_key",
    "_unseen_retreat_intercept_key",
    "_unseen_retreat_key",
    "_detected_threat_preparation_key",
    "_breeder_breakthrough_key",
    "_choke_engagement_key",
    "_ranged_attack_key",
    "_fruitless_disengage_key",
    "_breeder_breakthrough_escape_key",
    "_melee_swarm_combat_key",
    "_ranged_attack_key",
    "_esp_threat_rest_key",
)

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
                "ending", "last_perceived_turn",
            )},
            {
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
            bar, turn=turn, perceived=pairs, hold=HOLD, retired={}
        ))
        self.assertIsNotNone(bar_after_board(
            bar, turn=turn, perceived=indices, hold=HOLD, retired={}
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
    """P1: a retired errand is barred until the clearance key changes."""

    def test_an_errand_bar_lifts_on_a_clearance_key_change(self):
        board = _town_board()
        run = _Run(board)
        policy = run.policy
        family = policy._claim_family_of("shop:approach")
        self.assertNotIn(family, TRIGGER_FAMILIES)
        arbiter = policy._town_turn_arbiter
        cell = (board.player.position.y + 3, board.player.position.x)
        first_key = ("clearance", 1)
        arbiter._retired = {family: first_key}
        arbiter.telemetry = {"retired": True, "producer_owner": family}
        retired = run.decide("shop:approach", cell=cell)
        self.assertEqual(retired["state"], "retired")
        (entry,) = retired["bars_set"]
        self.assertEqual(
            (entry["owner"], entry["kind"], entry["ending"], entry["triggers"]),
            (family, BAR_ERRAND, "retired", []),
        )
        self.assertEqual(run.register.bars[0].clearance, first_key)
        # the arbiter re-evaluates the key on the next town board: unchanged
        arbiter.telemetry = {"retired": False, "producer_owner": family}
        arbiter.observe(
            in_town=True, reason="shop:approach", progress_vector=("v", 1),
            retirement_key_for=lambda owner: first_key,
        )
        kept = run.decide("shop:approach", cell=cell)
        self.assertIsNone(kept["bars_lifted"])
        self.assertEqual(kept["would_bar"]["owner"], family)
        # the clearance key changes: the arbiter clears the retirement, and
        # the bar lifts with it
        arbiter.observe(
            in_town=True, reason="shop:approach", progress_vector=("v", 2),
            retirement_key_for=lambda owner: ("clearance", 2),
        )
        self.assertNotIn(family, arbiter._retired)
        lifted = run.decide("shop:approach", cell=cell)
        (gone,) = lifted["bars_lifted"]
        self.assertEqual((gone["owner"], gone["kind"]), (family, BAR_ERRAND))
        self.assertIsNone(lifted["would_bar"])

    def test_an_errand_released_without_retirement_is_not_barred(self):
        board = _town_board()
        run = _Run(board)
        cell = (board.player.position.y + 3, board.player.position.x)
        run.decide("shop:approach", cell=cell)
        run.register.release("store-visit:abandoned")
        row = run.decide("explore", cell=(1, 1))
        self.assertIsNone(row["bars_set"])

    def test_a_bar_on_an_owner_the_arbiter_does_not_hold_lifts(self):
        bar = Bar(
            owner=ClaimOwner.STORE_ROUTER, goal=reach((1, 1)), kind=BAR_ERRAND,
            clearance=("k", 1),
        )
        standing = {"store-router": ("k", 1)}
        self.assertIs(
            bar_after_board(bar, turn=5, perceived=frozenset(), hold=HOLD,
                            retired=standing),
            bar,
        )
        for retired in ({}, {"store-router": ("k", 2)}, None):
            with self.subTest(retired=retired):
                self.assertIsNone(bar_after_board(
                    bar, turn=5, perceived=frozenset(), hold=HOLD,
                    retired=retired,
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

    def test_a_survival_decision_meets_no_would_bar_and_no_gate(self):
        run = _Run(self.board)
        policy = run.policy
        run.register.set_bar(Bar(
            owner=ClaimOwner.ESCAPE, goal=reach((4, 4)), kind=BAR_THREAT,
            triggers=((47, 1105),), since_turn=self.board.turn,
            last_perceived_turn=self.board.turn,
        ))
        row = run.decide("emergency:seek-upstairs", cell=(4, 4))
        self.assertTrue(row["survival"])
        self.assertIsNone(row["would_bar"])
        # the gate, switched on, passes a survival answer through
        policy._claim_bar_enforced = True
        saved = policy._claim_bar_saved()
        self.assertIsNotNone(saved)
        policy.last_reason = "emergency:seek-upstairs"
        policy._decision_goal = ("escape", reach((4, 4)), None)
        self.assertEqual(policy._claim_bar_gate(self.board, saved, "7"), "7")
        # the same goal under a non-survival escape reason is skipped
        policy.last_reason = "breeder-breakthrough:seek-upstairs"
        self.assertIsNone(policy._claim_bar_gate(self.board, saved, "7"))

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
    """The switch: an attribute, off, and the gate is the identity while off."""

    def test_the_switch_is_off_and_the_gate_passes_everything(self):
        _skill, boards = _dungeon_boards()
        board = boards[2]
        policy = HengbotPolicy(monrace_knowledge=_Replay.knowledge())
        self.assertIs(policy._claim_bar_enforced, False)
        policy._claim_register.set_bar(Bar(
            owner=ClaimOwner.POSITIONING, goal=reach(CHOKE_CELL),
            kind=BAR_THREAT, since_turn=board.turn,
            last_perceived_turn=board.turn,
        ))
        policy.last_reason = "detected:prepare-choke"
        policy._decision_goal = ("positioning", reach(CHOKE_CELL), None)
        self.assertIsNone(policy._claim_bar_saved())
        answer = "6"
        self.assertIs(policy._claim_bar_gate(board, None, answer), answer)
        self.assertEqual(policy.last_reason, "detected:prepare-choke")

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

    def test_the_wired_rungs(self):
        tree = ast.parse(POLICY_SOURCE.read_text(encoding="utf-8"))
        decide = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_decide"
        )
        wired = []
        for node in ast.walk(decide):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_claim_bar_gate"
            ):
                self.assertEqual(len(node.args), 3)
                saved, inner = node.args[1], node.args[2]
                self.assertEqual(saved.func.attr, "_claim_bar_saved")
                wired.append((inner.lineno, inner.func.attr))
        self.assertEqual(
            [name for _line, name in sorted(wired)], list(WIRED)
        )
        # every wired producer is a rung of a threat-triggered family
        families = {
            rung.producer: set() for rung in decide_rungs(CLAIM_LADDER)
        }
        for rung in decide_rungs(CLAIM_LADDER):
            families[rung.producer].add(rung.family)
        for name in set(WIRED):
            with self.subTest(producer=name):
                self.assertTrue(families[name] & TRIGGER_FAMILIES)


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
        # recorded only: no rung was skipped, the bar never lifted
        for _key, _reason, claim in self.off:
            self.assertIsNone(claim["bar_skipped"])
            self.assertIsNone(claim["bars_lifted"])

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
                self.assertEqual(
                    claim["bar_skipped"],
                    [{
                        "owner": "positioning",
                        "goal": {"kind": "Reach", "cell": CHOKE_CELL},
                        "reason": "detected:prepare-choke",
                        "bar_since_turn": BAR_TURN,
                    }],
                )
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
        policy._claim_bar_gate = lambda _snapshot, _saved, result: result
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
        self.assertIn("S2b.2 bar table", report)
        self.assertIn("would-bar events", report)
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
        self.assertIsNone(policy._claim_bar_saved())
        key = policy.choose_key(boards[0])
        self.assertEqual((str(key), policy.last_reason), PRE_S2B2_TRAJECTORY[0])
        self.assertIsNone(policy.decision_claim["would_bar"])


if __name__ == "__main__":
    unittest.main()
