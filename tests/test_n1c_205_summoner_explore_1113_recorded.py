"""n1-c (Magic-Eater) life-205 2026-11-13 04:49: loop-detected on ガラスの城 60F.

Recorded: tests/fixtures/loop-n1c-205-1113.json.gz
(tests/extract_n1c_205_summoner_explore_1113_fixture.py), the Lv42 Magic-Eater's boards from
the floor's arrival (turn 2921091) to the stop (2922761) and the recorded decision rows.

Three ノーム・メイジ (race 281, summoners, not NEVER_MOVE) stand in a pocket of glass floor
walled with glass (GLASS_WALL, terrain 218: LOS without PROJECTION, TerrainDefinitions.jsonc).
The player sees them through the glass; projectable() stops every bolt on a grid without
PROJECTION (projection-path-calculator.cpp:94).  They did not come to the choke (19,31) and
were remembered as summoners that never approach (summoner_wait's expired wait), their line of
fire a zone vetoed for every route.

A (04:48:54-57): from (29,38) the three were in view and the immobile summoner owner stepped
'9' out of the zone to (28,39); there telepathy sensed two of them (the third, asleep, out of
range), immobile_ranged_kill read them as killable from a shooting cell in the pocket, the zone
was withdrawn and the exploration stepped '1' back into (29,38), eight times up to the
oscillation break.  That ranged kill is carried out only for a never-moving monster
(``immobile_ranged_kill.key``, owner 2026-11-02); a summoner that moves now keeps its zone.

Every decision is the public ``choose_key`` of one policy built as the live one
(tests.support.recorded._policy) and driven over the recorded boards from turn 2921424
(the floor's second detection, before the mages were first seen).
DECLARED RESTORED (policy-state.json of the stop): the staff record ``_me_staff_sequence``, the
absorbed powers' uses on the floor before 2921424 (``_me_power_floor``) and the floor's
*Destruction* entitlement (the arrival's absorbed *Destruction*, 2921097).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import destruction_use, me_powers
from hengbot import me_staff_sequence as sequence
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DIRECTION_KEYS
from tests.support.recorded import EDIT, _policy


FIXTURE = Path(__file__).with_name("fixtures") / "loop-n1c-205-1113.json.gz"
START, FLOOR = 2921424, (20, 60, 0)
FIRST_ZONE_STEP = 2922364       # the first '9' out of the zone at (29, 38)
TELEPORT_TURN = 2922547         # the first 'mCn4' at (34, 40)
INSIDE, OUTSIDE = Position(29, 38), Position(28, 39)
MAGES = (Position(34, 22), Position(35, 22))
TELEPORT_AWAY = "me-power:unbeatable-in-range:teleport-away"
OFFSETS = {key: offset for offset, key in DIRECTION_KEYS.items()}


def _restore(policy, case):
    record = sequence.state(policy)
    for name, value in case["sequence"].items():
        setattr(record, name, frozenset(value) if name == "bought"
                else tuple(value) if name == "remaining" else value)
    destruction_use._memory(policy).entitled_floor = FLOOR
    floor = case["me_power_floor"]
    policy._me_power_floor = me_powers.FloorMemory(tuple(floor["floor"]), START, [
        me_powers.Use(tuple(use["served"]), tuple(use["used"]), use["trigger"],
                      Position(*use["position"]), use["turn"], use["reason"], use["key"],
                      None if use["target"] is None else Position(*use["target"]))
        for use in floor["uses"] if use["turn"] < START])


def _skill(case, raw):
    skill = case["skill"]
    return dict(copy.deepcopy(skill), turn=raw["turn"],
                player=dict(skill["player"], level=raw["player"]["level"]))


class SummonerZoneGlassRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.case = json.load(stream)
        races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        directory = TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), races)
        boards = [raw for raw in cls.case["boards"] if START <= raw["turn"] <= TELEPORT_TURN]
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), races))
        _restore(policy, cls.case)
        policy.consume_skill_knowledge(_skill(cls.case, boards[0]))
        cls.rows = []
        for raw in boards:
            board = parse_snapshot(copy.deepcopy(raw), races)
            key = str(policy.choose_key(board))
            if key.startswith("~f"):  # the recorded skill list answers the re-request
                policy.consume_skill_knowledge(_skill(cls.case, raw))
                key = str(policy.choose_key(board))
            remembered = dict(getattr(policy, "_immobile_summoner_memory", (None, {}))[1])
            cls.rows.append((raw, board, key, policy.last_reason, remembered,
                             frozenset(policy._immobile_summoner_avoid_cells),
                             frozenset(policy._engagement_avoid_cells)))
            if key:
                policy.confirm_key_posted(key)
        cls.policy = policy

    def test_recorded_rows(self):
        recorded = {row["turn"]: (row["reason"], row["key"]) for row in self.case["decisions"]}
        boards = {raw["turn"]: raw for raw in self.case["boards"]}
        here = {turn: Position(raw["player"]["y"], raw["player"]["x"])
                for turn, raw in boards.items()}
        pairs = {(here[turn], recorded[turn]) for turn in recorded
                 if FIRST_ZONE_STEP <= turn < 2922501 and recorded[turn][0] != "search"}
        self.assertEqual(pairs, {(INSIDE, ("explore:avoid-immobile-summoner", "9")),
                                 (OUTSIDE, ("explore", "1")),
                                 (OUTSIDE, ("breakout:seek-frontier", "1"))})
        teleports = [(row["reason"], row["key"]) for row in self.case["decisions"]
                     if row["turn"] >= TELEPORT_TURN]
        self.assertEqual(teleports.count((TELEPORT_AWAY, "mCn4")), 4)
        self.assertEqual(teleports.count((TELEPORT_AWAY, "mBd4")), 31)
        # The live stop stood in command mode with no prompt, one turn past the last use.
        self.assertEqual(self.case["stop"], {"input_kind": "command", "input_prompt": "",
                                             "turn": 2922765})
        for turn in (2922364, 2922547):
            raw = boards[turn]
            self.assertEqual({(m["y"], m["x"]) for m in raw["visible_monsters"]
                              if m["race_id"] == 281} >= {(p.y, p.x) for p in MAGES}, True)

    def test_the_zone_outside_keeps_the_mages_and_the_cell_left(self):
        checked = 0
        for raw, board, key, reason, remembered, zone, vetoed in self.rows:
            here = board.player.position
            if raw["turn"] <= FIRST_ZONE_STEP or here != OUTSIDE or raw["turn"] >= 2922501:
                continue
            checked += 1
            # The two sensed mages stay remembered; the cell the zone step left stays vetoed.
            self.assertTrue(set(MAGES) <= set(remembered), raw["turn"])
            self.assertIn(INSIDE, zone, raw["turn"])
            self.assertIn(INSIDE, vetoed, raw["turn"])
            offset = OFFSETS.get(key)
            if offset is not None:
                target = Position(here.y + offset[0], here.x + offset[1])
                self.assertNotIn(target, zone, (raw["turn"], key, reason))
        self.assertGreaterEqual(checked, 15)


if __name__ == "__main__":
    unittest.main()
