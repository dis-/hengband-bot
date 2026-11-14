"""Quest 25 on n1-b life-382 (2026-11-13 05:38-05:39): the tome phase and the KILL_ALL patrol, recorded.

The chain (bot-decisions of ~/hengbot-soak/n1-b/life-382/captures/20261113-053907-loop-detected,
build main 784d60f71; battle phase 5, the tome, record ``q25-battle.json``):

 * 05:38:34-05:38:46 (decisions 5837-5938): ``quest25:walk-to-sight`` reached every cell that sees
   the tome's grid [9,8] and never saw it (``blind_sights``); it walked over [9,8] itself (5907).  The tome
   never moves and resists teleportation (MonraceDefinitions 557): it was not on the floor.
 * 5939-6028: the phase still counted it alive (no kill of it counted), walked to the near stand
   [5,5] and shot the empty grid 85 times (``ranged:magic-eater-device`` '...@9,8').
 * 6029: every grid-aimed attack spent, the phase had no step; the navigator asked the KILL_ALL
   patrol (kill_all_patrol, merged 881723336), which cast the Rod of Detection -- two quylthulgs
   (480) far east, no tome -- and walked.
 * 6035-6081 and, after the restart, decisions 4-48: on [4,8] and [7,6] (a bolt-or-beam's ray to
   [9,8]) the phase answered again ('4', '8' ``quest25:walk`` toward its near stands), on the next
   cell [4,7] / [6,6] nothing, and the patrol walked back ('6', '2'); the loop guard stopped the
   bot at 05:39:04 and 05:39:14.

Two roots, two rules:

 * Ownership (kill_all_patrol ``_plan_running``): a plan with a phase still running owns every move
   of its floor; the patrol starts only when the plan has ended (owner 2026-11-13 「全滅クエストで作戦を
   完了しても終了しない場合、周回して敵を探す」), for Q25 from its own ``_after_the_phases``.
 * The plan's count (quest25_battle ``_immobile_gone``): every cell that sees the never-moving tome's
   grid reached with it unseen, it is not there (as the pen's ``_pen_sight`` counts the
   Ipsissimus escaped); the tome phase ends, kept over the phases and the record.

Recorded: tests/fixtures/n1b-382-q25-patrol-owner-1113.json.gz
(tests/extract_n1b_382_q25_patrol_owner_1113_fixture.py, copies of the captures in
C:\\hengband-backups\\pdca\\captures\\n1b-382-q25-patrol-1113): both processes' boards and the battle
record.  A fresh policy restores the record through the real path and decides the restarted
process's boards through the public ``choose_key``; each key is posted through the production
executor (``_ExecutorInputPort``), the game then showing the next recorded board.

DECLARED: the record is the one the last process left (05:39:14), its turn set to the first board's.
The boards carry no magic-eater lists: they are the 01:33 dump's powers of
tests/fixtures/n1b-378-q25-spent-balls-1113.json.gz, with every charge full or with the area
attacks spent, as each test says (``kill_all_patrol_test.lists``).  The restart's periodic reads
(decisions 0-3) are not issued by this harness.  The recorded boards are the player's recorded
cells, not where the replayed keys lead.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import kill_all_patrol, quest25_battle as battle, quest25_battle_record
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.model import parse_snapshot
from tests import test_kill_all_patrol_1113_recorded as kill_all_patrol_test
from tests.support import q25_house as q25
from tests.support import recorded as harness
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-382-q25-patrol-owner-1113.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

PATROL = {kill_all_patrol.WALK_REASON, kill_all_patrol.HUNT_REASON, kill_all_patrol.DETECT_REASON,
          kill_all_patrol.ABSORBED_DETECT_REASON}
TOME, TOME_CELL = battle.geo.TOME, (9, 8)
# The recorded walks one way and the other: the plan's step on one cell, the patrol's on the next.
OPPOSITE = {(7, 6): "8", (6, 6): "2", (4, 8): "4", (4, 7): "6"}
BLOCKED = "quest:blocked:execute"
# input/input-alloc.cpp do_cmd_rest's prompt (Japanese build).
REST_PROMPT = "休憩 (0-9999, '*' で HP/MP全快, '&' で必要なだけ): "
DECIDED = 45   # the restarted process's boards 4-48


def _shown(key) -> bool:
    """A key whose game screens this harness shows: a step, a list read, the counted rest, a wait
    (a power's prompts are not recorded here)."""
    return key in "12346789" or key in ("bA", "bB", "bC", battle.RECHARGE_REST_KEY, "5")


def new_policy(directory: Path, device_lists, record=None, case=None):
    """A fresh policy restoring ``record`` (else the case's) through the real path; ``case``: a
    fixture cut like this module's (default this module's)."""
    case = CASE if case is None else case
    boards = case["second"]["boards"]
    record = dict(record or case["battle_record"], turn=boards[0]["turn"])   # DECLARED (module note)
    (directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy._q25_battle_record_path = directory / "q25-battle.json"
    policy._warning_cell_record_path = directory / "warning-cells.json"
    first = copy.deepcopy(boards[0])
    policy.prime(parse_snapshot(first, policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(case["skill"]), turn=first["turn"],
        player=dict(case["skill"]["player"], level=first["player"]["level"])))
    policy._me_device_lists = device_lists
    return policy


def _rest_prompt():
    screen = harness.prompt_screen(REST_PROMPT)
    screen["cursor"]["visible"] = True
    screen["input_context"] = {"kind": "quantity", "prompt": REST_PROMPT}
    return screen


class _Replay(harness.ProductionHarness):
    case = CASE   # the fixture replayed (tests/test_n1b_384_q25_walk_sight_1113_recorded reuses this)

    def post(self, policy, raw, key, following):
        """``key`` through the production executor; the game then shows ``following``."""
        game = harness.FaithfulHookGame()
        game.capacity = 256
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        prompts = [_rest_prompt()] if key == battle.RECHARGE_REST_KEY else []
        if key == "mCg":
            # DECLARED CONSTRUCTED: the absorbed detection's owner (kill_all_patrol
            # ABSORBED_DETECT_REASON) answers the kind question and the rod list
            # (cmd-magiceat.cpp), as tests/test_n1c_208_q25_patrol_1115_recorded builds them.
            prompts = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                       power_screen("rod", [("g", "全感知", 0, 1, 5)])]
        game.screens = [*prompts, harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        policy.confirm_key_posted(key)

    def drive(self, device_lists, record=None):
        """[(sequence, cell, key, reason, phase)] of the restarted process's boards 4-48, to the
        first key whose prompts the recording does not hold (``_shown``)."""
        boards, recorded = self.case["second"]["boards"], self.case["second"]["recorded"]
        answers = []
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), device_lists, record, self.case)
            for index in range(4, len(boards)):
                raw = boards[index]
                snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
                key = policy.choose_key(snapshot)
                self.assertIsNotNone(key, recorded[index]["sequence"])
                answers.append((recorded[index]["sequence"],
                                (snapshot.player.position.y, snapshot.player.position.x),
                                key, policy.last_reason, policy._quest_navigators[25].phase_battle.phase))
                if not _shown(key):
                    break
                self.post(policy, raw, key, boards[min(index + 1, len(boards) - 1)])
        return answers

    def assert_one_owner(self, answers):
        """Every board decided and posted; no patrol move while a phase runs, and no walk one way
        then back on the recorded pairs."""
        self.assertEqual(len(answers), DECIDED, answers[-1])
        for sequence, cell, key, reason, phase in answers:
            self.assertNotIn(reason, PATROL, (sequence, cell, key, reason, phase))
        walks = {(cell, key) for _sequence, cell, key, reason, _phase in answers
                 if reason in PATROL | {battle.WALK_REASON}}
        for here, there in (((6, 6), (7, 6)), ((4, 7), (4, 8))):
            self.assertFalse({(here, OPPOSITE[here]), (there, OPPOSITE[there])} <= walks, walks)


