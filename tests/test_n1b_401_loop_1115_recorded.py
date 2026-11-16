"""n1-b life-401's two loop stops on Angband 49F (2026-11-15 17:17:49 and 17:17:56), and their cause.

Live (Magic-Eater Lv37, HP 815): a black dragon's breath sent the player by Teleportation from
(15,93) to (20,2), the west dead end (20,1)-(20,3) of a corridor whose one way on runs east past
a sleeping バイクロプス (race 490) on (20,11), the up stairs (21,13) beyond it.  After the searches
of the dead end the idle wander (``stuck:wander``, policy ``_town_idle_key``) stepped '6' from
(20,1) to (20,2) and '6' into (20,3), inside the sleeper's area (8 cells: HUNT_RANGE);
``threat:avoid-engagement`` (owner 2026-11-07 「眠っている敵でも強い敵からは離れる」) stepped '4'
back, its veto of (20,3) not made because it would seal the pocket (engagement_avoid_seal); the
wander went '4' to (20,1) and round again, 18 times, until the loop detector stopped the bot,
twice in 30 minutes, and the guard retired the life.

Why nothing broke it: each retreat reset the stuck count (``_stuck_escape_streak``: not a stuck
reason), so the stuck escape never came; the round was four moves over three cells (wander
1->2, wander 2->3, retreat 3->2, wander 2->1), no two-cell alternation A p->q, B q->p that the
ping-pong guard (pingpong_guard, owner 2026-11-13 part 2) reads.  The root: the wander kept off
only the retreats' vetoes and the left-cell registry, not the walks' one veto (``_walk_veto``,
the sleeper's area among it) every other walker keeps off, so it alone walked back into the
area the retreat had just left (owner 2026-11-13 part 1: 「歩く担当は全部これを読み、理由が消える
まで戻らない」).

Recorded: tests/fixtures/n1b-401-loop-1115.jsonl.gz (tests/extract_n1b_401_loop_1115_fixture.py),
the ~f skill list and the 61 boards of the 49F visit with their decision records.  The boards on
(15,93) are decided in order through the public ``choose_key`` of one fresh policy; from the
landing (20,2) on, in a closed loop: each step key moves the player as the game does and the
board of the player's cell is the next recorded board there (the sleeper as the game showed it
from that cell).  DECLARED CONSTRUCTED: in the closed loop the turn goes on 5 game turns a board
and the recorded boards' messages are not repeated; the absorbed power lists the live process
had read (the capture does not carry them) are not listed, so the fresh policy casts no Magic
Mapping on the landing.  The stuck escape's read is posted through the production executor.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from contextlib import nullcontext
import copy
from collections import defaultdict, deque
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import cli, engagement_avoid_seal, pingpong_guard, retreat_enclosure
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import DIRECTION_KEYS, HUNT_RANGE, STUCK_ESCAPE_LIMIT
from tests import test_me_nokey_1031_recorded as nokey
from tests.support.recorded import EDIT, READ_PROMPT, _policy, prompt_screen

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-401-loop-1115.jsonl.gz"
FIXTURE_SHA256 = "907e654f3404a03ee56a6f24fe91dbe67a4ed47230e8ba61929853cf003a8a89"
LANDING_TURN = 1981271       # decision 5637, the board after the emergency teleport 'rd'
FIRST_WANDER_TURN = 1981380  # decision 5655, the first stuck:wander '6' from (20,1)
DEAD_END = (Position(20, 1), Position(20, 2), Position(20, 3))
SLEEPER = Position(20, 11)
SLEEPER_RACE = 490
WANDER, RETREAT = "stuck:wander", "threat:avoid-engagement"
LEAVES = ("stuck:recall-escape", "stuck:teleport-escape", "stuck:enclosed-teleport",
          "stuck:walled-off-recall")
OFFSETS = {key: offset for offset, key in DIRECTION_KEYS.items()}


def _rows():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


ROWS = _rows()
SKILL = next(row["board"] for row in ROWS if row["role"] == "skill-knowledge")
BOARDS = [row["board"] for row in ROWS if row["role"] == "board"]
DECISIONS = [row["decision"] for row in ROWS if row["role"] == "decision"]
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
BEFORE_LANDING = [raw for raw in BOARDS if raw["turn"] < LANDING_TURN]
BY_CELL = defaultdict(list)
for _raw in BOARDS:
    if _raw["turn"] >= LANDING_TURN:
        BY_CELL[Position(_raw["player"]["y"], _raw["player"]["x"])].append(_raw)


def _without_walk_veto():
    """The wander as before the fix: off the retreats' vetoes and the registry only."""
    original = HengbotPolicy._least_visited_neighbor

    def old(self, snapshot, *, walk_veto=False):
        return original(self, snapshot)

    return mock.patch.object(HengbotPolicy, "_least_visited_neighbor", old)


