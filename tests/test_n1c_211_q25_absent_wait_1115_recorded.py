"""Quest 25 on n1-c life-211 (2026-11-15 05:57-06:53): the ambush waiting for a dead tyrannosaurus, recorded.

n1-c life-211 is life-208 resumed (Magic-Eater Lv33; no telepathy: the boards' ``ability_sources``
show none) on Quest 25 『幽霊屋敷』.  Owner 2026-11-15 「また、長時間何を待っているのかも確認」:

 * What it waited for: the ambush (phase 1, ``long_wait_actions`` 5000, owner 2026-11-06
   「事実上上限無し」) ends when the hound, the skeletal and the spectral tyrannosaurus and the vampire
   lord are counted killed.  The spectral tyrannosaurus (705) died in life-208 at turn 3965900 by
   the character's fire aura (「幽体ティラノサウルスは灰の山になった。」, combat/aura-counterattack.cpp),
   a line the kill reader did not know, so it was never counted.  life-208 had already held the
   ambush 4,995 decisions for it (turns 3909947-3965767, before it came).
 * Why phase 0: the resumed game loaded the save of turn 4034788 (the 04:49 stop), older than the
   battle record life-208 left (turn 4035146, phase 11, every phase over).  quest25_battle_record
   ``_before_the_save`` then keeps only the kills read at or before the save's turn and runs the
   phases again from the first (n1-c life-207, 2026-11-14), ending at once those the kills end --
   the ambush is not among them (705 uncounted).  Every restart (05:57, 06:12, 06:33) loaded the
   same save, so each began the 5000-action wait again: 1,167 quiet holds on [10,1] at the stop.
   The 11-14 rule had no telepathy or detection check ("Telepathy is no general answer",
   test_n1c_207_q25_memory_loss_1114_recorded); nothing ended a wait for a race already gone.

The fixes (quest25_presence; owner 2026-11-13 「可能なら感知して存在を確認する」, 「感知が使えるなら使って
処理する」):

 * A roster race no hostile of which a board shows, where every cell of the map it could be on is
   within this board's telepathy (not EMPTY_MIND / WEIRD_MIND) or the plan's detection just cast
   (detect_all every race, Detect Evil the evil), is absent; the plan counts it as its whole roster
   in every phase.  From [10,1] the detection (DETECT_RAD_DEFAULT 30, Grid::calc_distance) reaches
   every cell inside the map's ring.
 * A waiting phase checks: ready, no hostile in view, none of the races it waits for shown, and
   ``quiet_actions`` more quiet actions since the last check (at once in a battle restored from an
   older save) -- the plan's detection is cast.  What it shows keeps its wait.
 * The kill reader reads the aura and projection death notes (monster-damage.cpp show_kill_message
   prints a note as name + note).

Recorded: tests/fixtures/n1c-211-q25-absent-wait-1115.json.gz
(tests/extract_n1c_211_q25_absent_wait_1115_fixture.py): the 06:33 process's last 12 boards and its
last 300 decisions, the first boards of the reloaded save, both battle records, and life-208's
decisions of the ambush's wait and of the tyrannosaurus's last fight.  A fresh policy restores a
record through the real path and decides the boards through the public ``choose_key``; a key is
posted through the production executor (``_ExecutorInputPort``).

DECLARED RECONSTRUCTED: the remembered magic-eater lists (the boards do not carry them), the rods
and staffs as tests/test_n1c_208_q25_patrol_1115_recorded reconstructs life-208's, 全感知 ready.
DECLARED CONSTRUCTED: the board after the detection is the stop board ten game turns on, showing
what life-208's detection of turn 4027956 showed (the two Nexus quylthulgs and its three lines,
tests/fixtures/n1c-208-q25-patrol-1115.json.gz); the kind prompt and the rod list of the cast
(as tests/test_n1b_382_q25_patrol_owner_1113_recorded posts ``mCg``).  The controls change one
thing each, as each says.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_record, quest25_presence as presence
from hengbot.model import parse_snapshot
from tests.support import q25_house as q25
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay
from tests import test_n1c_208_q25_patrol_1115_recorded as life208

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-211-q25-absent-wait-1115.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

geo = battle.geo
HELD = (10, 1)
SAVE_TURN = 4034788          # the save every life-211 process loaded (the 04:49 stop)
RECORD_208_TURN = 4035146    # life-208's last record
AURA_TURN = 3965900          # 「幽体ティラノサウルスは灰の山になった。」
DETECTED_208 = 4027956       # life-208's detection: only the two Nexus quylthulgs
AURA_LINE = "幽体ティラノサウルスは灰の山になった。"
AMBUSH = battle.phase_index("ambush")
CAST = f"{presence.CAST_REASON}:detect-all"


def stop_board() -> dict:
    return copy.deepcopy(CASE["hold"]["boards"][-1])


def detected_board(raw: dict, *, turn_step: int = 10) -> dict:
    """DECLARED CONSTRUCTED (module note): ``raw`` ``turn_step`` game turns on, showing what
    life-208's detection of turn 4027956 showed."""
    shown = next(board for board in life208.boards("stuck") if board["turn"] == DETECTED_208)
    board = copy.deepcopy(raw)
    board["turn"] = raw["turn"] + turn_step
    board["detected_monsters"] = copy.deepcopy(shown["detected_monsters"])
    board["messages"] = list(shown["messages"][-3:])
    return board


