"""n1-c life-219's death on Angband 80F (2026-11-22 05:56, killed by 混沌), recorded.

1. The room light on 50F+.  Owner 2026-11-22 (asked 「深層ではライトエリアを使わないように指定した
   はずだが？」, answered 「50F以降は使わない」): the absorbed Light's dark-room trigger lit the room
   at (37,17) after the Teleportation landing (decision 14431, ``mAi``), and the next board says
   「白い光が辺りを覆った。」「『マダム・デビ』が目を覚ました。」 (the room light wakes every SMART
   sleeper it reaches, spell-kind/spells-lite.cpp cave_temp_room_lite); her confusion, nether and
   chaos breaths then took 180, 300 and 298.  The first light of the floor (decision 14051) woke a
   ゲイザー and a 古代レッド・ドラゴン.  Fixed: me_powers' Light row answers neither the dark room
   nor the zero light radius on a DEEP_FLOOR_DEPTH floor; 49F lights as before.

2. The monsters in view and the 50F+ 即死 test.  Owner 2026-11-14 「射線の通っている敵の合計予測
   被害95%が現在HPを上回るとき=即死のときのみ」 (deep_teleport).  Decision 14428 (HP 766/916, twelve
   混沌 in view, the absorbed *Destruction* spent, Recall counting down): the absorbed mapping of
   decision 14419 had drawn the rock west of the player (the board of 2751620 still shows it), the
   KILL_WALL swarm dug it into floor the game no longer marks, and the map memory
   (``_with_grid_memory``) kept the walls: nine of the twelve 混沌 in view read no line of fire
   (line_of_fire ``danger``), the sum in fire was 517, no Teleportation was offered
   (deep_teleport ``no_means``) and the bot sent ``qd`` (``emergency:heal``); the next board (HP
   600, two more stat drains) read the scroll.  Fixed: a monster in view has a line (the view is
   the game's line of sight), only known glass and the spell range stopping it; the board reads
   the scroll (``rg``) at 766.

Recorded: tests/fixtures/n1c-219-death-1122.pkl.xz (tests/extract_n1c_219_death_1122_fixture.py):
the town-arrival checkpoint of 05:54:32 and the boards of decisions 14051, 14424, 14428, 14429
and 14431 with their recorded keys.
DECLARED CONSTRUCTED: the checkpoint predates the dive, so the dive's state is rebuilt: (1) the
floor memory of me_powers is started on the asked board (``me_powers.observe``) and only the
dark-room trigger is asked (``power_key(..., only="dark-room")``); (2) the absorbed *Destruction*'s
displayed charges are emptied (the live floor spent its nine and the decision log reads it
missing from decision 14418 on), and the map memory is fed the board of 2751620 before the board
of 2751647 (the live memory had seen it).  The 49F control rewrites the board's floor level.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import lzma
import pickle
import unittest
from pathlib import Path

from hengbot import deep_teleport, destruction_use, line_of_fire, me_powers
from hengbot.latch_onset_capture import restore_checkpoint_bytes
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-219-death-1122.pkl.xz"
CASE = pickle.loads(lzma.decompress(FIXTURE.read_bytes()))
FIRST_LIGHT, MAPPED, HEAL, TELEPORT, LANDING_LIGHT = 2749569, 2751620, 2751647, 2751654, 2751669
UNMAKER = 815  # 混沌


def restored():
    return restore_checkpoint_bytes(HengbotPolicy, CASE["checkpoint"])


def board(policy, turn, level=None):
    raw = copy.deepcopy(CASE["boards"][turn])
    if level is not None:
        raw["floor"]["level"] = level
    return parse_snapshot(raw, policy._monrace_knowledge)


class RecordedRowsTest(unittest.TestCase):

    def test_recorded_keys(self):
        self.assertEqual(CASE["decisions"], {
            FIRST_LIGHT: ("mAi", "me-power:dark-room:lite-area"),
            MAPPED: ("5", "return:wait-recall"),
            HEAL: ("qd", "emergency:heal"),
            TELEPORT: ("rg", "emergency:teleport"),
            LANDING_LIGHT: ("mAi", "me-power:dark-room:lite-area"),
        })
        self.assertEqual(CASE["boards"][HEAL]["player"]["hp"], 766)
        self.assertEqual(CASE["boards"][TELEPORT]["player"]["hp"], 600)


class DeepRoomLightTest(unittest.TestCase):

    def dark_room_key(self, turn, level=None):
        policy = restored()
        snapshot = board(policy, turn, level)
        me_powers.observe(policy, snapshot)
        return me_powers.power_key(policy, snapshot, me_powers.FLOOR, only="dark-room"), policy

    def test_the_landing_room_is_not_lit_on_80f(self):
        key, policy = self.dark_room_key(LANDING_LIGHT)
        self.assertIsNone(key)
        self.assertNotEqual(policy.last_reason, "me-power:dark-room:lite-area")

    def test_the_first_dark_room_of_the_floor_is_not_lit(self):
        key, _ = self.dark_room_key(FIRST_LIGHT)
        self.assertIsNone(key)

    def test_control_the_same_room_on_49f_is_lit(self):
        key, policy = self.dark_room_key(LANDING_LIGHT, level=49)
        self.assertEqual((key, policy.last_reason), ("mAi", "me-power:dark-room:lite-area"))

    def test_the_sleeping_breather_was_in_the_room_light_reach(self):
        # 『マダム・デビ』 (SMART: the room light always wakes her) asleep within the light's reach
        # on the board the light was cast from; her blows are insults, so the old melee-only
        # strength judgment never kept the room dark for her.
        policy = restored()
        snapshot = board(policy, LANDING_LIGHT)
        debby = [m for m in snapshot.detected_monsters if m.race_id == 1032]
        self.assertEqual(len(debby), 1)
        self.assertTrue(debby[0].asleep)
        self.assertIn("SMART", policy._monrace_knowledge[1032].flags)


class InViewLineOfFireTest(unittest.TestCase):

    def heal_board(self):
        policy = restored()
        lists = policy._me_device_lists
        turn, rows = lists["staff"]
        emptied = tuple(dict(row, current=0) if row["name"] == "*破壊*" else row for row in rows)
        self.assertNotEqual(emptied, rows)
        policy._me_device_lists = dict(lists, staff=(turn, emptied))
        policy._with_grid_memory(board(policy, MAPPED))
        return policy, board(policy, HEAL)

    def test_the_constructed_board(self):
        policy, snapshot = self.heal_board()
        self.assertTrue(destruction_use.means_spent(policy, snapshot))
        self.assertTrue(snapshot.player.recalling)
        in_view = [m for m in snapshot.visible_monsters if m.race_id == UNMAKER]
        self.assertEqual(len(in_view), 12)

    def test_every_unmaker_in_view_has_a_line_of_fire(self):
        policy, snapshot = self.heal_board()
        merged = policy._with_grid_memory(snapshot)
        self.assertTrue(all(line_of_fire.danger(policy, merged, monster)
                            for monster in merged.visible_monsters if monster.race_id == UNMAKER))

    def test_the_teleport_is_read_on_the_instant_death_board(self):
        policy, snapshot = self.heal_board()
        key = policy.choose_key(snapshot)
        self.assertEqual((key, policy.last_reason), ("rg", "emergency:teleport"))
        merged = policy._with_grid_memory(snapshot)
        self.assertGreaterEqual(deep_teleport.fire_p95(policy, merged), snapshot.player.hp)


if __name__ == "__main__":
    unittest.main()
