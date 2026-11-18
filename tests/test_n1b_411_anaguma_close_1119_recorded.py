"""n1-b life-411: the Anaguma close-in step into a vein after a *Destruction* (2026-11-19).

life-411 (Magic-Eater Lv 50, Angband 95F, 05:15, loop-detected): a pocket for a pack of race 535
(an animal pack) was dug from the start (27,92) up to the pocket (19,91), eight cells.  The pack
stayed out; the detection after the wait showed one member left, at (24,78), so the plan went to
``close``: the absorbed Speed, then the step back down the tunnel to (20,92).  There a lesser
titan's attack drew the emergency *Destruction* (``mA3``), which turned the tunnel cell (21,91)
into a magma vein.  The close-in never looked at the board again: ``anaguma:close-step`` sent
'1' into the vein twelve times (「溶岩の鉱脈が行く手をはばんでいる。」, no game turn spent) until
the loop guard stopped the bot.

The fix: the close-in's step back along the tunnel is taken only onto an open cell; when the
tunnel back is closed (a *Destruction* re-walled it) there is no exit to follow and the plan
ends (``anaguma.CLOSE_BLOCKED``), as the walk and the dig end on a board that no longer fits
(``anaguma._site_lost``).

Recorded (tests/fixtures/n1b-411-anaguma-close-1119.json.xz, see
tests/extract_n1b_411_anaguma_close_1119_fixture.py): the player-turn boards from turn 8162386,
their decision rows, the absorption record and the plan held at the stop.  The stop's board is
decided by the public ``choose_key`` with the plan held at the stop.

DECLARED RECONSTRUCTED (as test_n1b_393_anaguma_walk_1114_recorded): the skill reply and the
absorbed wand and staff lists the process remembered.  The absorbed *Destruction* the record cast
(``mA3``) is listed with charges left, as the record's ladder read it (no means-spent return was
latched at the stop: ``_returning_to_town`` None in the incident's policy state).
"""
import tests  # noqa: F401 -- isolate live runtime files

import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import anaguma, anaguma_geometry as geo, me_capability
from hengbot.me_staff_sequence import MeStaffSequence
from hengbot.model import SV_STAFF_DESTRUCTION, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from tests.support.recorded import EDIT, ProductionHarness, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-anaguma-close-1119.json.xz"
STUCK = Position(20, 92)
VEIN = Position(21, 91)


def _plan(raw) -> anaguma.Plan:
    tunnel = raw["tunnel"]
    current = anaguma.Plan(
        tuple(raw["floor"]),
        geo.Zigzag(Position(*tunnel["start"]), tuple(tunnel["axis"]), tunnel["side"],
                   tuple(Position(*cell) for cell in tunnel["cells"])),
        raw["length"], raw["minimum"], raw["animal"], frozenset(raw["races"]),
        phase=raw["phase"], contact_turn=raw["contact_turn"])
    current.detected_turn = raw["detected_turn"]
    current.target = None if raw["target"] is None else Position(*raw["target"])
    current.hasted = raw["hasted"]
    return current


class AnagumaClose411RecordedTest(ProductionHarness):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8", "surrogateescape"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def board(self, raw):
        return parse_snapshot(raw, self.monrace)

    def policy(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.board(self.data["boards"][0])
        policy.prime(first)
        # DECLARED RECONSTRUCTED (module docstring): the skill reply and the absorbed lists.
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_staff_sequence = MeStaffSequence(absorbed=dict(self.data["absorbed"]))
        row = {"name": me_capability.names("wand", 6)[0], "current": 10, "max": 20, "fail": 5, "success": 95}
        destruction = {"name": me_capability.names("staff", SV_STAFF_DESTRUCTION)[0], "current": 5,
                       "max": 10, "fail": 5, "success": 95}
        policy._me_device_lists = {"wand": (first.turn, (row,)), "staff": (first.turn, (destruction,))}
        return policy

    def decide(self, policy, board):
        key = policy.choose_key(policy.with_known_skill_exp(board))
        return key, policy.last_reason

    def stop(self):
        """The stop's board decided with the plan held at the stop (the record's policy state)."""
        policy = self.policy()
        self.decide(policy, self.board(self.data["boards"][-2]))
        setattr(policy, anaguma.MEMORY, _plan(self.data["stop_plan"]))
        last = self.data["boards"][-1]
        return (policy, last) + self.decide(policy, self.board(last))

    # ------------------------------------------------------------ the record

    def test_the_record_steps_into_the_vein_at_the_stop(self):
        steps = [row for row in self.data["decisions"]
                 if row["reason"] == anaguma.REASON_CLOSE_STEP and row["position"] == {"y": 20, "x": 92}]
        self.assertGreaterEqual(len(steps), 12)
        self.assertTrue(all(row["key"] == "1" for row in steps))
        self.assertTrue(any(row["reason"].startswith("emergency:destruction") for row in self.data["decisions"]))
        plan = _plan(self.data["stop_plan"])
        self.assertEqual(plan.phase, "close")
        self.assertEqual(plan.tunnel.before(plan.cells.index(STUCK)), VEIN)
        last = self.board(self.data["boards"][-1])
        self.assertEqual(last.player.position, STUCK)
        self.assertTrue(last.grid_at(VEIN).known)
        self.assertFalse(last.grid_at(VEIN).passable)               # the magma vein

    # ------------------------------------------------------------ the pins

    def test_the_close_in_ends_when_the_tunnel_back_is_closed(self):
        """The stop's plan on the stop's board: the cell back down the tunnel is a vein, so the
        close-in ends instead of stepping into it."""
        policy, raw, key, reason = self.stop()
        self.assertNotEqual((reason, key), (anaguma.REASON_CLOSE_STEP, "1"))
        self.assertIsNone(anaguma.plan(policy))
        self.assertEqual(getattr(policy, "_anaguma_last_release", None), anaguma.CLOSE_BLOCKED)

    def test_the_close_in_still_steps_back_along_an_open_tunnel(self):
        """The board before the *Destruction*: on the pocket, the cell back (20,92) is open,
        and the close-in steps onto it as recorded ('3')."""
        policy = self.policy()
        raw = next(board for board in self.data["boards"]
                   if board["turn"] == 8162388)
        current = _plan(self.data["stop_plan"])
        setattr(policy, anaguma.MEMORY, current)
        key, reason = self.decide(policy, self.board(raw))
        self.assertEqual((reason, key), (anaguma.REASON_CLOSE_STEP, "3"))


if __name__ == "__main__":
    unittest.main()
