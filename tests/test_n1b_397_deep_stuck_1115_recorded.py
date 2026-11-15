"""n1-b life-397's stuck Teleportation at full HP on Angband 79F (2026-11-15 10:48), and its cause.

Owner 2026-11-14 (verbatim): 「50F以降のテレポートの条件を厳しくする。深い階層のテレポートには
即死抽選があるためである。射線の通っている敵の合計予測被害95%が現在HPを上回るとき=即死のとき
のみ。当てはまらない時は破壊または近寄って破壊を試みる。」 and 「50F以降で破壊手段なしの探索は許可しない。
敵への対処以前に手段が尽きた時点で帰還させる。」  Owner 2026-11-15, asked how the stuck escape leaves
without the teleport: 「岩石溶解で掘る・だめなら帰還」.

Live (Magic-Eater Lv50, HP 918/918): at 10:47:48 (decision 22519) the absorbed Teleport Away
sent a 闇のエルフの影 off from beside the player at (20,69); the next board printed
「闇のエルフの影が消え去った！」.  The bot walked north into the treasure room's dead end (3-9,
66-70), searched its walls, and at 10:48:02 (decision 22651, turn 5735278) the stuck escape read
Teleportation ('rh', ``stuck:destroyed-circle-teleport``) with no monster in view and the sum of
the p95 with a line of fire 0; it landed beside a dragon pit and died before its next turn.

Why it was stuck: the shadow stayed remembered awake at its last shown cell
(sleeper_reach_memory), and its area (rows 13-29 around (21,70)) was the routes' veto (policy
``_engagement_danger_cells``) across the one corridor south.  The descent walk found no route to
the down stairs the player had arrived by (56,53) and expired it, the explore found no frontier,
the secret-wall search ran the stuck count to STUCK_ESCAPE_LIMIT.  The game prints
「<name>が消え去った！」 for a monster a teleport moved (effect/effect-monster.cpp:546), so the
remembered cell no longer holds it (sleeper_loot_block ``shows_sent_away``).

Recorded: tests/fixtures/n1b-397-deep-stuck-1115.jsonl.gz
(tests/extract_n1b_397_deep_stuck_1115_fixture.py), the ~f skill list and the 268 boards of the
79F visit with their decision records, every board through the public ``choose_key`` of one
fresh policy, each carrying the previous decision's reason as the CLI adds it.
DECLARED CONSTRUCTED: the absorbed power lists the live process had read and the capture does not
carry (the staffs *破壊* 6/9, 周辺感知 and ドア/階段感知; the rod テレポート・アウェイ), so the replay
takes the live *Destruction* and Teleport Away of the window; the descent deferral of the
``stuck:ascend`` that brought the player up from 80F (``_defer_descent`` on the first board);
for the stuck board as the live policy saw it, the sent-away line not read (``shows_sent_away``
patched to False); the absorbed Stone to Mud (wand 岩石溶解, 10 charges) listed before the stuck
board; the 即死 board (``fire_p95`` at the HP plus one); the visit at 49F (every board's level).
The fresh policy reaches the stuck count on turn 5735250, two boards before the live read.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

from contextlib import nullcontext
import copy
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from hengbot import area_mapping, deep_teleport, retreat_enclosure, sealed_pocket, sleeper_loot_block, sleeper_reach_memory
from hengbot.me_absorbed_substitutes import CAST_SUFFIX
from hengbot.me_device_attacks import observe_lists
from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import STUCK_ESCAPE_LIMIT
from tests import test_me_nokey_1031_recorded as nokey
from tests.support.recorded import EDIT, READ_PROMPT, _policy, prompt_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_list, power_screen, row


FIXTURE = Path(__file__).with_name("fixtures") / "n1b-397-deep-stuck-1115.jsonl.gz"
FIXTURE_SHA256 = "d56e92f953272be1eb7bf68d48a3255de4171909a679988ffe9eaf151d030c92"
LIVE_TURN = 5735278          # decision 22651: 'rh' stuck:destroyed-circle-teleport
SENT_AWAY_TURN = 5734457     # the board after 22519 'mCn3', 「闇のエルフの影が消え去った！」
SHADOW = "闇のエルフの影"
ARRIVAL_STAIRS = Position(56, 53)
DEAD_END = Position(9, 66)
CORRIDOR = Position(20, 69)  # the one way south out of the dead end
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
DIRECTION_PROMPT = "方向 ('*'でターゲット選択, ESCで中断)? "
STUCK_REASONS = ("stuck:", "livelock:")


def _rows():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


ROWS = _rows()
SKILL = next(row["board"] for row in ROWS if row["role"] == "skill-knowledge")
BOARDS = [row["board"] for row in ROWS if row["role"] == "board"]
DECISIONS = {row["decision"]["turn"]: row["decision"] for row in ROWS if row["role"] == "decision"}
MONRACE = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
_REPLAYS = {}


def _listed(policy, raw, turn, listed):
    observe_lists(policy, parse_snapshot(dict(copy.deepcopy(raw), turn=turn,
                                              _magic_eater_power_list=listed), MONRACE))


def _replay(*, sent_away=True, level=None):
    """The visit replayed up to the first stuck escape (or its end): (policy, raw, key, reasons),
    the policy and raw of the board before that decision (deep copies, decided again by each
    test), the decided key and every reason decided."""
    config = (sent_away, level)
    if config not in _REPLAYS:
        directory = TemporaryDirectory()
        boards = copy.deepcopy(BOARDS)
        if level is not None:
            for raw in boards:
                raw["floor"]["level"] = level
        policy = _policy(Path(directory.name), MONRACE)
        first = parse_snapshot(copy.deepcopy(boards[0]), MONRACE)
        policy.prime(first)
        policy.consume_skill_knowledge({**SKILL, "player": {"level": first.player.level}})
        _listed(policy, boards[0], boards[0]["turn"] - 2, power_list(
            "staff", row("*破壊*", 5, current=6, count=9), row("周辺感知", 5, current=3, count=3),
            row("ドア/階段感知", 5, current=3, count=3)))
        _listed(policy, boards[0], boards[0]["turn"] - 1, power_list(
            "rod", row("テレポート・アウェイ", 5, charging=False, count=1)))
        policy._defer_descent(first)
        reasons, previous, result = [], None, None
        patch = (nullcontext() if sent_away else mock.patch.object(
            sleeper_loot_block, "shows_sent_away", lambda snapshot, name: False))
        with patch:
            for index, raw in enumerate(boards):
                raw = copy.deepcopy(raw)
                if previous is not None:
                    raw["_completed_operation_owner"] = previous
                # The policy before the decision, kept where a stuck escape can answer (a deep
                # copy a board is slow): the count one short of its limit, or the last board.
                before = ((copy.deepcopy(policy), copy.deepcopy(raw))
                          if policy._stuck_escape_streak >= STUCK_ESCAPE_LIMIT - 1
                          or index == len(boards) - 1 else (None, None))
                key = policy.choose_key(policy.with_known_skill_exp(parse_snapshot(raw, MONRACE)))
                previous = policy.last_reason
                reasons.append((raw["turn"], previous))
                result = (*before, key)
                if previous.startswith(STUCK_REASONS):
                    assert before[0] is not None, (raw["turn"], previous)
                    break
                if key:
                    policy.confirm_key_posted(key)
            _REPLAYS[config] = (policy, result, reasons, directory)
    policy, (before_policy, before_raw, key), reasons, _directory = _REPLAYS[config]
    return policy, copy.deepcopy(before_policy), copy.deepcopy(before_raw), key, reasons


def _decide(policy, raw, *, sent_away=False):
    """``raw`` decided by ``policy``: (key, reason, the board)."""
    board = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), MONRACE))
    if sent_away:
        return policy.choose_key(board), policy.last_reason, board
    with mock.patch.object(sleeper_loot_block, "shows_sent_away", lambda snapshot, name: False):
        return policy.choose_key(board), policy.last_reason, board


def _with_stone_to_mud(policy, raw):
    _listed(policy, raw, raw["turn"] - 1, power_list("wand", row("岩石溶解", 5, current=10, count=10)))


class RecordedWindowTest(unittest.TestCase):
    def test_the_live_rows(self):
        live = DECISIONS[LIVE_TURN]
        self.assertEqual((live["decision_sequence"], live["reason"], live["key"]),
                         (22651, "stuck:destroyed-circle-teleport", "rh"))
        last = BOARDS[-1]
        self.assertEqual(last["turn"], LIVE_TURN)
        self.assertEqual((last["floor"]["level"], last["player"]["hp"], last["player"]["max_hp"]),
                         (79, 918, 918))
        self.assertEqual((last["player"]["y"], last["player"]["x"]), (DEAD_END.y, DEAD_END.x))
        self.assertEqual(last["visible_monsters"], [])
        away = next(raw for raw in BOARDS if raw["turn"] == SENT_AWAY_TURN)
        self.assertIn(SHADOW + "が消え去った！", away["messages"])
        self.assertEqual(DECISIONS[SENT_AWAY_TURN - 4]["reason"],
                         "me-power:unbeatable-in-range:teleport-away")


class SentAwayForgottenTest(unittest.TestCase):
    """The stuck judgement was wrong: the sent-away shadow's area walled the corridor off."""

    def test_the_replay_matches_the_live_stuck_without_the_fix(self):
        """The control: the sent-away line not read, the fresh policy reaches the live stuck
        board with the shadow remembered at its last cell and the arrival stairs expired."""
        policy, before, raw, _key, reasons = _replay(sent_away=False)
        turn, reason = reasons[-1]
        self.assertEqual(reason, deep_teleport.STUCK_RECALL_REASON)
        self.assertEqual(turn, 5735250)
        self.assertEqual(before._stuck_escape_streak, STUCK_ESCAPE_LIMIT - 1)
        board = parse_snapshot(copy.deepcopy(raw), MONRACE)
        self.assertIn(SHADOW, [m.name for m in sleeper_reach_memory.remembered(before, board)])
        self.assertIn(ARRIVAL_STAIRS, before._nav_ledger.expired_targets("descend"))
        self.assertIn(CORRIDOR, before._engagement_danger_cells(board))
        # the live process's teleport-away 'mCn3' was replayed
        self.assertIn((SENT_AWAY_TURN - 4, "me-power:unbeatable-in-range:teleport-away"), reasons)

    def test_the_sent_away_monster_is_forgotten_and_the_way_down_stays(self):
        policy, _before, raw, key, reasons = _replay(sent_away=True)
        self.assertIn((SENT_AWAY_TURN - 4, "me-power:unbeatable-in-range:teleport-away"), reasons)
        self.assertEqual(raw["turn"], LIVE_TURN)  # no stuck escape through the window
        self.assertFalse([reason for _turn, reason in reasons if reason.startswith(STUCK_REASONS)])
        self.assertNotEqual(key, "rh")
        board = parse_snapshot(copy.deepcopy(raw), MONRACE)
        self.assertNotIn(SHADOW, [m.name for m in sleeper_reach_memory.remembered(policy, board)])
        self.assertNotIn(ARRIVAL_STAIRS, policy._nav_ledger.expired_targets("descend"))
        self.assertNotIn(CORRIDOR, policy._engagement_danger_cells(board))
        self.assertLess(policy._stuck_escape_streak, STUCK_ESCAPE_LIMIT)

    def test_the_line_names_the_monster(self):
        board = parse_snapshot(copy.deepcopy(next(raw for raw in BOARDS if raw["turn"] == SENT_AWAY_TURN)),
                               MONRACE)
        self.assertTrue(sleeper_loot_block.shows_sent_away(board, SHADOW))
        self.assertFalse(sleeper_loot_block.shows_sent_away(board, "イークの観光客"))
        self.assertFalse(sleeper_loot_block.shows_sent_away(
            replace(board, messages=(SHADOW + "は消え去った！",)), SHADOW))


