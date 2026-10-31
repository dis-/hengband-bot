"""#47: the Magic-Eater's absorbed stage-2 powers (me_powers, owner 2026-10-31).

Owner: 「魔道具術師の二段階目で取り込んだ魔法道具の使用ロジックを作る。」 and, on the
proposal, 「案はこれで良い。…保守性を維持するように作って。」

Boards are the recorded n1-c Magic-Eater board of life 16 on Yeek cave 1F
(turn 94171, tests/fixtures/me-mining-death-20261030.json.gz, see
test_me_mining_death_recorded) through the public choose_key and the
production executor.

DECLARED CONSTRUCTED: no recorded character has reached stage 2 yet, so the
absorbed staff list (``_magic_eater_power_list`` rows: BaseitemDefinitions
names, charges and fail percentages chosen per case) is constructed; the
recorded yeek is removed except where a visible hostile is the case; the
Yeek cave definition is a DungeonInfo (flags as DungeonDefinitions.jsonc, or
DARKNESS where that is the case); earlier uses on the floor are seeded into
``_me_power_floor``; the dark board removes the carried torches and the dark
room is drawn in an unexplored part of the map; the before-rest case patches
the town return out so the recorded board reaches the rest rung; the
light-sensitive case adds a detected small kobold with HURT_LITE.  Replies to
posted keys are constructed from the game's prompts (cmd-magiceat.cpp).
"""
import tests  # noqa: F401 -- isolate live runtime files

import copy
from dataclasses import replace
import unittest
from unittest import mock

from hengbot import me_powers
from hengbot.dungeon_knowledge import DungeonInfo
from hengbot.me_device_attacks_input import DeviceStep, compile_device
from hengbot.model import Position, parse_snapshot
from hengbot.policy import HengbotPolicy
from tests import test_me_mining_death_recorded as mining
from tests.test_input_executor import command_screen
from tests.test_magic_eater_o3 import prompt
from tests.test_me_device_attacks import power_screen

LIFE, TURN = "life-016", 94171
EVIL, TRAP, MAPPING, DOOR, LIGHT = 15, 12, 9, 13, 8
NAMES = {EVIL: "邪悪存在感知", TRAP: "トラップ感知", MAPPING: "周辺感知",
         DOOR: "ドア/階段感知", LIGHT: "光"}
TYPE_PROMPT = "[A] 杖, [B] 魔法棒, [C] ロッド:"
YEEK_CAVE = DungeonInfo(2, "Yeek cave", 1, 2, 1)
FAILED = "呪文をうまく唱えられなかった！"


def staff_rows(**overrides):
    """sval -> current charges (5 unless overridden by name)."""
    current = {sval: 5 for sval in NAMES}
    current.update({globals()[name.upper()]: value for name, value in overrides.items()})
    return current


def staff_list(current):
    return {"kind": "staff", "rows": [
        {"name": NAMES[sval], "current": count, "max": 14, "fail": 20, "success": 80}
        for sval, count in current.items()]}


def _recorded(name):
    return getattr(mining.MagicEaterMiningDeathRecordedTest, name)