def new_policy(directory: Path, record: dict, first: dict):
    (directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy._q25_battle_record_path = directory / "q25-battle.json"
    policy._warning_cell_record_path = directory / "warning-cells.json"
    snapshot = parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge)
    policy.prime(snapshot)
    policy._skill_exp_cache = (0, 0, snapshot.player.level, policy._town_visit_epoch)
    policy._me_device_lists = life208.lists()   # DECLARED RECONSTRUCTED (module note)
    return policy


def decide(policy, raw):
    return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))


def decide_past_reads(policy, raw):
    """The first key on ``raw`` that is not the policy's own periodic list read (posted each)."""
    key = decide(policy, raw)
    for _read in range(4):
        if not policy.last_reason.startswith("periodic:"):
            break
        policy.confirm_key_posted(key)
        key = decide(policy, raw)
    return key


def fight(policy):
    return policy._quest_navigators[geo.QUEST_ID].phase_battle


def phase_name(policy) -> str | None:
    index = fight(policy).phase
    return battle.PHASE_NAMES[index] if index < len(battle.PHASES) else None


def stop_record(**changes) -> dict:
    record = copy.deepcopy(CASE["battle_record"])
    record["battle"].update(changes)
    return record


class TheRecordingTest(unittest.TestCase):

    def test_the_stop_is_the_ambush_holding_with_nothing_shown(self):
        record = CASE["battle_record"]
        self.assertEqual(record["turn"], CASE["hold"]["boards"][-1]["turn"])
        fought = record["battle"]
        self.assertEqual((fought["phase"], fought["ready"], fought["quiet"]), (AMBUSH, True, 1167))
        kills = dict(map(tuple, fought["kills"]["dict"]))
        self.assertNotIn(geo.SPECTRAL_T, kills)
        self.assertEqual(kills[geo.SHADOW], 7)   # of 9: two more died uncounted
        self.assertNotIn(geo.QUYL, kills)
        for row in CASE["hold"]["decisions"]:
            if row["reason"] != "survival:mana-absorb":
                self.assertEqual((row["reason"], row["key"], tuple(row["cell"])),
                                 (battle.HOLD_REASON, "5", HELD), row["turn"])
        for raw in CASE["hold"]["boards"]:
            self.assertEqual((raw["visible_monsters"], raw["detected_monsters"]), ([], []))
            telepathy = raw["player"]["ability_sources"]["telepathy"]
            self.assertFalse(any(telepathy.values()))

    def test_life208_held_the_ambush_and_the_fire_aura_burnt_the_tyrannosaurus(self):
        holds = [row for row in CASE["life208_ambush"] if (row[1], row[2]) == (battle.HOLD_REASON, "5")]
        self.assertGreaterEqual(len(holds), 4995)
        aura = next(row for row in CASE["life208_aura"] if row["turn"] == AURA_TURN)
        self.assertIn(AURA_LINE, aura["messages"])
        record = CASE["life208_record"]
        self.assertEqual((record["turn"], record["battle"]["phase"]), (RECORD_208_TURN, len(battle.PHASES)))
        self.assertNotIn(geo.SPECTRAL_T, dict(map(tuple, record["battle"]["kills"]["dict"])))

    def test_the_reloaded_save_is_older_than_the_record(self):
        first = CASE["reload"]["boards"][0]
        self.assertEqual((first["turn"], first["player"]["y"], first["player"]["x"]), (SAVE_TURN, 11, 19))
        self.assertLess(SAVE_TURN, RECORD_208_TURN)


class TheReloadTest(replay._Replay):

    def test_the_older_save_runs_the_phases_again_from_the_ambush(self):
        """Why phase 0: the record is later than the board, so only its kills are kept."""
        restored = quest25_battle_record._before_the_save(
            battle.Battle(**{name: quest25_battle_record._decode(value) for name, value in
                             CASE["life208_record"]["battle"].items()
                             if name in {f.name for f in battle.Battle.__dataclass_fields__.values()}}),
            SAVE_TURN)
        self.assertEqual(restored.phase, AMBUSH)
        self.assertEqual(restored.kills, dict(map(tuple, CASE["life208_record"]["battle"]["kills"]["dict"])))
        self.assertTrue(restored.recheck)

    def test_on_the_reloaded_board_the_check_comes_at_once(self):
        """The restored battle checks before it walks to [10,1] and waits (``Battle.recheck``)."""
        first = CASE["reload"]["boards"][0]
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), CASE["life208_record"], first)
            key = decide(policy, first)
            self.assertEqual(phase_name(policy), "ambush")
            self.assertEqual((key, policy.last_reason), ("mCg", CAST))
            self.post(policy, first, key, detected_board(first))
            key = decide(policy, detected_board(first))
            self.assertIn(geo.SPECTRAL_T, fight(policy).absent)
            self.assertEqual(phase_name(policy), "sweep")


