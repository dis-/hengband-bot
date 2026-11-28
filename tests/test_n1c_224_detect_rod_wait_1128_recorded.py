"""The wait for the Rod of Detection on 50F+ ends (n1-c life-224, Angband 95F, 2026-11-28 16:45:45,
stationary:exhausted:deep-detection-rod:wait-recharge).

n1-c life-224 (zombie Magic-Eater CL44, speed +25, HP 948/948, no monster in view) stood at (24,74)
on Angband 95F with a neighbour not trap-detected (the board's unsafe_rows) and rested ``R10``
49 times, turns 7558860-7560220, for its absorbed Rod of Detection (4 rods), until the stationary
bound (DETECTION_ROD_RECHARGE_MAX_GAME_TURNS, 1090 game turns) stopped it.  The rod list the bot
read was the one last shown, at or before the last cast (``UCg``, turn 7557556); nothing showed it
again while it rested.  The game had the rod ready long before: 4 rods at INT 18/12 (stat_index 16,
adj_mag_mana 11) shed 19 of a cast's 1584 a tick unrested (rod_recharge), 84 ticks at most, so by
7558396 -- before the wait began.  The absorbed Detect Traps staff (44 charges) was not used.

Fixture n1c-224-detect-rod-wait-1128.jsonl.gz: every player_turn board of that floor from the
restart of 16:44:35 (turn 7556967) to the stop (7560220), 770 boards (``_same`` rows as
tests/support/finale_416.boards expands them); tests/extract_n1c_224_detect_rod_wait_1128_fixture.py.
Replayed open-loop through ``HengbotPolicy.choose_key`` (the stationary accounting included), from
the board of the last cast.

DECLARED RECONSTRUCTED: the absorbed-device lists (the snapshot files carry none): the lists of the
town-arrival policy of 16:40:29 (turn 7554943, its rod Detection row "4 of 4 charging"), shown at
the replay's first board (the last cast); a browse of the rod list (``bC``) is answered on the next
board with the rod list the game would show, the Detection charge from the last cast shed at the
unrested rate (rod_recharge).  DECLARED: ``_me_power_resume_reads`` as the CLI sets it.
DECLARED CONSTRUCTED: the variant without the Detect Traps staff, and that variant without the
resume reads (no browse).
"""
import tests  # noqa: F401 -- isolate live runtime files

import contextlib
import copy
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import deep_detection_rod, me_powers_refresh, rod_recharge, stationary_bounds
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support import finale_416
from tests.support.recorded import EDIT, _policy

FIXTURE = "n1c-224-detect-rod-wait-1128.jsonl.gz"
# The turn-free browse of the rod list (me_powers_refresh).
ROD_BROWSE = "b" + me_powers_refresh.KIND_LETTER["rod"]
LAST_CAST = 7557556   # the last UCg (Powerful Activation of the absorbed Detection)
WAIT_BEGAN = 7558860  # the recorded first wait-recharge
STOP = 7560220        # the recorded stop
DETECTION = "全感知"
DETECT_TRAPS = "トラップ感知"
COUNT = 4
INT_INDEX = 16
# The town-arrival policy's lists (16:40:29): (name, current or charging, max).
STAFF = (("軽傷の治癒", 57, 57), ("癒し", 22, 22), ("体力回復", 4, 4), ("テレポート", 21, 21),
         ("鑑定", 68, 68), ("解呪", 11, 11), ("スピード", 69, 69), ("スターライト", 40, 40),
         ("光", 54, 54), ("邪悪存在退散", 25, 25), ("周辺感知", 23, 23), ("力", 9, 9),
         ("財宝感知", 96, 96), ("アイテム感知", 41, 41), (DETECT_TRAPS, 44, 44), ("地震", 20, 20),
         ("ドア/階段感知", 60, 60), ("*破壊*", 29, 29), ("透明物体感知", 10, 10),
         ("邪悪存在感知", 42, 42))
WAND = (("アシッド・ボルト", 43, 43), ("ファイア・ボルト", 37, 37), ("テレポート・アウェイ", 82, 82),
        ("アイス・ボルト", 36, 36), ("トラップ解除", 23, 23), ("アシッド・ボール", 16, 16),
        ("トラップ/ドア破壊", 99, 99), ("サンダー・ボール", 40, 40), ("岩石溶解", 99, 99),
        ("ファイア・ボール", 11, 11), ("光", 37, 37), ("アイス・ボール", 32, 32),
        ("ドラゴンの火炎", 6, 7), ("ドラゴンの冷気", 9, 9), ("衰弱", 11, 11),
        ("ドラゴン・ブレス", 5, 5), ("ロケット", 4, 4), ("悪臭雲", 80, 80),
        ("マジック・ミサイル", 36, 36))
ROD = ((DETECT_TRAPS, 0, 11), ("光", 0, 8), ("ドア/階段感知", 0, 7), ("帰還", 0, 3),
       ("イルミネーション", 0, 17), ("周辺感知", 0, 2), ("アシッド・ボルト", 0, 9),
       (DETECTION, COUNT, COUNT), ("サンダー・ボルト", 0, 14), ("ファイア・ボルト", 0, 10),
       ("癒し", 0, 1), ("アイス・ボルト", 0, 17), ("アシッド・ボール", 0, 8),
       ("サンダー・ボール", 0, 3), ("ファイア・ボール", 0, 2), ("害虫駆除", 0, 7),
       ("アイス・ボール", 0, 5), ("テレポート・アウェイ", 0, 1), ("トラップ解除", 0, 10),
       ("岩石溶解", 0, 2))


