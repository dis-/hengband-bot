"""Quest 25 phase 5 with no attack left and the tome maybe still there: rest, and detect it.

Owner 2026-11-13, answering the open question of n1-b life-382's fix (quest25_battle
``_tome_gone``, now ``_immobile_gone``): with the tome possibly still on [9,8] (cells that see it
left), every grid-aimed attack and beam spent and no launcher, the phase answered nothing
(``quest:blocked:execute``).  The answer: 「休んで充填を待つ。また、可能なら感知して存在を確認する。」

The rule (quest25_battle ``_tome_unarmed``), through the shared refill (``_refill_key``, the
quylthulgs' 「使い切っただけなら休む」 too):

 1. out of the casters' fire first (``_leave_fire``, the walk of ``_withdraw``): the formation's
    「クイル・破壊集大成・ドルジの射線のマスでは待たず、休まない」;
 2. a detection that shows the tome's race from where its grid is within reach
    (``_confirm_tome_key``: the sweep's ``_detector``/``_detect_key``, hunt_target.REVEALS, the
    game's detect_monsters_* Grid::calc_distance <= DETECT_RAD_DEFAULT 30), read on the next board
    as the sweep reads its own (``_tome_absent``): a failed cast is cast again, the tome shown goes
    on, not shown ends the phase (``gone``, as ``_immobile_gone``);
 3. the between-phases rest (``_recharge_key``, ``quest25:rest-recharge``) until a charge is back.

Recorded: tests/fixtures/n1b-382-q25-patrol-owner-1113.json.gz (n1-b life-382, 2026-11-13
05:39, the tome phase; tests/test_n1b_382_q25_patrol_owner_1113_recorded).  Its restarted
process's board 6 is the board after a Rod of Detection the recorded process cast (decision 5,
'mCg'): two quylthulgs, no tome -- the "not shown" answer the game gave on this floor.  Each key
is decided through the public ``choose_key`` and posted through the production executor
(``_ExecutorInputPort``).

DECLARED CONSTRUCTED: the record without its reached sights (the tome's place not yet looked
at, so it may still be there); the boards without the light crossbow and its bolts (no launcher);
the magic-eater lists of the 01:33 dump with every attack power spent
(tests/test_n1b_384_q25_walk_sight_1113_recorded ``exhausted``; the Rod of Detection charged);
for the detection and the rest the player's cell set to the nearest cell out of the fire; the
control adds the tome on [9,8] to the detection's board.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import quest25_battle as battle
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.model import parse_snapshot
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay
from tests import test_n1b_384_q25_walk_sight_1113_recorded as walk_sight
from tests.support import recorded as harness
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_stage2_powers import TYPE_PROMPT

CASE = replay.CASE
BOARDS = CASE["second"]["boards"]
TOME_CELL = (9, 8)
SHOWN = 6          # the restarted process's board after its recorded Rod of Detection
DETECT = f"{battle.DETECT_REASON}:detect-all"
BLOCKED = "quest:blocked:execute"


def unarmed(raw, cell=None):
    """DECLARED CONSTRUCTED (module note): no launcher; at ``cell`` when given."""
    raw = copy.deepcopy(raw)
    raw["equipment"] = [item for item in raw["equipment"] if item.get("slot") != "bow"]
    raw["inventory"] = [item for item in raw["inventory"] if item.get("tval") != 18]
    if cell is not None:
        raw["player"]["y"], raw["player"]["x"] = cell
    return raw


def unproven():
    """DECLARED CONSTRUCTED (module note): the record without its reached sights."""
    record = copy.deepcopy(CASE["battle_record"])
    record["battle"]["blind_sights"] = {"set": []}
    return record


def with_tome(raw):
    """DECLARED CONSTRUCTED control: the detection's board showing the tome on its grid."""
    raw = copy.deepcopy(raw)
    shown = dict(raw["detected_monsters"][0], race_id=battle.geo.TOME, name="ラアルの破壊集大成",
                 index=99, y=TOME_CELL[0], x=TOME_CELL[1])
    raw["detected_monsters"] = [*raw["detected_monsters"], shown]
    return raw


