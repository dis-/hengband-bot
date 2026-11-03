"""The dungeon-family loop-detected stops of the 2026-11-03 night (build 91357d2d0).

Every board is decided through the public choose_key on the recorded boards;
a step is posted through the production executor.  Nothing but the marked
seeds is constructed.  Fixtures: tests/extract_dungeon_stops_1103_fixtures.py.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.town_arrival_checkpoint import JOURNAL_FILE, POLICY_FILE
from replay_town_arrival import decisions, journal, restore
from tests import test_lv7_town_stop_recorded as lv7
import tests.test_input_executor as executor_harness
from tests.test_esp_threat_rest_recorded import EDIT, _policy


FIXTURES = Path(__file__).with_name("fixtures") / "dungeon-stops-1103"


def fixture(name: str) -> dict:
    return json.loads(lzma.decompress((FIXTURES / name).read_bytes()))


class RecordedBoards(executor_harness.ProductionHarness):
    shelf_screen = staticmethod(lv7.Lv7TownStopRecordedTest.shelf_screen)
    post = lv7.Lv7TownStopRecordedTest.post

    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def fresh_policy(self, first_board: dict, terrain: dict | None = None):
        directory = Path(self.enterContext(TemporaryDirectory()))
        policy = _policy(directory, self.monrace)
        policy.prime(parse_snapshot(copy.deepcopy(first_board), policy._monrace_knowledge))
        # The captured process already held the skill list.
        policy.consume_skill_knowledge({
            "player": {"level": first_board["player"]["level"]},
            "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
        })
        if terrain is not None:
            for name in ("known", "marked", "floor", "wall", "door", "rubble"):
                getattr(policy, f"_remembered_{name}_t").update(
                    tuple(cell) for cell in terrain[f"{name}_t"])
            policy._remembered_upstairs.update(Position(*cell) for cell in terrain["upstairs"])
            policy._remembered_downstairs.update(Position(*cell) for cell in terrain["downstairs"])
        return policy

    @staticmethod
    def decide(policy, raw: dict):
        return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))


class TownAdjacentMeleeUnderErrandHold(RecordedBoards):
    """n1-c life-123, 2026-11-03 22:44 (no-wait:flee <-> town:kill-mob-approach).

    A 貧しげな傭兵 (5d8, one 1d10 blow) met a Lv18 character with three blows
    of a (+4,+13) pike while the home errand held the town.  Beside it,
    _town_kill_mob_key delegated to the ordinary melee rung, whose combat
    family the errand hold refused (_town_producer_entry asked
    _town_gate_exempt with the family alone); nothing answered, the idle WAIT
    was rewritten into no-wait:escape-scroll (all 15 Teleport scrolls were
    read over the visit), then into no-wait:flee, and at distance 2 the hunt
    walked back.  1 500 decisions later the loop guard stopped the bot.
    Decision row 21 is the first adjacent board of the visit.
    """

    ADJACENT_ROW = 21

    def test_first_adjacent_board_is_fought(self):
        with TemporaryDirectory() as raw:
            visit = Path(raw) / "town-arrival"
            visit.mkdir()
            (visit / POLICY_FILE).write_bytes(
                lzma.decompress((FIXTURES / "town-melee-policy.pkl.xz").read_bytes()))
            (visit / JOURNAL_FILE).write_bytes(gzip.compress(
                lzma.decompress((FIXTURES / "town-melee-journal.jsonl.xz").read_bytes())))
            rows = journal(visit)
            # 91357d2d0 read a Teleport scroll here.
            self.assertEqual((rows[self.ADJACENT_ROW]["key"], rows[self.ADJACENT_ROW]["reason"]),
                             ("rf", "no-wait:escape-scroll"))
            scratch = Path(raw) / "scratch"
            scratch.mkdir()
            policy = restore(visit, scratch)
            for row, (recorded, supply) in enumerate(decisions(policy, visit, scratch)):
                board = supply()
                key = policy.choose_key(board)
                if row == self.ADJACENT_ROW:
                    break
                self.assertEqual((key, policy.last_reason),
                                 (recorded["key"], recorded["reason"]))
                policy.confirm_key_posted(key)
        monster = next(iter(board.visible_monsters))
        self.assertEqual(monster.name, "貧しげな傭兵")
        self.assertEqual(board.player.position.distance_to(monster.position), 1)
        self.assertEqual((key, policy.last_reason), ("2", "melee"))
        self.post(policy, json.loads(rows[self.ADJACENT_ROW]["line"]), key,
                  json.loads(rows[self.ADJACENT_ROW + 1]["line"]))



class GivenUpDoorOnTheCommittedDescentRoute(RecordedBoards):
    """n1-c life-123, 2026-11-03 22:07 (approach-descent 'o4' repeated).

    The committed descent route ran through a locked door.  DOOR_OPEN_LIMIT
    gave the door up after three picks, but the committed path's step test
    (_is_step_open) still read a closed door as open, unlike rubble, so the
    route kept picking it ("鍵をはずせなかった。") until the loop guard.
    Fresh policy, stop's remembered terrain (DECLARED RECONSTRUCTED).
    """

    def test_door_is_given_up_after_its_limit(self):
        case = fixture("descent-door.json.xz")
        self.assertEqual(
            {(row["key"], row["reason"]) for row in case["rows"][4:]},
            {("o4", "approach-descent")})
        policy = self.fresh_policy(case["boards"][0], case["terrain"])
        at_door = [(raw, row) for raw, row in zip(case["boards"], case["rows"])
                   if (row["position"]["y"], row["position"]["x"]) == (30, 90)]
        keys = [self.decide(policy, raw) for raw, _row in at_door[:4]]
        self.assertEqual(keys[:3], ["o4", "o4", "o4"])
        self.assertIn((30, 89), policy._blocked_doors)
        self.assertNotEqual(keys[3], "o4")
        self.assertFalse(policy._nav_ledger.descent_path
                         and policy._nav_ledger.descent_path[0] == Position(30, 89))
        retry = self.fresh_policy(case["boards"][0], case["terrain"])
        key = self.decide(retry, at_door[0][0])
        self.post(retry, at_door[0][0], key, at_door[1][0])




if __name__ == "__main__":
    unittest.main()
