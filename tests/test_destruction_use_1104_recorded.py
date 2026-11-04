"""destruction-1104: *Destruction* in place of the Teleportation away from a seen threat.

Owner 2026-11-04: 「成功率80%以上の*破壊*を使えるとき、強敵からのテレポートによる逃走に
代わり*破壊*を使用する。」 (destruction_use).

Recorded boards (every decision through the public choose_key, the posted key through
the production executor):
 * HELD: tests/fixtures/rq-teleport-reserve-1101.json.gz "reserve-held", turn 1662215: a
   warrior (Lv38 band, magic device 26) on 鉄獄38階, random quest 45, seven awake hostiles
   in view, recorded ``emergency:teleport`` ``rc``.
 * Q31: tests/fixtures/death-n1c-099-1102.json.gz, turn 691626: a Magic-Eater on fixed
   quest 31, recorded by the current build as ``emergency:teleport`` ``re``.
 * PARALYZER: test_paralyzer_contact_recorded's board, ``status-threat:scroll``.

DECLARED CONSTRUCTED: no capture holds a *Destruction* use (the logs of the viewing bots
show no staff use), so:
 * the staff in the pack (slot s, 5 charges, the game's item row);
 * the magic device rating of a variant (60 is the least with 80%: (60-50-2)/(60-50));
 * class 16 and the displayed power list of the absorbed variant, on HELD's warrior;
 * the monsters moved, renamed to the quest target or marked wounded;
 * the board after the use: the flash message, the blindness, no monster in view and the
   map without the circle (destroy_area clears CAVE_MARK, and grid_map shows no such cell);
 * the executor's replies (the game's prompts, then the same board ten turns later).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
import unittest

from hengbot import destruction_use
from hengbot.cli import _ExecutorInputPort, SendResult
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.me_device_attacks import observe_lists
from hengbot.model import Position, game_distance, parse_snapshot
from hengbot.policy_constants import EMERGENCY_ESCAPE_REASONS
from tests import test_n1c_death_1102_recorded as q31
from tests import test_paralyzer_contact_recorded as paralyzer
from tests import test_rq_teleport_reserve_recorded as rq
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_list, power_screen, row

HELD_TURN = 1662215
TELEPORT = ("rc", "emergency:teleport")
STAFF_KEY = ("us", "emergency:destruction")
STAFF_NAME = "*破壊*"
SV_TELEPORT, SV_PHASE = 9, 8
NO_SCROLL_RUNG = "emergency:recall"
RELIABLE_SKILL = 60          # (60 - 50 - 2) / (60 - 50) = 80%
AWAKE_RACE = 338             # the air hounds of the recorded board
CURE_REASONS = ("item:cure", "item:cure-critical")
USE_PROMPT = "どの杖を使いますか? "
TARGET = rq.QUEST_TARGET_RACE


def with_staff(raw, *, skill=RELIABLE_SKILL, charges=5):
    item = dict(copy.deepcopy(raw["inventory"][0]), slot="s", tval=55, sval=29, count=1,
                known=True, aware=True, fully_known=True, charging=False, charges=charges, pval=charges,
                name=f"*破壊*の杖 ({charges}回分)", weight=50)
    raw["inventory"].append(item)
    set_skill(raw, skill)
    return raw


def set_skill(raw, skill):
    raw["player"]["skill_ratings"]["magic_device"]["value"] = skill


def move(raw, monster, y, x):
    """The monster at (y, x): the grid sidecar names the position first (model.py)."""
    for cell in raw["grid_map"]["cells"]:
        if cell.get("m") == monster["index"]:
            cell["m"] = 0
    monster["y"], monster["x"] = y, x


def destroyed_map(grid_map, centre, radius=destruction_use.WORST_RADIUS):
    """grid_map with no cell of the circle (the game forgot it)."""
    grid_map = copy.deepcopy(grid_map)
    def kept(y, x):
        return game_distance(centre, Position(y, x)) > radius
    runs = []
    for y, x0, length, palette in grid_map["runs"]:
        start = None
        for x in range(x0, x0 + length + 1):
            keep = x < x0 + length and kept(y, x)
            if keep and start is None:
                start = x
            elif not keep and start is not None:
                runs.append([y, start, x - start, palette])
                start = None
    grid_map["runs"] = runs
    grid_map["cells"] = [cell for cell in grid_map.get("cells", ()) if kept(cell["y"], cell["x"])]
    return grid_map


def after_flash(raw, *, blind=True):
    """The board of a use that worked: the flash, nothing in view, no circle."""
    centre = Position(raw["player"]["y"], raw["player"]["x"])
    following = dict(copy.deepcopy(raw), turn=raw["turn"] + 10,
                     messages=[destruction_use.FLASH[0]], visible_monsters=[], detected_monsters=[])
    following["grid_map"] = destroyed_map(raw["grid_map"], centre)
    following["player"]["status"]["blind"] = blind
    return following


def own_tests_only(cls):
    """A class borrowing a recorded harness runs none of the harness's own pins."""
    for name in dir(cls):
        if name.startswith("test_") and name not in vars(cls):
            setattr(cls, name, None)
    return cls


