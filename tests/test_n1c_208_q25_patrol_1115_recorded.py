"""Quest 25 on n1-c life-208 (2026-11-15 04:48-04:49): the KILL_ALL patrol's detection and hunt, recorded.

n1-c life-208 (Magic-Eater Lv33, build bot-5602f6e11) on Quest 25 『幽霊屋敷』, every phase of the
plan over (battle phase 11, ``q25-battle.json``) and the quest not won: both Nexus quylthulgs (480)
were never counted killed.  The KILL_ALL patrol (kill_all_patrol, owner 2026-11-13 「全滅クエストで作戦を
完了しても終了しない場合、周回して敵を探す。感知を持っていれば感知して敵を探す。」) owned the floor.

 * The prompt (04:48:00 and 04:49:09, ``stuck-prompt owner=quest-patrol:detect ... reason=unowned``):
   the patrol cast the absorbed Rod of Detection (``mCg``) at turn 4027945, then at the next round
   (turn 4028926, after a quylthulg's TELE_AWAY) sent ``mCg`` again under its bare reason.  The
   remembered rod list was the one displayed before the first cast (全感知 ready); the rod still
   charged, and the game kept 「('*'で一覧, ESCで中断) どの魔力を使いますか？」 over
   「g) 全感知 充填: 1/ 1」 (cmd-magiceat.cpp: 「その魔法はまだ充填している最中だ。」, msg_erase, ask
   again).  No table of me_device_attacks_input owned the reason, so nothing answered it.
 * The loop (04:48:57, 04:49:14, 04:49:21): the quylthulg (NEVER_MOVE, INVISIBLE, BLINK and
   TELE_AWAY 1_IN_1; the player sees invisible) was in view three times (turns 4032528, 4032531,
   4032559) and the patrol only walked toward it (``quest-patrol:hunt``); each time it teleported
   the player away.  The five rounds ran out and ``quest:blocked:quest-patrol-rounds`` -- a named
   stop no list declared -- repeated '5' until the loop guard stopped the bot.

The fixes: the absorbed detection is cast under its menu owner (``ABSORBED_DETECT_REASON``,
me_absorbed_substitutes.cast), which closes a charging power's prompt with ESC and records the
list; a detection whose prompt was closed is chosen again from that list (the Staff of Detect
Evil); a hostile in view is shot (quest_plan_base._shot) before the walk; the rounds' stop is a
policy final stop.

Recorded: tests/fixtures/n1c-208-q25-patrol-1115.json.gz
(tests/extract_n1c_208_q25_patrol_1115_fixture.py): both processes' boards and decisions, the game's
screen at the first stop and the battle record.  A fresh policy restores the record through the real
path and decides the recorded boards in order through the public ``choose_key``; a key is posted
through the production decision send and executor (``_ExecutorInputPort``).

DECLARED RECONSTRUCTED: the remembered magic-eater lists (the boards do not carry them): the rods as
the stop screen lists them, 全感知 ready as displayed before the cast of turn 4027945; the staffs
Detect Evil and Speed, the powers the restarted process cast (``mAp``, ``mAw``), with charges.  The
skill reply (as test_anaguma_detect_stuck_1110_recorded).  The record is the one the life left
(04:49:23), its turn set to the first board's.  The patrol's round memory before the capture is not
recorded: the stuck replay starts at the recorded cast (its own rounds then differ from the
process's), and the recorded stop board is decided with the round over, as the recorded '5' of turn
4028915 (``quest-patrol:walk``, the round's end) left it.
DECLARED CONSTRUCTED: the kind prompt screen (cmd-magiceat.cpp, as test_me_detection_rod_1101 builds
it), the staff list screen, and the board after the closed prompt (the same turn, the executor's
completed board).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import kill_all_patrol, me_capability, quest25_battle as battle
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.model import SV_STAFF_DETECT_EVIL, SV_STAFF_SPEED, parse_snapshot
from tests.support import q25_house as q25
from tests.support import recorded as harness
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-208-q25-patrol-1115.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

FIRST_CAST = 4027945        # the patrol's cast of the Rod of Detection (decision 96, then 全感知 charging)
ROUND_END = 4028915         # the recorded '5' that ended the round (after the TELE_AWAY)
STOP = 4028926              # the recorded ``mCg`` left on the power prompt
QUYL_IN_VIEW = (4032528, 4032531, 4032559)
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
DETECTION = "全感知"
DETECT_EVIL = me_capability.names("staff", SV_STAFF_DETECT_EVIL)[0]
SPEED = me_capability.names("staff", SV_STAFF_SPEED)[0]
QUYL = 480
# The absorbed detection's menu owner (kill_all_patrol.ABSORBED_DETECT_REASON).
OWNED = kill_all_patrol.DETECT_REASON + CAST_SUFFIX


def _row(name, **counts):
    return {"name": name, "fail": 7, "success": 93, **counts}


def lists(*, rod_charging=0):
    """DECLARED RECONSTRUCTED (module note): the remembered rod and staff lists."""
    rods = (_row("トラップ感知", charging=0, max=9), _row("ドア/階段感知", charging=0, max=6),
            _row("帰還", charging=0, max=1), _row("イルミネーション", charging=0, max=6),
            _row(DETECTION, charging=rod_charging, max=1), _row("害虫駆除", charging=0, max=3),
            _row("トラップ解除", charging=0, max=2), _row("光", charging=0, max=2),
            _row("アシッド・ボルト", charging=0, max=3), _row("サンダー・ボルト", charging=0, max=4),
            _row("ファイア・ボルト", charging=0, max=1), _row("アイス・ボルト", charging=0, max=1),
            _row("アイス・ボール", charging=0, max=1))
    staffs = (_row(DETECT_EVIL, current=10, max=10), _row(SPEED, current=5, max=5))
    return {"rod": (0, rods), "staff": (0, staffs)}


def boards(part):
    return CASE[part]["boards"]


def board(part, turn):
    return copy.deepcopy(next(raw for raw in boards(part) if raw["turn"] == turn))


def recorded(part):
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE[part]["decisions"]}


def new_policy(directory: Path, part, device_lists):
    first = boards(part)[0]
    record = dict(CASE["battle_record"], turn=first["turn"])   # DECLARED (module note)
    (directory / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
    policy = ConservativePolicy(monrace_knowledge=q25.RACES, quest_knowledge=q25.QUESTS,
                                quest_strategies=q25.STRATEGIES)
    policy._q25_battle_record_path = directory / "q25-battle.json"
    policy._warning_cell_record_path = directory / "warning-cells.json"
    snapshot = parse_snapshot(copy.deepcopy(first), policy._monrace_knowledge)
    policy.prime(snapshot)
    policy._skill_exp_cache = (0, 0, snapshot.player.level, policy._town_visit_epoch)
    policy._me_device_lists = device_lists
    return policy


def decide(policy, raw):
    return policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))


class _Replay(harness.ProductionHarness):
    def setUp(self):
        super().setUp()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def replay(self, part, first, last, device_lists):
        """(policy, [(turn, reason, key)]) of the recorded boards ``first``..``last``."""
        policy = new_policy(self.directory, part, device_lists)
        decided = []
        for raw in boards(part):
            if first <= raw["turn"] <= last:
                key = decide(policy, raw)
                decided.append((raw["turn"], policy.last_reason, key))
        return policy, decided

    def post(self, policy, raw, key, screens, following=None):
        """``key`` through the production decision send and the executor; the game's accepted keys,
        the send's result and the executor's completed board."""
        game = harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        following = following or raw
        game.screens = [*screens, harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": policy.last_reason},
            snapshot=parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge),
            posting_contract=PostingContract())
        return game.accepted, sent, port.last_result, executor.ready_board

    def stop_screen(self):
        """The game's screen at the stop: the power prompt over the rod list, 全感知 1/1 charging."""
        screen = copy.deepcopy(CASE["stuck"]["stop_screen"])
        self.assertEqual(screen["input_context"]["kind"], "spell")
        self.assertIn("g) 全感知                 充填: 1/ 1", "\n".join(screen["lines"]))
        return screen


