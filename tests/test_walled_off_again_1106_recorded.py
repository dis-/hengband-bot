"""Walled off again by a retreat's vetoes after the floor's Teleportation: dig, disarm, strike, then
Teleportation again or Recall.

Owner 2026-11-06: 「壁を掘る、罠を解除する、弱い敵なら倒すことを試みる。ダメならテレポートを使用し、
巻物が規定数以下になれば帰還。」, on a random quest floor too (retreat_enclosure.walled_off_key).

Recorded: n1-b life-317, Angband 50F, RANDOM quest 40 (tests/test_quest_loop_dwell_1106_recorded:
the fixture quest-loop-dwell-1106, its column (3..7, 93) of vetoes and the stop's last board).
The recorded kit: no digging tool, 15 Teleportation, 10 Recall.  The first Teleportation is read
and posted through the production executor; each test then decides the stop's board 10 game
turns later, walled off again (DECLARED: the read landed on this side).

DECLARED CONSTRUCTED, besides those of the recorded test: the half-giant the column was set for
shown by a detection where it was last detected (so the column stands); the recorded kit's two
Stone to Mud wands taken out (the recorded test pins them); a shovel in the pack, or in the hand with the cutlass in the
pack and the breakout's dig floor set; the Teleportation count; a pit trap in place of the column's top veto; a small kobold
standing on a veto.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_quest_loop_dwell_1106_recorded import (
    READ_PROMPT, VETOES_DONE_TURN, WalledOffBoards, shown as shown_with_wands, without_stone_to_mud,
)

from hengbot import retreat_enclosure, tunnel_feasibility
from hengbot.model import Position

SHOVEL = {"ac": 0, "aware": True, "charges": 0, "charging": False, "count": 1,
          "damage_dice": {"num": 1, "sides": 2}, "fully_known": True, "inscription": "",
          "is_artifact": False, "is_bounty": False, "is_broken": False, "is_cursed": False,
          "is_ego": False, "is_equipment": True, "known": True, "known_flags": [],
          "name": "シャベル (1d2) (+0,+0) (+1)", "pval": 1, "slot": "o", "sval": 1, "to_a": 0,
          "to_d": 0, "to_h": 0, "tval": 20, "weight": 60}
PIT = Position(3, 93)
PIT_TERRAIN = [18, 2, 416 | (1 << 14), 1]  # TRAP_SPIKED_PIT: floor, los, move and trap bits
KOBOLD = {"asleep": False, "confused": False, "fast": False, "fearful": False, "friendly": False,
          "health": "unhurt", "index": 200, "invulnerable": False, "level": None,
          "name": "スモール・コボルド", "pet": False, "race_id": 29, "slow": False,
          "stunned": False, "x": 93, "y": 5}


def shown(raw):
    """The half-giant shown, and the kit without Stone to Mud (DECLARED: so the openers after
    the dig, and Teleportation and Recall, are reached)."""
    shown_with_wands(raw)
    without_stone_to_mud(raw)


def teleportation(count):
    def edit(raw):
        shown(raw)
        next(item for item in raw["inventory"] if item["slot"] == "e")["count"] = count
    return edit


class WalledOffAgain(WalledOffBoards):
    def walled_off_again(self, edit=shown, setup=None, first=shown, between=None):
        """The first read on the stop's board as ``first`` changes it, posted, then the
        board 10 game turns later as ``edit`` changes it (``setup`` and ``between`` change
        the policy before each)."""
        replay, *_ = self.replay(lambda board, _reason: board.turn >= VETOES_DONE_TURN)
        if setup is not None:
            setup(replay.policy)
        _board, key, reason = self.at_the_stop(replay, edit=first)
        self.assertEqual(reason, retreat_enclosure.TELEPORT_REASON)
        self.post_item_command(replay.policy, self.stop_raw(edit=first), key, READ_PROMPT)
        if between is not None:
            between(replay.policy)
        board, key, reason = self.at_the_stop(replay, later=10, edit=edit)
        return replay, board, key, reason

    def test_at_the_random_quest_reserve_recall_is_read(self):
        replay, _board, key, reason = self.walled_off_again(teleportation(5))
        self.assertEqual(reason, retreat_enclosure.RECALL_REASON)
        self.assertEqual(key, "rf")
        self.assertTrue(replay.policy._returning_to_town)
        self.post_item_command(replay.policy, self.stop_raw(later=10, edit=teleportation(5)),
                               key, READ_PROMPT)

    def test_above_the_reserve_teleportation_is_read_again(self):
        _replay, _board, key, reason = self.walled_off_again(teleportation(6))
        self.assertEqual(reason, retreat_enclosure.TELEPORT_REASON)
        self.assertEqual(key, "re")

    def test_with_a_shovel_the_dig_route_is_walked(self):
        """The route's first wall is far: the walk to it comes first (the shovel is
        wielded beside it, walkout_dig.dig_step_key)."""
        def edit(raw):
            shown(raw)
            raw["inventory"].append(dict(SHOVEL))
        _replay, board, key, reason = self.walled_off_again(edit)
        self.assertEqual(reason, retreat_enclosure.DIG_REASON)
        self.assertIn(key, set("12346789"))

    def test_a_wielded_shovel_stays_in_hand_while_the_dig_has_a_route(self):
        """The breakout's restore rung would swap the cutlass back on every board."""
        def edit(raw):
            shown(raw)
            raw["inventory"].append(dict(raw["equipment"][0], slot="o"))
            raw["equipment"][0] = dict(SHOVEL, slot="main_hand")

        def between(policy):  # the shovel was wielded for this dig
            policy._breakout_dig_floor = policy._floor_key

        replay, board, _key, reason = self.walled_off_again(edit, between=between)
        self.assertEqual(replay.policy._breakout_dig_floor, board.floor_key)
        self.assertEqual(reason, retreat_enclosure.DIG_REASON)

    def test_stone_to_mud_melts_walls_the_digger_cap_refuses(self):
        """The beam does not depend on the digging skill: a wall the owner's dig cap
        (tunnel_feasibility.not_dug) refuses to a digger is still melted."""
        class AllTried(dict):
            def get(self, key, default=None):
                return float(tunnel_feasibility.NOT_DUG_OVER_ATTEMPTS)

        def between(policy):  # DECLARED: every wall already tried 100 times with a digger
            setattr(policy, tunnel_feasibility.MEMORY,
                    tunnel_feasibility.Memory(floor=policy._floor_key, tries=AllTried()))

        _replay, _board, key, reason = self.walled_off_again(
            shown_with_wands, first=shown_with_wands, between=between)
        self.assertEqual(reason, retreat_enclosure.MELT_REASON)

    def test_a_trap_in_the_wall_is_walked_to_for_its_disarm(self):
        def setup(policy):
            policy._engagement_owned_avoid_cells.discard(PIT)
            policy._engagement_avoid_cells.discard(PIT)

        def edit(raw):
            shown(raw)
            grid_map = raw["grid_map"]
            grid_map["palette"].append(PIT_TERRAIN)
            grid_map["runs"].append([PIT.y, PIT.x, 1, len(grid_map["palette"]) - 1])
        _replay, board, _key, reason = self.walled_off_again(edit, setup, first=edit)
        self.assertTrue(board.grids[PIT].trap)
        self.assertEqual(reason, retreat_enclosure.DISARM_REASON)

    def test_a_weak_enemy_on_the_wall_is_struck(self):
        def edit(raw):
            shown(raw)
            raw["visible_monsters"] = [*raw.get("visible_monsters", []), dict(KOBOLD)]
        _replay, _board, _key, reason = self.walled_off_again(edit)
        self.assertEqual(reason, retreat_enclosure.STRIKE_REASON)


if __name__ == "__main__":
    unittest.main()
