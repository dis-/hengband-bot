"""n1-b life-370, Angband 80F, 2026-11-12 00:50: Stone to Mud aimed at walls already melted.

The Magic-Eater held a choke against a sensed threat at (3,16) (37 detected:hold-choke), used its
absorbed *Destruction* when the threat came into view (decision 34628), mapped the circle
(34629, 周辺感知) and stood in a pocket of rock.  The Stone to Mud rule (owner 2026-11-05
「*破壊*後全方位壁なら岩石溶解で脱出すれば良い」) then aimed its wand (168 charges) along six lines
from (3,16) and (4,15): 38 uses, every one 「…が溶けて泥になった！」, and the player never walked;
the loop guard stopped it at 34667.

Why: a wall melted out of the player's view becomes floor that the game does not remember
(cave_alter_feat; floor has no REMEMBER), so the board stops showing the grid, while the bot's
grid memory kept the wall.  sealed_pocket aimed again at the remembered wall, the beam crossed
it and melted the next wall of the line, and each line was dropped only after
me_powers.FAILURES_PER_PLACE (5) uses at one remembered wall.  The fix drops the remembered wall
the melt message names (sealed_pocket.forget_melted_wall, before the grid memory's merge).

Recorded (tests/extract_stm_livelock_1112_fixture.py): every state row of the floor from its
arrival (turn 8674881) to the board after the sixth use (8675192), delivered through the CLI's
response consumption (``_consume_response_sequence``) and every board decided through the public
``choose_key`` of one fresh policy (``confirm_key_posted`` after each key), as the driver does;
the live decision rows of the floor.

DECLARED RECONSTRUCTION / RESTORED: the skill knowledge is supplied before each decision (the
capture holds no ~f reply; tests/test_deaths_1109_recorded's ``skill``); the absorbed device lists
the game last displayed (the incident's town-arrival checkpoint ``_me_device_lists``) are shown to
``observe_lists`` before the first board, as the executor's menu reading would.
DECLARED CONSTRUCTED: in the failed-use test, the board after the third use shown again with
later game turns and the game's failure message 「魔法棒をうまく使えなかった。」 in place of the melt.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import sealed_pocket
from hengbot.cli import _consume_response_sequence
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.me_device_attacks import observe_lists
from hengbot.me_powers import FAILURES_PER_PLACE
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support.recorded import EDIT
from tests.test_deaths_1109_recorded import skill

FIXTURE = Path(__file__).with_name("fixtures") / "stm-livelock-1112.json.xz"
DESTRUCTION_TURN, MAPPED_TURN = 8675158, 8675163
FIRST_USE_TURN = 8675166
OUT_OF_VIEW_MELT_TURN = 8675179  # the board after the third use: (10,9) melted out of view
LAST_BOARD_TURN = 8675192        # the board after the sixth use
POCKET = Position(3, 16)
STM = "livelock:stone-to-mud"
FAILED_USE = "魔法棒をうまく使えなかった。"


class StoneToMudLivelockRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def recorded(self) -> dict:
        """turn -> (reason, key) of the live decision rows (the last row of a turn)."""
        return {turn: (reason, key) for _sequence, turn, reason, key in self.payload["decisions"]}

    def fresh_policy(self):
        rows = self.payload["rows"]
        first = next(row for row in rows if row.get("type") == "player_turn")
        policy = HengbotPolicy(monrace_knowledge=dict(self.races), dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(first), self.races))
        # RESTORED: the displayed lists, oldest first.
        for kind, (turn, lines) in sorted(self.payload["lists"].items(), key=lambda entry: entry[1][0]):
            shown = dict(copy.deepcopy(first), turn=turn,
                         _magic_eater_power_list={"kind": kind, "rows": lines})
            observe_lists(policy, parse_snapshot(shown, self.races))
        return policy

    def deliver(self, policy, raw):
        line = json.dumps(raw, ensure_ascii=False) + "\n"
        _consume_response_sequence([line], policy, lambda _key: True, self.races,
                                   parse_snapshots=False,
                                   knowledge_ledger_path=self.root / "knowledge.jsonl")

    def decide(self, policy, raw, previous):
        raw = copy.deepcopy(raw)
        if previous is not None:
            raw["_completed_operation_owner"] = previous
        skill(policy, raw)
        key = policy.choose_key(parse_snapshot(raw, self.races))
        if key:
            policy.confirm_key_posted(key)
        return str(key), policy.last_reason

    def replay(self, until=LAST_BOARD_TURN):
        """(policy, {turn: (key, reason)}) of every recorded board up to ``until``."""
        policy, answers, previous = self.fresh_policy(), {}, None
        for raw in self.payload["rows"]:
            if raw["turn"] > until:
                break
            raw = copy.deepcopy(raw)
            self.deliver(policy, raw)
            if raw.get("type") != "player_turn":
                continue
            answers[raw["turn"]] = self.decide(policy, raw, previous)
            previous = answers[raw["turn"]][1]
        return policy, answers

    def board(self, turn):
        return copy.deepcopy(next(row for row in self.payload["rows"]
                                  if row["turn"] == turn and row.get("type") == "player_turn"))

    def test_the_recorded_pocket_is_entered_as_live(self):
        """The fresh replay reaches the pocket as the live process did: the choke held, the
        *Destruction*, its map and the first uses of the wand along line 1 (south-west)."""
        recorded = self.recorded()
        _policy, answers = self.replay(OUT_OF_VIEW_MELT_TURN)
        self.assertEqual(answers[DESTRUCTION_TURN], ("mA3", "emergency:destruction:absorbed-power"))
        self.assertEqual(recorded[DESTRUCTION_TURN], ("emergency:destruction:absorbed-power", "mA3"))
        self.assertEqual(answers[MAPPED_TURN], ("mAj", "me-power:after-destruction:map-area"))
        for turn in (FIRST_USE_TURN, 8675171, 8675176, OUT_OF_VIEW_MELT_TURN):
            self.assertEqual(answers[turn], ("ah1", STM), turn)
            self.assertEqual(recorded[turn], (STM, "ah1"), turn)

    def test_a_wall_melted_out_of_view_leaves_the_grid_memory(self):
        """Live: the third use melted (10,9) out of view (「溶岩の鉱脈が溶けて泥になった！」) and the
        next four uses aimed at its remembered wall again, each melting the next wall of the line.
        The melted wall leaves the memory, so the next use names the next wall, (11,8)."""
        policy, _answers = self.replay(8675176)
        self.assertEqual(policy._remembered_grids[Position(10, 9)].passable, False)
        raw = self.board(OUT_OF_VIEW_MELT_TURN)
        self.assertTrue(any("溶けて泥になった" in message for message in raw["messages"]))
        shown = parse_snapshot(copy.deepcopy(raw), self.races).grid_at(Position(10, 9))
        self.assertTrue(shown is None or not shown.known)  # the game forgot the melted grid
        self.deliver(policy, raw)
        self.assertEqual(self.decide(policy, raw, policy.last_reason), ("ah1", STM))
        self.assertNotIn(Position(10, 9), policy._remembered_grids)
        uses = getattr(policy, sealed_pocket.MEMORY).uses
        self.assertEqual(uses[(10, 9)], 1)
        self.assertEqual(uses[(11, 8)], 1)

    def test_no_line_is_aimed_twice_at_a_melted_wall_and_the_opened_pocket_is_walked(self):
        """Live: 'ah1' at the remembered (10,9) for the fifth time on 8675192, then lines 3, 2
        and 6 five uses each, 'ah3'/'ah2' from (4,15), and the loop stop.  Each use now aims at
        a wall still standing, and once the line reaches ground that leads on the pocket is no
        longer sealed: the next decision is not another use."""
        recorded = self.recorded()
        self.assertEqual(recorded[LAST_BOARD_TURN], (STM, "ah1"))
        self.assertEqual(sum(row[2] == STM for row in self.payload["decisions"]), 38)
        self.assertEqual(self.payload["decisions"][-1][2], "loop-detected")
        policy, answers = self.replay()
        uses = getattr(policy, sealed_pocket.MEMORY).uses
        self.assertEqual(max(uses.values()), 1, dict(uses))
        self.assertNotEqual(answers[LAST_BOARD_TURN][1], STM, answers[LAST_BOARD_TURN])
        self.assertIsNone(sealed_pocket.sealed_region(
            policy, policy._with_grid_memory(parse_snapshot(self.board(LAST_BOARD_TURN), self.races))))

    def test_a_failed_use_keeps_the_wall_and_the_line_is_left_after_the_failures(self):
        """No melt message, nothing melted: the remembered wall stays, and after
        FAILURES_PER_PLACE uses at it its line is not aimed at again."""
        policy, answers = self.replay(8675176)
        self.assertEqual(answers[8675176], ("ah1", STM))
        raw = self.board(8675176)
        keys = []
        for step in range(FAILURES_PER_PLACE + 1):
            # DECLARED CONSTRUCTED: the same board later, the use failed.
            later = dict(copy.deepcopy(raw), turn=raw["turn"] + 3 * (step + 1), messages=[FAILED_USE])
            self.deliver(policy, later)
            keys.append(self.decide(policy, later, policy.last_reason))
            self.assertIn(Position(10, 9), policy._remembered_grids)
        uses = getattr(policy, sealed_pocket.MEMORY).uses
        self.assertEqual(uses[(10, 9)], FAILURES_PER_PLACE)
        self.assertEqual(keys[:FAILURES_PER_PLACE - 1], [("ah1", STM)] * (FAILURES_PER_PLACE - 1))
        self.assertNotEqual(keys[-1], ("ah1", STM))


if __name__ == "__main__":
    unittest.main()