class ThePresenceCheckTest(replay._Replay):

    def stop_policy(self, directory, record=None, board=None):
        return new_policy(Path(directory), record or CASE["battle_record"], board or stop_board())

    def test_the_stop_board_casts_the_detection(self):
        with TemporaryDirectory() as directory:
            policy = self.stop_policy(directory)
            key = decide(policy, stop_board())
            self.assertEqual((key, policy.last_reason, phase_name(policy)), ("mCg", CAST, "ambush"))
            self.post(policy, stop_board(), key, detected_board(stop_board()))

    def test_what_the_detection_showed_ends_every_wait_for_the_gone(self):
        """The two quylthulgs shown, nothing else: the ambush, the wall-passers, the Ipsissimus and
        the stragglers end; the quylthulgs, off their placements, are the sweep's targets."""
        with TemporaryDirectory() as directory:
            policy = self.stop_policy(directory)
            key = decide(policy, stop_board())
            self.post(policy, stop_board(), key, detected_board(stop_board()))
            after = detected_board(stop_board())
            key = decide(policy, after)
            absent = fight(policy).absent
            self.assertTrue({geo.SPECTRAL_T, geo.SHADOW, geo.SPECTRE, geo.IPSISSIMUS} <= set(absent))
            self.assertNotIn(geo.QUYL, absent)
            self.assertEqual(set(absent.values()), {after["turn"]})
            self.assertEqual(phase_name(policy), "sweep")
            ctx = battle._ctx(policy, parse_snapshot(copy.deepcopy(after), policy._monrace_knowledge))
            self.assertEqual({monster.race_id for monster in battle._sweep_targets(ctx)}, {geo.QUYL})
            self.assertNotEqual((key, policy.last_reason), ("mCg", CAST))

    def test_control_a_shown_tyrannosaurus_keeps_the_wait(self):
        """DECLARED CONSTRUCTED: the detection also shows a spectral tyrannosaurus on its cell."""
        with TemporaryDirectory() as directory:
            policy = self.stop_policy(directory)
            key = decide(policy, stop_board())
            after = detected_board(stop_board())
            tyrannosaurus = dict(copy.deepcopy(after["detected_monsters"][0]), race_id=geo.SPECTRAL_T,
                                 index=99, y=9, x=19, name="幽体ティラノサウルス")
            after["detected_monsters"].append(tyrannosaurus)
            self.post(policy, stop_board(), key, after)
            key = decide(policy, after)
            self.assertNotIn(geo.SPECTRAL_T, fight(policy).absent)
            self.assertIn(geo.SHADOW, fight(policy).absent)
            self.assertEqual(phase_name(policy), "ambush")
            self.assertEqual((key, policy.last_reason), ("5", battle.HOLD_REASON))
            self.assertEqual(fight(policy).quiet, 1168)   # what the detection showed did not come

    def test_control_a_cast_that_did_not_go_off_proves_nothing(self):
        """DECLARED CONSTRUCTED: the board after the cast shows the same game turn (the menu walk
        closed the prompt, the list showing the rod charging and, here, no staff), or a later one
        with the failure
        line: neither is a detection, nothing is absent, and the check is cast again -- at once
        after the failure, once the rod is ready after the closed prompt."""
        with TemporaryDirectory() as directory:
            policy = self.stop_policy(directory)
            self.assertEqual(decide(policy, stop_board()), "mCg")
            policy.confirm_key_posted("mCg")
            # The closed prompt's list: the rod charging; no staff (else Detect Evil is cast instead).
            policy._me_device_lists = dict(life208.lists(rod_charging=1), staff=(0, ()))
            closed = dict(stop_board(), messages=[])
            key = decide(policy, closed)
            self.assertEqual((fight(policy).absent, phase_name(policy)), ({}, "ambush"))
            self.assertNotEqual(key, "mCg")
            policy.confirm_key_posted(key)
            policy._me_device_lists = life208.lists()                 # charged again
            later = dict(detected_board(stop_board(), turn_step=20), detected_monsters=[], messages=[])
            self.assertEqual((decide_past_reads(policy, later), policy.last_reason), ("mCg", CAST))
            self.assertEqual(fight(policy).absent, {})
        with TemporaryDirectory() as directory:
            policy = self.stop_policy(directory)
            self.assertEqual(decide(policy, stop_board()), "mCg")
            policy.confirm_key_posted("mCg")
            failed = dict(detected_board(stop_board()), detected_monsters=[],
                          messages=["呪文をうまく唱えられなかった！"])
            self.assertEqual((decide(policy, failed), policy.last_reason), ("mCg", CAST))
            self.assertEqual((fight(policy).absent, phase_name(policy)), ({}, "ambush"))

    def test_control_a_board_without_the_detections_lines_proves_nothing(self):
        """DECLARED CONSTRUCTED: the board ten game turns on shows nothing and no 「…の存在を感じとった！」
        (detect_all always senses the doors: such a board is not the detection's), so nothing is
        absent and the check waits its next window: the ambush holds."""
        with TemporaryDirectory() as directory:
            policy = self.stop_policy(directory)
            self.assertEqual(decide(policy, stop_board()), "mCg")
            policy.confirm_key_posted("mCg")
            silent = dict(detected_board(stop_board()), detected_monsters=[], messages=[])
            key = decide_past_reads(policy, silent)
            self.assertEqual(fight(policy).absent, {})
            self.assertEqual((key, policy.last_reason, phase_name(policy)), ("5", battle.HOLD_REASON, "ambush"))

    def test_control_before_the_window_there_is_no_check(self):
        """DECLARED CONSTRUCTED: the record's quiet count below ``quiet_actions`` (50)."""
        with TemporaryDirectory() as directory:
            policy = self.stop_policy(directory, stop_record(quiet=10))
            self.assertEqual((decide(policy, stop_board()), policy.last_reason), ("5", battle.HOLD_REASON))

    def test_control_from_the_ranged_stand_it_steps_to_a_cell_the_detection_covers(self):
        """DECLARED CONSTRUCTED: the player on [13,1] (the ranged stand): the detection from there
        misses [1,29] and [2,29], so the check walks first."""
        board = stop_board()
        board["player"]["y"], board["player"]["x"] = 13, 1
        with TemporaryDirectory() as directory:
            policy = self.stop_policy(directory, board=board)
            key = decide(policy, board)
            self.assertEqual(policy.last_reason, presence.WALK_REASON)
            self.assertIn(key, ("8", "9"))   # toward [10,1]-[12,2], cells the detection covers


