"""The absorbed Detect Traps is cast beside harmless hostiles, not beside a threat (ME-TRAP-DETECT).

Owner 2026-11-22 (asked 「取り込んだトラップ感知を、害の無い敵（眠っている弱い敵など）が見えている時にも
唱えますか？」, answered 「害の無い敵の横でも唱える」): as the mapping (owner 2026-11-01 「脅威でなければ
感知する」), the Detect Traps row is ``beside_harmless`` (me_powers ``_hostiles_allow``: no visible
threat by ``visible_threat``, the combat ladder's own danger reading, and not just hit).

n1-c life-220 (Magic-Eater Lv32, Angband, 2026-11-22 10:23-10:24): on the 49F arrival stair
(24,7) five sleeping ogres were in view (a half-ogre and four ogres); the absorbed Detect Traps
(``mAm``) was held back, the Magic Mapping was cast instead and deep_fall_guard, finding no usable
trap detection on a floor whose trap door would newly reach 50F, left by the up stairs (20 round
trips, the loop fixed by tests/test_n1c_220_deep_fall_loop_1122_recorded.py).

Recorded: the 10:23:55 town-arrival checkpoint of n1-c life-220
(tests/fixtures/n1c-220-deep-fall-loop-1122, its town rows replayed as recorded) and the capture's
boards from the 48F down stair to the 49F board on which the Magic Mapping was cast (turn 1826835).

DECLARED CONSTRUCTED:

* after a Magic-Eater power key, the next board carries the completed operation the production
  executor adds to it (``_completed_operation_owner``/``_sequence``/``_receipt``,
  input_executor.py), which the capture's state.jsonl lines do not keep;
* the executor's game for the cast: the recorded board it is posted on, the Magic-Eater's type
  prompt and power list (cmd-magiceat.cpp, the staff row ``m`` トラップ感知 with the remembered
  charges, its fail rate written), and the recorded next board (on which the game showed the
  Magic Mapping's effect, not the Detect Traps');
* the threat case: the same 49F board with an awake Great Hell Wyrm (race 1192) two grids away.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import contextlib
import io
import json
import lzma
import pickle
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot import deep_fall_guard, me_capability, me_powers
from hengbot.cli import PostingContract, _ExecutorInputPort, _send_new_decision_key
from hengbot.model import SV_STAFF_DETECT_TRAP, Position, parse_snapshot
from support.town_arrival_fixture import load
from tests.support import recorded as executor_pins
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from town_work_corpus import replay_window

FIXTURE = Path(__file__).with_name("fixtures") / "n1c-220-deep-fall-loop-1122"
STAIR_49F = Position(24, 7)
MAPPED_TURN = 1826835        # recorded ('mAj', 'me-power:new-floor:map-area') beside the ogres
DETECT_TRAPS_KEY = "mAm"
GREAT_HELL_WYRM = 1192
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"


def _quiet(call, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return call(*args)


class DetectTrapsBesideHarmlessTest(executor_pins.ProductionHarness):

    @classmethod
    def setUpClass(cls):
        cls.scratch = TemporaryDirectory()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            cls.policy, _journal, steps = load(FIXTURE, Path(cls.scratch.name))
            cls.town = replay_window("n1c-220-deep-fall-loop", cls.policy, iter(steps))
        lines = lzma.decompress((FIXTURE / "boards.jsonl.xz").read_bytes()).decode(
            "utf-8").splitlines()
        seen = set()
        raws = []
        for line in lines:
            raw = json.loads(line)
            if raw.get("type") == "player_turn" and raw["turn"] not in seen:
                seen.add(raw["turn"])
                raws.append(raw)
        previous = None
        for index, raw in enumerate(raws):
            if previous is not None and previous[0][:1] in ("m", "U"):
                # DECLARED CONSTRUCTED (module docstring): the executor's completed operation.
                raw = dict(raw, _completed_operation_owner=previous[1],
                           _completed_operation_sequence=cls.policy._decision_sequence,
                           _completed_operation_receipt={})
            if raw["turn"] == MAPPED_TURN:
                cls.raw, cls.next_raw = raw, raws[index + 1]
                break
            board = parse_snapshot(raw, cls.policy._monrace_knowledge)
            key = _quiet(cls.policy.choose_key, board)
            previous = (key or "", cls.policy.last_reason)
        # Each test decides on its own copy of the policy before the 49F board.
        cls.before = pickle.dumps(cls.policy)

    @classmethod
    def tearDownClass(cls):
        cls.policy._home_disposal.history_path.unlink(missing_ok=True)
        cls.scratch.cleanup()

    def _policy(self):
        return pickle.loads(self.before)

    def _post(self, policy, key, raw, screens, next_raw, reason):
        """The production executor posts ``key`` on ``raw`` through ``screens``, the game showing
        ``next_raw`` after the command."""
        game = executor_pins.FaithfulHookGame()
        game.state = raw
        game.screen = executor_pins.command_screen(raw["turn"])
        game.screens = [*screens, executor_pins.command_screen(next_raw["turn"])]
        game.states = [next_raw for _screen in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        sent, _line = _send_new_decision_key(
            port, "recorded-board", key, None, set(), in_store=False,
            decision={"sequence": policy._decision_sequence, "reason": reason},
            snapshot=parse_snapshot(raw, policy._monrace_knowledge),
            posting_contract=PostingContract())
        self.assertTrue(sent, port.last_result.stop_line)
        return game.accepted

    def test_the_town_visit_replays_as_recorded(self):
        self.assertIsNone(self.town.first_divergence)

    def test_detect_traps_is_cast_beside_the_sleeping_ogres(self):
        policy = self._policy()
        board = parse_snapshot(self.raw, policy._monrace_knowledge)
        self.assertEqual((board.floor_key, board.player.position), ((1, 49, 0), STAIR_49F))
        hostiles = policy._physical_hostiles(board)
        self.assertEqual(len(hostiles), 5)
        self.assertTrue(all(monster.asleep for monster in hostiles))
        self.assertFalse(me_powers.visible_threat(policy, board))
        self.assertTrue(deep_fall_guard.at_risk(policy, board))
        self.assertTrue(deep_fall_guard.holds_detection(policy, board))
        # Recorded 2026-11-22 10:24: ('mAj', 'me-power:new-floor:map-area'), then the leave.
        key = _quiet(policy.choose_key, board)
        self.assertEqual(key, DETECT_TRAPS_KEY)
        self.assertEqual(policy.last_reason, "me-power:new-floor:detect-traps")
        charges = me_capability.charges(policy, board, "staff", SV_STAFF_DETECT_TRAP)
        self.assertGreater(charges, 0)
        screens = [prompt(TYPE_PROMPT),
                   power_screen("staff", [("m", "トラップ感知", charges, charges, 5)])]
        accepted = self._post(policy, key, self.raw, screens, self.next_raw, policy.last_reason)
        self.assertEqual("".join(accepted), DETECT_TRAPS_KEY)

    def test_the_deep_fall_guard_detects_instead_of_leaving(self):
        policy = self._policy()
        board = parse_snapshot(self.raw, policy._monrace_knowledge)
        _quiet(me_powers.observe, policy, board)
        key = _quiet(deep_fall_guard.key, policy, board)
        self.assertEqual(key, DETECT_TRAPS_KEY)
        self.assertEqual(policy.last_reason, deep_fall_guard.DETECT_REASON)

    def test_no_detect_traps_beside_a_threat(self):
        policy = self._policy()
        # DECLARED CONSTRUCTED (module docstring): an awake Great Hell Wyrm beside the ogres.
        race = policy._monrace_knowledge[GREAT_HELL_WYRM]
        wyrm = dict(self.raw["visible_monsters"][0], asleep=False, index=99, level=race.level,
                    race_id=GREAT_HELL_WYRM, y=26, x=9)
        raw = dict(self.raw, visible_monsters=[*self.raw["visible_monsters"], wyrm])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertTrue(me_powers.visible_threat(policy, board))
        probe = self._policy()
        _quiet(me_powers.observe, probe, board)
        self.assertIsNone(_quiet(me_powers.power_key, probe, board, me_powers.TRAP_CELL))
        key = _quiet(policy.choose_key, board)
        self.assertNotEqual(key, DETECT_TRAPS_KEY)
        self.assertNotIn("detect-traps", policy.last_reason or "")


if __name__ == "__main__":
    unittest.main()