class TomeRestDetectTest(replay._Replay):

    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.policy = replay.new_policy(Path(directory), walk_sight.exhausted(), unproven())

    def decide(self, raw):
        snapshot = parse_snapshot(copy.deepcopy(raw), self.policy._monrace_knowledge)
        key = self.policy.choose_key(snapshot)
        battle_now = self.policy._quest_navigators[25].phase_battle
        return snapshot, key, self.policy.last_reason, battle_now

    def post_power(self, raw, key, following):
        """A rod power through the production executor: the type prompt, the rod list, the game
        then showing ``following``."""
        game = harness.FaithfulHookGame()
        game.capacity = 256
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        game.screens = [prompt(TYPE_PROMPT), power_screen("rod", [(key[-1], "全感知", 0, 3, 5)]),
                        harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": self.policy.last_reason,
                                            "sequence": self.policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted[0], "m")
        self.policy.confirm_key_posted(key)

    def out_of_fire(self, snapshot):
        ctx = battle._ctx(self.policy, snapshot)
        fire = battle._fire(ctx)
        return min(battle._safe_cells(ctx, fire),
                   key=lambda cell: (battle.quest_exposure.game_distance(cell, ctx.here), cell))

    def test_in_the_tomes_fire_it_walks_out_first(self):
        raw = unarmed(BOARDS[4])
        snapshot, key, reason, fight = self.decide(raw)
        self.assertEqual(fight.phase, battle.phase_index("tome"))
        self.assertEqual(reason, battle.WITHDRAW_REASON, key)
        self.assertEqual((snapshot.player.position.y, snapshot.player.position.x), (4, 8))
        self.post(self.policy, raw, key, unarmed(BOARDS[5]))

    def _detect(self, shown_board):
        snapshot, key, reason, _fight = self.decide(unarmed(BOARDS[4]))
        self.post(self.policy, unarmed(BOARDS[4]), key, unarmed(BOARDS[5]))
        safe = self.out_of_fire(snapshot)
        self.assertLessEqual(battle.quest_exposure.game_distance(safe, TOME_CELL),
                             battle.me_powers.DETECT_RAD)
        raw = unarmed(BOARDS[5], safe)
        _snapshot, key, reason, fight = self.decide(raw)
        self.assertEqual((key, reason), ("mCg", DETECT), fight.phase)
        following = unarmed(shown_board, safe)
        self.post_power(raw, key, following)
        return safe, following

    def test_out_of_the_fire_a_detection_not_showing_it_ends_the_phase(self):
        safe, following = self._detect(BOARDS[SHOWN])
        _snapshot, key, reason, fight = self.decide(following)
        self.assertGreater(fight.phase, battle.phase_index("tome"))
        self.assertIn(battle.geo.TOME, fight.gone)
        self.assertNotEqual(reason, BLOCKED)

    def test_control_the_tome_shown_the_phase_rests_for_a_charge(self):
        safe, following = self._detect(with_tome(BOARDS[SHOWN]))
        answers = []
        raw = following
        for index in range(SHOWN, SHOWN + 6):
            _snapshot, key, reason, fight = self.decide(raw)
            answers.append((key, reason, fight.phase))
            nxt = unarmed(BOARDS[index + 1], safe)
            self.post(self.policy, raw, key, nxt)
            raw = nxt
        self.assertTrue(all(phase == battle.phase_index("tome") for *_rest, phase in answers), answers)
        reasons = {reason for _key, reason, _phase in answers}
        self.assertIn(battle.RECHARGE_REASON, reasons)
        self.assertNotIn(DETECT, reasons)        # shown once: no detection again while resting
        self.assertNotIn(BLOCKED, reasons)

    def test_a_failed_cast_is_cast_again(self):
        # DECLARED CONSTRUCTED: the board after the cast says it failed and shows nothing.
        failed = dict(copy.deepcopy(BOARDS[SHOWN]), detected_monsters=[],
                      messages=["呪文をうまく唱えられなかった！"])
        safe, following = self._detect(failed)
        _snapshot, key, reason, fight = self.decide(following)
        self.assertEqual((key, reason, fight.phase), ("mCg", DETECT, battle.phase_index("tome")))
        self.assertNotIn(battle.geo.TOME, fight.gone)


if __name__ == "__main__":
    unittest.main()
