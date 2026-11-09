"""n1-a life-501 (2026-11-09 19:26, イークの洞穴13階): paralysers in view are left on shallow floors.

Analysis: C:/hengband-backups/pdca/captures/n1a-501-death-1109/REPORT.txt.  The Lv17 warrior
without Free Action opened a door ('o1', ``explore``); behind it a ゲイザー (race 218, GAZE
PARALYZE, HOLD) and ボルドールの息子『オルファックス』 (race 180, SLOW, TELE_TO) chain-paralysed it
to death.  The game asks for no command while paralysed (core/player-processor.cpp:309-316),
so nothing the bot could do after the first paralysis mattered.  No board of the visit shows
either monster: they stood behind the door, unseen.

Owner 2026-11-09, verbatim: 「浅い階で要求しても達成できないので要求階層は今のまま。浅い階層で
見かけたら逃げる。耐麻痺装備をたまたま浅い階から拾っていたら装備することを確認する。」

Boards: tests/fixtures/death-n1a-501-1109.json.xz (tests/extract_n1a_501_fixture.py), the
player_turn boards of the 13F visit with their live decision rows; each decision is the public
``choose_key`` of one fresh policy replaying the recorded boards in order
(``confirm_key_posted`` after each key).

RESTORED: the capture holds no ~f reply, so the skill knowledge is supplied before each decision
(as tests/test_deaths_1109_recorded.py does).

DECLARED CONSTRUCTED (each named at its test): the ゲイザー on the last board (the bot never saw
it: it was behind the door), asleep in the lit room four cells from the player, so neither the
09-18 contact rule (melee reach) nor rule E (an awake caster in sight) covers it; Free Action
from the equipment for the guard; the boards after the teleport (the player elsewhere in the
room, the turn later).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
from dataclasses import replace
import json
import lzma
from pathlib import Path
import unittest

from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import SV_SCROLL_TELEPORT, TVAL_SCROLL, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import DEPTH_ABILITY_REQUIREMENTS
from policy_fixtures import seed_character_calibration
from tests.support.recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "death-n1a-501-1109.json.xz"
LAST_TURN = 419662
GAZER, ORFAX = 218, 180
GAZER_CELL = (4, 50)
SCROLL_REASON = "shallow-paralyzer:scroll"


def skill(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })


def teleport_letter(raw):
    return next(item["slot"] for item in raw["inventory"]
                if (item.get("tval"), item.get("sval")) == (TVAL_SCROLL, SV_SCROLL_TELEPORT))


def with_gazer(raw, y, x, *, asleep=True):
    """DECLARED CONSTRUCTED: a ゲイザー in view at (y, x), and its map mark."""
    raw["visible_monsters"].append({
        "asleep": asleep, "confused": False, "fast": False, "fearful": False,
        "friendly": False, "health": "unhurt", "index": 77, "invulnerable": False,
        "level": 12, "name": "ゲイザー", "pet": False, "race_id": GAZER, "slow": False,
        "stunned": False, "x": x, "y": y})
    raw["grid_map"]["cells"].append({"m": 77, "y": y, "x": x})
    return raw


def free_action(raw):
    """DECLARED CONSTRUCTED: Free Action from the equipment."""
    raw["player"]["ability_sources"]["free_action"] = {
        "equipment": True, "permanent": False, "temporary": False}
    return raw


def moved(raw, y, x, turn):
    """DECLARED CONSTRUCTED: the board after a teleport: the player at (y, x), ``turn``."""
    raw = copy.deepcopy(raw)
    raw["player"]["y"], raw["player"]["x"] = y, x
    raw["turn"] = turn
    raw["messages"] = []
    return raw


class ShallowParalyzerRecordedHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def board(self, turn):
        return copy.deepcopy(next(raw for raw in self.payload["boards"] if raw["turn"] == turn))

    def decide(self, policy, raw):
        skill(policy, raw)
        key = policy.choose_key(parse_snapshot(copy.deepcopy(raw), self.races))
        if key:
            policy.confirm_key_posted(key)
        return str(key), policy.last_reason

    def replay(self, last=None):
        """Every recorded board before the last, one fresh policy; then ``last`` (the last
        board, changed or not) is decided.  Returns the policy and the last answer."""
        boards = self.payload["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        for raw in boards[:-1]:
            self.decide(policy, raw)
        last = self.board(LAST_TURN) if last is None else last
        return policy, self.decide(policy, last)


class RecordedFactsTest(ShallowParalyzerRecordedHarness):
    def test_the_recorded_visit(self):
        decisions = self.payload["decisions"]
        self.assertEqual((decisions[-1]["turn"], decisions[-1]["reason"], decisions[-1]["key"]),
                         (LAST_TURN, "explore", "o1"))
        raw = self.board(LAST_TURN)
        board = parse_snapshot(copy.deepcopy(raw), self.races)
        self.assertEqual(board.floor_key, (2, 13, 0))  # イークの洞穴13階, no quest
        self.assertNotIn("free_action", board.player.abilities)
        self.assertEqual(sum(item.count for item in board.inventory
                             if (item.tval, item.sval) == (TVAL_SCROLL, SV_SCROLL_TELEPORT)), 15)
        # Neither attacker was ever on a board of the visit.
        seen = {monster["race_id"] for raw in self.payload["boards"]
                for monster in raw["visible_monsters"]}
        self.assertFalse(seen & {GAZER, ORFAX})
        # The depth requirement is unchanged (owner 「要求階層は今のまま」): Free Action from 20F.
        self.assertIn((20, frozenset({"free_action", "resist_fire"})), DEPTH_ABILITY_REQUIREMENTS)
        self.assertTrue(all("free_action" not in adds
                            for first, adds in DEPTH_ABILITY_REQUIREMENTS if first < 20))
        # The ゲイザー paralyses by its gaze and casts HOLD; it moves.
        gazer = self.races[GAZER]
        self.assertIn("PARALYZE", [blow.effect for blow in gazer.blows])
        self.assertIn("HOLD", gazer.abilities)
        self.assertNotIn("NEVER_MOVE", gazer.flags)

    def test_the_replay_reproduces_every_recorded_decision(self):
        boards = self.payload["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        answers = [self.decide(policy, raw) for raw in boards]
        self.assertEqual(answers, [(row["key"], row["reason"]) for row in self.payload["decisions"]])
        self.assertEqual(answers[-1], ("o1", "explore"))


class ShallowSightTest(ShallowParalyzerRecordedHarness):
    def test_a_sleeping_gazer_in_view_on_13f_is_left_by_teleport(self):
        # DECLARED CONSTRUCTED: the ゲイザー asleep in the room, four cells away.
        raw = with_gazer(self.board(LAST_TURN), *GAZER_CELL)
        _policy, answer = self.replay(raw)
        self.assertEqual(answer, ("r" + teleport_letter(raw), SCROLL_REASON))

    def test_with_free_action_the_gazer_is_no_reason_to_leave(self):
        # DECLARED CONSTRUCTED: the same board with Free Action from the equipment.
        raw = free_action(with_gazer(self.board(LAST_TURN), *GAZER_CELL))
        _policy, (key, reason) = self.replay(raw)
        self.assertFalse(reason.startswith(("shallow-paralyzer:", "status-threat:")), (key, reason))
        self.assertFalse(key.startswith("r"), (key, reason))

    def test_two_teleports_from_paralysers_return_to_town(self):
        # Owner 2026-11-09 A 「全部の逃げを数える」: the leave counts once it relocated the
        # player; the second of the dive starts the town return.
        raw = with_gazer(self.board(LAST_TURN), *GAZER_CELL)
        policy, answer = self.replay(raw)
        self.assertEqual(answer[1], SCROLL_REASON)
        before = policy._dive_emergencies
        # DECLARED CONSTRUCTED: the board after the read, elsewhere in the room, the ゲイザー gone.
        landed = moved(self.board(LAST_TURN), 8, 52, LAST_TURN + 10)
        self.decide(policy, landed)
        self.assertEqual(policy._dive_emergencies, before + 1)
        # DECLARED CONSTRUCTED: the ゲイザー in view again; it is left again and that second
        # relocation returns to town.
        again = with_gazer(moved(self.board(LAST_TURN), 8, 52, LAST_TURN + 20), *GAZER_CELL)
        self.assertEqual(self.decide(policy, again)[1], SCROLL_REASON)
        self.decide(policy, moved(self.board(LAST_TURN), 2, 47, LAST_TURN + 30))
        self.assertEqual(policy._dive_emergencies, before + 2)
        self.assertTrue(policy._returning_to_town)
        self.assertEqual(policy._last_return_trigger, "emergency-repeat")


TR_FREE_ACT = 46
STAT_ORDER = ("str", "int", "wis", "dex", "con", "chr")


class FreeActionPickupTest(ShallowParalyzerRecordedHarness):
    """Owner 「耐麻痺装備をたまたま浅い階から拾っていたら装備することを確認する」: a Free Action
    piece carried home from a shallow floor is in the town optimizer's target loadout.

    The recorded character of the last board: Lv17 warrior, a ring of 恐れ知らず on one hand,
    硬革ブーツ [3,+0] on the feet, no Free Action, recall depth 13 (イークの洞穴).

    DECLARED CONSTRUCTED: the board back in town (the floor's town fields; nothing in view), a
    Free Action piece in the pack; the character calibration (the capture has none; seeded from
    the board with the stat tops as the displayed stats, as tests/test_gloves_phase_1102_recorded
    does); the ~f skill exp (0, as this file's skill()); an empty Home (its pages were not
    captured)."""

    def town_board(self, piece):
        raw = self.board(LAST_TURN)
        raw["floor"].update(dungeon_id=0, level=0, in_town=True, town_id=1)
        raw["visible_monsters"] = []
        raw["inventory"].append(dict(piece, slot=chr(ord("a") + len(raw["inventory"]))))
        return raw

    def target(self, raw):
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        board = parse_snapshot(copy.deepcopy(raw), self.races)
        board = replace(board, player=replace(board.player, two_weapon_skill=0, shield_skill=0))
        tops = tuple(raw["player"]["stats"][name]["top"] for name in STAT_ORDER)
        seed_character_calibration(policy, replace(
            board, player=replace(board.player, stat_cur=tops, stat_use=tops)))
        policy._character_calibration = replace(
            policy._character_calibration, stat_cur=tuple(board.player.printed_stat_cur_key))
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        policy._equipment_catalog.observe_home_page([])
        prepared = policy._prepare_equipment_optimization(board)
        self.assertEqual(prepared.blockers, ())
        return dict(prepared.result.best.loadout.slots)

    def piece(self, slot_of, **fields):
        worn = next(item for item in self.board(LAST_TURN)["equipment"]
                    if item.get("slot") == slot_of)
        return dict(copy.deepcopy(worn), **fields)

    def test_the_recorded_kit(self):
        slots = {item["slot"]: item for item in self.board(LAST_TURN)["equipment"]}
        self.assertEqual((slots["feet"]["tval"], slots["feet"]["ac"], slots["feet"]["to_a"]),
                         (30, 3, 0))
        self.assertNotIn("sub_ring", slots)
        self.assertNotIn("arms", slots)

    def test_free_action_boots_replace_the_worn_boots_with_more_ac(self):
        # DECLARED CONSTRUCTED: 軟革ブーツ [2,+0] of Free Action in the pack.
        boots = self.piece("feet", name="軟革ブーツ [2,+0] (耐麻痺)", sval=2, ac=2, weight=20,
                           known_flags=[TR_FREE_ACT], fully_known=True, is_ego=True)
        feet = self.target(self.town_board(boots))["feet"]
        self.assertIn(TR_FREE_ACT, feet.flags)
        self.assertEqual(feet.item.name, "軟革ブーツ [2,+0] (耐麻痺)")

    def test_a_free_action_ring_goes_on_the_free_hand(self):
        # DECLARED CONSTRUCTED: a Ring of Free Action in the pack.
        ring = self.piece("main_ring", name="耐麻痺の指輪", known_flags=[TR_FREE_ACT],
                          fully_known=True)
        slots = self.target(self.town_board(ring))
        self.assertEqual(sorted(TR_FREE_ACT in slots[slot].flags
                                for slot in ("main_ring", "sub_ring")), [False, True])


if __name__ == "__main__":
    unittest.main()
