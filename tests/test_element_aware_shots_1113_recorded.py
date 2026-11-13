"""Quest 25 on n1-b life-384 (2026-11-13 08:30-08:42): no shot of an element the stairway is immune to.

Owner 2026-11-12 「射撃と取り込んだ魔法道具は常に期待値で比べて高い方（耐性・命中率・成功率まで）」,
its use 「免疫の属性を撃たない」.  The stairway to hell (lib/edit MonraceDefinitions 439) has IM_ACID,
IM_ELEC, IM_FIRE and IM_POIS and no HURT_LITE: an immunity leaves dam / 9
(src/effect/effect-monster-resist-hurt.cpp:34-40, :53-59, :72-78, :130-136) and the weak light
deals 0 to a race without HURT_LITE (src/effect/effect-monster-lite-dark.cpp:15-16).  From
[13,27] (battle phase 9) the recorded bot used 235 attacks at it: weak light 75, acid 41,
lightning 41, fire 29, poison 15, and only the cold 28 and the Magic Missile 6 hurt it.

The chooser walked its rows strongest first to the first that could be sent, a row the target's
flags cancel included: with the cold spent, Dragon's Flame and the acid ball (a ninth) and at the
end the weak light (nothing).  The rule (me_device_attacks ``expected_damage``: a power whose one
element the race's known flags leave at a ninth or less scores 0; attack_expectation
``effective``: no chooser keeps a row that deals nothing; quest25_battle ``_stairway_spent``:
with nothing that hurts the stairway ready and something that does held, the refill rest of
owner 2026-11-13 「休んで充填を待つ」).

Recorded: tests/fixtures/n1b-384-q25-walk-sight-1113.json.gz (tests/test_n1b_384_q25_walk_sight_
1113_recorded): the restarted process's boards, the record of phase 9.  Each board is decided by
a fresh policy through the public ``choose_key`` and its key posted through the production
executor (``_ExecutorInputPort``), the game then showing the next recorded board.

DECLARED CONSTRUCTED: the boards carry no magic-eater lists; they are the 01:33 dump's powers
(``kill_all_patrol_test.lists``, every row 95%) with the rows each test names spent, as the
recorded process's charges ran down.  The power list and prompts the executor answers are built
(tests/test_me_device_attacks ``power_screen``).  The controls change the stairway's race flags.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import dataclasses
import json
import lzma
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.policy import ConservativePolicy  # noqa: F401 -- first: the plan modules import in a cycle alone
from hengbot import me_device_attacks, me_ranged_first, quest25_battle as battle
from hengbot.cli import SendResult, _ExecutorInputPort
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests import test_kill_all_patrol_1113_recorded as kill_all_patrol_test
from tests import test_n1b_382_q25_patrol_owner_1113_recorded as replay
from tests import test_n1b_384_q25_walk_sight_1113_recorded as walk_sight
from tests.support import recorded as harness
from tests.support.recorded import EDIT, skill
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen
from tests.test_me_stage2_powers import TYPE_PROMPT

CASE = walk_sight.CASE
BOARDS, RECORDED = CASE["second"]["boards"], CASE["second"]["recorded"]
STAIRWAY = battle.geo.STAIRWAY
COLD = {"アイス・ボルト", "アイス・ボール", "ドラゴンの冷気"}
COLD_BALLS = {"アイス・ボール", "ドラゴンの冷気"}
MISSILE = "マジック・ミサイル"
LIGHT = "光"
# The powers the stairway is immune to, or that leave it unhurt (by element).
CANCELLED = {"LITE_WEAK", "ACID", "ELEC", "FIRE", "POIS"}
ACID_BALL_BOARD = 4     # recorded 'mCy@13,29': the rod's Acid Ball
LIGHT_BOARD = 26        # recorded 'mCp6': the rod's Light
RANGED_FIXTURE = Path(__file__).with_name("fixtures") / "n1b-370-ranged-1112.json.xz"
NIBELUNG = 111


def spent(names):
    """DECLARED CONSTRUCTED (module note): the dump's lists with the rows of ``names`` spent."""
    return {kind: (stamp, tuple(_spend(kind, row) if row["name"] in names else dict(row)
                                for row in rows))
            for kind, (stamp, rows) in kill_all_patrol_test.lists().items()}