@own_tests_only
class DestructionUseTest(rq.RandomQuestTeleportReserveRecordedTest):
    def setUp(self):
        boards = self.boards("reserve-held")
        self.first = boards[0]
        self.raw = next(raw for raw in boards if raw["turn"] == HELD_TURN)

    def policy(self):
        policy = rq.HengbotPolicy(monrace_knowledge=dict(self.monraces))
        policy.prime(parse_snapshot(copy.deepcopy(self.first), policy._monrace_knowledge))
        rq.decide(policy, copy.deepcopy(self.first))
        return policy

    def answer(self, raw, policy=None):
        policy = policy or self.policy()
        key = rq.decide(policy, copy.deepcopy(raw))
        return (key, policy.last_reason), policy

    def post_staff(self, policy, raw, key):
        accepted = self.post(policy, raw, key, [rq.executor_pins.prompt_screen(USE_PROMPT)],
                             self.later(raw))
        self.assertEqual(accepted, ["u", key[1:]])

    def test_recorded_board_reads_teleport(self):
        answer, _ = self.answer(self.raw)
        self.assertEqual(answer, TELEPORT)
        board = parse_snapshot(copy.deepcopy(self.raw), self.monraces)
        self.assertEqual(board.floor_key[2], rq.QUEST_ID)

    def test_reliable_staff_replaces_teleport_through_the_executor(self):
        raw = with_staff(self.raw)
        answer, policy = self.answer(raw)
        self.assertEqual(answer, STAFF_KEY)
        self.assertIsNone(policy._emergency_consumable_issue_watch)
        self.post_staff(policy, raw, answer[0])

    def test_staff_below_eighty_percent_reads_teleport(self):
        # The warrior's own rating (26): the recorded character could not use it.
        self.assertEqual(self.answer(with_staff(self.raw, skill=26))[0], TELEPORT)
        self.assertEqual(self.answer(with_staff(self.raw, skill=RELIABLE_SKILL - 1))[0], TELEPORT)

    def test_empty_or_unknown_staff_reads_teleport(self):
        self.assertEqual(self.answer(with_staff(self.raw, charges=0))[0], TELEPORT)
        raw = with_staff(self.raw)
        raw["inventory"][-1]["known"] = False
        self.assertEqual(self.answer(raw)[0], TELEPORT)

    def absorbed(self, fail):
        raw = copy.deepcopy(self.raw)
        raw["player"]["class_id"] = 16
        policy = self.policy()
        listed = dict(copy.deepcopy(raw), turn=raw["turn"] - 1,
                      _magic_eater_power_list=power_list(
                          "staff", row(STAFF_NAME, fail, current=2, count=2)))
        observe_lists(policy, parse_snapshot(listed, policy._monrace_knowledge))
        return raw, policy

    def test_absorbed_power_at_eighty_percent_through_the_executor(self):
        raw, policy = self.absorbed(20)
        answer, policy = self.answer(raw, policy)
        letter = answer[0][2:]
        self.assertEqual(answer, ("mA" + letter, "emergency:destruction:absorbed-power"))
        game = rq.executor_pins.FaithfulHookGame()
        game.state = copy.deepcopy(raw)
        game.screen = rq.executor_pins.command_screen(raw["turn"])
        game.screens = [prompt("[A] 杖, [B] 魔法棒, [C] ロッド:"),
                        power_screen("staff", [(letter, STAFF_NAME, 2, 2, 20)]),
                        rq.executor_pins.command_screen(raw["turn"] + 10)]
        game.states = [self.later(raw) for _ in game.screens]
        _, _, executor = self.make(game)
        self.assertEqual(executor.observe_boundary(deadline=9999999999).outcome, "ready")
        port = _ExecutorInputPort(executor, tunnel_macros_ready=True, request_budget=2)
        self.assertEqual(port(answer[0], decision={"reason": policy.last_reason,
                                                   "sequence": policy._decision_sequence}),
                         SendResult.SENT, port.last_result.reason)
        self.assertEqual(game.accepted, ["m", "A", letter])

    def test_absorbed_power_below_eighty_percent_reads_teleport(self):
        raw, policy = self.absorbed(21)
        self.assertEqual(self.answer(raw, policy)[0], TELEPORT)

    def test_status_keeps_the_read_or_the_cure(self):
        raw = with_staff(self.raw)
        raw["player"]["status"]["confused"] = True
        self.assertNotEqual(self.answer(raw)[0][1], "emergency:destruction")
        raw = with_staff(self.raw)
        raw["player"]["status"]["stunned"] = True
        self.assertNotEqual(self.answer(raw)[0][1], "emergency:destruction")

    def beyond_range(self, raw):
        """Every awake hostile 14 squares or more away on the same row."""
        here = raw["player"]
        for offset, monster in enumerate(raw["visible_monsters"]):
            move(raw, monster, here["y"], here["x"] + 14 + offset)
        return raw

    def test_threat_beyond_the_guaranteed_radius_reads_teleport(self):
        answer, policy = self.answer(with_staff(self.beyond_range(copy.deepcopy(self.raw))))
        self.assertNotEqual(answer[1], "emergency:destruction", answer)

    def test_threat_at_the_guaranteed_radius_is_used_on(self):
        raw = with_staff(copy.deepcopy(self.raw))
        here = raw["player"]
        for monster in raw["visible_monsters"][1:]:
            move(raw, monster, here["y"], here["x"] + 5)
        move(raw, raw["visible_monsters"][0], here["y"], here["x"] + 13)
        self.assertEqual(self.answer(raw)[0], STAFF_KEY)

    def test_unseen_attacker_reads_teleport(self):
        # DECLARED CONSTRUCTED: the visible hound is not what hit the player.
        raw = with_staff(self.raw)
        raw["messages"] = ["何かに噛まれた。"]
        raw["player"]["hp"] -= 5
        answer, _ = self.answer(raw)
        self.assertNotEqual(answer[1], destruction_use.REASON)

    def test_fixed_quest_floor_reads_teleport(self):
        # Q31's Magic-Eater with the staff: the game refuses the floor.
        policy = q31.new_policy()
        turn = q31.LOW_HP_TURNS[0]
        for raw in q31.CASE["boards"]:
            raw = copy.deepcopy(raw)
            if raw["turn"] == turn:
                with_staff(raw)
            key = q31.d57.loops.decide(policy, raw)
            if raw["turn"] == turn:
                self.assertEqual((key, policy.last_reason), q31.EMERGENCY_TELEPORT)
                return
            policy.confirm_key_posted(key)
        self.fail(turn)

    def as_target(self, raw, *, wounded, distance=None):
        target = raw["visible_monsters"][0]
        target["race_id"] = TARGET
        target["health"] = "wounded" if wounded else "unhurt"
        if distance is not None:
            move(raw, target, raw["player"]["y"], raw["player"]["x"] + distance)
        for other in raw["visible_monsters"][1:]:
            self.assertNotEqual(other["race_id"], TARGET)
        return raw

    def test_unhurt_target_beside_other_threats_is_no_bar(self):
        raw = self.as_target(with_staff(copy.deepcopy(self.raw)), wounded=False)
        self.assertEqual(self.answer(raw)[0], STAFF_KEY)

    def test_wounded_target_within_seventeen_reads_teleport(self):
        raw = self.as_target(with_staff(copy.deepcopy(self.raw)), wounded=True, distance=17)
        self.assertEqual(self.answer(raw)[0], TELEPORT)

    def test_wounded_target_beyond_seventeen_is_no_bar(self):
        raw = self.as_target(with_staff(copy.deepcopy(self.raw)), wounded=True, distance=18)
        self.assertEqual(self.answer(raw)[0], STAFF_KEY)

    def test_the_target_alone_reads_teleport(self):
        raw = with_staff(copy.deepcopy(self.raw))
        raw["visible_monsters"] = raw["visible_monsters"][:1]
        self.as_target(raw, wounded=False)
        self.assertNotEqual(self.answer(raw)[0][1], "emergency:destruction")

    def test_guardian_in_the_circle_reads_teleport(self):
        # DECLARED CONSTRUCTED: the floor made the dungeon's last and one hound its guardian.
        raw = with_staff(copy.deepcopy(self.raw))
        policy = self.policy()
        policy._dungeon_knowledge[raw["floor"]["dungeon_id"]] = DungeonInfo(
            raw["floor"]["dungeon_id"], "", 1, raw["floor"]["level"], 1, guardian_id=AWAKE_RACE)
        self.assertEqual(self.answer(raw, policy)[0], TELEPORT)

    def test_after_the_flash_the_character_cures_and_explores_on(self):
        raw = with_staff(copy.deepcopy(self.raw))
        answer, policy = self.answer(raw)
        self.assertEqual(answer, STAFF_KEY)
        self.assertNotIn(answer[1], EMERGENCY_ESCAPE_REASONS)
        policy.confirm_key_posted(answer[0])
        emergencies = policy._dive_emergencies
        centre = Position(raw["player"]["y"], raw["player"]["x"])
        inside = Position(centre.y, centre.x + 3)
        policy._remembered_upstairs.add(inside)
        policy._engagement_avoid_cells.add(inside)
        policy._known_loot.add(inside)
        policy._remembered_floor_t.add((inside.y, inside.x))
        policy._explore_path = [inside]
        outside = Position(centre.y, centre.x + 30)
        policy._remembered_upstairs.add(outside)

        cured = after_flash(raw)
        cure = rq.decide(policy, copy.deepcopy(cured))
        self.assertEqual(policy._dive_emergencies, emergencies)
        self.assertFalse(policy._emergency_escape_pending)
        self.assertFalse(policy._returning_to_town)
        self.assertNotIn(inside, policy._remembered_upstairs)
        self.assertIn(outside, policy._remembered_upstairs)
        self.assertNotIn(inside, policy._engagement_avoid_cells)
        self.assertNotIn(inside, policy._known_loot)
        self.assertNotIn((inside.y, inside.x), policy._remembered_floor_t)
        self.assertNotIn(inside, policy._explore_path)
        self.assertNotIn(inside, policy._remembered_grids)
        self.assertIn(policy.last_reason, CURE_REASONS)
        self.assertEqual(cure[0], "q")
        policy.confirm_key_posted(cure)

        seeing = dict(copy.deepcopy(cured), turn=cured["turn"] + 10, messages=[])
        seeing["player"]["status"]["blind"] = False
        rq.decide(policy, copy.deepcopy(seeing))
        self.assertEqual(policy._dive_emergencies, emergencies)
        self.assertFalse(policy._returning_to_town, policy.last_reason)
        self.assertFalse(policy.last_reason.startswith(("emergency:", "return:")),
                         policy.last_reason)

    def test_a_failed_use_reads_teleport_on_the_next_ask(self):
        raw = with_staff(copy.deepcopy(self.raw))
        answer, policy = self.answer(raw)
        self.assertEqual(answer, STAFF_KEY)
        policy.confirm_key_posted(answer[0])
        failed = dict(copy.deepcopy(raw), turn=raw["turn"] + 10,
                      messages=["杖をうまく使えなかった。"])
        self.assertEqual(self.answer(failed, policy)[0], TELEPORT)
        policy.confirm_key_posted(TELEPORT[0])
        # The fallback is one ask: the threat still there asks for the staff again.
        again = dict(copy.deepcopy(failed), turn=failed["turn"] + 10, messages=[])
        self.assertEqual(self.answer(again, policy)[0], STAFF_KEY)

    def test_a_key_the_game_did_not_take_reads_teleport_on_the_same_turn(self):
        raw = with_staff(copy.deepcopy(self.raw))
        answer, policy = self.answer(raw)
        self.assertEqual(answer, STAFF_KEY)
        self.assertEqual(self.answer(raw, policy)[0], TELEPORT)

    def without_scrolls(self, raw, *svals):
        """DECLARED CONSTRUCTED: the pack without the named scrolls (it holds no Phase Door)."""
        raw["inventory"] = [item for item in raw["inventory"]
                            if not (item["tval"] == 70 and item["sval"] in svals)]
        return raw

    def assert_staff_first(self, raw, rung_reason):
        """No staff: the rung reads.  The staff: it comes first, through the executor.
        The following board of a failed use: the rung reads again."""
        control, _ = self.answer(copy.deepcopy(raw))
        self.assertEqual(control[1], rung_reason, control)
        staffed = with_staff(copy.deepcopy(raw))
        answer, policy = self.answer(staffed)
        self.assertEqual(answer, STAFF_KEY)
        self.post_staff(policy, staffed, answer[0])
        policy.confirm_key_posted(answer[0])
        failed = dict(copy.deepcopy(staffed), turn=staffed["turn"] + 10,
                      messages=["杖をうまく使えなかった。"])
        self.assertEqual(self.answer(failed, policy)[0][1], rung_reason)

    def test_no_teleport_comes_before_phase_door(self):
        # DECLARED CONSTRUCTED: the recorded Teleportation stack made Phase Door.
        raw = copy.deepcopy(self.raw)
        next(item for item in raw["inventory"]
             if item["tval"] == 70 and item["sval"] == SV_TELEPORT)["sval"] = SV_PHASE
        self.assert_staff_first(raw, "emergency:phase")

    def test_no_escape_scroll_comes_before_recall(self):
        self.assert_staff_first(
            self.without_scrolls(copy.deepcopy(self.raw), SV_TELEPORT), NO_SCROLL_RUNG)


@own_tests_only
class StatusThreatRungTest(paralyzer.ParalyzerContactRecordedTest):
    """The rung that reads for a paralyzer takes the same hook."""

    def raw(self, turn, *, scrolls=True):
        return with_staff(super().raw(turn, scrolls=scrolls))

    def test_fast_paralyzer_two_cells_away_reads_teleport_through_the_executor(self):
        policy, keys = self.decide()
        self.assertEqual((keys[1], policy.last_reason), ("us", destruction_use.REASON))
        self.assertEqual(self.post(policy, self.raw(paralyzer.DEATH_TURN), keys[1], USE_PROMPT),
                         ["u", "s"])


if __name__ == "__main__":
    unittest.main()
