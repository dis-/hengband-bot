"""Quest 25 on n1-c life-207 (2026-11-14 17:23-17:54): the wall-passers' endless hold on [10,1], recorded.

The chain (decision log and snapshot logs of ~/hengbot-soak/n1-c/life-207, and the stop's capture
20261114-175423-stall-floor-dwell-quest-strategy-hold):

 * 17:23:53, the ambush (phase 0, melee): the spectre killed, the phase stepped '8' from [10,1]
   onto the door cell [9,1] to meet the spectral tyrannosaur beside it (``quest25:engage``,
   decision 3973).  The weapon warned (「★ライト・クロスボウ『ウィザッパー』が鋭く震えた！」
   「本当にこのまま進むか？[y/n]」, 3974), the prompt was refused and [9,1] latched
   (trap_warning ``note_warned``; the record warning-cells.json: refused [[9,1]]).  The
   tyrannosaur was killed on [10,1] two decisions later.
 * The ambush ended, the HP was rested full, and the wall-passers' phase (phase 1, 「全快にして
   (7,1)に移動」) walked to [7,1].  [9,1] is the only way from [10,1], and the plan's walks never
   step onto a refused cell (``_refused``): no path, ``_walk`` gave None, and the phase held
   (``quest-strategy:hold`` '5') on [10,1] from 17:24 to the stall stop at 17:54:23, over 5,300
   decisions, nothing in view, the nine shadow demons sensed in the walls east of it.  Its wait
   (``wall_passer_quiet_actions``, 100 actions) counts only on [7,1], so it never ended.

Then (capture 20261114-184915-stuck-prompt-quest25-close-door): the game reloaded the 17:54 stop's
save (turn 8010826), the battle record of 18:02 was of a later turn and not restored, so the plan
began at the ambush again (melee, on [10,1]); [9,1] not being a closed door, it keyed 'c' to close
it, but [9,1] is FLOOR now (an open door on the boards of 17:23:53, FLOOR from 17:24:07): with no
open door around, do_cmd_close asked 「方向 (ESCで中断)?」 and the prompt stopped the bot.

The rules (quest25_battle):

 * ``_refused``: a refused cell stays refused while a known monster could still raise that warning
   (trap_warning ``_monster_could_warn``, the test that latched it); with its monsters gone the
   plan's step onto it lifts the latch (``_unlatch_stale``).  No known monster could warn of [9,1]
   on any recorded hold board, so the phase walks to [7,1] and its wait counts there.
 * ``battle.no_way``: where the phase's walk to its stand held with no way on (none, or only toward
   the shunned movers), its wait counts as on the stand (「道が無ければ今いる召喚を受けないマスで
   迎え撃つ」 2026-11-12, 「50回来なければ終える」 2026-11-06), so it ends instead of holding on.
 * ``_door_to_close``: the melee ambush closes [9,1] only when it is an open door.

Recorded: tests/fixtures/n1c-207-q25-wallpasser-hold-1114.json.gz
(tests/extract_n1c_207_q25_wallpasser_hold_1114_fixture.py, copies in
C:/hengband-backups/pdca/q25-hold-1114): the refusal's boards, the stop's 100 boards (17:54), 140
earlier hold boards (17:24) and the 18:49 restart's five boards, with the battle records and both
warning records.  A fresh policy
restores both records through the real paths and decides the boards in order through the public
``choose_key``; each key is posted through the production executor (``_ExecutorInputPort``), the
game then showing the next recorded board.

DECLARED CONSTRUCTED: the recorded boards are all on [10,1]; where a replayed step leads elsewhere,
the next board is the next recorded one with the player's cell set to where the step led and the
floor item's 「〜がある。」 line of [10,1] dropped (every recorded board of the hold has nothing in
view and the same map).  The records' turns are set to the first board's (as
tests/test_n1b_382_q25_patrol_owner_1113_recorded does); the battle record is the one of 17:42
(phase 1, ready, quiet 0, the same at the stop).  The boards carry no magic-eater lists (none were
displayed on the floor's boards), so the policy holds none.  The control tests move one sensed
shadow demon as each says.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_record, trap_warning
from hengbot.model import Position, parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay
from tests.support import q25_house as q25

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-207-q25-wallpasser-hold-1114.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

HELD, DOOR, STAND = (10, 1), (9, 1), battle.geo.WALL_PASSER_STAND
WALL_PASSERS, IPSISSIMUS = battle.phase_index("wall-passers"), battle.phase_index("ipsissimus")
WAIT = 100   # QUEST_25 wait_limits.wall_passer_quiet_actions (owner 2026-11-09 「待つターンを倍にしてみる」)
PROMPT = "本当にこのまま進むか？[y/n]"
STEPS = {"8": (-1, 0), "2": (1, 0), "4": (0, -1), "6": (0, 1),
         "7": (-1, -1), "9": (-1, 1), "1": (1, -1), "3": (1, 1)}


def boards(part: str) -> list[dict]:
    """The part's recorded boards rebuilt from the first and each one's changes (extraction)."""
    base = CASE[part]["base"]
    found = []
    for change in CASE[part]["changes"]:
        changed = {key: change[key] for key in ("turn", "clock", "messages", "detected_monsters")}
        board = dict(copy.deepcopy(base), **copy.deepcopy(changed))
        board["player"] = dict(board["player"], **change["player"])
        found.append(board)
    return found


def at(raw: dict, cell) -> dict:
    """DECLARED CONSTRUCTED (module note): the recorded board with the player on ``cell``."""
    board = copy.deepcopy(raw)
    if tuple(cell) != HELD:
        board["player"]["y"], board["player"]["x"] = cell
        board["messages"] = [text for text in board["messages"] if "がある。" not in text]
    return board


def demon_beside_door(raw: dict) -> dict:
    """DECLARED CONSTRUCTED control: one sensed shadow demon moved into the wall at [8,2], beside
    [9,1] (and two cells from [10,1]): a known monster that could raise the warning."""
    board = copy.deepcopy(raw)
    demon = next(monster for monster in board["detected_monsters"]
                 if monster["race_id"] == battle.geo.SHADOW)
    demon["y"], demon["x"] = 8, 2
    return board


def new_policy(directory: Path, first: dict, warning_record, battle_record=None):
    first_turn = first["turn"]
    record = dict(battle_record or CASE["battle_record"], turn=first_turn)   # DECLARED (module note)
    (directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
    if warning_record is not None:
        (directory / "warning-cells.json").write_text(
            json.dumps(dict(warning_record, turn=first_turn)), encoding="utf-8")
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy._q25_battle_record_path = directory / "q25-battle.json"
    policy._warning_cell_record_path = directory / "warning-cells.json"
    policy.prime(parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge))
    policy.consume_skill_knowledge(dict(
        copy.deepcopy(CASE["skill"]), turn=first_turn,
        player=dict(CASE["skill"]["player"], level=first["player"]["level"])))
    policy._me_device_lists = {}
    return policy


class _Hold(replay._Replay):
    case = CASE

    def drive(self, part, warning_record, shape=lambda raw: raw):
        """[(index, cell, key, reason, phase, quiet, refused)] of the part's boards in order, to the
        first key whose screens this harness does not show (``replay._shown``)."""
        recorded = [shape(raw) for raw in boards(part)]
        answers, cell = [], HELD
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), recorded[0], warning_record)
            for index, raw in enumerate(recorded):
                shown = at(raw, cell)
                key = policy.choose_key(parse_snapshot(copy.deepcopy(shown), policy._monrace_knowledge))
                self.assertIsNotNone(key, index)
                fight = policy._quest_navigators[battle.geo.QUEST_ID].phase_battle
                answers.append((index, cell, key, policy.last_reason, fight.phase, fight.quiet,
                                frozenset((spot.y, spot.x) for spot in policy._warning_refused_cells)))
                if not replay._shown(key) or index + 1 == len(recorded):
                    break
                step = STEPS.get(key)
                following = cell if step is None else (cell[0] + step[0], cell[1] + step[1])
                self.post(policy, shown, key, at(recorded[index + 1], following))
                cell = following
        return answers

    def assert_walks_to_the_stand(self, answers):
        walk = [(cell, key, reason) for _index, cell, key, reason, *_rest in answers[:3]]
        self.assertEqual(walk, [((10, 1), "8", battle.WALK_REASON), ((9, 1), "8", battle.WALK_REASON),
                                ((8, 1), "8", battle.WALK_REASON)])
        self.assertEqual(answers[0][6], frozenset())   # the stale latch lifted by the step onto [9,1]
        self.assertEqual(answers[3][1], STAND)
        self.assertNotIn(battle.HOLD_REASON, {reason for _i, cell, _k, reason, *_rest in answers
                                              if cell == HELD})


class TheRecordingTest(unittest.TestCase):

    def test_the_refusal_latched_the_door_cell(self):
        (engage, prompt, after) = CASE["refusal"]["recorded"]
        self.assertEqual((engage["key"], engage["reason"]), ("8", battle.ENGAGE_REASON))
        self.assertEqual([(board["player"]["y"], board["player"]["x"])
                          for board in CASE["refusal"]["boards"]], [HELD] * 3)
        self.assertIn(PROMPT, prompt["messages"])
        # The spectral tyrannosaur beside [9,1] (on [8,1]) warned; on the next board it stood on [9,1].
        seen = [[(monster["race_id"], monster["y"], monster["x"]) for monster in board["visible_monsters"]]
                for board in CASE["refusal"]["boards"]]
        spectral = battle.geo.SPECTRAL_T
        self.assertEqual(seen, [[(spectral, 8, 1)], [(spectral, 8, 1)], [(spectral, 9, 1)]])
        self.assertEqual(after["reason"], "quest-strategy:melee")
        for record in (CASE["warning_record"], CASE["stop_warning_record"]):
            self.assertEqual(record["state"]["refused"], [list(DOOR)])
        self.assertEqual(CASE["warning_record"]["turn"], prompt["turn"])

    def test_the_hold_saw_nothing_that_could_warn_of_the_door(self):
        record = CASE["battle_record"]["battle"]
        self.assertEqual((record["phase"], record["ready"], record["quiet"]), (WALL_PASSERS, True, 0))
        kills = dict(quest25_battle_record._decode(record["kills"]))
        self.assertEqual(kills.get(battle.geo.SPECTRE), 2)
        self.assertNotIn(battle.geo.SHADOW, kills)
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), boards("hold")[0], None)
            for part in ("hold", "stop"):
                rows = CASE[part]["recorded"]
                self.assertTrue(all((row["key"], row["reason"]) == ("5", battle.HOLD_REASON) for row in rows))
                for raw in boards(part):
                    self.assertEqual((raw["player"]["y"], raw["player"]["x"]), HELD)
                    self.assertEqual(raw["visible_monsters"], [])
                    snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
                    self.assertEqual(sum(1 for monster in snapshot.detected_monsters
                                         if monster.race_id == battle.geo.SHADOW and not monster.asleep), 9)
                    self.assertFalse(trap_warning._monster_could_warn(policy, snapshot, Position(*DOOR)))


class TheStopTest(_Hold):

    def test_the_phase_walks_to_its_stand_and_its_wait_counts(self):
        answers = self.drive("stop", CASE["stop_warning_record"])
        self.assertEqual(len(answers), len(CASE["stop"]["recorded"]), answers[-1])
        self.assert_walks_to_the_stand(answers)
        on_stand = answers[3:]
        self.assertTrue(all(cell == STAND and phase == WALL_PASSERS for _i, cell, _k, _r, phase, *_rest
                            in on_stand))
        self.assertEqual([quiet for *_rest, quiet, _refused in on_stand], list(range(1, len(on_stand) + 1)))


class TheWaitEndsTest(_Hold):

    def test_after_the_wait_on_the_stand_the_ipsissimus_phase_runs(self):
        answers = self.drive("hold", CASE["warning_record"])
        self.assert_walks_to_the_stand(answers)
        first = next(index for index, *_rest, phase, _quiet, _refused in answers if phase != WALL_PASSERS)
        self.assertEqual(answers[first][4], IPSISSIMUS)
        self.assertEqual(answers[first - 1][5], WAIT - 1)   # the 100th quiet board on [7,1] is this one
        self.assertEqual(first, 3 + WAIT - 1)
        self.assertTrue(all(cell == STAND for _i, cell, *_rest in answers[3:first + 1]))
        # Phase 2's own walk on (「(7,1)に移動、…(6,1)(5,1)と移動」, PHASE2_WALK) or its preparation.
        self.assertNotEqual(answers[first][3], battle.HOLD_REASON, answers[first:first + 3])


class TheBlamedLatchTest(_Hold):

    def test_a_monster_that_could_warn_keeps_the_latch_and_the_wait_counts_where_it_holds(self):
        # DECLARED CONSTRUCTED control (``demon_beside_door``): the latch stays (life-200's rule),
        # the phase has no way to [7,1] and holds on [10,1], and its wait counts there.
        answers = self.drive("hold", CASE["warning_record"], demon_beside_door)
        self.assertTrue(all(refused == frozenset({DOOR}) for *_rest, refused in answers))
        before = [row for row in answers if row[4] == WALL_PASSERS]
        self.assertTrue(all(cell == HELD and key == "5" for _i, cell, key, *_rest in before))
        self.assertEqual([quiet for *_rest, quiet, _refused in before], list(range(len(before))))
        self.assertEqual(len(before), WAIT)   # counted from the second board, once the walk held
        # The wall-passers' phase ended (phase 2, with no way to a cell that sees the pen and no
        # attack aimed at its grid, counts the three escaped at once: ``_pen_sight``).
        self.assertGreater(answers[len(before)][4], WALL_PASSERS)


def with_door(raw: dict, palette_index: int) -> dict:
    """The board with [9,1] drawn as the palette row ``palette_index`` (the recorded grid map's)."""
    board = copy.deepcopy(raw)
    runs = board["grid_map"]["runs"]
    at_door = next(index for index, run in enumerate(runs) if run[:3] == [DOOR[0], DOOR[1], 1])
    runs[at_door] = [DOOR[0], DOOR[1], 1, palette_index]
    return board


class TheCloseDoorStopTest(replay._Replay):
    """18:49:13, the restarted process (stuck-prompt:quest25:close-door): the reloaded save's turn
    8010826 is before the battle record's (18:02, 8033912), so the record was not restored
    (quest25_battle_record ``observe``) and the plan began at the ambush again; melee, on [10,1]
    with nothing in view and [9,1] not a closed door, it keyed 'c'.  [9,1] is FLOOR: no door
    around, and do_cmd_close asked for a direction (``_door_to_close``)."""
    case = CASE
    STOP = 4

    def decide(self, raw):
        close = CASE["close"]
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), close["boards"][0], CASE["stop_warning_record"],
                                close["battle_record"])
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            reason = policy.last_reason
            fight = policy._quest_navigators[battle.geo.QUEST_ID].phase_battle
            if replay._shown(key):
                self.post(policy, raw, key, raw)
            return key, reason, fight

    def test_the_recording(self):
        close = CASE["close"]
        self.assertEqual([(row["key"], row["reason"]) for row in close["recorded"]][self.STOP],
                         ("c", battle.CLOSE_REASON))
        record = close["battle_record"]
        self.assertEqual((record["turn"], record["battle"]["phase"], record["battle"]["style"]),
                         (close["boards"][0]["turn"], battle.phase_index("ambush"), "melee"))
        # The reloaded save is the 17:54 stop's (the 18:02 process's record, turn 8033912, was later).
        self.assertGreaterEqual(record["turn"], CASE["stop"]["recorded"][-1]["turn"])
        raw = close["boards"][self.STOP]
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), raw, None, record)
            grid = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge).grid_at(Position(*DOOR))
        self.assertTrue(grid.known and grid.passable and not grid.is_door)

    def test_no_door_no_close(self):
        key, reason, fight = self.decide(CASE["close"]["boards"][self.STOP])
        self.assertEqual(fight.phase, battle.phase_index("ambush"))
        self.assertNotEqual(key, "c")
        self.assertEqual((key, reason), ("5", battle.HOLD_REASON))

    def test_an_open_door_is_still_closed(self):
        # DECLARED CONSTRUCTED control: [9,1] drawn as the recorded palette's OPEN_DOOR row (as it
        # was on the boards of 17:23:53): the ambush still closes it.
        raw = CASE["close"]["boards"][self.STOP]
        palette = raw["grid_map"]["palette"]
        open_door = next(index for index, row in enumerate(palette) if row[0] == 4)   # OPEN_DOOR
        key, reason, _fight = self.decide(with_door(raw, open_door))
        self.assertEqual((key, reason), ("c", battle.CLOSE_REASON))


if __name__ == "__main__":
    unittest.main()