def only(names):
    """DECLARED CONSTRUCTED: every attack power spent but those of ``names``."""
    attack = {row["name"] for kind, (_stamp, rows) in kill_all_patrol_test.lists().items()
              for row in rows if (kind, row["name"]) in me_device_attacks._BY_NAME}
    return spent(attack - set(names))


def _spend(kind, row):
    return dict(row, **({"charging": row["max"]} if kind == "rod" else {"current": 0}))


def _power_of(key):
    kind = {"A": "staff", "B": "wand", "C": "rod"}[key[1]]
    sval = battle.me_powers.decode_letter(key[2])
    return me_device_attacks.POWERS[(kind, sval)]


def _with_flags(policy, change):
    """DECLARED CONSTRUCTED control: the stairway's race with its flags changed by ``change``."""
    races = dict(policy._monrace_knowledge)
    races[STAIRWAY] = dataclasses.replace(races[STAIRWAY], flags=change(races[STAIRWAY].flags))
    policy._monrace_knowledge = races


class TheRecordingTest(unittest.TestCase):

    def test_the_stairway_was_shot_with_what_cannot_hurt_it(self):
        keys = {row["key"] for row in RECORDED[4:34]}
        fired = {_power_of(key).element for key in keys}
        self.assertLessEqual(CANCELLED, fired)
        self.assertEqual(RECORDED[ACID_BALL_BOARD]["key"], "mCy@13,29")
        self.assertEqual(RECORDED[LIGHT_BOARD]["key"], "mCp6")
        raw = BOARDS[ACID_BALL_BOARD]
        self.assertEqual((raw["player"]["y"], raw["player"]["x"]), battle.geo.STAIRWAY_STAND)
        self.assertEqual(CASE["battle_record"]["battle"]["phase"], battle.phase_index("stairway"))
        with TemporaryDirectory() as directory:
            policy = replay.new_policy(Path(directory), spent(()), None, CASE)
        flags = policy._monrace_knowledge[STAIRWAY].flags
        self.assertLessEqual({"IM_ACID", "IM_ELEC", "IM_FIRE", "IM_POIS"}, flags)
        self.assertNotIn("HURT_LITE", flags)


