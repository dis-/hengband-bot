"""Quest 25 on n1-c life-211 (2026-11-15 09:03-09:08): empty Detect Evil casts read as nothing, recorded.

After the Q25-ABSENT-WAIT fix (bot-6e4387a44) the restarted process reloaded the save of turn
4034788 again, restored the 06:53 battle (an older save: the phases from the ambush, the presence
check due at once) and cast the absorbed Staff of Detect Evil (``mAp``) 51 times, on [11,19] first
and every 50 quiet actions on [10,1] after it.  48 of the boards after a cast show no message at
all, the player still on the cell the cast was keyed on; three show 「呪文をうまく唱えられなかった！」.
Nothing became absent, and the ambush went on waiting for the dead spectral tyrannosaurus (quiet
2376 at the stop, ``q25-battle.json``).

Why: the check read a detection's board only when it showed the game's 「…の存在を感じとった！」.  The
game prints it only for what the detection found (spell-kind/spells-detection.cpp should_notify;
detect_monsters_evil prints nothing with no EVIL monster in reach), so an empty Detect Evil -- the
strongest sign that no evil roster race is left -- was thrown away.  The fix (quest25_presence
``_settle_cast``): the first board after the cast is its result when the game's time passed, no
failure line shows and the player still stands on the cell it was cast from (a detection does not
move the player).  What the detection cannot show stays unproved: Detect Evil shows only the EVIL
races (hunt_target.REVEALS); 705 and 665 are EVIL, the Nexus quylthulg 480 is not
(MonraceDefinitions), and a waiting phase whose races the held detection cannot show keeps its
plain wait (``presence_key``).

Why the staff and not the absorbed Rod of Detection: ``_detector`` takes the rod only while the
remembered rod list shows a charge.  The process read the rod list once (``bC`` at 09:03 on the
save's board, me_powers_refresh ``resume_read_key``: once per process) and the save is the 04:49
stop's, whose screens showed 「g) 全感知 充填: 1/ 1」 (charging, tests/test_n1c_208_q25_patrol_1115_recorded).

Recorded: tests/fixtures/n1c-211-q25-absent-empty-1115.json.gz
(tests/extract_n1c_211_q25_absent_empty_1115_fixture.py): the process's first 12 boards and their
decisions, every cast and the board after it, the stop's record.  A fresh policy restores the 06:53
record (tests/fixtures/n1c-211-q25-absent-wait-1115.json.gz) through the real path and decides the
recorded boards through the public ``choose_key``; the cast is posted through the production executor.

DECLARED RECONSTRUCTED: the remembered magic-eater lists (the boards do not carry them) as
tests/test_n1c_208_q25_patrol_1115_recorded reconstructs them, the rod 全感知 charging as the
04:49 save's screens showed it.  DECLARED CONSTRUCTED: the kind prompt and the staff list of the cast
(cmd-magiceat.cpp, as tests/test_me_device_attacks ``power_screen``); the controls change one thing each.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import me_capability, quest25_battle as battle, quest25_presence as presence
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.model import SV_STAFF_DETECT_EVIL, parse_snapshot
from tests.support import recorded as harness
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests import test_n1c_208_q25_patrol_1115_recorded as life208
from tests import test_n1c_211_q25_absent_wait_1115_recorded as wait

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-211-q25-absent-empty-1115.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

geo = battle.geo
SAVE_TURN = 4034788
CAST_CELL = (11, 19)
RESULT_TURN = 4034801          # the board after the first cast: no message, the player on [11,19]
CAST = f"{presence.CAST_REASON}:detect-evil"
DETECT_EVIL = me_capability.names("staff", SV_STAFF_DETECT_EVIL)[0]
EVIL_ROSTER = {geo.IPSISSIMUS, geo.TOME, geo.HOUND, geo.SKELETAL_T, geo.SPECTRAL_T, geo.SPECTRE,
               geo.SHADOW, geo.VAMPIRE, geo.DREADMASTER, geo.DRUJ, geo.STAIRWAY, geo.MASS}


def board(turn: int) -> dict:
    return copy.deepcopy(next(raw for raw in CASE["boards"] if raw["turn"] == turn))


def lists():
    """DECLARED RECONSTRUCTED (module note): the rod 全感知 charging, the staffs ready."""
    return life208.lists(rod_charging=1)


def new_policy(directory: Path):
    policy = wait.new_policy(directory, wait.CASE["battle_record"], board(SAVE_TURN))
    policy._me_device_lists = lists()
    return policy


class _Replay(harness.ProductionHarness):

    def post(self, policy, raw, key, following):
        """``key`` through the production executor: the kind question, the staff list, then
        ``following``."""
        game = harness.FaithfulHookGame()
        game.capacity = 256
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        game.screens = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                        power_screen("staff", [("p", DETECT_EVIL, 10, 10, 5)]),
                        harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        policy.confirm_key_posted(key)
        return game.accepted

    def cast_on_the_save(self, directory):
        policy = new_policy(Path(directory))
        key = wait.decide_past_reads(policy, board(SAVE_TURN))
        self.assertEqual((key, policy.last_reason, wait.phase_name(policy)), ("mAp", CAST, "ambush"))
        return policy, key


class TheRecordingTest(unittest.TestCase):

    def test_every_cast_was_the_staff_and_most_showed_nothing(self):
        casts, after = CASE["casts"], CASE["after_casts"]
        self.assertEqual(len(casts), 51)
        self.assertEqual({cast["key"] for cast in casts}, {"mAp"})
        failed = [row for row in after if row["messages"]]
        self.assertEqual(len(failed), 3)
        self.assertTrue(all(row["messages"][0].startswith("呪文をうまく唱えられなかった！") for row in failed))
        empty = [(cast, row) for cast, row in zip(casts, after) if not row["messages"]]
        self.assertEqual(len(empty), 48)
        self.assertTrue(all(cast["cell"] == row["cell"] and row["turn"] > cast["turn"] for cast, row in empty))
        recorded = [(row["turn"], row["reason"], row["key"]) for row in CASE["decisions"]]
        self.assertIn((SAVE_TURN, CAST, "mAp"), recorded)
        self.assertEqual((board(RESULT_TURN)["messages"], board(RESULT_TURN)["detected_monsters"]), ([], []))

    def test_the_stop_record_waited_with_nothing_absent(self):
        fought = CASE["stop_record"]["battle"]
        self.assertEqual((fought["phase"], fought["quiet"], fought["absent"]), (0, 2376, {"dict": []}))

    def test_detect_evil_shows_the_awaited_races_not_the_quylthulg(self):
        races = wait.q25.RACES
        for race in (geo.SPECTRAL_T, geo.SHADOW):
            self.assertIn("EVIL", races[race].flags)
            self.assertTrue(presence.shown_by("detect-evil", races[race].flags))
        self.assertNotIn("EVIL", races[geo.QUYL].flags)
        self.assertFalse(presence.shown_by("detect-evil", races[geo.QUYL].flags))


class TheEmptyDetectionTest(_Replay):

    def test_the_recorded_empty_board_ends_the_waits_for_every_evil_race(self):
        with TemporaryDirectory() as directory:
            policy, key = self.cast_on_the_save(directory)
            accepted = self.post(policy, board(SAVE_TURN), key, board(RESULT_TURN))
            self.assertEqual(accepted, ["m", "A", "p"])
            wait.decide(policy, board(RESULT_TURN))
            absent = wait.fight(policy).absent
            self.assertEqual(set(absent), EVIL_ROSTER)
            self.assertNotIn(geo.QUYL, absent)
            self.assertNotIn(wait.phase_name(policy), ("ambush", "wall-passers", "ipsissimus", "stragglers"))

    def test_control_the_player_moved_off_the_cast_cell(self):
        """DECLARED CONSTRUCTED: the recorded result board with the player one cell east."""
        moved = board(RESULT_TURN)
        moved["player"] = dict(moved["player"], x=CAST_CELL[1] + 1)
        with TemporaryDirectory() as directory:
            policy, key = self.cast_on_the_save(directory)
            policy.confirm_key_posted(key)
            wait.decide(policy, moved)
            self.assertEqual(wait.fight(policy).absent, {})
            self.assertEqual(wait.phase_name(policy), "ambush")

    def test_control_a_failed_cast_proves_nothing(self):
        """DECLARED CONSTRUCTED: the recorded result board with the recorded failure line."""
        failed = dict(board(RESULT_TURN), messages=["呪文をうまく唱えられなかった！"])
        with TemporaryDirectory() as directory:
            policy, key = self.cast_on_the_save(directory)
            policy.confirm_key_posted(key)
            wait.decide(policy, failed)
            self.assertEqual(wait.fight(policy).absent, {})

    def test_control_an_evil_monster_shown_keeps_its_race(self):
        """DECLARED CONSTRUCTED: the result board shows a spectral tyrannosaurus on its cell."""
        shown = board(RESULT_TURN)
        quyl = life208.boards("stuck")
        entry = copy.deepcopy(next(raw for raw in quyl if raw["turn"] == wait.DETECTED_208)["detected_monsters"][0])
        shown["detected_monsters"] = [dict(entry, race_id=geo.SPECTRAL_T, index=99, y=9, x=19,
                                           name="幽体ティラノサウルス")]
        with TemporaryDirectory() as directory:
            policy, key = self.cast_on_the_save(directory)
            policy.confirm_key_posted(key)
            wait.decide(policy, shown)
            absent = wait.fight(policy).absent
            self.assertNotIn(geo.SPECTRAL_T, absent)
            self.assertIn(geo.SHADOW, absent)
            self.assertEqual(wait.phase_name(policy), "ambush")


class TheDetectorCoverTest(unittest.TestCase):

    def test_no_check_when_the_held_detection_cannot_show_the_awaited_race(self):
        """DECLARED CONSTRUCTED: a waiting phase for the quylthulg alone with only Detect Evil held:
        no cast, the plain wait (Detect Evil cannot show the non-evil 480)."""
        with TemporaryDirectory() as directory:
            policy = new_policy(Path(directory))
            raw = board(SAVE_TURN)
            wait.decide_past_reads(policy, raw)
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            ctx = battle._ctx(policy, snapshot)
            ctx.battle.recheck, ctx.battle.cast, ctx.battle.ready = True, None, True
            phase = battle.Phase("quyl-wait", "phase3", False, lambda _ctx: False, lambda _ctx: None,
                                 None, "long_wait_actions", (geo.QUYL,))
            self.assertIsNone(presence.presence_key(ctx, phase))
            ambush = battle.PHASES[battle.phase_index("ambush")]
            self.assertEqual(presence.presence_key(ctx, ambush), "mAp")


if __name__ == "__main__":
    unittest.main()