def _without_route_veto_seal():
    """The idle layer before owner 2026-11-17 「半径13以内なら *破壊*、無理なら溶かして抜ける」
    (retreat_enclosure ``route_veto_sealed_key``, n1-c life-216): no answer below the explore for
    a sleeper's area that holds every way on, so the dead end's searches and the wander ran
    first.  The live process (the control) and the 11-15 wander fix are read under it."""
    return mock.patch.object(retreat_enclosure, "route_veto_sealed_key", lambda policy, snapshot: None)


_WALKS = {}


def _walk(decisions=120, *, fixed=True, guard_cells=pingpong_guard.CYCLE_MAX_CELLS, route_seal=None):
    """``_walked`` once per configuration (the replay takes seconds); the policy and board are
    the replay's own, shared by the tests that read them.  ``route_seal`` (default ``fixed``)
    keeps the 2026-11-17 route-veto rung; the control walks without it."""
    route_seal = fixed if route_seal is None else route_seal
    if (decisions, fixed, guard_cells, route_seal) not in _WALKS:
        _WALKS[(decisions, fixed, guard_cells, route_seal)] = _walked(
            decisions, fixed=fixed, guard_cells=guard_cells, route_seal=route_seal)
    return _WALKS[(decisions, fixed, guard_cells, route_seal)]


def _two_cell_guard():
    """The ping-pong guard as it was before the owner's 2026-11-15 「6マスまで広げる」: two cells."""
    return mock.patch.object(pingpong_guard, "CYCLE_MAX_CELLS", 2)


def _walked(decisions, *, fixed, guard_cells=pingpong_guard.CYCLE_MAX_CELLS, route_seal=None):
    """(rows, the decision the CLI loop detector tripped on, the ping-pong events, policy, the
    raw board of the last decision): each row (cell, key, reason); the walk stops at a leave."""
    directory = TemporaryDirectory()
    policy = _policy(Path(directory.name), MONRACE)
    first = parse_snapshot(copy.deepcopy(BOARDS[0]), MONRACE)
    policy.prime(first)
    policy.consume_skill_knowledge({**SKILL, "player": {"level": first.player.level}})
    rows, events, tripped, previous_reason = [], [], None, None
    recent = deque(maxlen=cli.MULTIPLIER_COMBAT_LOOP_WINDOW)
    last_position = last_player = raw = None
    used = defaultdict(int)
    position, turn = DEAD_END[1], LANDING_TURN
    patch = nullcontext() if fixed else _without_walk_veto()
    guard = nullcontext() if guard_cells == pingpong_guard.CYCLE_MAX_CELLS else (
        mock.patch.object(pingpong_guard, "CYCLE_MAX_CELLS", guard_cells))
    route_seal = fixed if route_seal is None else route_seal
    seal = nullcontext() if route_seal else _without_route_veto_seal()
    with patch, guard, seal:
        for index in range(len(BEFORE_LANDING) + decisions):
            if index < len(BEFORE_LANDING):
                raw = copy.deepcopy(BEFORE_LANDING[index])
            else:
                boards = BY_CELL[position]
                assert boards, position  # every cell walked has a recorded board
                raw = copy.deepcopy(boards[used[position] % len(boards)])
                if used[position] or raw["turn"] != LANDING_TURN:
                    raw["messages"] = []
                used[position] += 1
                raw["turn"] = turn
                turn += 5
            if previous_reason is not None:
                raw["_completed_operation_owner"] = previous_reason
            snapshot = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), MONRACE))
            key = str(policy.choose_key(snapshot))
            previous_reason = policy.last_reason
            if index < len(BEFORE_LANDING):
                if key:
                    policy.confirm_key_posted(key)
                continue
            rows.append((position, key, policy.last_reason))
            if pingpong_guard.report(policy):
                events.append((len(rows) - 1, pingpong_guard.report(policy)))
            previous_position, last_position = last_position, snapshot.player.position
            previous_player, last_player = last_player, snapshot.player
            if cli._cell_loop_guard_applies(snapshot, policy.last_reason, previous_position,
                                            previous_player):
                recent.append((snapshot.floor_key, position.y, position.x))
                if tripped is None and cli._is_looping(recent):
                    tripped = len(rows) - 1
            else:
                recent.clear()
            if policy.last_reason in LEAVES:
                break
            if key:
                policy.confirm_key_posted(key)
            offset = OFFSETS.get(key)
            if offset is not None:
                position = Position(position.y + offset[0], position.x + offset[1])
    return rows, tripped, events, policy, raw, directory