class TheRecordingTest(_Replay):
    def test_the_recorded_chain(self):
        stuck, loop = recorded("stuck"), recorded("loop")
        self.assertEqual(stuck[FIRST_CAST], (kill_all_patrol.DETECT_REASON, "mCg"))
        self.assertEqual(stuck[ROUND_END], (kill_all_patrol.WALK_REASON, "5"))
        self.assertEqual(stuck[STOP], (kill_all_patrol.DETECT_REASON, "mCg"))
        for turn in QUYL_IN_VIEW:
            self.assertEqual(loop[turn][0], kill_all_patrol.HUNT_REASON, turn)
            self.assertEqual([monster["race_id"] for monster in board("loop", turn)["visible_monsters"]],
                             [QUYL])
        stops = [row for row in CASE["loop"]["decisions"] if row["reason"] == kill_all_patrol.STOP_REASON]
        self.assertGreaterEqual(len(stops), 10)
        self.assertEqual({row["key"] for row in stops}, {"5"})
        self.assertEqual(CASE["loop"]["decisions"][-1]["reason"], "loop-detected")

    def test_the_battle_is_over_and_the_quylthulgs_uncounted(self):
        fight = CASE["battle_record"]["battle"]
        self.assertEqual(fight["phase"], len(battle.PHASES))
        kills = dict(map(tuple, fight["kills"]["dict"]))
        self.assertNotIn(QUYL, kills)

    def test_the_quylthulg_teleports_the_player_away(self):
        """MonraceDefinitions 480 (the game's data): never moves, invisible, BLINK and TELE_AWAY."""
        race = q25.RACES[QUYL]
        self.assertTrue({"NEVER_MOVE", "INVISIBLE"} <= set(race.flags))


