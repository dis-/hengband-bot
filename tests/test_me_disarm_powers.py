"""#47: the Magic-Eater aims an absorbed disarming power at the trap it would
disarm (me_powers, owner 2026-11-01).

Owner: 「魔道具術師が罠を解除するとき、トラップ解除やトラップ/ドア破壊を取り込み済なら
使用する」.  The rows are the Rod of Disarming (rod 14), the Wand of Disarming
(wand 4) and the Wand of Trap/Door Destruction (wand 5); the trigger is
``trap-to-disarm``, asked by the walk's trap step (policy_navigation
._step_toward) and the chest pipeline's disarm phase.

Boards are the recorded n1-c Magic-Eater board of life 16 on Yeek cave 1F
(turn 94171, tests/fixtures/me-mining-death-20261030.json.gz, see
test_me_stage2_powers) through the public choose_key and the production
executor.  On it the bot walks west ('4', fundraise:seek-upstairs-door) to
(14, 44) along a one-wide corridor.

DECLARED CONSTRUCTED: no recorded character has absorbed these devices yet,
so the displayed wand/rod lists (``_me_device_lists`` rows: BaseitemDefinitions
names, charges and fail percentages chosen per case) are constructed; a pit
(TerrainDefinitions id 17, TRAP) is drawn on the corridor step (14, 44); the
chest case draws a small wooden chest (tval 7) on the floor east of the player
with the pipeline seeded at its disarm phase and the town return patched out
(as test_me_stage2_powers' before-rest case) so the pipeline is reached; the
renamed-walk case wraps the fundraising route producer to rename its decision
after the walk returned (the shape of dark:backtrack, policy_navigation.py
``key = self._step_toward(...); self.last_reason = ...``).  The stage-2 staff
powers are seeded as used here.  Replies are the game's prompts
(cmd-magiceat.cpp: kind, power list, get_aim_dir).

The rows are cast beside harmless visible hostiles (``beside_harmless``,
owner 2026-11-01 answer 8 「脅威でなければ使う」) and never beside a dangerous
one or after a hit.
"""
import tests  # noqa: F401 -- isolate live runtime files

from dataclasses import replace
import unittest
from unittest import mock

from hengbot import me_powers
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import CHEST_SEARCH_BUDGET
from tests import test_me_mapping_1101_recorded as mapping_recorded
from tests import test_me_stage2_powers as stage2
from tests.support.recorded import command_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

TRAP_STEP = Position(14, 44)       # west of the player (14, 45)
CHEST_AT = Position(14, 46)        # east of the player
PIT = 17                           # TerrainDefinitions TRAP_PIT
TERRAIN_TRAP_BIT = 1 << 14         # model._GRID_TERRAIN_NAMES "trap"
FLOOR_BITS = 416                   # the fixture's floor (los, move, floor)
TVAL_CHEST = 7
DISARMING, TRAP_DOOR = "トラップ解除", "トラップ/ドア破壊"
ROD_DISARMING, WAND_DISARMING, WAND_TRAP_DOOR = ("rod", 14), ("wand", 4), ("wand", 5)
DIRECTION_PROMPT = "方向 ('*'でターゲット選択, ESCで中断)?"
CALM = {"_returning_to_town": False, "_emergency_return_active": False,
        "_fundraising_mode": None}


def _stage2(name):
    return getattr(stage2.MagicEaterStage2PowersTest, name)


def wand_row(name, current):
    return {"name": name, "current": current, "max": 10, "fail": 20, "success": 80}


def rod_row(charging):
    return {"name": DISARMING, "charging": charging, "max": 1, "fail": 20, "success": 80}


