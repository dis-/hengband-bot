"""Quest 25 on n1-b life-399 (2026-11-15 16:46-16:47): two loops, recorded.

n1-b life-399 (Magic-Eater, bot_play3, build bot-e305dfdea; no telepathy) on Quest 25 『幽霊屋敷』.

 * 16:46:40, the ambush on the ranged stand [13,1] (``navigation exhausted``): every 50 quiet actions
   the presence check (quest25_presence ``presence_key``, 2026-11-15) walked to [12,2] -- from [13,1]
   the detection misses [1,29] and [2,29] -- cast, saw the spectral tyrannosaurus (705) on the floor,
   and the ambush walked back; four rounds (turns 1901862, 1902224, 1902584, 1902972) until the loop guard
   read the walks as no progress.  The fix: a check that shows a race the phase waits for ends the
   checks of that phase (``Battle.presence_shown``): the wait for a monster on the floor is the
   plan's own (owner 2026-11-06 ambush: 「5000 = 事実上上限無し」).
 * 16:47:47 and 16:47:54, the corpse masses (phase4) on [1,7] (``confined to [(1, 7)]``, then the
   escalation): the masses had bred into the east room ([2,19]-[2,25], [1,26], [1,27]), seen
   through the open door [1,18] along row 1.  No cell out of the living dreadmaster's vision
   reaches them, and from [1,7] the shot's path to [2,20] ends on the wall [2,18]: the phase fired
   36 arrows with no hit or miss line.  The fix (quest25_battle ``_phase_masses``, ``_mass_reached``):
   only a mass a shot reaches is shot; the phase is for the masses of the north corridor and those a
   shot reaches from a cell the plan may stand on (owner 2026-11-06 phase4 「北の通路…の死体の塊を
   処理する」, phase6_sweep 「[1,6] から見て通路に1体もいないことで判定して良い」); the east room's are
   met later (beside the player in every phase, the breeders in line, the sweep).

Recorded: tests/fixtures/n1b-399-q25-loops-1115.json.gz (tests/extract_n1b_399_q25_loops_1115_fixture.py):
the ambush's boards 1902224-1902989 and the masses' 1918900-1919043 with their decisions, the record
left (turn 1919350, phase 6).  A fresh policy restores a record through the real path and decides the
recorded boards through the public ``choose_key``; a key is posted through the production executor.

DECLARED RECONSTRUCTED: the remembered magic-eater lists (tests/test_n1c_208_q25_patrol_1115_recorded,
the rod 全感知 ready); the record's turn set to the board's.  For the ambush, the record of that time
is not kept: it is the stop's with phase 0 (the ambush), ready, the ranged style, the kills read
before the board (the hound, the skeletal tyrannosaur, the vampire lord, absent since turn 1901880),
and the quiet count past the check's window (100, the last check at 50).  DECLARED CONSTRUCTED: the
quiet count raised past the next window before the recorded board of the second check (1902584: the
recorded quiet holds in between are not decided here), the board on [1,6] after the step there.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_record as record_mod, quest25_presence as presence
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay
from tests import test_n1c_211_q25_absent_wait_1115_recorded as wait

with gzip.open(Path(__file__).with_name("fixtures") / "n1b-399-q25-loops-1115.json.gz",
               "rt", encoding="utf-8") as _stream:
    CASE = json.load(_stream)

geo = battle.geo
FIRST_CHECK, CAST, SHOWN, SECOND_CHECK = 1902224, 1902235, 1902244, 1902584
MASS_BOARD = 1918903
STAND, ARROW_AIM = (13, 1), (2, 20)
CAST_REASON = f"{presence.CAST_REASON}:detect-all"


def board(part: str, turn: int) -> dict:
    return copy.deepcopy(next(raw for raw in CASE[part]["boards"] if raw["turn"] == turn))


def recorded(part: str):
    return [tuple(row[:3]) + (tuple(row[3]),) for row in CASE[part]["decisions"]]


def ambush_record(turn: int) -> dict:
    """DECLARED RECONSTRUCTED (module note)."""
    found = copy.deepcopy(CASE["battle_record"])
    found["turn"] = turn
    fought = found["battle"]
    kept = [row for row in fought["kill_turns"]["tuple"] if row["tuple"][1] <= turn]
    fought.update(phase=0, ready=True, quiet=100, presence_quiet=50, style="ranged", lit=False,
                  detected=None, detect_turn=-1, gone=record_mod._encode(frozenset()),
                  kill_turns={"tuple": kept}, kills=record_mod._encode({row["tuple"][0]: 1 for row in kept}))
    return found


class TheRecordingTest(unittest.TestCase):

    def test_the_ambush_walked_out_and_back_for_each_check(self):
        checks = [row for row in recorded("ambush") if row[1] == presence.WALK_REASON]
        self.assertEqual([(row[0], row[2], row[3]) for row in checks],
                         [(turn, "9", STAND) for turn in (1901862, 1902224, 1902584, 1902972)])
        shown = board("ambush", SHOWN)
        self.assertIn(geo.SPECTRAL_T, {monster["race_id"] for monster in shown["detected_monsters"]})

    def test_the_masses_were_shot_at_a_cell_no_arrow_reaches(self):
        shots = [row for row in recorded("masses") if row[1] == battle.SHOT_REASON and row[3] == (1, 7)]
        self.assertGreaterEqual(len(shots), 36)
        raw = board("masses", MASS_BOARD)
        self.assertEqual({(m["race_id"], m["y"], m["x"]) for m in raw["visible_monsters"]} >= {(geo.MASS, 2, 20)}, True)
        texts = [text for row in CASE["masses"]["boards"] for text in row["messages"]]
        self.assertFalse(any("命中" in text or "外れ" in text for text in texts))
        self.assertEqual(CASE["battle_record"]["battle"]["phase"], battle.phase_index("corpse-masses"))
        self.assertEqual(CASE["last"]["decisions"][-1][1], "loop-detected")


class TheAmbushCheckTest(replay._Replay):

    def test_a_check_that_showed_the_tyrannosaurus_is_not_made_again(self):
        with TemporaryDirectory() as directory:
            raw = board("ambush", FIRST_CHECK)
            policy = wait.new_policy(Path(directory), ambush_record(raw["turn"]), raw)
            key = wait.decide_past_reads(policy, raw)
            self.assertEqual((key, policy.last_reason), ("9", presence.WALK_REASON))
            self.post(policy, raw, key, board("ambush", CAST))
            key = wait.decide_past_reads(policy, board("ambush", CAST))
            self.assertEqual((key, policy.last_reason), ("mCg", CAST_REASON))
            self.post(policy, board("ambush", CAST), key, board("ambush", SHOWN))
            wait.decide_past_reads(policy, board("ambush", SHOWN))
            fight = wait.fight(policy)
            self.assertIn(geo.SPECTRAL_T, fight.presence_shown)
            fight.quiet = fight.presence_quiet + 60      # DECLARED CONSTRUCTED (module note)
            key = wait.decide_past_reads(policy, board("ambush", SECOND_CHECK))
            self.assertNotEqual(policy.last_reason, presence.WALK_REASON)
            self.assertNotEqual(key, "mCg")
            self.assertEqual(wait.phase_name(policy), "ambush")


class TheMassesTest(replay._Replay):

    def test_the_recorded_board_walks_back_to_the_stand_not_shooting_the_east_room(self):
        raw = board("masses", MASS_BOARD)
        with TemporaryDirectory() as directory:
            policy = wait.new_policy(Path(directory), dict(CASE["battle_record"], turn=raw["turn"]), raw)
            key = wait.decide_past_reads(policy, raw)
            self.assertEqual((key, policy.last_reason), ("4", battle.WALK_REASON))
            following = copy.deepcopy(raw)
            following["player"] = dict(following["player"], y=1, x=6)
            following["turn"], following["messages"] = raw["turn"] + 10, []
            self.post(policy, raw, key, following)
            key = wait.decide_past_reads(policy, following)
            self.assertEqual(wait.phase_name(policy), "dreadmaster")
            self.assertNotEqual(policy.last_reason, battle.SHOT_REASON)

    def test_no_arrow_reaches_the_east_room_from_the_corridor_mouth(self):
        raw = board("masses", MASS_BOARD)
        with TemporaryDirectory() as directory:
            policy = wait.new_policy(Path(directory), dict(CASE["battle_record"], turn=raw["turn"]), raw)
            wait.decide_past_reads(policy, raw)
            from hengbot.model import parse_snapshot
            ctx = battle._ctx(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            target = next(m for m in battle._masses_seen(ctx) if (m.position.y, m.position.x) == ARROW_AIM)
            self.assertFalse(battle._mass_reached(ctx, (1, 7), target))
            self.assertEqual(battle._phase_masses(ctx), [])

    def test_control_a_corridor_mass_keeps_the_phase(self):
        """DECLARED CONSTRUCTED: one more mass on the corridor cell [1,12] (the board places a monster
        by the grid map's index first, so a new index is placed by its own cell)."""
        raw = board("masses", MASS_BOARD)
        mass = copy.deepcopy(next(m for m in raw["visible_monsters"] if (m["y"], m["x"]) == ARROW_AIM))
        mass.update(index=999, y=1, x=12, health="unhurt")
        raw["visible_monsters"].append(mass)
        with TemporaryDirectory() as directory:
            policy = wait.new_policy(Path(directory), dict(CASE["battle_record"], turn=raw["turn"]), raw)
            wait.decide_past_reads(policy, raw)
            from hengbot.model import parse_snapshot
            ctx = battle._ctx(policy, parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            self.assertEqual([(m.position.y, m.position.x) for m in battle._phase_masses(ctx)], [(1, 12)])
            self.assertEqual(wait.phase_name(policy), "corpse-masses")


if __name__ == "__main__":
    unittest.main()