class TheKillReaderTest(replay._Replay):

    def test_the_fire_aura_kill_is_counted_and_ends_the_ambush(self):
        """DECLARED CONSTRUCTED: life-208's recorded lines of turn 3965900 on the stop board, with the
        record's quiet count below the check's window."""
        aura = next(row for row in CASE["life208_aura"] if row["turn"] == AURA_TURN)
        board = dict(stop_board(), messages=aura["messages"])
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), stop_record(quiet=0), board)
            decide(policy, board)
            self.assertEqual(fight(policy).kills.get(geo.SPECTRAL_T), 1)
            self.assertEqual(phase_name(policy), "wall-passers")

    def test_the_death_notes_name_the_victim(self):
        for line, name in ((AURA_LINE, "幽体ティラノサウルス"), ("シャドウ・デーモンは凍りついた。", "シャドウ・デーモン"),
                           ("The Spectre is destroyed.", "Spectre"),
                           ("バンパイア・ロードは光を受けてしぼんでしまった！", "バンパイア・ロード")):
            self.assertEqual(battle._killed_name(line), name)


class TheRecordTest(unittest.TestCase):

    def test_an_absence_before_the_save_is_kept_and_one_after_it_is_not(self):
        fought = battle.Battle(phase=11, absent={geo.SPECTRAL_T: SAVE_TURN - 5, geo.SHADOW: SAVE_TURN + 5})
        restored = quest25_battle_record._before_the_save(fought, SAVE_TURN)
        self.assertEqual(restored.absent, {geo.SPECTRAL_T: SAVE_TURN - 5})
        self.assertEqual(restored.phase, AMBUSH)


class TheMapReachTest(unittest.TestCase):
    """The reaches the module docstring states, on the shipped map (quest25_presence)."""

    def reach(self, cell):
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory), stop_record(quiet=10), stop_board())
            snapshot = parse_snapshot(stop_board(), policy._monrace_knowledge)
            decide(policy, stop_board())
            ctx = battle._ctx(policy, snapshot)
            cells = presence.possible_cells(ctx, geo.SPECTRAL_T)
            return {spot for spot in cells if presence._distance(cell, spot) > presence.detect_radius(ctx)}

    def test_the_detection_from_the_ambush_stands(self):
        self.assertEqual(self.reach(HELD), set())
        self.assertEqual(self.reach((13, 1)), {(1, 29), (2, 29)})


if __name__ == "__main__":
    unittest.main()