class TheDetectionTest(_Replay):
    def test_the_replayed_cast_is_owned(self):
        policy, decided = self.replay("stuck", FIRST_CAST, FIRST_CAST, lists())
        self.assertEqual(decided, [(FIRST_CAST, OWNED, "mCg")])
        self.assertEqual(getattr(kill_all_patrol, "ABSORBED_DETECT_REASON", None), OWNED)

    def test_the_recorded_stop_board_closes_the_prompt_then_detects_with_the_staff(self):
        """The recorded stop board, the round over (the recorded '5' of ``ROUND_END``): ``mCg`` under
        its owner; on the recorded screen (全感知 charging) the owner closes the prompt with ESC, no
        game time passes, and the closed detection is chosen again from the game's list: the Staff of
        Detect Evil."""
        policy, _decided = self.replay("stuck", FIRST_CAST, ROUND_END, lists())
        patrol = policy._kill_all_patrol
        patrol.detected_round = patrol.round - 1   # DECLARED (module note): the round over
        raw = board("stuck", STOP)
        key = decide(policy, raw)
        self.assertEqual((policy.last_reason, key), (OWNED, "mCg"))
        accepted, sent, result, after = self.post(
            policy, raw, key, [prompt(TYPE_PROMPT), self.stop_screen()])
        self.assertTrue(sent, result.stop_line)
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(accepted, ["m", "C", "\x1b"])
        self.assertEqual(after["turn"], STOP)
        listed = after["_magic_eater_power_list"]
        self.assertEqual(next(row for row in listed["rows"] if row["name"] == DETECTION)["charging"], 1)
        policy.confirm_key_posted(key)
        key = decide(policy, after)
        self.assertEqual((policy.last_reason, key), (OWNED, "mAp"))
        accepted, sent, result, _after = self.post(policy, after, key, [
            prompt(TYPE_PROMPT), power_screen("staff", [("p", DETECT_EVIL, 10, 10, 7)])],
            following=dict(copy.deepcopy(after), turn=STOP + 10))
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(accepted, ["m", "A", "p"])

    def test_control_the_bare_reason_leaves_the_recorded_prompt(self):
        """The recorded send: ``mCg`` under ``quest-patrol:detect`` goes out raw and the prompt the
        game keeps is nobody's (the recorded stuck-prompt)."""
        policy, _decided = self.replay("stuck", FIRST_CAST, FIRST_CAST, lists())
        policy.last_reason = kill_all_patrol.DETECT_REASON
        raw = board("stuck", STOP)
        accepted, _sent, result, _after = self.post(policy, raw, "mCg", [self.stop_screen()])
        self.assertEqual("".join(accepted), "mCg")
        self.assertNotEqual(result.outcome, "completed")
        self.assertIn("unowned", result.stop_line)

    def test_a_ready_rod_is_cast(self):
        policy, _decided = self.replay("stuck", FIRST_CAST, ROUND_END, lists())
        patrol = policy._kill_all_patrol
        patrol.detected_round = patrol.round - 1
        raw = board("stuck", STOP)
        key = decide(policy, raw)
        accepted, _sent, result, _after = self.post(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("rod", [("g", DETECTION, 0, 1, 7)])],
            following=dict(copy.deepcopy(raw), turn=STOP + 10))
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(accepted, ["m", "C", "g"])

    def test_a_rod_seen_charging_is_not_asked(self):
        """The list already shows the rod charging: the staff first, no prompt to close."""
        policy, _decided = self.replay("stuck", FIRST_CAST, ROUND_END, lists(rod_charging=1))
        patrol = policy._kill_all_patrol
        patrol.detected_round = patrol.round - 1
        key = decide(policy, board("stuck", STOP))
        self.assertEqual((policy.last_reason, key), (OWNED, "mAp"))


if __name__ == "__main__":
    import unittest
    unittest.main()
