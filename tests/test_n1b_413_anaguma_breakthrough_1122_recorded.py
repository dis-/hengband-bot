"""n1-b life-413: the Anaguma tunnel dug out onto a corridor and on past it (2026-11-21).

Owner 2026-11-22 (verbatim): 「穴熊を作るとき、掘りすぎて反対側に掘り抜くケースが見られる。
掘りすぎると周囲7マス壁の要件を満たせなくなり意味がない。」

life-413 (Magic-Eater, Angband 44F, 23:28): for a pack of energy hounds (race 309, an animal
pack: 4 cells, up to 8) the plan dug down from the start (26,104), axis (1,0), side 1, the eight
cells (27,104) .. (34,105).  The absorbed mapping cast at (11,111) at turn 1813009 had shown a
corridor (33,99)-(33,104) and down column 104 from row 34: blank grids between marked walls,
which map_area leaves blank because they are floor (anaguma_geometry's docstring).  The plan
presumed those blanks rock and put its seventh cell (33,104) on the corridor's end.  From
(31,104) the dig melted (32,105) and stepped onto it (turn 1813874); there the seventh cell
showed open -- no use had been aimed at it -- and the dig stepped onto it as if it had melted it
(1813881, '1'); standing on the corridor's end with (33,103) and (34,104) open beside it, it
melted the eighth cell (34,105) as well (1813889, ``mBg3``).  The pocket's 7-wall enclosure was
gone from the melt of (32,105) on, and every later key only lengthened a passage into the
corridor.

The fixes (anaguma ``_dig_key``, anaguma_geometry ``floor``):

- a mapping's blank is open floor, never presumed rock: the plan from (26,104) stops at the
  fifth cell (31,104), whose neighbours are all rock but the mouth;
- before every melt and every step the cells dug so far and the next one are checked against
  the board; a tunnel cell found open that no use was aimed at is ground the tunnel came out
  on.  Either ends the dig (``BROKE_THROUGH``): the player holds where it stands when that is
  still a pocket, else the plan is released and the existing rules plan again.

Recorded (tests/fixtures/n1b-413-anaguma-breakthrough-1122.json.xz, see
tests/extract_n1b_413_anaguma_breakthrough_1122_fixture.py): the 44F player-turn boards from turn
1813730 to 1813902 and their decision rows.  Each pinned board is decided by the public
``choose_key`` after the earlier boards have gone through the policy's grid memory
(``_with_grid_memory``, as the live process remembered the dug cells it no longer saw).

DECLARED RECONSTRUCTED: the capture keeps no policy state.  The plan held during the dig is the
record's own tunnel (start, axis and side read off the record's melts and steps: the eight cells
it dug and aimed at), length 8, minimum 4, animal, races {309}, phase ``dig``; the uses aimed at
the six cells the record melted before the stop (sealed_pocket's count); the absorbed mapping
(me_powers floor memory) at (11,111), turn 1813009, from the record's decision row
``me-power:stairs-needed-and-unknown:map-area``; the skill reply and the absorbed wand list
(as test_n1b_411_anaguma_close_1119_recorded).
"""
import tests  # noqa: F401 -- isolate live runtime files

import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import anaguma, anaguma_geometry as geo, me_capability, me_powers, sealed_pocket
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import SV_STAFF_MAPPING, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, ProductionHarness, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-413-anaguma-breakthrough-1122.json.xz"
START = Position(26, 104)
AXIS, SIDE = (1, 0), 1
CORRIDOR_END = Position(33, 104)          # the seventh cell: open before any use
CORRIDOR = (Position(33, 103), Position(34, 104))
MAPPED_AT, MAPPED_TURN = Position(11, 111), 1813009
ENERGY_HOUND = 309
MELT_FROM_ROCK, STEP_INTO_ROCK, STEP_OUT, MELT_FROM_CORRIDOR = 1813864, 1813874, 1813881, 1813889


def _cells():
    return tuple(geo.cell(START, AXIS, SIDE, index) for index in range(1, anaguma.MAX_LENGTH + 1))