class MagicEaterStage2PowersTest(mining.harness.ProductionHarness):
    setUpClass = classmethod(_recorded("setUpClass").__func__)
    raw = _recorded("raw")
    recorded_policy = _recorded("policy")
    choose = _recorded("choose")
    post = _recorded("post")

    def board(self, current=None, *, hostile=False):
        raw = self.raw(LIFE, TURN)
        if not hostile:
            raw["visible_monsters"] = []
        raw["_magic_eater_power_list"] = staff_list(current or staff_rows())
        return raw

    def policy(self, raw, *, flags=frozenset(), dungeon=True, used=None):
        policy = self.recorded_policy(LIFE, raw)
        policy._dungeon_knowledge = {2: replace(YEEK_CAVE, flags=flags)} if dungeon else {}
        if used is not None:
            # Earlier successful uses on this floor visit: sval -> position.
            memory = me_powers.FloorMemory((2, 1, 0), raw["turn"])
            for sval, position in used.items():
                ident = ("staff", sval)
                memory.uses.append(me_powers.Use(ident, ident, "new-floor", position, raw["turn"] - 5))
            policy._me_power_floor = memory
        return policy

    @staticmethod
    def here(raw):
        return Position(raw["player"]["y"], raw["player"]["x"])

    def cast(self, policy, raw, key, current, *, after=()):
        sval = me_powers.decode_letter(key[2])
        rows = [(me_powers.encode_letter(each), NAMES[each], count, 14, 20)
                for each, count in current.items()]
        game, port = self.post(policy, raw, key, [
            prompt(TYPE_PROMPT), power_screen("staff", rows), *after])
        self.assertEqual(game.accepted, ["m", "A", me_powers.encode_letter(sval)])
        return port.last_result.board

    def assertPower(self, policy, key, letter, reason):
        self.assertEqual((key, policy.last_reason), ("mA" + letter, reason))

    def test_new_floor_detects_evil_then_traps_then_maps(self):
        raw = self.board()
        policy = self.policy(raw)
        expected = (("p", "me-power:new-floor:detect-evil"),
                    ("m", "me-power:new-floor:detect-traps"),
                    ("j", "me-power:new-floor:map-area"))
        for letter, reason in expected:
            key = self.choose(policy, raw)
            self.assertPower(policy, key, letter, reason)
            raw = self.cast(policy, raw, key, staff_rows())
        self.assertFalse(self.choose(policy, raw).startswith("mA"))
        self.assertFalse(policy.last_reason.startswith("me-power:"), policy.last_reason)

    def test_no_power_with_a_visible_hostile_or_without_charges(self):
        cases = {"visible yeek": self.board(hostile=True),
                 "no charges": self.board({sval: 0 for sval in NAMES})}
        for label, raw in cases.items():
            with self.subTest(label):
                policy = self.policy(raw)
                key = self.choose(policy, raw)
                self.assertFalse(policy.last_reason.startswith("me-power:"), (key, policy.last_reason))
        raw = self.board()
        policy = self.policy(raw)
        policy._took_damage = True
        self.assertIsNone(me_powers.power_key(
            policy, parse_snapshot(raw, policy._monrace_knowledge), me_powers.FLOOR))

    def test_no_power_in_town_or_the_wilderness(self):
        for label, floor in (("town", {"dungeon_id": 0, "level": 0, "in_town": True}),
                             ("wilderness", {"dungeon_id": 0, "level": 0, "in_town": False})):
            with self.subTest(label):
                raw = self.board()
                raw["floor"].update(floor)
                policy = self.policy(raw)
                board = parse_snapshot(raw, policy._monrace_knowledge)
                me_powers.observe(policy, board)
                for occasion in (me_powers.FLOOR, me_powers.DARK, me_powers.REST,
                                 me_powers.SECRET_SEARCH):
                    self.assertIsNone(me_powers.power_key(policy, board, occasion))

    def test_failed_cast_is_retried_at_the_same_place_up_to_five_failures(self):
        # Owner 2026-10-31 「最大5回まで同じ場所で試す」.
        raw = self.board()
        policy = self.policy(raw)
        board = raw
        for failure_number in range(1, 5 + 1):
            key = self.choose(policy, board)
            self.assertPower(policy, key, "p", "me-power:new-floor:detect-evil")
            failure = command_screen(board["turn"] + 10)
            failure["lines"][0] = FAILED
            board = self.cast(policy, board, key, staff_rows(), after=[failure])
            self.assertEqual(board["_completed_operation_receipt"]["refusal"], "failed:magic-eater",
                             failure_number)
        # Five failures here: the next due power, not a sixth cast.
        key = self.choose(policy, board)
        self.assertPower(policy, key, "m", "me-power:new-floor:detect-traps")
        # One step away the failed trigger is due again.
        moved = copy.deepcopy(board)
        moved["turn"] += 10
        moved["player"]["x"] -= 1
        self.assertEqual(self.choose(policy, moved), "mAp")
        self.assertEqual(me_powers.FAILURES_PER_PLACE, 5)

    def test_mapping_without_charge_serves_door_detection(self):
        current = staff_rows(mapping=0)
        raw = self.board(current)
        here = self.here(raw)
        policy = self.policy(raw, used={EVIL: here, TRAP: here})
        key = self.choose(policy, raw)
        self.assertPower(policy, key, "n", "me-power:new-floor:detect-doors-stairs")
        board = self.cast(policy, raw, key, current)
        key = self.choose(policy, board)
        self.assertFalse(policy.last_reason.startswith("me-power:"), (key, policy.last_reason))

    def test_detected_trap_area_edge_detects_again(self):
        raw = self.board()
        here = self.here(raw)
        for distance, due in ((29, True), (28, False)):
            with self.subTest(distance=distance):
                far = Position(here.y, here.x - distance)
                policy = self.policy(raw, used={EVIL: here, TRAP: far, MAPPING: here})
                key = self.choose(policy, raw)
                if due:
                    self.assertPower(policy, key, "m", "me-power:left-detected-trap-area:detect-traps")
                else:
                    self.assertFalse(policy.last_reason.startswith("me-power:"), policy.last_reason)

    def _dark_board(self):
        raw = self.board()
        raw["player"]["can_see_own_grid"] = False
        # No carried torch or flask: the light repair has nothing to wield.
        raw["inventory"] = [item for item in raw["inventory"] if item["tval"] not in (39, 77)]
        return raw

    def test_light_radius_zero_uses_light_before_the_dark_walk(self):
        raw = self._dark_board()
        policy = self.policy(raw)
        key = self.choose(policy, raw)
        self.assertPower(policy, key, "i", "me-power:light-radius-zero:lite-area")
        self.cast(policy, raw, key, staff_rows())
        for label, kwargs in (("DARKNESS dungeon", {"flags": frozenset({"DARKNESS"})}),
                              ("unknown dungeon", {"dungeon": False})):
            with self.subTest(label):
                policy = self.policy(raw, **kwargs)
                key = self.choose(policy, raw)
                self.assertFalse(policy.last_reason.startswith("me-power:"), (key, policy.last_reason))

    def _room_board(self, *, lit_ring):
        """The player in an open 3x3 floor drawn where nothing is known."""
        raw = self.board()
        gm = raw["grid_map"]
        y, x = 20, 20
        known = {(r[0], c) for r in gm["runs"] for c in range(r[1], r[1] + r[2])}
        known |= {tuple(c) for name in ("known_t", "marked_t", "floor_t", "wall_t")
                  for c in self.data["cases"][LIFE]["terrain"][name]}
        self.assertFalse({(y + dy, x + dx) for dy in range(-4, 5) for dx in range(-4, 5)} & known)
        torch_floor = gm["palette"].index([1, 1, 416, 1])
        gm["palette"].append([1, 0, 416, 1])  # a glowing floor in view (F_LIT_STANDARD)
        gm["runs"] += [[y + dy, x - 1, 3, torch_floor] for dy in (-1, 0, 1)]
        if lit_ring:
            gm["runs"].append([y + 2, x - 1, 3, len(gm["palette"]) - 1])
        raw["player"].update(y=y, x=x)
        return raw, Position(y, x)

    def test_dark_room_is_lit_once(self):
        for lit_ring, due in ((False, True), (True, False)):
            with self.subTest(lit_ring=lit_ring):
                raw, here = self._room_board(lit_ring=lit_ring)
                policy = self.policy(raw, used={EVIL: here, TRAP: here, MAPPING: here})
                key = self.choose(policy, raw)
                if not due:
                    self.assertFalse(policy.last_reason.startswith("me-power:"), policy.last_reason)
                    continue
                self.assertPower(policy, key, "i", "me-power:dark-room:lite-area")
                board = self.cast(policy, raw, key, staff_rows())
                self.choose(policy, board)
                self.assertFalse(policy.last_reason.startswith("me-power:"), policy.last_reason)

    def test_light_sensitive_detected_neighbour(self):
        raw = self.board()
        here = self.here(raw)
        kobold = dict(self.raw(LIFE, TURN)["visible_monsters"][0], race_id=29,
                      name="スモール・コボルド", y=here.y, x=here.x + 1)
        raw["detected_monsters"] = [kobold]
        policy = self.policy(raw, used={EVIL: here, TRAP: here, MAPPING: here})
        races = dict(policy._monrace_knowledge)
        races[29] = replace(races[29], flags=races[29].flags | {"HURT_LITE"})
        policy._monrace_knowledge = races
        key = self.choose(policy, raw)
        self.assertPower(policy, key, "i", "me-power:light-sensitive-adjacent:lite-area")

    def test_detect_evil_before_resting(self):
        calm = {"_returning_to_town": False, "_emergency_return_active": False,
                "_fundraising_mode": None}
        raw = self.board()
        here = self.here(raw)
        with mock.patch.object(HengbotPolicy, "_should_start_town_return", return_value=False), \
                mock.patch.object(HengbotPolicy, "_return_to_town_key", return_value=None):
            for evil_at, expected in ((Position(1, 1), "mAp"), (here, "R&\r")):
                with self.subTest(evil_at=evil_at):
                    policy = self.policy(raw, used={EVIL: evil_at, TRAP: here, MAPPING: here})
                    for name, value in calm.items():
                        setattr(policy, name, value)
                    key = self.choose(policy, raw)
                    self.assertEqual(key, expected, policy.last_reason)
                    if key == "mAp":
                        self.assertEqual(policy.last_reason, "me-power:before-rest:detect-evil")

    def test_door_detection_before_the_secret_wall_search(self):
        raw = self.board()
        here = self.here(raw)
        for door_at, expected in ((None, "mAn"), (Position(here.y, here.x - 29), None),
                                  (Position(here.y, here.x - 30), "mAn")):
            with self.subTest(door_at=door_at):
                policy = self.policy(raw, used={} if door_at is None else {DOOR: door_at})
                board = parse_snapshot(raw, policy._monrace_knowledge)
                me_powers.observe(policy, board)
                self.assertEqual(me_powers.power_key(policy, board, me_powers.SECRET_SEARCH), expected)

    def test_every_row_is_complete_and_executable(self):
        for power in me_powers.POWERS:
            with self.subTest(power=power.effect):
                self.assertTrue(set(power.triggers) <= set(me_powers.TRIGGERS))
                self.assertTrue(set(power.requires) <= set(me_powers.REQUIREMENTS))
                self.assertIs(me_powers.BY_KEY[power.ident], power)
                self.assertEqual(me_powers.decode_letter(power.letter), power.sval)
                if power.fallback is not None:
                    self.assertIn(power.fallback, me_powers.BY_KEY)
                prefix, steps = compile_device(power.key, "me-power:new-floor:" + power.effect)
                self.assertEqual(prefix, "m")
                self.assertEqual((type(steps[0]), steps[0].kind, steps[0].sval),
                                 (DeviceStep, power.kind, power.sval))
                self.assertIsNone(compile_device(power.key, "explore"))
        # Grid::calc_distance truncates toward zero (2,2 looped with floor division);
        # its Newton step stops at 30 for (20, 21) although the root is 29.
        for (dy, dx), distance in (((2, 2), 3), ((3, 4), 5), ((29, 0), 29), ((20, 21), 30)):
            self.assertEqual(me_powers.game_distance(Position(0, 0), Position(dy, dx)), distance)
        # staff 15 (Detect Evil) and wand 15 (Magic Missile) are different rows.
        self.assertNotIn(("wand", 15), me_powers.BY_KEY)

    def test_adding_a_power_is_one_row(self):
        # Staff of Detect Invisible (sval 14, BaseitemDefinitions id 313).
        row = me_powers.Power("staff", 14, ("透明物体感知", "Detect Invisible"),
                              "detect-invisible", 0, 5, ("new-floor",), darkness_scaled=False)
        powers = (*me_powers.POWERS, row)
        current = staff_rows()
        raw = self.board(current)
        raw["_magic_eater_power_list"]["rows"].append(
            {"name": "透明物体感知", "current": 3, "max": 14, "fail": 20, "success": 80})
        with mock.patch.object(me_powers, "POWERS", powers), \
                mock.patch.object(me_powers, "BY_KEY", {power.ident: power for power in powers}):
            policy = self.policy(raw)
            key = self.choose(policy, raw)
            self.assertPower(policy, key, "o", "me-power:new-floor:detect-invisible")
            game, _ = self.post(policy, raw, key, [
                prompt(TYPE_PROMPT),
                power_screen("staff", [("o", "透明物体感知", 3, 14, 20)])])
            self.assertEqual(game.accepted, ["m", "A", "o"])


if __name__ == "__main__":
    unittest.main()
