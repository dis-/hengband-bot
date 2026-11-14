"""Quest 25 on n1-c life-207 (2026-11-14 17:23-18:49): the battle memory after an older save, recorded.

The chain (tests/test_n1c_207_q25_wallpasser_hold_1114_recorded has the hold before it):

 * 17:23-17:24, the ambush and the first wall-passers: six kill lines read (decisions 3797-4025:
   the hound, the vampire lord, the skeletal and spectral tyrannosaurs, both spectres), the battle
   record (jsonlog/q25-battle.json) keeping their counts.
 * 17:54:23 the stall stop; the game saved at turn 8010826.  A restarted process played on to turn
   8033912 (18:02) without a save, and its record carried that turn.
 * 18:49 the game reloaded the 17:54 save: the board's turn 8010826 was before the record's, so the
   record was dropped (quest25_battle_record ``observe``: a later record is not this game), the plan
   began at the ambush with no kills, and would have waited its 5000 actions (long_wait_actions)
   for four monsters dead since 17:23.

The rules:

 * ``Battle.kill_turns``: each kill read is kept with its game turn; a game reloaded from an older
   save keeps the kills read at or before the save's turn (quest25_battle_record
   ``_before_the_save``) and runs the phases again from the first, ending at once those the kills
   end.  A kill read after the save's turn is not in the reloaded game and is not kept.
 * ``_pen_sight`` (phase 2, no attack aimed at the pen's grid): the Ipsissimus are counted escaped
   only when every cell that sees the pen was reached with none seen, and not those telepathy or
   evil ESP senses in the pen (owner 2026-11-06 phase2 「テレポートしたメッセージで判断」「当たらない撃ちで
   補う」).  With cells left and no way to them the phase holds, at most the phase-2 wait
   (``wait_limits.quiet_actions``, 「50ターン待っても来なくなったら」) in a row; then the count is made.

Telepathy is no general answer for the lost memory (q25-memory-loss-1114, checked against the
game): monster-update.cpp senses within MAX_PLAYER_SIGHT (20, gamevalue.h) of the player, and the
quest map is 31 wide -- from the ambush's [10,1] the east wing (the stairway [13,29] at 29) is out
of reach -- and EMPTY_MIND races (the skeletal tyrannosaur 466 of the ambush, the tome 557, the
quylthulgs 480, the stairway 439, the corpse masses 202) are never shown by telepathy.

Recorded: tests/fixtures/n1c-207-q25-wallpasser-hold-1114.json.gz (its ``kill_lines``, ``close``,
``hold`` and the warning records; tests/extract_n1c_207_q25_wallpasser_hold_1114_fixture.py).

DECLARED CONSTRUCTED:
 * The kill lines are shown on the floor's recorded board (the 17:24 hold's first) with each line's
   recorded turn and messages; a fresh policy reads them through the public ``choose_key`` and the
   real record path writes the record.  That record's turn is then set to 8033912, the 18:02
   process's last (its record file was rewritten at 18:49 and is not kept), and the 18:49 board is
   decided by another fresh policy restoring it.
 * The phase-2 boards are the 17:24 hold's with one shadow demon moved beside [9,1]
   (tests/test_n1c_207_q25_wallpasser_hold_1114_recorded ``demon_beside_door``), the record set to
   phase 2, ready; the controls drop the sensed Ipsissimus or mark every cell that sees the pen
   reached.  The boards carry no magic-eater lists, so no attack is aimed at the pen's grid.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle, quest25_battle_record
from hengbot.model import parse_snapshot
from tests import test_n1c_207_q25_wallpasser_hold_1114_recorded as hold

CASE = hold.CASE
SAVE_TURN = 8010826        # the 18:49 board (the 17:54 stop's save)
LATER_TURN = 8033912       # the 18:02 process's last decision and record
AMBUSH, WALL_PASSERS, IPSISSIMUS = (battle.phase_index(name)
                                    for name in ("ambush", "wall-passers", "ipsissimus"))
RECORDED_KILLS = {battle.geo.HOUND: 1, battle.geo.VAMPIRE: 1, battle.geo.SKELETAL_T: 1,
                  battle.geo.SPECTRE: 2, battle.geo.SPECTRAL_T: 1}


def read_kills() -> dict:
    """The record a fresh policy writes after reading the recorded kill lines (module note)."""
    base = hold.boards("hold")[0]
    with TemporaryDirectory() as directory:
        policy = hold.new_policy(Path(directory), base, None, {"version": 1, "floor": [0, 48, 25],
                                                              "battle": None, "board": None})
        for row in CASE["kill_lines"]:
            raw = dict(copy.deepcopy(base), turn=row["turn"], messages=row["messages"])
            key = policy.choose_key(parse_snapshot(raw, policy._monrace_knowledge))
            policy.confirm_key_posted(key)
        return json.loads((Path(directory) / "q25-battle.json").read_text(encoding="utf-8"))


class TheKillLogTest(unittest.TestCase):

    def test_each_kill_is_kept_with_its_turn(self):
        record = read_kills()
        kept = quest25_battle_record._decode(record["battle"]["kill_turns"])
        self.assertEqual(sorted(kept), sorted(
            (race, row["turn"]) for row, race in zip(CASE["kill_lines"], (
                battle.geo.HOUND, battle.geo.VAMPIRE, battle.geo.SKELETAL_T, battle.geo.SPECTRE,
                battle.geo.SPECTRAL_T, battle.geo.SPECTRE))))
        self.assertEqual(dict(quest25_battle_record._decode(record["battle"]["kills"])), RECORDED_KILLS)
        self.assertTrue(all(turn <= SAVE_TURN for _race, turn in kept))


class _Reloaded(hold._Hold):

    def decide_close(self, record):
        close = CASE["close"]
        raw = close["boards"][-1]
        with TemporaryDirectory() as directory:
            policy = hold.new_policy(Path(directory), close["boards"][0], CASE["stop_warning_record"])
            # The record as the later process left it (module note): written over new_policy's.
            (Path(directory) / "q25-battle.json").write_text(json.dumps(record), encoding="utf-8")
            policy._q25_battle_record_read = False
            key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
            reason, fight = policy.last_reason, policy._quest_navigators[battle.geo.QUEST_ID].phase_battle
            if hold.replay._shown(key):
                self.post(policy, raw, key, raw)
            return key, reason, fight


class TheReloadedSaveTest(_Reloaded):

    def later_record(self, extra=()):
        record = read_kills()
        record["turn"] = LATER_TURN
        if extra:
            kept = quest25_battle_record._decode(record["battle"]["kill_turns"])
            record["battle"]["kill_turns"] = quest25_battle_record._encode(tuple(kept) + tuple(extra))
        return record

    def test_the_kills_before_the_save_end_the_ambush(self):
        key, reason, fight = self.decide_close(self.later_record())
        self.assertEqual(dict(fight.kills), RECORDED_KILLS)
        self.assertEqual(fight.phase, WALL_PASSERS)
        self.assertEqual((key, reason), ("8", battle.WALK_REASON))   # on to [7,1], not the ambush's wait

    def test_a_kill_after_the_save_is_not_kept(self):
        # DECLARED CONSTRUCTED: a shadow demon's kill read at a turn after the save's.
        _key, _reason, fight = self.decide_close(self.later_record(((battle.geo.SHADOW, SAVE_TURN + 1),)))
        self.assertNotIn(battle.geo.SHADOW, fight.kills)
        self.assertEqual(dict(fight.kills), RECORDED_KILLS)

    def test_a_record_with_no_kill_turns_starts_at_the_ambush(self):
        # The record as it was written before kill_turns (18:02): nothing to keep, the ambush again.
        record = self.later_record()
        del record["battle"]["kill_turns"]
        key, reason, fight = self.decide_close(record)
        self.assertEqual((fight.phase, dict(fight.kills)), (AMBUSH, {}))
        self.assertEqual((key, reason), ("5", battle.HOLD_REASON))


def phase2_record():
    """DECLARED CONSTRUCTED (module note): the 17:42 record at phase 2, ready."""
    record = copy.deepcopy(CASE["battle_record"])
    record["battle"].update(phase=IPSISSIMUS, ready=True, quiet=0)
    return record


def without_sensed_ipsissimus(raw):
    board = hold.demon_beside_door(raw)
    board["detected_monsters"] = [monster for monster in board["detected_monsters"]
                                  if monster["race_id"] != battle.geo.IPSISSIMUS]
    return board


class _Phase2(hold._Hold):

    def drive_phase2(self, shape, record, count=12):
        """[(index, cell, key, reason, phase, assumed escaped)] of the hold's first ``count`` boards
        (shaped), each key posted through the executor, to the first key that moves or whose
        screens this harness does not show."""
        recorded = [shape(raw) for raw in hold.boards("hold")[:count]]
        answers = []
        with TemporaryDirectory() as directory:
            policy = hold.new_policy(Path(directory), recorded[0], CASE["warning_record"], record)
            for index, raw in enumerate(recorded):
                key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
                fight = policy._quest_navigators[battle.geo.QUEST_ID].phase_battle
                answers.append((index, hold.HELD, key, policy.last_reason, fight.phase,
                                fight.assumed_escaped))
                if key in hold.STEPS or not hold.replay._shown(key) or index + 1 == len(recorded):
                    break
                self.post(policy, raw, key, recorded[index + 1])
        return answers

    def quiet_actions(self) -> int:
        """The shipped QUEST_25 ``wait_limits.quiet_actions`` as the plan reads it."""
        base = hold.demon_beside_door(hold.boards("hold")[0])
        with TemporaryDirectory() as directory:
            policy = hold.new_policy(Path(directory), base, CASE["warning_record"], phase2_record())
            snapshot = parse_snapshot(copy.deepcopy(base), policy._monrace_knowledge)
            policy.choose_key(snapshot)
            return battle._ctx(policy, snapshot).values.quiet_actions

    def all_sights_reached(self, record):
        """``record`` with every cell that sees [7,17] reached unseen (``blind_sights``)."""
        base = hold.demon_beside_door(hold.boards("hold")[0])
        with TemporaryDirectory() as directory:
            policy = hold.new_policy(Path(directory), base, CASE["warning_record"], record)
            snapshot = parse_snapshot(copy.deepcopy(base), policy._monrace_knowledge)
            policy.choose_key(snapshot)
            ctx = battle._ctx(policy, snapshot)
            aim = battle.geo.IPSISSIMUS_AIM
            sights = battle.geo.sight_cells(ctx.open_terrain(), aim, battle._sight_radius(ctx, aim))
        record = copy.deepcopy(record)
        record["battle"]["blind_sights"] = quest25_battle_record._encode(
            frozenset((aim, tuple(cell)) for cell in sights))
        return record


class ThePenSightTest(_Phase2):

    def test_no_way_to_the_sights_holds_and_counts_none_escaped(self):
        answers = self.drive_phase2(hold.demon_beside_door, phase2_record())
        self.assertEqual(len(answers), 12, answers)
        self.assertTrue(all(row[4] == IPSISSIMUS and row[5] == 0 for row in answers), answers)
        self.assertTrue(all(row[2] == "5" for row in answers), answers)

    def test_the_hold_with_no_way_is_the_phase2_wait(self):
        # Owner 2026-11-06 「50ターン待っても来なくなったら」 (wait_limits.quiet_actions): none sensed, the
        # hold ends after that many and the count is made; sensed in the pen, they stay unescaped.
        limit = self.quiet_actions()
        unsensed = self.drive_phase2(without_sensed_ipsissimus, phase2_record(), count=limit + 5)
        self.assertTrue(all(row[4] == IPSISSIMUS and row[5] == 0 for row in unsensed[:limit]), unsensed)
        self.assertEqual((unsensed[limit][4], unsensed[limit][5]), (IPSISSIMUS + 1, 3), unsensed[limit])
        sensed = self.drive_phase2(hold.demon_beside_door, phase2_record(), count=limit + 5)
        self.assertTrue(all(row[4] == IPSISSIMUS and row[5] == 0 and row[2] == "5" for row in sensed),
                        sensed)

    def test_every_sight_reached_the_sensed_in_the_pen_are_not_escaped(self):
        answers = self.drive_phase2(hold.demon_beside_door, self.all_sights_reached(phase2_record()))
        self.assertTrue(all(row[4] == IPSISSIMUS and row[5] == 0 for row in answers), answers)

    def test_every_sight_reached_none_sensed_they_are_counted_escaped(self):
        # The existing count kept: every cell that sees the pen reached and none sensed there.
        answers = self.drive_phase2(without_sensed_ipsissimus, self.all_sights_reached(phase2_record()))
        self.assertGreater(answers[0][4], IPSISSIMUS, answers[:2])


if __name__ == "__main__":
    unittest.main()