class TheRecordingTest(unittest.TestCase):

    def test_the_two_owners_alternated(self):
        for part in ("first", "second"):
            rows = [(tuple((board["player"]["y"], board["player"]["x"])), row["key"], row["reason"])
                    for board, row in zip(CASE[part]["boards"], CASE[part]["recorded"])]
            seen = set(rows)
            self.assertIn(((7, 6), "8", battle.WALK_REASON), seen, part)
            self.assertIn(((6, 6), "2", kill_all_patrol.WALK_REASON), seen, part)
            self.assertIn(((4, 8), "4", battle.WALK_REASON), seen, part)
            self.assertIn(((4, 7), "6", kill_all_patrol.WALK_REASON), seen, part)
        self.assertEqual(CASE["battle_record"]["battle"]["phase"], battle.phase_index("tome"))
        self.assertEqual(CASE["battle_record"]["battle"]["kills"], {"dict": []})

    def test_the_tome_was_not_on_its_grid(self):
        # Every cell that sees [9,8] was reached with the tome unseen (the record), and the Rod of
        # Detection the patrol cast (6029; the restart's 5) showed two quylthulgs and no tome.
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), kill_all_patrol_test.lists())
            raw = CASE["second"]["boards"][4]
            ctx = battle._ctx(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            sights = battle.geo.sight_cells(ctx.open_terrain(), TOME_CELL,
                                            battle._sight_radius(ctx, TOME_CELL))
        pairs = quest25_battle_record._decode(CASE["battle_record"]["battle"]["blind_sights"])
        reached = {cell for aimed, cell in pairs if aimed == TOME_CELL}
        self.assertTrue(sights)
        self.assertLessEqual(sights, reached)
        for part, sequence in (("first", 6030), ("second", 6)):
            board = next(board for board, row in zip(CASE[part]["boards"], CASE[part]["recorded"])
                         if row["sequence"] == sequence)
            races = {monster["race_id"] for monster in board["detected_monsters"]}
            self.assertEqual(races, {battle.geo.QUYL}, part)


class PlanOwnsItsFloorTest(_Replay):

    def test_charged_the_tome_phase_ends_and_the_plan_walks_on(self):
        answers = self.drive(kill_all_patrol_test.lists())
        self.assertTrue(all(phase > battle.phase_index("tome") for *_rest, phase in answers), answers)
        self.assertFalse([row for row in answers if row[2].endswith("@%d,%d" % TOME_CELL)])
        self.assert_one_owner(answers)
        by_cell = {cell: (key, reason) for _sequence, cell, key, reason, _phase in answers}
        # The plan's walk on to the corpse masses: one way on both cells of each recorded pair.
        self.assertEqual(by_cell[(7, 6)], ("8", battle.WALK_REASON))
        self.assertEqual(by_cell[(6, 6)], ("7", battle.WALK_REASON))
        self.assertEqual(by_cell[(4, 8)], ("4", battle.WALK_REASON))
        self.assertEqual(by_cell[(4, 7)], ("4", battle.WALK_REASON))

    def test_spent_the_plan_rests_between_the_phases_never_blocked(self):
        answers = self.drive(kill_all_patrol_test.lists(spent=True))
        reasons = {reason for _sequence, _cell, _key, reason, _phase in answers}
        self.assertNotIn(BLOCKED, reasons)
        self.assertTrue(all(phase > battle.phase_index("tome") for *_rest, phase in answers), answers)
        self.assertIn(battle.RECHARGE_REASON, reasons)   # the next phase's 「全快させる」 rest
        self.assert_one_owner(answers)

    def test_the_tome_unproven_keeps_the_phase(self):
        # DECLARED CONSTRUCTED control: the record without its reached sights -- the tome's place
        # is not yet looked at -- keeps the tome phase, which walks to look.
        record = copy.deepcopy(CASE["battle_record"])
        record["battle"]["blind_sights"] = {"set": []}
        answers = self.drive(kill_all_patrol_test.lists(spent=True), record)
        self.assert_one_owner(answers)
        self.assertEqual(answers[0][4], battle.phase_index("tome"))
        self.assertEqual(answers[0][3], battle.SIGHT_REASON)

    def _board_policy(self, cell, record=None):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = new_policy(Path(directory.name), kill_all_patrol_test.lists(), record)
        index = next(index for index, raw in enumerate(CASE["second"]["boards"])
                     if index >= 4 and (raw["player"]["y"], raw["player"]["x"]) == cell)
        return policy, CASE["second"]["boards"][index], CASE["second"]["boards"][index + 1]

    def test_a_running_phase_with_no_step_keeps_the_patrol_out(self):
        # DECLARED CONSTRUCTED: the running phase has no step on the recorded [6,6] (the
        # recorded 6029 / restart 11 situation); the patrol does not take the move.
        policy, raw, following = self._board_policy((6, 6))
        with patch.object(battle, "_phase_key", lambda *_args: None):
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        self.assertTrue(battle.phases_left(
            policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        self.assertEqual((key, policy.last_reason), ("5", BLOCKED))
        self.post(policy, raw, key, following)

    def test_after_the_last_phase_the_patrol_takes_the_floor(self):
        # DECLARED CONSTRUCTED: the record with every phase ended and both quylthulgs' cells
        # cleared (``_after_the_phases`` has no quylthulg to shoot): the patrol's own job.
        policy, raw, _following = self._board_policy((6, 6))
        ctx = battle._ctx(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        quyls = [list(cell) for cell, race in ctx.navigator.battlefield.monster_placements
                 if race == battle.geo.QUYL]
        self.assertEqual(len(quyls), battle.geo.ROSTER[battle.geo.QUYL])
        record = copy.deepcopy(CASE["battle_record"])
        record["battle"]["phase"] = len(battle.PHASES)
        record["battle"]["quyls_done"] = {"set": [{"tuple": cell} for cell in quyls]}
        policy, raw, following = self._board_policy((6, 6), record)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        key = policy.choose_key(snapshot)
        self.assertFalse(battle.phases_left(policy, snapshot))
        self.assertIn(policy.last_reason, PATROL, key)
        self.post(policy, raw, key, following)


if __name__ == "__main__":
    unittest.main()