class DeepStuckTest(nokey.PostedKey):
    """The stuck board as the live policy saw it (the sent-away line not read)."""

    def test_without_stone_to_mud_recall_is_read(self):
        """Live 'rh' (Teleportation); now Word of Recall, the reason named."""
        _policy_after, policy, raw, _key, _reasons = _replay(sent_away=False)
        key, reason, board = _decide(policy, raw)
        recall = next(item for item in board.inventory if item.is_recall_scroll)
        self.assertEqual((key, reason), ("r" + recall.slot, deep_teleport.STUCK_RECALL_REASON))
        self.assertTrue(policy._returning_to_town)
        self.assertFalse(deep_teleport.allows(policy, board))
        self.assertEqual(deep_teleport.fire_p95(policy, board), 0)
        self.post(policy, raw, key, screens=(prompt_screen(READ_PROMPT),))

    def test_with_stone_to_mud_the_way_is_melted(self):
        """The absorbed Stone to Mud first: the melt along the route that melts the fewest walls
        to a known staircase or a frontier, sent through the executor."""
        _policy_after, policy, raw, _key, _reasons = _replay(sent_away=False)
        _with_stone_to_mud(policy, raw)
        key, reason, board = _decide(policy, raw)
        self.assertEqual(reason, deep_teleport.STUCK_MELT_REASON + CAST_SUFFIX)
        self.assertTrue(key.startswith("mBg"), key)
        self.assertFalse(policy._returning_to_town)
        # The melt holds the stuck count: the escape goes on to the goal.
        self.assertIn(reason, deep_teleport.STUCK_HELD_REASONS)
        self.post(policy, raw, key, screens=(
            prompt(TYPE_PROMPT), power_screen("wand", [("g", "岩石溶解", 10, 10, 5)]),
            prompt(DIRECTION_PROMPT, "direction", can_choose_target=True)))
        # The next board (the wall still shown: the beam failed): the count held, the escape
        # goes on along the route.
        policy.confirm_key_posted(key)
        later = dict(copy.deepcopy(raw), turn=raw["turn"] + 10, messages=[],
                     _completed_operation_owner=reason)
        again, reason_again, _board = _decide(policy, later)
        self.assertGreaterEqual(policy._stuck_escape_streak, STUCK_ESCAPE_LIMIT)
        self.assertEqual(reason_again, reason)
        self.assertTrue(again.startswith("mBg"), again)

    def test_a_reachable_goal_is_walked_to(self):
        """DECLARED CONSTRUCTED: the stuck board with the routes' danger veto empty (the stuck
        judgement wrong): the arrival stairs are walkable, so the walk goes there, no read."""
        _policy_after, policy, raw, _key, _reasons = _replay(sent_away=False)
        with mock.patch.object(type(policy), "_engagement_danger_cells",
                               lambda self, snapshot: frozenset()):
            key, reason, board = _decide(policy, raw)
            self.assertEqual(reason, deep_teleport.STUCK_WALK_REASON)
            self.assertIsNotNone(policy._nearest_goal_step(
                board, lambda grid: grid.position == ARRIVAL_STAIRS))
        self.assertIn(key, "12346789")
        self.assertIn(reason, deep_teleport.STUCK_HELD_REASONS)
        self.assertFalse(policy._returning_to_town)

    def test_the_instant_death_board_still_teleports(self):
        _policy_after, policy, raw, _key, _reasons = _replay(sent_away=False)
        with mock.patch.object(deep_teleport, "fire_p95",
                               lambda policy, snapshot: snapshot.player.hp + 1):
            key, reason, _board = _decide(policy, raw)
        self.assertEqual((key, reason), ("rh", "stuck:destroyed-circle-teleport"))

    def test_at_49f_the_old_order_stays(self):
        _policy_after, policy, raw, key, reasons = _replay(sent_away=False, level=49)
        self.assertEqual(reasons[-1][1], "stuck:destroyed-circle-teleport")
        self.assertEqual(key, "rh")