class RecordedWindowTest(unittest.TestCase):
    def test_the_live_rows(self):
        landing = next(raw for raw in BOARDS if raw["turn"] == LANDING_TURN)
        self.assertEqual((landing["player"]["y"], landing["player"]["x"]), (20, 2))
        self.assertEqual({raw["floor"]["level"] for raw in BOARDS}, {49})
        self.assertEqual(set(BY_CELL), set(DEAD_END))
        for raw in BY_CELL[DEAD_END[2]] + BY_CELL[DEAD_END[1]]:
            sleeper = [m for m in raw["visible_monsters"] if m["race_id"] == SLEEPER_RACE]
            self.assertEqual([(m["y"], m["x"], m["asleep"]) for m in sleeper],
                             [(SLEEPER.y, SLEEPER.x, True)])
        live = [(d["reason"], d["key"]) for d in DECISIONS if d["turn"] >= FIRST_WANDER_TURN]
        # The live round: wander '6', wander '6', retreat '4', wander '4' ... to the stop.
        self.assertEqual(live[:8], [(WANDER, "6"), (WANDER, "6"), (RETREAT, "4"), (WANDER, "4")] * 2)
        self.assertEqual(live[-1], ("loop-detected", ""))
        self.assertEqual(sum(1 for row in live if row == (RETREAT, "4")), 10)

    def test_the_cell_beside_the_dead_end_is_in_the_sleepers_area(self):
        """From (20,2) the sleeper is 9 cells off (outside HUNT_RANGE): its whole area is the
        routes' veto, (20,3) in it; from (20,3), 8 cells off, the retreat fires."""
        self.assertEqual(DEAD_END[1].distance_to(SLEEPER), HUNT_RANGE + 1)
        self.assertEqual(DEAD_END[2].distance_to(SLEEPER), HUNT_RANGE)
        rows, _tripped, _events, policy, _raw, _directory = _walk(2)
        raw = copy.deepcopy(BY_CELL[DEAD_END[1]][0])
        board = parse_snapshot(raw, MONRACE)
        self.assertIn(DEAD_END[2], policy._engagement_danger_cells(board))
        self.assertIn(DEAD_END[2], policy._walk_veto(board))
        self.assertNotIn(DEAD_END[0], policy._walk_veto(board))


