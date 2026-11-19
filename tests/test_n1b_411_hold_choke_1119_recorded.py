"""A pack an expired choke hold waited out arms no later wait on the floor (n1-b life-411, 1119).

n1-b life-411 (Magic-Eater Lv50, Angband 95F, 2026-11-19 15:21:56-15:52:26) was halted by the
server watcher ``stall:floor-dwell:seek-loot``.  Of the floor's 6,743 game turns, 4,137 (61%)
were ``detected:hold-choke`` and ``summoner:hold-choke`` waits at chokes beside two packs that
never came: a wolf pack (Draugluin, Pennywise, wolf chieftains, hounds) and an orc nest (snagas,
cave orcs, an orc shaman), awake and detected two to three cells away behind their walls,
never in view.  Each wait ended by its bound (owner 2026-09-20 「構えて待つと決めて50ターン敵の
目視がなければ解除する」, ``DETECTED_THREAT_HOLD_MAX_GAME_TURNS``): six of them ran the whole 500
game turns.  The expiry latched the owner only until the next hostile in view; the bot shot a
blink dog or an orc, walked on, came near the same pack and waited 500 game turns again.

Now the hostiles a hold waited out (owner 2026-10-28 「待っても来ないかで判定」, and the anaguma
answer of 2026-11-11 「その階ではもう掘らない」) arm no later detected-pack preparation on the
floor visit (summoner_wait.record_outwaited / outwaited).

Recorded (tests/fixtures/n1b-411-hold-choke-1119.json.xz,
tests/extract_n1b_411_hold_choke_1119_fixture.py): four runs of the floor's player-turn boards,
decided in order by one policy's public ``choose_key`` -- the prepare-choke walk and the hold at
(20,18) it began, the same hold's bound, a hostile shot in view at (13,27), and the walk back
near the wolves where the recording prepared a choke and waited at (30,12) again.

DECLARED RECONSTRUCTED: the Magic-Eater's power lists are the viewer's record of the same
character on 2026-11-19 05:41 (fixtures/n1b-411-loot-walk-1119.me-lists.json, the capture keeps
none), and the floor's earlier power uses (the once-only arrival casts, and the redetection the
decision log shows the floor making again and again) are put in me_powers' ``FloorMemory`` at
the first board of each run; without them the replay casts them instead of walking.  The runs
are not contiguous: the boards between them are left out.
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot import me_powers, summoner_wait
from hengbot.model import SV_ROD_DETECTION, SV_STAFF_DETECT_EVIL, Position, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy_constants import DETECTED_THREAT_HOLD_MAX_GAME_TURNS
from tests.support.recorded import EDIT, _policy

FIXTURE = Path(__file__).with_name("fixtures") / "n1b-411-hold-choke-1119.json.xz"
ME_LISTS = Path(__file__).with_name("fixtures") / "n1b-411-loot-walk-1119.me-lists.json"
HOLD_CELL = Position(20, 18)
HOLD_START = 8902486
REARM = 8903329          # (23,14): the recording's detected:prepare-choke toward the wolves
WOLF_HOLD = 8903347      # (30,12): the recording's summoner:hold-choke, 500 game turns again
PREPARE = "detected:prepare-choke"
WAITS = summoner_wait.HOLD_CHOKE_REASONS | {PREPARE}


class HoldChoke1119RecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.lists = json.loads(ME_LISTS.read_text(encoding="utf-8"))
        cls.monrace = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.recorded = {row["turn"]: row["reason"] for row in cls.data["decisions"]}

    def board(self, raw):
        return parse_snapshot(copy.deepcopy(raw), self.monrace)

    def replay(self, runs, *, between=None):
        """Decide every board of ``runs`` in order; {turn: (board, key, reason)}."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        policy = _policy(Path(directory.name), self.monrace)
        first = self.board(self.data["runs"][runs[0]][0])
        policy.prime(first)
        policy._skill_exp_cache = (0, 0, first.player.level, policy._town_visit_epoch)
        policy._me_device_lists = {kind: (first.turn, tuple(listed["rows"]))
                                   for kind, listed in self.lists.items()}
        memory = me_powers.FloorMemory(first.floor_key, first.turn)
        for power in me_powers.POWERS:
            if ("new-floor" in power.triggers and power.effect != "detect-evil") or (
                    "deep-arrival-unhasted" in power.triggers):
                memory.uses.append(me_powers.Use(power.ident, power.ident, "new-floor",
                                                 first.player.position, first.turn))
        setattr(policy, me_powers.MEMORY, memory)
        answers = {}
        for name in runs:
            if between is not None:
                between(policy, name)
            start = self.board(self.data["runs"][name][0])
            # DECLARED RECONSTRUCTED (module docstring): the floor's redetection.
            getattr(policy, me_powers.MEMORY).uses.append(me_powers.Use(
                ("staff", SV_STAFF_DETECT_EVIL), ("rod", SV_ROD_DETECTION),
                "deep-explore-redetect", start.player.position, start.turn))
            for raw in self.data["runs"][name]:
                board = policy.with_known_skill_exp(self.board(raw))
                key = policy.choose_key(board)
                answers[board.turn] = (board, key, policy.last_reason)
                if key:
                    policy.confirm_key_posted(key)
        return policy, answers

    # ------------------------------------------------------------ the record

    def test_the_record_waits_at_the_wolves_again_after_waiting_out_a_hold(self):
        self.assertEqual(self.recorded[REARM], PREPARE)
        self.assertEqual(self.recorded[WOLF_HOLD], summoner_wait.HOLD_CHOKE_REASON)
        holds = [turn for turn, reason in self.recorded.items()
                 if reason == summoner_wait.DETECTED_HOLD_CHOKE_REASON]
        self.assertGreaterEqual(max(holds) - HOLD_START, DETECTED_THREAT_HOLD_MAX_GAME_TURNS - 1)
        sight = [self.board(raw) for raw in self.data["runs"]["sight"]]
        self.assertTrue(any(board.visible_monsters for board in sight))

    def test_a_fresh_policy_prepares_the_choke_as_recorded(self):
        """Control: without the waited-out hold the walk near the wolves arms the wait."""
        _, answers = self.replay(["rearm"])
        self.assertEqual(answers[REARM][2], PREPARE)
        self.assertEqual(answers[WOLF_HOLD][1:], ("5", summoner_wait.HOLD_CHOKE_REASON))

    # ------------------------------------------------------------ the pins

    def test_the_hold_waits_to_its_bound_and_records_the_pack(self):
        policy, answers = self.replay(["arm", "expire"])
        board, key, reason = answers[HOLD_START]
        self.assertEqual(board.player.position, HOLD_CELL)
        self.assertEqual((key, reason), ("5", summoner_wait.DETECTED_HOLD_CHOKE_REASON))
        expired = [turn for turn in answers if turn - HOLD_START > DETECTED_THREAT_HOLD_MAX_GAME_TURNS]
        self.assertTrue(expired)
        for turn in expired:
            self.assertNotIn(answers[turn][2], WAITS)
        memory = getattr(policy, summoner_wait.OUTWAITED)
        self.assertEqual(memory[:2], (board.floor_key, HOLD_START))
        self.assertTrue(memory[2])

    def test_the_waited_out_pack_does_not_arm_another_wait(self):
        """Recorded: detected:prepare-choke at (23,14), then 500 game turns of
        summoner:hold-choke at (30,12).  Now the walk goes on."""
        _, answers = self.replay(["arm", "expire", "sight", "rearm"])
        rearm = [raw["turn"] for raw in self.data["runs"]["rearm"]]
        self.assertIn(REARM, rearm)
        self.assertIn(WOLF_HOLD, rearm)
        for turn in rearm:
            self.assertNotIn(answers[turn][2], WAITS, turn)

    def test_a_new_floor_visit_forgets_the_waited_out_pack(self):
        """The memory is the floor visit's: forgotten, the same boards arm the wait again."""
        def between(policy, name):
            if name == "rearm":
                summoner_wait.forget_floor_visit(policy)
        _, answers = self.replay(["arm", "expire", "sight", "rearm"], between=between)
        self.assertEqual(answers[REARM][2], PREPARE)


if __name__ == "__main__":
    unittest.main()
