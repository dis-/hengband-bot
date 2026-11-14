"""n1-b life-397 2026-11-14: the telepathy amulet waited in the Home and every dive stayed at 49F.

Owner 2026-11-14 「n1-bがテレパシー装備を手に入れたのに50F以降に進まない理由」.  The
Lv47 Magic-Eater (absorbed *Destruction* at 95%, 26 charges) picked up a
テレパシーのアミュレット {~感} on 49F of the Castle and put it in the Home.  From 50F the
depth requirements add telepathy (DEPTH_ABILITY_REQUIREMENTS, cumulative); the worn
set had every other one, so the destination stayed at 49F (_resistance_depth_limit 49,
missing at 50F: telepathy only).  Two causes kept the amulet off:

* From 16:15 (Lv45) the STR and CON maxima printed a '!' over the ':' of their rows of
  the character sheet (display-player-stat-info.cpp process_stats), the sheet parser
  read every dump as ``partial-stat-table`` and the equipment optimizer answered
  ``calibration-required-return`` on every board: it never ran again.
* Its search from the worn set changes one slot at a time.  The amulet replaces the
  worn 賢者のアミュレット, the only worn Free Action (required from 20F), so it was
  refused alone, and the Home's Free Action gauntlets or cloaks alone unlocked
  nothing: no searched set met 50F ("no-set" on the 80 band).

Recorded: the town-arrival checkpoint of the 19:14:06 visit, its first 84 journal rows
and the sidecar files (tests/extract_n1b_397_50f_gate_1114_fixture.py), decided through
the public choose_key and compared with the record; the arrival policy keeps the
calibration state it held (the rejected dump), not the Lv45 sidecar calibration.  Row
82 is the visit's character dump; on row 83 the recorded bot walked on to the next
shop (shop:travel), and the key decided now walks to the Home for the transaction that
wears the amulet, posted through the production executor (_ExecutorInputPort).

DECLARED CONSTRUCTED: the game wrote the row-82 dump to the dump file, which the
journal does not hold; the sidecar copy of the dump (the same character, taken at the
arrival) is written again after the posted dump.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from hengbot.character_sheet import parse_character_sheet
from hengbot.cli import TRAVEL_MACRO_TRIGGERS
from hengbot.equipment_optimizer import ABILITY_FLAG, divable_depth, required_abilities
from hengbot.policy import staged_prompt_chain_matches
from support.town_arrival_fixture import load
from tests.support import recorded as executor_harness

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-397-50f-gate-1114"
DUMP_ROW = 82
BOARD_ROW = 83
AMULET = "テレパシーのアミュレット {~感}"


def post_recorded(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


class N1b397FiftyFloorGateRecordedTest(executor_harness.RecordedHarness):
    @classmethod
    def setUpClass(cls):
        # The dungeon-1031 corpus of RecordedHarness is not read.
        cls.scratch = TemporaryDirectory()
        policy, cls.journal, steps = load(
            FIXTURE, Path(cls.scratch.name), adopt_recorded_calibration=False)
        cls.policy = policy
        cls.arrival_reason = policy._calibration_unavailable_reason
        dump = Path(policy._character_dump_path)
        cls.dump = dump.read_bytes()
        cls.replayed = []
        for recorded, supply in steps[:BOARD_ROW]:
            board = supply()
            key = policy.choose_key(board)
            cls.replayed.append(((key, policy.last_reason), (recorded["key"], recorded["reason"])))
            post_recorded(policy, key)
            if recorded["row"] == DUMP_ROW:
                # DECLARED CONSTRUCTED (module docstring): the game writes the dump.
                time.sleep(0.02)
                dump.write_bytes(cls.dump)
        cls.board = steps[BOARD_ROW][1]()
        cls.key = policy.choose_key(cls.board)
        cls.reason = policy.last_reason

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def test_the_visit_replays_to_the_dump(self):
        for row, (decided, recorded) in enumerate(self.replayed):
            self.assertEqual(decided, recorded, row)
        self.assertEqual(self.journal[DUMP_ROW]["reason"], "town:character-dump")
        self.assertEqual(self.arrival_reason, "partial-stat-table")

    def test_the_sheet_with_maximum_marks_parses(self):
        lines = self.dump.decode("euc_jp").splitlines()
        header = next(index for index, line in enumerate(lines) if "abcdefghijkl@" in line)
        table = lines[header + 1:header + 7]
        # The '!' of a stat at its maximum stands where the ':' of the others is.
        self.assertIn("腕力 !18/100", table[0])
        self.assertIn("知能 :18/129", table[1])
        self.assertIn("耐久 ! 18/70", table[4])
        sheet = parse_character_sheet(self.dump)
        self.assertEqual([(row.base, row.actual) for row in sheet.rows],
                         [(118, 178), (147, 127), (85, 25), (128, 188), (88, 208), (66, 66)])
        self.assertEqual((sheet.level, sheet.max_hp, sheet.language), (47, 975, "ja"))

    def test_the_optimizer_wears_the_amulet_and_keeps_free_action(self):
        policy = self.policy
        self.assertIsNotNone(policy._character_calibration)
        self.assertIsNone(policy._calibration_unavailable_reason)
        result = policy._equipment_optimization_preparation.result
        self.assertFalse(result.timed_out)
        bands = {decision.band: decision for decision in result.band_decisions}
        self.assertTrue(bands[80].satisfying_set_existed)
        self.assertEqual(result.chosen_depth, 80)
        best = result.best.loadout
        worn = {slot: item.item.name for slot, item in best.slots}
        self.assertEqual(worn["neck"], AMULET)
        self.assertNotEqual(worn["neck"], self.worn("neck"))
        # Every 50F requirement is met by the set and the character's own abilities:
        # Free Action now comes from another slot.
        intrinsic = policy._character_calibration.intrinsic_abilities
        abilities = set(intrinsic) | {
            name for name, flag in ABILITY_FLAG.items() if flag in best.flags}
        self.assertLessEqual(required_abilities(80), abilities)
        free_action = [slot for slot, item in best.slots
                       if ABILITY_FLAG["free_action"] in item.flags]
        self.assertTrue(free_action)
        self.assertNotIn("neck", free_action)
        self.assertEqual(divable_depth(best, intrinsic_abilities=frozenset(intrinsic),
                                       has_destruction=True,
                                       speed_bonus=result.best.metrics.speed_bonus), 80)
        # The worn set reaches 49F, the telepathy its only gap at 50F.
        self.assertEqual(policy._resistance_depth_limit(self.board), 49)
        self.assertEqual(policy._missing_required_abilities(self.board, 50), {"telepathy"})

    def test_the_board_walks_to_the_home_through_the_executor(self):
        recorded = self.journal[BOARD_ROW]
        self.assertEqual((recorded["key"], recorded["reason"]), ("\x1b`n(.", "shop:travel"))
        self.assertEqual((self.key, self.reason), ("\x1b`n(.", "equipment-transaction:travel-home"))
        raw = json.loads(recorded["line"] if recorded["line"] is not None else recorded["inputs"][-1])
        self.assertEqual(self.post(self.policy, raw, self.key, [], self.later(raw)),
                         [TRAVEL_MACRO_TRIGGERS[self.key]])

    def worn(self, slot):
        return next(item.name for item in self.board.equipment if item.slot == slot)


if __name__ == "__main__":
    import unittest
    unittest.main()