class WithoutTheFixTest(unittest.TestCase):
    """The control: the wander off the retreats' vetoes and the registry only, with the
    ping-pong guard of the live process (two cells; 2026-11-15 Q1 widened it, see below), and
    without the 2026-11-17 route-veto rung (``_without_route_veto_seal``), as the live process."""

    def test_the_live_round_and_the_loop_stop(self):
        rows, tripped, events, _policy_, _raw, _directory = _walk(fixed=False, guard_cells=2)
        reasons = [reason for _cell, _key, reason in rows]
        self.assertIn(RETREAT, reasons)
        retreats = [(cell, key) for cell, key, reason in rows if reason == RETREAT]
        self.assertEqual(set(retreats), {(DEAD_END[2], "4")})
        self.assertGreaterEqual(len(retreats), 8)
        self.assertIn((DEAD_END[1], "6", WANDER), rows)
        self.assertIsNotNone(tripped, rows)
        self.assertEqual({cell for cell, _key, _reason in rows}, set(DEAD_END))
        # The ping-pong guard reads no two-cell alternation in the four-move round.
        self.assertEqual(events, [])
        # The loop detector stops the bot before any leave (live: decision 5694, the 57th
        # board after the landing, as here).
        self.assertEqual(rows[tripped], (DEAD_END[1], "4", WANDER))
        leaves = [index for index, reason in enumerate(reasons) if reason in LEAVES]
        self.assertTrue(not leaves or leaves[0] > tripped, (tripped, leaves))
        # As live from the board after the landing's Magic Mapping (5637 'mAj', no power list
        # here: the fresh policy searches one board earlier): the searches, the round and its
        # retreats up to the stop on the same board.
        live = [(d["reason"], d["key"]) for d in DECISIONS
                if LANDING_TURN <= d["turn"] and d["reason"] != "loop-detected"]
        self.assertEqual(live[0], ("me-power:new-floor:map-area", "mAj"))
        self.assertEqual(len(live), tripped + 2)
        self.assertEqual([(reason, key) for _cell, key, reason in rows[:tripped + 1]], live[1:])

    def test_the_retreat_made_no_veto_and_reset_the_stuck_count(self):
        """Every retreat up to the stop left (20,3) unvetoed (its veto would seal the pocket the
        step enters) and reset the stuck count the stuck escape waits for."""
        sealed, streaks = [], []
        seals = engagement_avoid_seal.seals

        def logged(policy, snapshot, cell, step):
            answer = seals(policy, snapshot, cell, step)
            sealed.append((policy._decision_sequence, cell, step, answer))
            return answer

        observe = HengbotPolicy._observe

        def counted(policy, snapshot, *args, **kwargs):
            result = observe(policy, snapshot, *args, **kwargs)
            streaks.append((policy._decision_sequence, policy.last_reason, policy._stuck_escape_streak))
            return result

        with mock.patch.object(engagement_avoid_seal, "seals", logged), \
                mock.patch.object(HengbotPolicy, "_observe", counted):
            rows, tripped, _events, _policy_, _raw, _directory = _walked(
                STUCK_ESCAPE_LIMIT, fixed=False, guard_cells=2, route_seal=False)
        self.assertIsNotNone(tripped)
        retreats = sum(1 for _cell, _key, reason in rows if reason == RETREAT)
        self.assertGreaterEqual(sum(1 for _cell, _key, reason in rows[:tripped + 1] if reason == RETREAT), 10)
        self.assertEqual(len(sealed), retreats)
        self.assertTrue(all(answer and (cell, step) == (DEAD_END[2], DEAD_END[1])
                            for _sequence, cell, step, answer in sealed), sealed)
        self.assertLess(max(streak for _sequence, _reason, streak in streaks), STUCK_ESCAPE_LIMIT)
        # Reset on every retreat.
        self.assertTrue(all(streak == 0 for _sequence, reason, streak in streaks if reason == RETREAT))


