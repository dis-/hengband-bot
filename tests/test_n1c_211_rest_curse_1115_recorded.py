"""Quest 25 on n1-c life-211 (2026-11-15 06:29-06:53): the hold with cursed gear, recorded (curse_cure).

n1-c life-211 (Magic-Eater Lv33) on Quest 25 『幽霊屋敷』, battle phase 0 (the ambush) ready on [10,1],
held '5' (``quest-strategy:hold``) with seven cursed pieces worn -- the druj's CAUSE_3 curses: the
boots ★鉄鋲底の靴『炎の鉄ゲタ』 called an animal (「…が動物を引き寄せた！」, turn 4123620: ラオウの愛馬
『黒王号』 beside the player at once) and three pieces drained HP (「高速度のヘヴィ・クロスボウはあなたの体力を
吸収した！」, turn 4135981, 652 -> 586).  A quest floor has no natural spawns (world-turn-processor.cpp
decide_alloc_monster), so the summoning curse alone kept feeding the floor while the hold went on; the
owner stopped n1-c: 「休憩でモンスターが無限に湧く状態になっており、いずれ強敵が溢れてクリア不能になる」.

Owner 2026-11-15: 「呪われていれば休む前に解く」, 「クエストの階は残って続ける」, 「持ち歩かない」, 「強力発動を
先にする」 (curse_cure's docstring).  The character holds the absorbed Staff of Remove Curse (its
Powerful Activation ``UAg`` succeeded in town at 03:02, 「誰かに見守られているような気がする。」).

Recorded: tests/fixtures/n1c-211-rest-curse-1115.json.gz (tests/extract_n1c_211_rest_curse_1115_fixture.py):
the boards and decisions of turns 4123566-4123700 and 4135901-4136145, and the battle record.  A fresh
policy restores the record through the real path and decides the recorded boards through the public
``choose_key``; a key is posted through the production decision send and executor (``_ExecutorInputPort``).

DECLARED RECONSTRUCTED: the remembered staff list (the boards do not carry it): 解呪 (Remove Curse) and
スピード (Speed, cast as ``mAw`` at turn 4123620), with charges; the skill reply (as
test_n1c_208_q25_patrol_1115_recorded).  The record is the one the life left (06:53), its turn set to the
first decided board's.
DECLARED CONSTRUCTED: the game's replies to the posted keys (the racial prompt and list of
cmd-action/cmd-racial.cpp, the kind prompt and staff list of cmd-item/cmd-magiceat.cpp, as
test_me_powerful_activation builds them); the board after a use (the next recorded board with the worn
curses removed as exe_curse_removal removes them, HP less the cost); a lowered HP for the ordinary use; the
normal floor (the recorded board's floor key replaced by a 30F dungeon floor) and a staff list without
Remove Curse for rule 2.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # first: the plan modules import in a cycle alone
from hengbot import curse_cure, me_capability, me_powerful_activation as powerful
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import SV_STAFF_REMOVE_CURSE, SV_STAFF_SPEED, parse_snapshot
from hengbot.quest_plan_base import HOLD_REASON
from tests.support import q25_house as q25
from tests.support import recorded as harness
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_powerful_activation import TYPE_PROMPT, racial_screen

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-211-rest-curse-1115.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

CALLED = 4123620           # 「★鉄鋲底の靴『炎の鉄ゲタ』が動物を引き寄せた！」, 黒王号 beside the player
BEFORE_CALL = 4123605      # the hold before it
HOLD = 4135901             # the first hold board of the life's last minute (HP 652/652)
BEFORE_DRAIN = 4135966
DRAINED = 4135981          # 「高速度のヘヴィ・クロスボウはあなたの体力を吸収した！」 (652 -> 586)
AFTER_DRAIN = 4135992
LATER = 4136029
LEVEL = 33
UNCURSE_NAME = me_capability.names("staff", SV_STAFF_REMOVE_CURSE)[0]
SPEED_NAME = me_capability.names("staff", SV_STAFF_SPEED)[0]
CURSED_TAG = "呪われている"


def _row(name, current, maximum):
    return {"name": name, "fail": 20, "success": 80, "current": current, "max": maximum}


def lists(*, uncurse=True, charges=3):
    """DECLARED RECONSTRUCTED (module note): the remembered staff list."""
    rows = [_row(SPEED_NAME, 5, 5)]
    if uncurse:
        rows.insert(0, _row(UNCURSE_NAME, charges, 3))
    return {"staff": (0, tuple(rows))}


def board(turn):
    return copy.deepcopy(next(raw for raw in CASE["boards"] if raw["turn"] == turn))


def recorded():
    return {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}


def uncursed(raw, *, keep=()):
    """exe_curse_removal (spells-curse-removal.cpp): every worn curse removed, the slots ``keep`` left
    cursed; the name loses its 呪われている feeling as describe_flavor drops it."""
    for item in raw["equipment"]:
        if item.get("is_cursed") and item["slot"] not in keep:
            item["is_cursed"] = False
            item["name"] = (item["name"].replace(f" {{{CURSED_TAG}}}", "")
                            .replace(f"{CURSED_TAG}, ", ""))
    return raw


def normal_floor(raw):
    """DECLARED CONSTRUCTED: the board on a 30F floor of the Angband dungeon (no quest)."""
    raw["floor"].update(dungeon_id=1, dungeon_name="アングバンド", level=30, quest_id=0)
    return raw


def new_policy(directory: Path, first, device_lists):
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

    def policy(self, first, device_lists=None):
        return new_policy(self.directory, first, lists() if device_lists is None else device_lists)

    def post(self, policy, raw, key, screens, following):
        """``key`` through the production decision send and the executor; the game's accepted keys,
        the send's result and the executor's completed board."""
        game = harness.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
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

    def powerful_screens(self):
        return [racial_screen(LEVEL, listed=False), racial_screen(LEVEL), prompt(TYPE_PROMPT),
                power_screen("staff", [("g", UNCURSE_NAME, 3, 3, 20), ("w", SPEED_NAME, 5, 5, 20)])]

    def normal_screens(self):
        return [prompt(TYPE_PROMPT),
                power_screen("staff", [("g", UNCURSE_NAME, 3, 3, 20), ("w", SPEED_NAME, 5, 5, 20)])]


class TheRecordingTest(_Replay):
    def test_the_recorded_hold_with_cursed_gear(self):
        decided = recorded()
        for turn in (BEFORE_CALL, HOLD, BEFORE_DRAIN, DRAINED, AFTER_DRAIN, LATER):
            self.assertEqual(decided[turn], (HOLD_REASON, "5"), turn)
        self.assertEqual(decided[CALLED][1], "mAw")
        cursed = [item for item in board(HOLD)["equipment"] if item.get("is_cursed")]
        self.assertEqual(len(cursed), 7)
        self.assertIn("★鉄鋲底の靴『炎の鉄ゲタ』が動物を引き寄せた！", board(CALLED)["messages"])
        self.assertIn("高速度のヘヴィ・クロスボウはあなたの体力を吸収した！", board(DRAINED)["messages"])
        self.assertEqual((board(DRAINED)["player"]["hp"], board(BEFORE_DRAIN)["player"]["hp"]), (586, 652))
        self.assertEqual(CASE["battle_record"]["battle"]["phase"], 0)
        self.assertEqual(CASE["battle_record"]["floor"], [0, 48, 25])


class ThePowerfulRemovalTest(_Replay):
    def test_the_hold_board_removes_the_curses_first(self):
        """The recorded hold board (HP 652): Powerful Activation of the absorbed Remove Curse before the
        hold, through the executor with its prompts answered; the plan holds again after it, the cost
        no hit."""
        raw = board(HOLD)
        policy = self.policy(raw)
        key = decide(policy, raw)
        self.assertEqual((policy.last_reason, key), (curse_cure.POWERFUL_REASON, "UAg"))
        following = uncursed(board(board_after(HOLD)))
        following["player"]["hp"] = raw["player"]["hp"] - 15
        accepted, sent, result, after = self.post(policy, raw, key, self.powerful_screens(), following)
        self.assertTrue(sent, result.stop_line)
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(accepted, ["U", "*", "b", "A", "g"])
        policy.confirm_key_posted(key)
        key = decide(policy, after)
        self.assertFalse(policy._took_damage)
        self.assertEqual((policy.last_reason, key), (HOLD_REASON, "5"))

    def test_a_curse_that_stays_is_learnt_permanent_and_not_retried(self):
        raw = board(HOLD)
        policy = self.policy(raw)
        key = decide(policy, raw)
        following = uncursed(board(board_after(HOLD)), keep=("arms",))
        _accepted, _sent, result, after = self.post(policy, raw, key, self.powerful_screens(), following)
        self.assertEqual(result.outcome, "completed", result.reason)
        policy.confirm_key_posted(key)
        key = decide(policy, after)
        gloves = next(item for item in parse_snapshot(after, policy._monrace_knowledge).equipment
                      if item.slot == "arms")
        self.assertIn(policy._item_signature(gloves), policy._permanent_cursed_items)
        self.assertEqual((policy.last_reason, key), (HOLD_REASON, "5"))

    def test_below_the_low_hp_line_after_the_cost_the_ordinary_use(self):
        """HP 370 of 652: the cost (21 at Lv33) would leave it at the low-HP line (max(50%, max - 300) =
        352): the ordinary use (``mAg``); the piece it leaves cursed is learnt heavy."""
        raw = board(HOLD)
        raw["player"]["hp"] = 370
        policy = self.policy(raw)
        self.assertFalse(powerful.pays_safely(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))
        key = decide(policy, raw)
        self.assertEqual((policy.last_reason, key), (curse_cure.NORMAL_OWNER, "mAg"))
        following = uncursed(board(board_after(HOLD)), keep=("arms",))
        following["player"]["hp"] = 370
        accepted, sent, result, after = self.post(policy, raw, key, self.normal_screens(), following)
        self.assertTrue(sent, result.stop_line)
        self.assertEqual(result.outcome, "completed", result.reason)
        self.assertEqual(accepted, ["m", "A", "g"])
        policy.confirm_key_posted(key)
        key = decide(policy, after)
        gloves = next(item for item in parse_snapshot(after, policy._monrace_knowledge).equipment
                      if item.slot == "arms")
        self.assertIn(policy._item_signature(gloves), policy._heavy_cursed_items)
        self.assertFalse(policy.last_reason.startswith(curse_cure.REASON), (policy.last_reason, key))

    def test_the_drain_hit_board_waits_and_the_next_board_removes(self):
        """The drain itself is a hit taken (utility_device_permitted): that board holds as recorded, the
        next one removes; the drained piece is remembered as announced."""
        policy = self.policy(board(BEFORE_DRAIN), lists(charges=0))
        decide(policy, board(BEFORE_DRAIN))      # no charge: the recorded hold
        policy._me_device_lists = lists()
        key = decide(policy, board(DRAINED))
        self.assertEqual((policy.last_reason, key), (HOLD_REASON, "5"))
        self.assertEqual(curse_cure._memory(policy).announced, {"bow": "高速度のヘヴィ・クロスボウ"})
        key = decide(policy, board(AFTER_DRAIN))
        self.assertEqual((policy.last_reason, key), (curse_cure.POWERFUL_REASON, "UAg"))

    def test_no_charge_holds_as_recorded(self):
        raw = board(HOLD)
        policy = self.policy(raw, lists(charges=0))
        self.assertEqual(decide(policy, raw), "5")
        self.assertEqual(policy.last_reason, HOLD_REASON)


class TheThreatTest(_Replay):
    def test_an_enemy_beside_the_player_is_answered_not_the_curse(self):
        """Turn 4123620: 黒王号 beside the player as the boots called it: no removal."""
        raw = board(CALLED)
        policy = self.policy(board(BEFORE_CALL))
        policy._me_device_lists = lists(charges=0)
        decide(policy, board(BEFORE_CALL))
        policy._me_device_lists = lists()
        key = decide(policy, raw)
        self.assertFalse(policy.last_reason.startswith(curse_cure.REASON), (policy.last_reason, key))
        self.assertFalse(curse_cure.safe(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)))


class TheRuleTwoTest(_Replay):
    def test_a_normal_floor_without_the_means_reads_recall(self):
        """A summoning curse announced on a normal floor and no Remove Curse absorbed: Word of Recall,
        the town return latched under its named trigger."""
        quiet = normal_floor(board(BEFORE_CALL))
        policy = self.policy(quiet, lists(uncurse=False))
        called = normal_floor(board(BEFORE_CALL))
        called["turn"] += 10
        called["messages"] = ["★鉄鋲底の靴『炎の鉄ゲタ』が動物を引き寄せた！"]
        key = decide(policy, called)
        self.assertEqual(policy.last_reason, curse_cure.RECALL_REASON, key)
        self.assertEqual(key[0], "r")
        self.assertEqual(policy._last_return_trigger, curse_cure.RECALL_TRIGGER)
        self.assertTrue(policy._returning_to_town)

    def test_a_normal_floor_without_a_summoning_curse_does_not_recall(self):
        quiet = normal_floor(board(BEFORE_CALL))
        policy = self.policy(quiet, lists(uncurse=False))
        later = normal_floor(board(BEFORE_CALL))
        later["turn"] += 10
        decide(policy, later)
        self.assertNotEqual(policy._last_return_trigger, curse_cure.RECALL_TRIGGER)
        self.assertNotEqual(policy.last_reason, curse_cure.RECALL_REASON)

    def test_the_once_quest_floor_goes_on(self):
        """The same announcement on the Q25 floor without the means: no Recall, the plan holds."""
        policy = self.policy(board(BEFORE_CALL), lists(uncurse=False))
        called = board(BEFORE_CALL)
        called["turn"] += 10
        called["messages"] = ["★鉄鋲底の靴『炎の鉄ゲタ』が動物を引き寄せた！"]
        key = decide(policy, called)
        self.assertEqual((policy.last_reason, key), (HOLD_REASON, "5"))
        self.assertTrue(curse_cure.remains(policy, parse_snapshot(copy.deepcopy(called), policy._monrace_knowledge)))
        self.assertNotEqual(policy._last_return_trigger, curse_cure.RECALL_TRIGGER)

    def test_with_the_means_the_normal_floor_removes_instead(self):
        quiet = normal_floor(board(BEFORE_CALL))
        policy = self.policy(quiet)
        called = normal_floor(board(BEFORE_CALL))
        called["turn"] += 10
        called["messages"] = ["★鉄鋲底の靴『炎の鉄ゲタ』が動物を引き寄せた！"]
        key = decide(policy, called)
        self.assertEqual((policy.last_reason, key), (curse_cure.POWERFUL_REASON, "UAg"))


def board_after(turn):
    turns = sorted(raw["turn"] for raw in CASE["boards"])
    return turns[turns.index(turn) + 1]


if __name__ == "__main__":
    import unittest
    unittest.main()
