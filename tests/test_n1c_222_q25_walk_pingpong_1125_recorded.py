"""Quest 25's tome phase on n1-c life-222 (2026-11-25 00:30): the near plan and the far plan, recorded.

The chain (Zombie Magic-Eater Lv37, floor (0,48,25); the incident capture
20261125-003056-livelock-exhausted, decisions 41220-41234; battle phase 5, the tome on [9,8],
unseen, its grid glowing):

 * ``quest25_battle_rooms._tome`` weighs two plans: the near stands [5,5], [4,5], [5,6] with the
   attacks aimed at the grid (``near``), or a cell that sees the tome with the launcher too
   (``far``).  ``near`` was the strongest of ``_fire_options`` from where the player stood.
 * The balls spent, what was left aimed at the grid was the bolt-or-beam along a ray, and a ray
   from [4,8] or [5,8] runs down column 8 to [9,8]: there ``near`` (33) beat the launcher (29),
   and the near plan walked toward [5,5] (``quest25:walk`` '4' or '7').  On [4,7] or [5,7] no ray
   reaches [9,8], ``near`` was 0, and the far plan walked to the nearest sight, [4,8] or [5,8]
   (``quest25:walk-to-sight`` '6' or '3').  The two alternated every board until the bot stopped
   with ``livelock:exhausted`` at 00:31:03.

The rule (``_near_damage``): the near plan's damage is what its stands can fire -- a ball or a
breath from any of them, a beam only along a stand's own ray.  No near stand has a ray to [9,8], so
``near`` no longer depends on the cell the player stands on and one plan (the walk to a sight)
holds on every board.

Recorded: tests/fixtures/n1c-222-q25-walk-pingpong-1125.json.gz
(tests/extract_n1c_222_q25_walk_pingpong_1125_fixture.py, copies of the capture in
C:/hengband-backups/pdca/captures/n1c-222-q25-walk-pingpong-1125).  A fresh policy restores the
record the process left (q25-battle.json at the halt) through the real path and decides the
recorded boards in order through the public ``choose_key``, each key confirmed as posted; the
recorded boards are the player's recorded cells, not where the replayed keys lead.

DECLARED CONSTRUCTED: no board carries the magic-eater lists (the client reads them off the
screen); they are the life's last town-arrival lists (``me_lists``), with every ball and breath
spent (``spent``) as the process's were after the haste and the Powerful Activation volley before
41193 -- with them the replay decides all fifteen recorded keys and reasons as recorded
(``test_the_old_near_value_replays_the_recording``).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_rooms as rooms, quest25_battle_record
from hengbot.model import parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay

with gzip.open(Path(__file__).with_name("fixtures") / "n1c-222-q25-walk-pingpong-1125.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

TOME = (9, 8)
# The attacks aimed at a grid with no ray (me_device_attacks: ball, breath and rocket shapes).
BALLS = {"アシッド・ボール", "アイス・ボール", "ファイア・ボール", "ロケット", "悪臭雲"}


def lists(spent: bool):
    """DECLARED CONSTRUCTED (module note): the town-arrival lists, the balls spent or not."""
    found = {}
    for kind, (stamp, rows) in CASE["me_lists"].items():
        made = []
        for row in rows:
            row = dict(row)
            if spent and row["name"] in BALLS:
                row.update({"charging": row["max"]} if kind == "rod" else {"current": 0})
            made.append(row)
        found[kind] = (stamp, tuple(made))
    return found


def drive(device_lists, inspect=None):
    """[(sequence, cell, key, reason)] of the recorded boards; ``inspect(policy, snapshot)`` after
    each decision."""
    answers = []
    with TemporaryDirectory() as directory:
        policy = replay.new_policy(Path(directory), device_lists, None, CASE)
        for raw, row in zip(CASE["second"]["boards"], CASE["second"]["recorded"]):
            snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
            key = policy.choose_key(snapshot)
            phase = battle.PHASE_NAMES[policy._quest_navigators[25].phase_battle.phase]
            answers.append((row["sequence"], (snapshot.player.position.y, snapshot.player.position.x),
                            key, policy.last_reason, phase))
            if inspect is not None:
                inspect(policy, snapshot)
            policy.confirm_key_posted(key)
    return answers


class TheRecordingTest(unittest.TestCase):

    def test_the_two_walks_alternated(self):
        rows = {((board["player"]["y"], board["player"]["x"]), row["key"], row["reason"])
                for board, row in zip(CASE["second"]["boards"], CASE["second"]["recorded"])}
        self.assertIn(((4, 8), "4", battle.WALK_REASON), rows)
        self.assertIn(((4, 7), "6", battle.SIGHT_REASON), rows)
        self.assertIn(((5, 8), "4", battle.WALK_REASON), rows)
        self.assertIn(((5, 7), "6", battle.SIGHT_REASON), rows)
        record = CASE["battle_record"]["battle"]
        self.assertEqual(record["phase"], battle.phase_index("tome"))
        blind = {cell for aimed, cell in quest25_battle_record._decode(record["blind_sights"]) if aimed == TOME}
        self.assertIn((4, 7), blind)
        self.assertNotIn((4, 8), blind)   # never reached by the walk to a sight: the near plan's
        self.assertNotIn((5, 8), blind)


class OnePlanPerBoardTest(unittest.TestCase):

    def test_the_balls_spent_the_walk_to_a_sight_holds(self):
        answers = drive(lists(spent=True))
        self.assertEqual(len(answers), len(CASE["second"]["boards"]))
        self.assertTrue(all(phase == "tome" for *_rest, phase in answers), answers)
        self.assertEqual({reason for _sequence, _cell, _key, reason, _phase in answers},
                         {battle.SIGHT_REASON}, answers)
        by_cell = {cell: key for _sequence, cell, key, _reason, _phase in answers}
        # On [4,8] and [5,8] the walk goes on to another sight, never back west toward [5,5].
        self.assertNotIn(by_cell[(4, 8)], {"4", "7", "1"})
        self.assertNotIn(by_cell[(5, 8)], {"4", "7", "1"})

    def test_the_near_value_is_the_stands_not_the_present_ray(self):
        seen = []

        def inspect(policy, snapshot):
            ctx = battle._ctx(policy, snapshot)
            if ctx.here == (4, 8):
                here = max((damage for damage, _make in rooms._fire_options(
                    ctx, TOME, battle.geo.TOME, missiles=False)), default=0.0)
                stands = [stand for stand in battle.geo.TOME_NEAR_STANDS if rooms._path(ctx, {stand})]
                seen.append((here, rooms._near_damage(ctx, TOME, stands)))

        drive(lists(spent=True), inspect)
        self.assertTrue(seen)
        for here, near in seen:
            self.assertGreater(here, 0.0)   # the ray down column 8 from [4,8]
            self.assertEqual(near, 0.0)     # no near stand has one

    def test_with_a_ball_the_near_plan_holds(self):
        # DECLARED CONSTRUCTED control: the balls charged, the near stands' ball wins on every
        # board as before, and the walk goes to [5,5] from both columns.
        answers = drive(lists(spent=False))
        self.assertEqual({reason for _sequence, _cell, _key, reason, _phase in answers},
                         {battle.WALK_REASON}, answers)


class TheOldNearValueTest(unittest.TestCase):

    def test_the_old_near_value_replays_the_recording(self):
        # The near value as it was (the strongest grid-aimed attack from the present cell)
        # decides every recorded key and reason: the lists above are the process's.
        old = rooms._near_damage

        def present(ctx, tome, stands):
            return max((damage for damage, _make in rooms._fire_options(
                ctx, tome, battle.geo.TOME, missiles=False)), default=0.0)

        rooms._near_damage = present
        try:
            answers = drive(lists(spent=True))
        finally:
            rooms._near_damage = old
        self.assertEqual([(key, reason) for _sequence, _cell, key, reason, _phase in answers],
                         [(row["key"], row["reason"]) for row in CASE["second"]["recorded"]])


if __name__ == "__main__":
    unittest.main()