class TeleportAskersTest(unittest.TestCase):
    """Every asker of the teleport on the stuck board, asked directly (the board as the live
    policy saw it): no Teleportation is read."""

    def board(self, raw=None):
        _policy_after, policy, recorded, _key, _reasons = _replay(sent_away=False)
        raw = recorded if raw is None else raw
        return policy, policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), MONRACE))

    def test_the_circle_leave_reads_no_teleport(self):
        """sealed_pocket.destroyed_leave_key (the live 'rh'): None, the asker's next means."""
        policy, board = self.board()
        self.assertTrue(area_mapping.destroyed_since_arrival(policy, board))
        self.assertIsNone(sealed_pocket.destroyed_leave_key(policy, board))

    def test_the_enclosure_leave_reads_recall(self):
        policy, board = self.board()
        self.assertIsNone(retreat_enclosure._read_teleport(policy, board))
        key = retreat_enclosure._leave_key(policy, board)
        self.assertEqual(policy.last_reason, deep_teleport.STUCK_RECALL_REASON)
        self.assertTrue(key.startswith("r"), key)

    def test_any_read_of_teleportation_off_the_instant_death_board_is_recall(self):
        """``_read_key`` (every rung's read), with the board's awake yeeks known by detection
        (14-17 cells away, the sum with a line of fire 0) and, DECLARED CONSTRUCTED, without any
        monster: the substitute answers with Recall."""
        for monsters in (True, False):
            with self.subTest(monsters=monsters):
                raw = copy.deepcopy(_replay(sent_away=False)[2])
                if not monsters:
                    raw["detected_monsters"] = []
                policy, board = self.board(raw)
                self.assertEqual(bool(deep_teleport.concerned(policy, board)), monsters)
                teleport = next(item for item in board.inventory if item.is_teleport_scroll)
                recall = next(item for item in board.inventory if item.is_recall_scroll)
                key = policy._read_key(board, teleport)
                self.assertEqual((key, policy.last_reason),
                                 ("r" + recall.slot, deep_teleport.RECALL_REASON))

    def test_without_recall_the_stuck_escape_reads_nothing(self):
        """DECLARED CONSTRUCTED: the stuck board without the Recall scrolls: no means, so the
        stuck escape answers nothing and no teleport is read (the floor's ladder goes on)."""
        raw = copy.deepcopy(_replay(sent_away=False)[2])
        raw["inventory"] = [item for item in raw["inventory"] if item["sval"] != 11 or item["tval"] != 70]
        policy, board = self.board(raw)
        self.assertIsNone(deep_teleport.stuck_key(policy, board))
        key, reason, _board = _decide(self.board(raw)[0], raw)
        self.assertNotEqual(key, "rh")
        self.assertFalse(reason.endswith("teleport"), reason)

    def test_with_no_monster_and_no_recall_a_teleport_read_holds(self):
        """DECLARED CONSTRUCTED: the stuck board without the Recall scrolls and the detected
        monsters: a read of Teleportation is a search turn, nothing read."""
        raw = copy.deepcopy(_replay(sent_away=False)[2])
        raw["inventory"] = [item for item in raw["inventory"] if item["sval"] != 11 or item["tval"] != 70]
        raw["detected_monsters"] = []
        policy, board = self.board(raw)
        teleport = next(item for item in board.inventory if item.is_teleport_scroll)
        self.assertEqual((policy._read_key(board, teleport), policy.last_reason),
                         ("s", deep_teleport.HOLD_REASON))

if __name__ == "__main__":
    unittest.main()
