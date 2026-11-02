"""An avoided immobile summoner no longer suspends the floor visit.

Owner 2026-10-27 (immobile-summoner-avoid-decision-20261027): 「動かない
召喚の敵は近づかずに避ける」 -- avoid it (do not approach, stay out of its
view), fight it only where no retreat exists.  Owner 2026-11-02:
「動かない召喚敵を避ける動きをしているとき、色々と判断が通常と異なるように
見える」.

Recorded (tests/fixtures/summoner-avoid-narrow-1102.json.gz,
tests/extract_summoner_avoid_narrow_1102_fixture.py): n1-c life-099 on
迷宮12階 held for the unique summoner (race 1150) at (2,27) until the
50-game-turn wait expired (decisions 117-121), then the immobile-summoner
owner took every decision of the visit as ``explore:avoid-immobile-summoner``
(122-150): no detection, no ranged fire, and at turn 676217 (decision 142)
it walked '4' with a worm mass and a warg in view.  The player stood out of
the summoner's line of fire throughout.  Now the zone stays a routing veto,
but every other owner plays: the 676217 board fires at the worm mass, and the
ordinary descent walks to a downstairs outside the zone (owner 2026-11-02
「下り階段を先に使う」).

The recall countdown (DECLARED CONSTRUCTED ``recalling`` on recorded
boards): out of the zone the ordinary ``return:wait-recall`` waits; inside
the line of fire of the 2026-10-27 glass-wall summoner
(tests/fixtures/glass-summoner-20261027.json.gz, after its wait expired)
the owner steps out of the zone instead of waiting in it.

Every decision is the public ``choose_key`` on the recorded decision boards
in turn order; each board carries the recorded previous operation's
completion as the live driver reports it (DECLARED CONSTRUCTED from the
recorded decision rows).  Posted keys go through the production executor.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from hengbot.model import Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests import test_n1c_deaths_1101_recorded as d57
from tests.test_immobile_summoner_recorded import EDIT


FIXTURES = Path(__file__).with_name("fixtures")
with gzip.open(FIXTURES / "summoner-avoid-narrow-1102.json.gz", "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)
AVOID = "explore:avoid-immobile-summoner"
SUMMONER, SUMMONER_CELL = 1150, Position(2, 46)
LAST_HOLD_TURN, FIRST_AVOID_TURN = 675997, 676006  # decisions 121 / 122
FIRE_TURN, RECALL_TURN = 676217, 676068  # decisions 142 / 129
GLASS = FIXTURES / "glass-summoner-20261027.json.gz"
GLASS_SHA256 = "59c9c108d76f2279e7c4f2e854abb3f32206c846dccfe2181450ec04f49f9abb"


def decision_boards():
    rows = {row["turn"]: row for row in CASE["decisions"]}
    previous = None
    for raw in sorted((b for b in CASE["boards"] if b["turn"] in rows),
                      key=lambda b: b["turn"]):
        raw = copy.deepcopy(raw)
        if previous is not None:
            raw["_completed_operation_sequence"] = previous["decision_sequence"]
            raw["_completed_operation_owner"] = previous["reason"]
        previous = rows[raw["turn"]]
        yield raw, previous


class SummonerAvoidNarrowRecordedTest(d57.PostedDeathKey):

    def drive(self, until, adjust=lambda raw: raw):
        """Decide every recorded board up to ``until``; returns the rows
        (turn, recorded reason, key, reason) and the last board's policy."""
        policy, rows = d57.new_policy(CASE), []
        for raw, recorded in decision_boards():
            if raw["turn"] == until:
                raw = adjust(raw)
            key = d57.loops.decide(policy, raw)
            rows.append((raw["turn"], recorded["reason"], key, policy.last_reason))
            if raw["turn"] == until:
                return policy, raw, rows
            policy.confirm_key_posted(key)
        self.fail(until)

    def test_recorded_visit_plays_on_outside_the_summoner_zone(self):
        recorded = {row["turn"]: (row["reason"], row["key"]) for row in CASE["decisions"]}
        self.assertEqual(recorded[LAST_HOLD_TURN], ("summoner:hold-choke", "5"))
        self.assertEqual(recorded[FIRST_AVOID_TURN], (AVOID, "3"))
        self.assertEqual(recorded[FIRE_TURN], (AVOID, "4"))
        fire_board = next(b for b in CASE["boards"] if b["turn"] == FIRE_TURN)
        self.assertEqual(len(fire_board["visible_monsters"]), 2)

        policy, raw, rows = self.drive(FIRE_TURN)
        self.assertEqual(rows[-1][2:], ("fp4", "ranged:fire"))
        self.post(policy, raw, rows[-1][2])
        self.assertEqual(policy._immobile_summoner_memory[1], {SUMMONER_CELL: SUMMONER})
        zone = policy._immobile_summoner_avoid_cells
        self.assertTrue(zone and zone <= policy._engagement_avoid_cells)
        visit = [row for row in rows if row[0] >= FIRST_AVOID_TURN]
        self.assertEqual([row for row in visit if row[3] == AVOID], [])
        self.assertIn("seek-downstairs", {row[3] for row in visit})

    def test_recall_countdown_waits_out_of_the_zone(self):
        def recalling(raw):
            raw["player"]["recalling"] = True  # DECLARED CONSTRUCTED
            return raw

        policy, raw, rows = self.drive(RECALL_TURN, recalling)
        self.assertEqual(rows[-1][1], AVOID)
        self.assertEqual(rows[-1][2:], ("5", "return:wait-recall"))
        self.assertNotIn(Position(raw["player"]["y"], raw["player"]["x"]),
                         policy._immobile_summoner_avoid_cells)
        self.assertTrue(policy._immobile_summoner_avoid_cells)
        self.post(policy, raw, "5")

    def test_recall_countdown_steps_out_of_the_zone_first(self):
        data = GLASS.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), GLASS_SHA256)
        record = json.loads(gzip.decompress(data))[0]
        knowledge = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        board = parse_snapshot(record["board"], knowledge)
        policy = HengbotPolicy(monrace_knowledge=knowledge)
        policy.prime(board)
        policy._skill_exp_cache = (board.player.race_id, board.player.class_id,
                                   board.player.level, policy._town_visit_epoch)
        # The recorded hold until its 50-game-turn wait expires (unchanged
        # boards, DECLARED CONSTRUCTED later turns).
        for step in range(30):
            later = replace(board, turn=board.turn + step * 10)
            key = policy.choose_key(later)
            if policy.last_reason != "summoner:hold-choke" and not policy.last_reason.startswith("ranged:"):
                break
        self.assertIn(board.player.position, policy._immobile_summoner_avoid_cells)
        # DECLARED CONSTRUCTED: the Recall read, its countdown running.
        waiting = replace(later, turn=later.turn + 10,
                          player=replace(later.player, recalling=True))
        key = policy.choose_key(waiting)
        self.assertEqual((str(key), policy.last_reason), ("3", AVOID))
        raw = copy.deepcopy(record["board"])
        raw["turn"] = waiting.turn
        raw["player"]["recalling"] = True
        self.post(policy, raw, str(key))


if __name__ == "__main__":
    unittest.main()