class SixCellGuardTest(unittest.TestCase):
    """(Read without the wander fix and so without the 2026-11-17 route-veto rung: the round under
    test is the live one.)  Owner 2026-11-15 「6マスまで広げる」 (maintainability review Q1): the ping-pong guard reads a
    round of up to six cells, the loop detector's own bound.  Without the wander's root fix the
    live round (wander 1->2, wander 2->3, retreat 3->2, wander 2->1: four moves over three
    cells) is read on its second turn, and the same round again escalates to the existing
    livelock leave, which reads Recall before the loop detector would stop the bot."""

    def test_the_three_cell_round_is_read_and_left_before_the_loop_stop(self):
        rows, tripped, events, _policy_, _raw, _directory = _walk(fixed=False)
        round_ = f"{WANDER}/{WANDER}/{RETREAT}/{WANDER}"
        self.assertEqual([event for _index, event in events],
                         [f"pingpong:{round_}", f"pingpong-escalate:{round_}"])
        first, escalated = (index for index, _event in events)
        # Read on the board after the round's second turn (the eight moves before it).
        self.assertEqual([(cell, key, reason) for cell, key, reason in rows[first - 8:first]],
                         [(DEAD_END[0], "6", WANDER), (DEAD_END[1], "6", WANDER),
                          (DEAD_END[2], "4", RETREAT), (DEAD_END[1], "4", WANDER)] * 2)
        # The escalation's board answers with the livelock leave, before the loop detector.
        self.assertEqual(rows[escalated][2], "livelock:recall-escape", rows[escalated])
        self.assertIsNotNone(tripped)
        self.assertLess(escalated, tripped)

    def test_the_two_cell_guard_reads_nothing_in_the_round(self):
        """The control of the widening: the two-cell guard reads no event (as live)."""
        _rows, _tripped, events, _policy_, _raw, _directory = _walk(fixed=False, guard_cells=2)
        self.assertEqual(events, [])


class FixedTest(nokey.PostedKey):
    """The wander keeps off the walks' veto: it never steps into the sleeper's area (11-15).
    Read without the 2026-11-17 route-veto rung, which now answers this dead end first
    (RouteVetoSealTest): the wander fix stays pinned for the boards that rung leaves to it."""

    def test_no_retreat_and_the_stuck_escape_reads_recall_before_the_loop_stop(self):
        rows, tripped, events, policy, raw, _directory = _walk(route_seal=False)
        cells = [cell for cell, _key, _reason in rows]
        reasons = [reason for _cell, _key, reason in rows]
        self.assertNotIn(DEAD_END[2], cells, rows)
        self.assertNotIn(RETREAT, reasons, rows)
        self.assertIsNone(tripped, rows)
        # The wander between (20,1) and (20,2) is the alternation the ping-pong guard reads: the
        # step back to (20,1) is refused and the wander has no step left, so the idle fallback's
        # stuck escape reads Recall (49F: the old escape, deep_teleport is 50F+).
        self.assertTrue(events and events[0][1].startswith(f"pingpong:{WANDER}/{WANDER}"), events)
        cell, key, reason = rows[-1]
        self.assertEqual((cell, reason), (DEAD_END[1], "stuck:recall-escape"), rows)
        board = parse_snapshot(copy.deepcopy(raw), MONRACE)
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(key, "r" + recall.slot)
        self.assertTrue(policy._returning_to_town)
        self.assertLess(len(rows), 40, rows)
        self.post(policy, raw, key, screens=(prompt_screen(READ_PROMPT),))

    def test_the_wander_still_steps_where_the_veto_holds_no_cell(self):
        """From (20,1) the one neighbour (20,2) is off the area: the wander takes it."""
        rows, _tripped, _events, _policy_, _raw, _directory = _walk(route_seal=False)
        self.assertIn((DEAD_END[0], "6", WANDER), rows)


class RouteVetoSealTest(nokey.PostedKey):
    """Owner 2026-11-17 (n1-c life-216) 「半径13以内なら *破壊*、無理なら溶かして抜ける」: the
    sleeper's area holds the dead end's one way on, so the route-veto rung answers on the landing
    board itself, before any search or wander.  No absorbed power list is replayed (the module
    note), so neither *Destruction* nor Stone to Mud is held and the floor's stuck escape answers:
    the 11-15 fix's end state (Recall at (20,2), 49F) without the searches and the wander."""

    def test_the_landing_board_reads_recall(self):
        rows, tripped, events, policy, raw, _directory = _walk()
        self.assertIsNone(tripped, rows)
        self.assertEqual(events, [])
        board = parse_snapshot(copy.deepcopy(raw), MONRACE)
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual(rows, [(DEAD_END[1], "r" + recall.slot, "stuck:recall-escape")])
        self.assertTrue(policy._returning_to_town)
        self.post(policy, raw, rows[-1][1], screens=(prompt_screen(READ_PROMPT),))


if __name__ == "__main__":
    unittest.main()
