"""A sleeper's reach that holds every way on is answered by the enclosure ladder (n1-c life-216).

n1-c life-216 (Magic-Eater Lv 47), Angband 62F, 2026-11-17.  The first Recall (04:18:44, the random
quest 46 floor given up, ``quest-unviable``) went through: the town visit ran and the town's
Recall landed the player on a new 62F (quest 0) at (3,29) at 04:19:21.  The dark room it landed in
had two ways on, the open door (5,30) and the west side (5,24) toward the door (5,23); a sleeping
百足龍虫 (race 1257, CRUSH 5d12 x2 and GAZE 7d14 x2, speed +10) lay five cells off in the
corridor (8,28) below the room.  Its reach (policy ``_engagement_danger_cells``: the cells nearer
it than the player, owner 2026-11-07 「眠っている敵でも強い敵からは離れる」) held both, so the
explore had no frontier; ``search``, ``seek-secret-wall`` and ``stuck:wander`` walked the room's top
row (3,24)-(3,29) for 280 game turns until ``livelock:recall-escape`` read Recall at full HP
(934/934) at 04:19:25.  No retreat had claimed a cell, so neither enclosure read saw it: the
oscillation branch's escape asks only while ``_engagement_owned_avoid_cells`` is non-empty, and
retreat_enclosure drew its sides by those cells only.

The fix (retreat_enclosure ``route_veto_sealed_key``, asked in ladder_idle right below the
explore), owner 2026-11-17 「半径13以内なら *破壊*、無理なら溶かして抜ける」: while the routes'
engagement veto is what holds every way on (engagement_avoid_seal ``route_veto_encloses``: none
avoiding every veto, one with that veto lifted), *Destruction* leaving the sealing monsters alone
(``sealers``; destruction_use ``key`` with them as ``leaving``, the most dangerous of them within
GUARANTEED_RADIUS); else the openers toward the known ground past the veto (Stone to Mud among
them); else the floor's stuck escape (50F+ deep_teleport ``stuck_key``: Stone to Mud toward a goal,
else Recall).

Recorded (tests/fixtures/route-veto-sealed-20261117.json.gz, see
tests/extract_route_veto_sealed_1117_fixture.py): the 7 player-turn boards from the landing to
the first board the explore found nothing on (turns 3897141-3897167) and the decision rows of
the floor visit.  The boards are decided in order by one policy's public ``choose_key``.

DECLARED RECONSTRUCTED: the absorbed *Destruction* (the capture keeps no power list; the decision
row of 04:18:44 cast it, ``emergency:destruction:absorbed-power``, key ``mA3``), shown as a list row
with 22 charges at 95% so that the 50F+ means-spent Recall (destruction_use) is not what answers.
DECLARED CONSTRUCTED: an absorbed Stone to Mud (the capture does not say whether it was held),
the boards without the 百足龍虫, and for the melt and Recall cases the *Destruction* taken as
having failed the board before the stuck board (destruction_use's fallback).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import deep_teleport, destruction_use, engagement_avoid_seal, me_capability, retreat_enclosure, threat_tiers
from hengbot.model import SV_STAFF_DESTRUCTION, SV_WAND_STONE_TO_MUD, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "route-veto-sealed-20261117.json.gz"
DRAGON_CENTIPEDE = 1257
SLEEPER = Position(8, 28)
STUCK_TURN = 3897167
STUCK_AT = Position(3, 26)
DOORS_ON = (Position(5, 30), Position(5, 24))
WEST_DOOR = Position(5, 23)
FLOOR = {"dungeon_id": 1, "level": 62, "quest_id": 0}


def _row(kind, sval, current, maximum):
    return {"name": me_capability.names(kind, sval)[0], "current": current, "max": maximum,
            "fail": 5, "success": 95}


class RouteVetoSealedRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
            cls.data = json.load(stream)
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def policy(self, *, stone_to_mud=False):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.board(self.data["boards"][0])
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        # DECLARED RECONSTRUCTED / CONSTRUCTED (module docstring): the absorbed powers.
        lists = {"staff": (first.turn, (_row("staff", SV_STAFF_DESTRUCTION, 22, 22),))}
        if stone_to_mud:
            lists["wand"] = (first.turn, (_row("wand", SV_WAND_STONE_TO_MUD, 10, 20),))
        policy._me_device_lists = lists
        return policy

    def board(self, raw, *, sleeper=True):
        raw = copy.deepcopy(raw)
        if not sleeper:  # DECLARED CONSTRUCTED: the 百足龍虫 gone
            for field in ("visible_monsters", "detected_monsters"):
                raw[field] = [m for m in raw[field] if m["race_id"] != DRAGON_CENTIPEDE]
        return parse_snapshot(raw, self.monrace)

    def replay(self, *, stone_to_mud=False, sleeper=True, destruction_failed=True):
        """(policy, the stuck board, its key, its reason) after deciding every board in order.
        ``destruction_failed`` (DECLARED CONSTRUCTED): on the stuck board the *Destruction* is
        taken as having failed the board before (destruction_use's fallback: its next ask
        declines once), so the rungs after it answer."""
        policy = self.policy(stone_to_mud=stone_to_mud)
        key = board = None
        for raw in self.data["boards"]:
            board = policy.with_known_skill_exp(self.board(raw, sleeper=sleeper))
            if destruction_failed and board.turn == STUCK_TURN:
                destruction_use._memory(policy).fallback = board.floor_key
            key = policy.choose_key(board)
        self.assertEqual(board.turn, STUCK_TURN)
        return policy, board, key, policy.last_reason

    # ------------------------------------------------------------ the record

    def test_the_record_walks_the_top_row_until_the_livelock_reads_recall_at_full_hp(self):
        rows = [row for row in self.data["decisions"]
                if {k: row["floor"][k] for k in FLOOR} == FLOOR]
        reasons = [row["reason"] for row in rows]
        stuck = reasons[reasons.index("search"):reasons.index("livelock:recall-escape")]
        self.assertEqual(set(stuck) - {"search", "seek-secret-wall", "stuck:wander",
                                       "magic-eater:absorb", "me-power:new-floor:detect-traps",
                                       "me-power:before-secret-search:detect-doors-stairs"}, set())
        self.assertGreaterEqual(stuck.count("search"), 40)
        self.assertGreaterEqual(stuck.count("stuck:wander"), 10)
        self.assertTrue(all(row["position"]["y"] == 3 and 24 <= row["position"]["x"] <= 29
                            for row in rows), rows)
        escape = next(row for row in rows if row["reason"] == "livelock:recall-escape")
        self.assertEqual(escape["hp"], 934)
        board = self.board(self.data["boards"][-1])
        self.assertEqual(board.player.position, STUCK_AT)
        sleeper = next(m for m in board.visible_monsters if m.race_id == DRAGON_CENTIPEDE)
        self.assertEqual(sleeper.position, SLEEPER)
        self.assertTrue(sleeper.asleep)

    # ------------------------------------------------------------ the pins

    def test_the_sleepers_reach_holds_both_ways_on(self):
        policy, board, _key, _reason = self.replay()
        veto = policy._engagement_route_veto(board)
        for door in DOORS_ON:
            self.assertIn(door, veto)
        self.assertFalse(policy._engagement_owned_avoid_cells)
        self.assertTrue(engagement_avoid_seal.route_veto_encloses(policy, board))

    def test_the_sealing_sleeper_is_destroyed_first(self):
        """Owner 2026-11-17 「半径13以内なら *破壊*」: the 百足龍虫 sealing both doors, 6 cells
        off (inside GUARANTEED_RADIUS), is left by the absorbed *Destruction* (``mA3``, the key
        the record cast at 04:18:44) on the first board the explore finds nothing on (the record
        searched there).  The engagement also holds an awake 1367 at (31,59), 44 cells off, the
        most dangerous from contact: it is not asked about (the sealers alone are left)."""
        policy, board, key, reason = self.replay(destruction_failed=False)
        self.assertEqual(key, "mA3")
        self.assertEqual(reason, destruction_use.REASON + retreat_enclosure.ROUTE_VETO_DESTRUCTION_SUFFIX
                         + ":absorbed-power")
        walled = retreat_enclosure._sides(policy, board, frozenset(policy._engagement_route_veto(board)))
        self.assertEqual([m.race_id for m in retreat_enclosure.sealers(policy, board, walled)],
                         [DRAGON_CENTIPEDE])
        engagement = [m.race_id for m in threat_tiers.engagement(policy, board)]
        self.assertIn(1367, engagement)

    def test_the_enclosure_ladder_answers_before_any_search(self):
        """50F+ off the 即死 board, the *Destruction* failed and no means to melt: deep_teleport's
        stuck Recall."""
        _policy_, board, key, reason = self.replay()
        self.assertEqual(reason, deep_teleport.STUCK_RECALL_REASON)
        self.assertTrue(key.startswith("r"), key)

    def test_stone_to_mud_melts_out_past_the_reach_first(self):
        """DECLARED CONSTRUCTED: an absorbed Stone to Mud.  The ground past the reach is the west
        door (5,23); the route melts one wall, (4,23), from the room's top row."""
        policy, board, key, reason = self.replay(stone_to_mud=True)
        self.assertEqual(reason, retreat_enclosure.MELT_REASON)
        self.assertEqual(key, "4")
        walled = retreat_enclosure._sides(policy, board, frozenset(policy._engagement_route_veto(board)))
        self.assertIn(WEST_DOOR, walled.ground)
        self.assertEqual(retreat_enclosure.melt_route(policy, board, walled.ground),
                         (Position(3, 25), 1))

    def test_without_the_sleeper_the_explore_goes_on(self):
        """DECLARED CONSTRUCTED: the 百足龍虫 gone; nothing is enclosed and the floor's walk goes on
        (to the down stairs (27,60) the detection showed)."""
        policy, board, _key, reason = self.replay(sleeper=False)
        self.assertFalse(engagement_avoid_seal.route_veto_encloses(policy, board))
        self.assertIsNone(retreat_enclosure.route_veto_sealed_key(policy, board))
        self.assertEqual(reason, "approach-descent")


if __name__ == "__main__":
    unittest.main()
