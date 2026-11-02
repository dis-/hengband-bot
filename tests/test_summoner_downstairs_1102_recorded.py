"""An avoided immobile summoner's floor is left by its downstairs first.

Owner 2026-11-02 (choice 「下り階段を先に使う」): leaving a floor to avoid an
immobile summoner, prefer a downstairs reachable outside its line of fire,
then upstairs, Teleport Level, Recall; while avoiding, leave by the normal
floor rules instead of exploring the whole floor first.

Recorded (tests/fixtures/summoner-downstairs-1102.json.gz,
tests/extract_summoner_downstairs_1102_fixture.py): n1-c life-103 on
Angband 23F saw a クイルスルグ (race 342, NEVER_MOVE) at (36,192) on turn
3693780 (13:09:33); the immobile-summoner owner then took every decision as
``explore:avoid-immobile-summoner`` (these 31 boards, and 209 decisions in
all) and read Recall after exploring the floor.  No downstairs was known on
the floor.  Now the ordinary floor rules play outside the summoner's zone
(``explore`` towards an unknown downstairs on these boards).  DECLARED
CONSTRUCTED on the first recorded board: a downstairs at (35,191), the one
cell of the zone, is not a descent target; with a second downstairs at
(36,169), outside the zone, the ordinary descent walks to that one.

Owner 2026-11-02 「遠距離で安全に倒せるなら倒す方を優先する」
(immobile-weak-kill-1102): with its 99 bolts the player kills the 48-HP
quylthulg within the three-shot rule, so the first recorded board now walks
to a cell that shoots it (immobile_ranged_kill).  The avoidance boards below
are DECLARED CONSTRUCTED without the bolts, where it is still avoided.

Every decision is the public ``choose_key`` on the recorded boards in turn
order.  DECLARED RECONSTRUCTED: the Magic-Eater power uses of this floor
visit before the ring begins (``floor_powers``, the timeline's rows from the
12:59:14 arrival) are the policy's floor memory, as the live bot held it;
each board carries the recorded previous operation's completion.  Posted
keys go through the production executor.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot import me_powers
from hengbot.model import Position, parse_snapshot
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_summoner_avoid_narrow_1102_recorded import AVOID


FIXTURE = Path(__file__).with_name("fixtures") / "summoner-downstairs-1102.json.gz"
with gzip.open(FIXTURE, "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
FLOOR = (3, 23, 0)
QUYLTHULG, QUYLTHULG_CELL = 342, Position(36, 192)
FIRST_TURN = 3693780
ZONE_STAIRS, OUTSIDE_STAIRS = Position(35, 191), Position(36, 169)


def floor_memory():
    """The recorded power uses of the floor visit (DECLARED RECONSTRUCTED)."""
    memory = me_powers.FloorMemory(FLOOR, CASE["floor_powers"][-1]["turn"])
    for row in CASE["floor_powers"]:
        _, trigger, effect = row["reason"].split(":")[:3]
        used = next(power for power in me_powers.POWERS if power.effect == effect)
        served = used if trigger in used.triggers else next(
            power for power in me_powers.POWERS
            if used.ident in power.preferred and trigger in power.triggers)
        memory.uses.append(me_powers.Use(
            served.ident, used.ident, trigger,
            Position(row["position"]["y"], row["position"]["x"]),
            row["turn"], row["reason"], row["key"]))
    return memory


BOLTS = 18


def decision_boards(*, bolts=False):
    rows = {row["turn"]: row for row in CASE["decisions"]}
    previous = None
    for raw in sorted(CASE["boards"], key=lambda board: board["turn"]):
        raw = copy.deepcopy(raw)
        if not bolts:  # DECLARED CONSTRUCTED: no safe ranged kill (module docstring)
            raw["inventory"] = [item for item in raw["inventory"] if item.get("tval") != BOLTS]
        if previous is not None:
            raw["_completed_operation_sequence"] = previous["decision_sequence"]
            raw["_completed_operation_owner"] = previous["reason"]
        previous = rows[raw["turn"]]
        yield raw, previous


def new_policy():
    policy = d57.new_policy(CASE)
    setattr(policy, me_powers.MEMORY, floor_memory())
    return policy


def with_downstairs(board, *cells):
    grids = dict(board.grids)
    for cell in cells:  # DECLARED CONSTRUCTED
        grids[cell] = replace(grids[cell], has_down_stairs=True)
    return replace(board, grids=grids)


class SummonerDownstairsRecordedTest(d57.PostedDeathKey):

    def test_recorded_board_shoots_the_killable_summoner(self):
        raw, _recorded = next(decision_boards(bolts=True))
        policy = new_policy()
        key = d57.loops.decide(policy, raw)
        self.assertEqual(policy.last_reason, "immobile-threat:approach-to-shoot")
        self.assertEqual(policy._immobile_summoner_memory[1], {})
        self.post(policy, raw, key)

    def test_recorded_avoidance_leaves_by_the_floor_rules(self):
        self.assertEqual({row["reason"] for row in CASE["decisions"]}, {AVOID})
        policy, rows = new_policy(), []
        for raw, recorded in decision_boards():
            key = d57.loops.decide(policy, raw)
            rows.append((raw["turn"], key, policy.last_reason))
            policy.confirm_key_posted(key)
        self.assertEqual(policy._immobile_summoner_memory[1], {QUYLTHULG_CELL: QUYLTHULG})
        self.assertEqual({reason for _turn, _key, reason in rows}, {"explore"})

        first, _recorded = next(decision_boards())
        for cells, expected in (((ZONE_STAIRS,), ("explore", None)),
                                ((ZONE_STAIRS, OUTSIDE_STAIRS), ("seek-downstairs", OUTSIDE_STAIRS))):
            policy = new_policy()
            board = with_downstairs(parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge),
                                    *cells)
            key = policy.choose_key(board)
            self.assertEqual(policy._immobile_summoner_avoid_cells, {ZONE_STAIRS})
            self.assertEqual((policy.last_reason, policy._descent_target_goal), expected)
        self.assertEqual(key, "4")
        self.post(policy, first, key)


if __name__ == "__main__":
    unittest.main()