class AnagumaBreakthrough413RecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def board(self, turn):
        raw = next(row for row in self.data["boards"] if row["turn"] == turn)
        return parse_snapshot(raw, self.monrace)

    def recorded(self, turn):
        row = next(row for row in self.data["decisions"] if row["turn"] == turn)
        return row["reason"], row["key"], Position(row["position"]["y"], row["position"]["x"])

    def policy(self, turn, *, mapped):
        """The policy on the board of ``turn``, the plan of the dig held (module docstring)."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        policy.prime(parse_snapshot(self.data["boards"][0], self.monrace))
        for raw in self.data["boards"]:
            if raw["turn"] < turn:
                policy._with_grid_memory(parse_snapshot(raw, self.monrace))
        board = self.board(turn)
        # DECLARED RECONSTRUCTED (module docstring).
        policy._skill_exp_cache = (0, 0, board.player.level, policy._town_visit_epoch)
        policy._me_staff_sequence = MeStaffSequence(absorbed={})
        row = {"name": me_capability.names("wand", 6)[0], "current": 10, "max": 20, "fail": 5, "success": 95}
        policy._me_device_lists = {"wand": (board.turn, (row,))}
        cells = _cells()
        setattr(policy, anaguma.MEMORY, anaguma.Plan(
            board.floor_key, geo.Zigzag(START, AXIS, SIDE, cells), anaguma.MAX_LENGTH,
            anaguma.ANIMAL_LENGTH, True, frozenset({ENERGY_HOUND}), phase="dig",
            contact_turn=1813769))
        uses = sealed_pocket._memory(policy, board).uses
        for cell in cells[:6]:
            uses[(cell.y, cell.x)] += 1
        if mapped:
            self.mapped(policy, board)
        return policy, board

    @staticmethod
    def mapped(policy, board):
        memory = me_powers.FloorMemory(board.floor_key, 1808150)
        mapping = ("staff", SV_STAFF_MAPPING)
        memory.uses.append(me_powers.Use(mapping, mapping, "stairs-needed-and-unknown",
                                         MAPPED_AT, MAPPED_TURN))
        setattr(policy, me_powers.MEMORY, memory)

    def decide(self, turn, *, mapped=False):
        policy, board = self.policy(turn, mapped=mapped)
        key = policy.choose_key(policy.with_known_skill_exp(board))
        return policy, board, policy.last_reason, key

    # ------------------------------------------------------------ the record

    def test_the_record_steps_out_onto_the_corridor_and_melts_on(self):
        cells = _cells()
        self.assertEqual(self.recorded(STEP_OUT), ("anaguma:step", "1", cells[5]))
        self.assertEqual(self.recorded(MELT_FROM_CORRIDOR),
                         ("anaguma:dig:absorbed-power", "mBg3", CORRIDOR_END))
        self.assertEqual(cells[6], CORRIDOR_END)
        # No use was aimed at the seventh cell: from (32,105) the record stepped onto it.
        aimed = [row for row in self.data["decisions"] if row["reason"].startswith("anaguma:dig")
                 and row["position"] == {"y": 32, "x": 105}]
        self.assertEqual(aimed, [])
        before = self.board(1813759)
        blank = before.grid_at(CORRIDOR_END)
        self.assertTrue(blank is None or not blank.known)           # a blank of the map
        last = self.board(MELT_FROM_CORRIDOR)
        for cell in CORRIDOR:
            self.assertTrue(geo.open_cell(last.grid_at(cell)), cell)

    # ------------------------------------------------------------ the pins

    def test_the_mapped_corridor_is_not_presumed_rock(self):
        """The plan's start on the board of the walk: presumed rock, the eight cells of the record
        reach the corridor; read as the map shows it, the tunnel stops at the fifth cell."""
        policy, board = self.policy(1813759, mapped=True)
        blank = anaguma._blank(policy, board)
        for cell in (CORRIDOR_END, *CORRIDOR):
            self.assertIn((cell.y, cell.x), blank)
        presumed = geo.longest(board, START, AXIS, SIDE, anaguma.MAX_LENGTH)
        self.assertEqual(presumed.cells, _cells())
        mapped = geo.longest(board, START, AXIS, SIDE, anaguma.MAX_LENGTH, floor=blank)
        self.assertEqual(mapped.cells, _cells()[:5])
        self.assertGreaterEqual(len(mapped.cells), anaguma.ANIMAL_LENGTH)

    def test_with_the_map_the_dig_holds_on_the_fifth_cell(self):
        """On (31,104) before the melt of (32,105): the next cell touches the mapped corridor, so
        nothing is melted and the player holds on a pocket whose mouth is its only opening."""
        policy, board, reason, key = self.decide(MELT_FROM_ROCK, mapped=True)
        self.assertEqual(self.recorded(MELT_FROM_ROCK)[:2], ("anaguma:dig:absorbed-power", "mBg3"))
        self.assertEqual((reason, key), (anaguma.REASON_HOLD, "5"))
        current = anaguma.plan(policy)
        self.assertEqual((current.phase, current.length), ("hold", 5))
        self.assertTrue(geo.pocket_holds(board, current.pocket, current.mouth))

    def test_the_dig_does_not_step_out_onto_ground_it_did_not_melt(self):
        """On (32,105) without the map: the seventh cell is open and no use was aimed at it."""
        policy, _board, reason, key = self.decide(STEP_OUT)
        self.assertNotEqual((reason, key), ("anaguma:step", "1"))
        self.assertIsNone(anaguma.plan(policy))
        self.assertEqual(policy._anaguma_last_release, anaguma.BROKE_THROUGH)

    def test_the_dig_does_not_melt_on_from_the_corridor(self):
        """On the corridor's end with the corridor in view: no melt of the eighth cell."""
        policy, _board, reason, key = self.decide(MELT_FROM_CORRIDOR)
        self.assertFalse(reason.startswith(anaguma.REASON_DIG), (reason, key))
        self.assertIsNone(anaguma.plan(policy))
        self.assertEqual(policy._anaguma_last_release, anaguma.BROKE_THROUGH)

    def test_inside_unmapped_rock_the_dig_melts_and_steps_as_recorded(self):
        """Nothing known open: the melt of (32,105) and the step onto it are the record's."""
        for turn in (MELT_FROM_ROCK, STEP_INTO_ROCK):
            _policy_, _board, reason, key = self.decide(turn)
            self.assertEqual((reason, key), self.recorded(turn)[:2], turn)


if __name__ == "__main__":
    unittest.main()