def _rows(kind, table):
    if kind == "rod":
        return tuple({"name": name, "charging": charging, "max": count, "fail": 6, "success": 94}
                     for name, charging, count in table)
    return tuple({"name": name, "current": current, "max": count, "fail": 6, "success": 94}
                 for name, current, count in table)


def _rod_rows_at(turn):
    """The rod list the game shows at ``turn``: the Detection charge of the last cast (4 rods
    charging, at most 4 x 1584) shed at the unrested rate since."""
    shed = rod_recharge.absorbed_shed_per_tick(COUNT, INT_INDEX, rod_recharge.PY_REGEN_NORMAL)
    full = COUNT * rod_recharge.DETECTION_ROD_PVAL * rod_recharge.EATER_ROD_CHARGE
    charge = max(0, full - shed * ((turn - LAST_CAST) // rod_recharge.TURNS_PER_TICK))
    per_rod = rod_recharge.DETECTION_ROD_PVAL * rod_recharge.EATER_ROD_CHARGE
    charging = (charge - 1) // per_rod + 1 if charge > 0 else 0
    return tuple((name, charging if name == DETECTION else shown, count)
                 for name, shown, count in ROD)


def drive(*, staff=STAFF, resume_reads=True):
    """(turn, (y, x), key, reason) of each board from the last cast to the stop."""
    monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
    raw_boards = [row for row in finale_416.boards(FIXTURE) if LAST_CAST <= row["turn"] <= STOP]
    directory = TemporaryDirectory()
    try:
        policy = _policy(Path(directory.name), monrace)
        first = policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw_boards[0]), monrace))
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_power_resume_reads = resume_reads
        turn = first.turn
        policy._me_device_lists = {"staff": (turn, _rows("staff", staff)),
                                   "wand": (turn, _rows("wand", WAND)),
                                   "rod": (turn, _rows("rod", ROD))}
        decided, owner, browsed = [], None, False
        for raw in raw_boards:
            raw = copy.deepcopy(raw)
            if owner:
                raw["_completed_operation_owner"] = owner
            if browsed:
                raw["_magic_eater_power_list"] = {"kind": "rod",
                                                  "rows": list(_rows("rod", _rod_rows_at(raw["turn"])))}
            board = policy.with_known_skill_exp(parse_snapshot(raw, monrace))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                key = policy.choose_key(board)
            decided.append((board.turn, (board.player.position.y, board.player.position.x), key,
                            policy.last_reason))
            owner = policy.last_reason if key else None
            browsed = key == ROD_BROWSE and policy.last_reason == me_powers_refresh.REFRESH_REASON
            if key:
                policy.confirm_key_posted(key)
        return decided
    finally:
        directory.cleanup()


def _stops(rows):
    return [row for row in rows if row[2] is None or stationary_bounds.is_stop(row[3] or "")]


def _waits_from(rows, start):
    return [row for row in rows if row[0] >= start and row[3] == deep_detection_rod.WAIT_REASON]


class DetectRodWaitRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recorded = drive()
        cls.without_staff = drive(staff=tuple(row for row in STAFF if row[0] != DETECT_TRAPS))
        cls.unread = drive(staff=tuple(row for row in STAFF if row[0] != DETECT_TRAPS),
                           resume_reads=False)

    def test_the_span_is_longer_than_the_old_bound(self):
        self.assertGreater(STOP - WAIT_BEGAN, stationary_bounds.DETECTION_ROD_RECHARGE_MAX_GAME_TURNS)
        self.assertEqual(self.recorded[-1][0], STOP)

    def test_no_halt_and_no_empty_key(self):
        for rows in (self.recorded, self.without_staff, self.unread):
            self.assertEqual(_stops(rows), [], [row for row in rows if row[0] >= WAIT_BEGAN][:60])

    def test_the_detect_traps_staff_answers_the_undetected_step(self):
        # The board of the recorded first wait: the absorbed Detect Traps staff (44 charges) is cast
        # (me_powers' deep-undetected-step), not a rest for the rod.
        at = next(row for row in self.recorded if row[0] == WAIT_BEGAN)
        self.assertEqual(at[3], "me-power:deep-undetected-step:detect-traps", at)
        self.assertEqual(_waits_from(self.recorded, WAIT_BEGAN), [])

    def test_without_the_staff_the_rod_list_is_shown_again_and_the_rod_cast(self):
        rows = [row for row in self.without_staff if row[0] >= WAIT_BEGAN]
        browse = next(n for n, row in enumerate(rows) if row[2] == ROD_BROWSE)
        # At most one rest before the list is read again (the rested rate had it ready at 7557976).
        self.assertLessEqual(len(_waits_from(rows[:browse], WAIT_BEGAN)), 1, rows[:browse + 3])
        cast = rows[browse + 1]
        self.assertTrue((cast[3] or "").startswith("me-power:deep-undetected-step:detect-all"), rows[:browse + 3])

    def test_a_list_not_shown_again_ends_the_wait_at_the_real_recharge(self):
        # No browse (a policy without the CLI's resume reads): 4 rods at stat_index 16 recharge in
        # 84 ticks at most from a cast (rod_recharge), so no rest past the first one + 840.
        waits = _waits_from(self.unread, WAIT_BEGAN)
        self.assertTrue(waits, [row for row in self.unread if row[0] >= WAIT_BEGAN][:10])
        latest = waits[0][0] + rod_recharge.game_turns(
            rod_recharge.absorbed_ready_ticks(COUNT, COUNT, INT_INDEX, rod_recharge.PY_REGEN_NORMAL))
        self.assertEqual([row for row in waits if row[0] > latest], [])
        self.assertLess(latest - waits[0][0], stationary_bounds.DETECTION_ROD_RECHARGE_MAX_GAME_TURNS)

if __name__ == "__main__":
    unittest.main()