class MagicEaterDisarmPowersTest(stage2.mining.harness.ProductionHarness):
    setUpClass = classmethod(_stage2("setUpClass").__func__)
    raw = _stage2("raw")
    recorded_policy = _stage2("recorded_policy")
    choose = _stage2("choose")
    post = _stage2("post")
    board = _stage2("board")
    staff_policy = _stage2("policy")

    def trapped(self, cell=TRAP_STEP):
        raw = self.board()
        grid_map = raw["grid_map"]
        grid_map["palette"].append([PIT, 0, FLOOR_BITS | TERRAIN_TRAP_BIT, 1])
        grid_map["runs"].append([cell.y, cell.x, 1, len(grid_map["palette"]) - 1])
        return raw

    def policy(self, raw, *, wand=(), rod=None):
        here = Position(raw["player"]["y"], raw["player"]["x"])
        policy = self.staff_policy(raw, used={stage2.EVIL: here, stage2.TRAP: here,
                                              stage2.MAPPING: here})
        lists = {}
        if wand:
            lists["wand"] = (raw["turn"], tuple(wand))
        if rod is not None:
            lists["rod"] = (raw["turn"], (rod,))
        policy._me_device_lists = lists
        return policy

    def zap(self, policy, raw, key, *, after=()):
        """Post the power key through the executor's kind/list/aim answers."""
        kind = me_powers.kind_of(key[1])
        rows = ([("o", DISARMING, 0, 1, 20)] if kind == "rod" else
                [("e", DISARMING, 3, 10, 20), ("f", TRAP_DOOR, 3, 10, 20)])
        game, port = self.post(policy, raw, key, [
            prompt(stage2.TYPE_PROMPT), power_screen(kind, rows),
            prompt(DIRECTION_PROMPT, "direction", can_choose_target=True), *after])
        self.assertEqual(game.accepted, ["m", key[1], key[2], key[3]])
        return port.last_result.board

    def assertAimed(self, policy, key, expected, effect="disarm-trap"):
        self.assertEqual((key, policy.last_reason),
                         (expected, f"me-power:trap-to-disarm:{effect}"))

    def test_absorbed_disarming_wand_is_aimed_at_the_trap_step(self):
        raw = self.trapped()
        policy = self.policy(raw, wand=[wand_row(DISARMING, 3)])
        key = self.choose(policy, raw)
        self.assertAimed(policy, key, "mBe4")
        self.zap(policy, raw, key)
        # The disarm command's own budget is untouched by the power.
        self.assertEqual(policy._floor_trap_disarm_attempts[(TRAP_STEP.y, TRAP_STEP.x)], 0)

    def test_order_rod_then_disarming_wand_then_trap_door_wand(self):
        cases = (
            ("rod and both wands", [wand_row(DISARMING, 3), wand_row(TRAP_DOOR, 3)],
             rod_row(0), "mCo4", "disarm-trap"),
            ("both wands", [wand_row(DISARMING, 3), wand_row(TRAP_DOOR, 3)], None,
             "mBe4", "disarm-trap"),
            ("rod charging", [wand_row(TRAP_DOOR, 3)], rod_row(1), "mBf4", "destroy-trap-door"),
            ("only trap/door", [wand_row(TRAP_DOOR, 3)], None, "mBf4", "destroy-trap-door"),
        )
        for label, wand, rod, expected, effect in cases:
            with self.subTest(label):
                raw = self.trapped()
                policy = self.policy(raw, wand=wand, rod=rod)
                key = self.choose(policy, raw)
                self.assertAimed(policy, key, expected, effect)
                self.zap(policy, raw, key)

    def test_without_an_absorbed_charged_power_the_disarm_command_stays(self):
        cases = {"not absorbed": {}, "no charge": {"wand": [wand_row(DISARMING, 0),
                                                            wand_row(TRAP_DOOR, 0)]},
                 "rod charging": {"rod": rod_row(1)}}
        for label, lists in cases.items():
            with self.subTest(label):
                raw = self.trapped()
                policy = self.policy(raw, **lists)
                self.assertEqual(self.choose(policy, raw), "D4")
                self.assertEqual(policy.last_reason, "fundraise:seek-upstairs-door")

    def test_failed_zap_is_retried_at_the_same_place_up_to_five_failures(self):
        # Owner 2026-10-31 「最大5回まで同じ場所で試す」.
        raw = self.trapped()
        policy = self.policy(raw, wand=[wand_row(DISARMING, 3)], rod=rod_row(0))
        board = raw
        for failure_number in range(1, me_powers.FAILURES_PER_PLACE + 1):
            key = self.choose(policy, board)
            self.assertAimed(policy, key, "mCo4")
            failure = command_screen(board["turn"] + 10)
            failure["lines"][0] = stage2.FAILED
            board = self.zap(policy, board, key, after=[failure])
            self.assertEqual(board["_completed_operation_receipt"]["refusal"],
                             "failed:magic-eater", failure_number)
        # Five rod failures here: the wand, then the disarm command after its five.
        key = self.choose(policy, board)
        self.assertAimed(policy, key, "mBe4")
        policy._me_power_floor.failed[(WAND_DISARMING, "trap-to-disarm", Position(14, 45))] = 5
        self.assertEqual(self.choose(policy, board), "D4")

    def test_one_aim_per_trap_then_the_walk(self):
        raw = self.trapped()
        policy = self.policy(raw, wand=[wand_row(DISARMING, 3)])
        key = self.choose(policy, raw)
        board = self.zap(policy, raw, key)
        # A trap still shown after the turn is left to the disarm command.
        self.assertEqual(self.choose(policy, board), "D4")
        use = policy._me_power_floor.uses[-1]
        self.assertEqual((use.used, use.target, use.key), (WAND_DISARMING, TRAP_STEP, "mBe4"))
        cleared = self.board()
        cleared["turn"] = board["turn"]
        self.assertEqual(self.choose(policy, cleared), "4")

    def test_a_walk_renamed_after_the_step_keeps_the_power_reason(self):
        original = HengbotPolicy._fundraising_return_route_key

        def renamed(self, key, **kwargs):
            result = original(self, key, **kwargs)
            self.last_reason = "fundraise:renamed-after-walk"
            return result

        raw = self.trapped()
        policy = self.policy(raw, wand=[wand_row(DISARMING, 3)])
        with mock.patch.object(HengbotPolicy, "_fundraising_return_route_key", renamed):
            key = self.choose(policy, raw)
        self.assertAimed(policy, key, "mBe4")
        self.zap(policy, raw, key)

    def test_chest_disarm_phase_aims_the_power_at_the_chest(self):
        # effect/effect-item.cpp:201: KILL_TRAP/KILL_DOOR disarm and unlock a chest.
        with mock.patch.object(HengbotPolicy, "_should_start_town_return", return_value=False), \
                mock.patch.object(HengbotPolicy, "_return_to_town_key", return_value=None):
            for wand, expected in (([wand_row(DISARMING, 3)], "mBe6"), ((), "D6")):
                with self.subTest(expected=expected):
                    raw = self.board()
                    raw["grid_map"].setdefault("cells", []).append(
                        {"y": CHEST_AT.y, "x": CHEST_AT.x, "o": 1, "t": [TVAL_CHEST]})
                    policy = self.policy(raw, wand=wand)
                    for name, value in CALM.items():
                        setattr(policy, name, value)
                    policy._chest_position = CHEST_AT
                    policy._chest_phase_counts = {"search": CHEST_SEARCH_BUDGET}
                    key = self.choose(policy, raw)
                    if expected == "D6":
                        self.assertEqual((key, policy.last_reason), ("D6", "chest:disarm"))
                        continue
                    self.assertAimed(policy, key, expected)
                    self.zap(policy, raw, key)
                    self.assertNotIn("disarm", policy._chest_phase_counts)

    def test_the_beam_reaches_only_a_trap_on_an_open_straight_line(self):
        raw = self.trapped()
        policy = self.policy(raw, wand=[wand_row(DISARMING, 3)])
        board = parse_snapshot(raw, policy._monrace_knowledge)
        me_powers.observe(policy, board)
        here = board.player.position
        cases = (
            (TRAP_STEP, "mBe4"),                       # adjacent
            (Position(here.y, here.x - 3), "mBe4"),    # along the corridor
            (Position(here.y - 2, here.x - 1), None),  # a knight's move: no line
            (Position(here.y + 2, here.x), None),      # behind the corridor wall
        )
        for target, expected in cases:
            with self.subTest(target=target):
                self.assertEqual(
                    me_powers.power_key(policy, board, me_powers.TRAP, target), expected)
        # Not without a target, not on another occasion; beside the recorded
        # attacker the combat ladder answers it first.
        self.assertIsNone(me_powers.power_key(policy, board, me_powers.TRAP))
        self.assertIsNone(me_powers.power_key(policy, board, me_powers.FLOOR, TRAP_STEP))
        hostile = self.trapped()
        hostile["visible_monsters"] = self.raw(stage2.LIFE, stage2.TURN)["visible_monsters"]
        policy = self.policy(hostile, wand=[wand_row(DISARMING, 3)])
        key = self.choose(policy, hostile)
        self.assertFalse(policy.last_reason.startswith("me-power:"), (key, policy.last_reason))

    def test_harmless_visible_hostile_keeps_the_power(self):
        # Owner 2026-11-01 (answer 8, 「脅威でなければ使う」, as the mapping's
        # beside_harmless).  DECLARED CONSTRUCTED: life-065's recorded asleep
        # level-1 monster (tests/fixtures/me-mapping-1101.json.gz, the
        # 「脅威でなければ感知する」 case) stands in the room west of the corridor,
        # off every beam of the player.  Unfixed: 'D4'.
        mapping = mapping_recorded.MagicEaterMappingRecordedTest
        mapping.setUpClass()
        monster = mapping.data["life-065"]["board"]["visible_monsters"][0]
        race = monster["race_id"]
        self.addCleanup(setattr, type(self), "races", self.races)
        type(self).races = {**self.races, race: mapping.races[race]}

        def beside(**changes):
            raw = self.trapped()
            raw["visible_monsters"] = [dict(monster, **{"y": 13, "x": 33, **changes})]
            return raw, self.policy(raw, wand=[wand_row(DISARMING, 3)])

        raw, policy = beside()
        board = parse_snapshot(raw, policy._monrace_knowledge)
        self.assertEqual(len(policy._physical_hostiles(board)), 1)
        self.assertFalse(me_powers.visible_threat(policy, board))
        key = self.choose(policy, raw)
        self.assertAimed(policy, key, "mBe4")
        self.zap(policy, raw, key)

        with self.subTest("dangerous visible hostile: no power"):
            # Awake in the recorded attacker's niche beside the player, with a
            # ranged attack worth the whole HP.
            type(self).races = {**self.races, race: replace(
                mapping.races[race], max_ranged_damage=board.player.max_hp)}
            raw, policy = beside(asleep=False, y=13, x=46)
            snapshot = parse_snapshot(raw, policy._monrace_knowledge)
            self.assertTrue(me_powers.visible_threat(policy, snapshot))
            key = self.choose(policy, raw)
            self.assertFalse(policy.last_reason.startswith("me-power:"), (key, policy.last_reason))
            type(self).races = {**self.races, race: mapping.races[race]}
        with self.subTest("just hit: no power"):
            raw, policy = beside()
            snapshot = parse_snapshot(raw, policy._monrace_knowledge)
            me_powers.observe(policy, snapshot)
            self.assertEqual(me_powers.power_key(policy, snapshot, me_powers.TRAP, TRAP_STEP),
                             "mBe4")
            policy._took_damage = True
            self.assertIsNone(me_powers.power_key(policy, snapshot, me_powers.TRAP, TRAP_STEP))


if __name__ == "__main__":
    unittest.main()