class ImmuneElementsTest(unittest.TestCase):

    def test_the_one_expectation(self):
        flags = frozenset({"IM_ACID", "IM_ELEC", "IM_FIRE", "IM_POIS", "UNDEAD", "EVIL"})
        level = 37
        by_name = {power.names[0]: power for power in me_device_attacks.POWERS.values()}
        for name in ("アシッド・ボール", "サンダー・ボール", "ファイア・ボール", "悪臭雲", "光"):
            self.assertEqual(me_device_attacks.expected_damage(by_name[name], level, flags), 0, name)
        for name in ("アイス・ボール", MISSILE, "ドラゴン・ブレス", "邪悪存在退散"):
            self.assertGreater(me_device_attacks.expected_damage(by_name[name], level, flags), 0, name)
        # The control: a light-sensitive race takes the weak light, a race with no immunity the acid.
        self.assertGreater(me_device_attacks.expected_damage(by_name["光"], level, {"HURT_LITE"}), 0)
        self.assertEqual(me_device_attacks.expected_damage(
            me_device_attacks.POWERS[("wand", 20)], level, frozenset()), 60 + 3 * level // 4)


class StairwayShotTest(replay._Replay):
    case = CASE

    def decide(self, lists, index, change=None):
        directory = self.enterContext(TemporaryDirectory())
        policy = replay.new_policy(Path(directory), lists, None, CASE)
        if change is not None:
            _with_flags(policy, change)
        raw = BOARDS[index]
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge))
        self.assertEqual(policy._quest_navigators[25].phase_battle.phase,
                         battle.phase_index("stairway"))
        return policy, raw, key

    def post_power(self, policy, raw, key, following):
        """The absorbed power through the executor's prompts (cmd-magiceat.cpp; get_aim_dir; for a
        grid, target_set's free cursor walked to it)."""
        power = _power_of(key)
        rows = [(key[2], power.names[0], 0 if power.kind == "rod" else 5, 5, 5)]   # charged
        screens = [prompt(TYPE_PROMPT), power_screen(power.kind, rows),
                   prompt("方向?", "direction", can_choose_target=True)]
        if "@" in key:
            y, x = (int(value) for value in key.split("@")[1].split(","))
            here = (raw["player"]["y"], raw["player"]["x"])
            screens += [prompt("[q止 t決 p自 m近 +次 -前]", "target", look=False, free=True,
                               can_target=True, y=here[0], x=here[1] + step)
                        for step in range(x - here[1] + 1)]
            self.assertEqual(y, here[0])
        game = harness.FaithfulHookGame()
        game.capacity = 256
        game.state = copy.deepcopy(raw)
        game.screen = harness.command_screen(raw["turn"])
        game.screens = [*screens, harness.command_screen(following["turn"])]
        game.states = [copy.deepcopy(following) for _ in game.screens]
        _game, _client, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(key, decision={"reason": policy.last_reason,
                                            "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(port.last_result.outcome, "completed")
        policy.confirm_key_posted(key)
        return game.accepted

    def shot(self, lists, index, change=None):
        policy, raw, key = self.decide(lists, index, change)
        self.assertEqual(policy.last_reason, me_device_attacks.DEVICE_REASON, key)
        accepted = self.post_power(policy, raw, key, BOARDS[index + 1])
        return _power_of(key), accepted

    def test_charged_the_cold_breath(self):
        power, accepted = self.shot(spent(()), ACID_BALL_BOARD)
        self.assertEqual((power.names[0], power.element), ("ドラゴンの冷気", "COLD"))
        self.assertEqual(accepted, ["m", "B", "1", "*", "6", "6", "t"])

    def test_cold_balls_spent_the_frost_bolt_not_the_acid_ball(self):
        # The recorded board's answer was the rod's Acid Ball (a ninth on IM_ACID).
        power, accepted = self.shot(spent(COLD_BALLS), ACID_BALL_BOARD)
        self.assertEqual((power.names[0], power.element), ("アイス・ボルト", "COLD"))
        self.assertEqual(accepted, ["m", "B", "t", "6"])

    def test_cold_spent_the_magic_missile(self):
        power, accepted = self.shot(spent(COLD), ACID_BALL_BOARD)
        self.assertEqual(power.names[0], MISSILE)
        self.assertEqual(accepted[:3], ["m", "B", "p"])

    def test_cold_and_missile_spent_rest_for_a_charge(self):
        for index in (ACID_BALL_BOARD, LIGHT_BOARD):
            policy, raw, key = self.decide(spent(COLD | {MISSILE}), index)
            self.assertEqual((key, policy.last_reason),
                             (battle.RECHARGE_REST_KEY, battle.RECHARGE_REASON), index)
            self.post(policy, raw, key, BOARDS[index + 1])

    def test_only_the_light_left_rest_not_the_light(self):
        # The recorded board's answer was the rod's Light (nothing on a race without HURT_LITE).
        policy, raw, key = self.decide(only({LIGHT}), LIGHT_BOARD)
        self.assertEqual((key, policy.last_reason), (battle.RECHARGE_REST_KEY, battle.RECHARGE_REASON))
        self.post(policy, raw, key, BOARDS[LIGHT_BOARD + 1])

    def test_nothing_that_hurts_it_held_the_walk_to_a_sight(self):
        # DECLARED CONSTRUCTED: the cold and the Magic Missile never absorbed (not listed), the
        # Acid Balls spent; what is held cannot hurt the stairway, so no rest waits for it (the
        # spent Acid Balls are no reason): the walk to a cell that sees it (``_unseen_fire``;
        # both stands were looked from, the record's ``blind_sights``).
        lists = {kind: (stamp, tuple(row for row in rows if row["name"] not in COLD | {MISSILE}))
                 for kind, (stamp, rows) in spent({"アシッド・ボール"}).items()}
        policy, raw, key = self.decide(lists, ACID_BALL_BOARD)
        self.assertEqual((key, policy.last_reason), ("7", battle.SIGHT_REASON))
        self.post(policy, raw, key, BOARDS[ACID_BALL_BOARD + 1])

    def test_control_a_light_sensitive_stairway_takes_the_light(self):
        power, _accepted = self.shot(only({LIGHT}), LIGHT_BOARD, lambda flags: flags | {"HURT_LITE"})
        self.assertEqual(power.element, "LITE_WEAK")

    def test_control_a_stairway_with_no_immunity_keeps_the_strongest(self):
        # Without its immunities the cold spent leaves Dragon's Flame the strongest, as before.
        power, _accepted = self.shot(spent(COLD), ACID_BALL_BOARD,
                                     lambda flags: flags - {"IM_ACID", "IM_ELEC", "IM_FIRE", "IM_POIS"})
        self.assertEqual((power.names[0], power.element), ("ドラゴンの火炎", "FIRE"))


class DistantChooserTest(unittest.TestCase):
    """The distant chooser of the quest plans, the summon response and the blind strike
    (me_ranged_first ``attack_key``) walks its fixed order to the first answer it can send.

    Recorded: tests/fixtures/n1b-370-ranged-1112.json.xz, decision 34173 (n1-b life-370, Castle
    64F: a ニーベルング, race 111, 10 grids west on the row; tests/test_me_ranged_vs_device_1112_
    recorded).  DECLARED CONSTRUCTED: every absorbed attack power spent and the absorbed Magic
    Missile seen empty, no arrows, the carried wand of slot h a known Fire Balls wand; the
    Nibelung's race given IM_FIRE (the control: as recorded, no fire immunity)."""

    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(RANGED_FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")

    def answer(self, immune: bool, beside: bool = False):
        case = copy.deepcopy(self.payload["cases"]["34173"])
        raw = case["board"]
        if beside:
            # DECLARED CONSTRUCTED: the Nibelung of [37,68] beside the player at [37,77], the
            # player afraid (fear refuses melee only, attack_expectation.melee_refused).
            raw["visible_monsters"] = [monster for monster in raw["visible_monsters"]
                                       if (monster["y"], monster["x"]) == (37, 68)]
            # A fresh index: the board's grid map places the recorded one at [37,68].
            raw["visible_monsters"][0].update(y=37, x=77, index=9999)
            raw["player"]["status"]["afraid"] = True
        raw["_magic_eater_wand_charges"] = 0
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] != 17]
        wand = next(item for item in raw["inventory"] if item["slot"] == "h")
        wand.update(sval=22, name="ファイア・ボールの魔法棒 (5回分)", charges=5, count=1)
        races = dict(self.races)
        if immune:
            races[NIBELUNG] = dataclasses.replace(races[NIBELUNG],
                                                  flags=races[NIBELUNG].flags | {"IM_FIRE"})
        policy = HengbotPolicy(monrace_knowledge=races)
        policy.prime(parse_snapshot(copy.deepcopy(raw), races))
        for kind, entry in case["lists"].items():
            rows = [_spend(kind, row) if (kind, row["name"]) in me_device_attacks._BY_NAME else row
                    for row in entry["rows"]]
            shown = dict(copy.deepcopy(raw), turn=entry["turn"],
                         _magic_eater_power_list={"kind": kind, "rows": rows})
            me_device_attacks.observe_lists(policy, parse_snapshot(shown, races))
        skill(policy, raw)
        snapshot = parse_snapshot(copy.deepcopy(raw), races)
        target = next(monster for monster in snapshot.visible_monsters
                      if (monster.position.y, monster.position.x) == ((37, 77) if beside else (37, 68)))
        return me_ranged_first.attack_key(policy, snapshot, target), policy.last_reason

    def test_a_fire_immune_target_gets_no_fire_ball(self):
        key, _reason = self.answer(immune=True)
        self.assertIsNone(key)

    def test_control_without_the_immunity_the_wand(self):
        self.assertEqual(self.answer(immune=False), ("ah4", me_ranged_first.WAND_REASON))

    def test_beside_and_afraid_no_fire_ball_at_a_fire_immune_target(self):
        key, _reason = self.answer(immune=True, beside=True)
        self.assertIsNone(key)
        self.assertEqual(self.answer(immune=False, beside=True), ("ah4", me_ranged_first.WAND_REASON))


if __name__ == "__main__":
    unittest.main()
