"""A blind one-shot board escapes by the teleport no scroll gives (threat_tiers.blind_teleport_key).

Recorded n1-c life-171 (Zombie Magic-Eater Lv50, max HP 993, 城65階, 2026-11-08 20:08): the
second 65F visit (decisions 20580-20590).  皇帝『レイザーク』's darkness storm blinded it at the
door (turn 4244010); decision 20589 (turn 4244017, HP 818, the summoner in view) cast the
absorbed Cure Light Wounds (``emergency:cure-light:absorbed-power`` ``mAq``); the emperor
summoned ハスター, ウートガルザ・ロキ, a Black Wraith and giants and blinded it again, and
decision 20590 (turn 4244027, HP 259, next action p95 1421: 即死) found no readable escape and
fired the absorbed rocket (``ranged:magic-eater-device`` ``mB37``).  It died on the next turn
with the absorbed Teleportation at 24/24, 98%.  Design 3.1 即死→逃げる; owner 2026-11-06
「低HPで召喚・引き寄せ・速い敵が見えたら1歩退却でなくテレポート/帰還」; owner 2026-11-08
「その敵の感知範囲内なら早急に離脱する」 and 「即死の危険があるときは成功率の高いものを使うべき
なので巻物によるテレポートを優先」.

Boards: tests/fixtures/hastur-blind-escape-n1c-171-1108.json.xz
(tests/extract_hastur_blind_escape_1108_fixture.py), one fresh policy deciding every recorded
decision board in order through ``choose_key``.

DECLARED CONSTRUCTED / RESTORED (pin_vacuity):
 * the absorbed device lists the game last displayed (staff, wand, rod: the town-arrival
   checkpoint's ``_me_device_lists``) are shown to ``observe_lists`` on boards before the floor,
   as the executor's menu reading would (the live policy held them; the capture has no menu board);
 * the carried-staff case: no absorbed staff list, and a Staff of Teleportation in the pack;
 * the side-defect cases replay the floor without the absorbed staff list, so the recorded
   blindness cure is drunk on 20589 (no teleport, no absorbed Cure Light Wounds);
 * the blind *Destruction* cases: the 20590 board with the guardian taken off (and, for the
   refusal, confusion added);
 * the scroll-first case: the 20590 board with sight restored (the own grid seen) and the guardian 皇帝『レイザーク』
   taken off the board (a guardian in the circle refuses *Destruction*, destruction_use).
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot import me_device_attacks_input, status_cure, threat_tiers
from hengbot.me_device_attacks import observe_lists
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import TVAL_SCROLL, TVAL_STAFF, parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import EMERGENCY_ESCAPE_REASONS
from test_esp_threat_rest_recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "hastur-blind-escape-n1c-171-1108.json.xz"
# The recorded decisions 20580-20590 (bot-decisions.jsonl): turn -> (key, reason).
RECORDED = {
    4243941: ("UCg", "me-power:new-floor:detect-all:powerful"),
    4243948: ("7", "explore"),
    4243957: ("mAm", "me-power:new-floor:detect-traps"),
    4243964: ("mAj", "me-power:after-destruction:map-area"),
    4243970: ("2", "explore"),
    4243978: ("3", "hunt:detected-target"),
    4243985: ("2", "explore"),
    4243991: ("1", "explore"),
    4244001: ("o3", "explore"),
    4244017: ("mAq", "emergency:cure-light:absorbed-power"),
    4244027: ("mB37", "ranged:magic-eater-device"),
}
ARRIVAL = 4243941         # decision 20580, the first 65F board
SUMMONER_OPEN = 4244017   # decision 20589
ONE_SHOT = 4244027        # decision 20590
EMPEROR, HASTUR = 882, 757
ABSORBED_TELEPORT = "mAe"  # m, A (staff), the power letter of sval 4
ESCAPE = "emergency:teleport:absorbed-power"


class HasturBlindEscapeRecordedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.skill = payload["skill"]
        cls.lists = payload["lists"]
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        # The castle's guardian (皇帝『レイザーク』 on 65F) as the live bot knows it.
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
        # The last board of each recorded decision turn.
        cls.boards = {raw["turn"]: raw for raw in payload["boards"] if raw["turn"] in RECORDED}
        cls.answers = None

    def new_policy(self, kinds=("staff", "wand", "rod")):
        first = self.boards[min(self.boards)]
        policy = HengbotPolicy(monrace_knowledge=self.races, dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(first), self.races))
        # RESTORED: the displayed lists, oldest first (observe_lists starts over on a turn
        # going backwards).
        for kind, (turn, rows) in sorted(self.lists.items(), key=lambda entry: entry[1][0]):
            if kind in kinds:
                shown = dict(copy.deepcopy(first), turn=turn,
                             _magic_eater_power_list={"kind": kind, "rows": rows})
                observe_lists(policy, parse_snapshot(shown, self.races))
        return policy

    def snapshot(self, policy, raw):
        policy.consume_skill_knowledge({**self.skill, "player": {"level": raw["player"]["level"]}})
        return policy.with_known_skill_exp(parse_snapshot(copy.deepcopy(raw), self.races))

    def replay(self, until=ONE_SHOT, change=None, kinds=("staff", "wand", "rod")):
        """turn -> (key, reason, snapshot): one policy deciding the recorded boards in order."""
        policy = self.new_policy(kinds)
        answers = {}
        for turn in sorted(self.boards):
            if turn > until:
                break
            raw = copy.deepcopy(self.boards[turn])
            if change is not None:
                change(raw)
            snapshot = self.snapshot(policy, raw)
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(key)
            answers[turn] = (str(key), policy.last_reason, snapshot)
        return policy, answers

    def recorded_answers(self):
        if type(self).answers is None:
            type(self).answers = self.replay()
        return type(self).answers

    # -- the recorded boards -----------------------------------------------------------------

    def test_the_blind_one_shot_board_casts_the_absorbed_teleport(self):
        policy, answers = self.recorded_answers()
        key, reason, snapshot = answers[ONE_SHOT]
        player = snapshot.player
        self.assertTrue(player.blind)
        self.assertFalse(player.confused)
        self.assertEqual((player.hp, player.max_hp), (259, 993))
        races = {monster.race_id for monster in snapshot.visible_monsters}
        self.assertTrue({EMPEROR, HASTUR} <= races)
        # 即死: the next action's p95 is past the HP (the recorded 1421).
        self.assertTrue(threat_tiers.instant_death(policy, snapshot).holds)
        self.assertEqual((key, reason), (ABSORBED_TELEPORT, ESCAPE))
        self.assertNotEqual(key, RECORDED[ONE_SHOT][0])
        # The executor admits the key under that reason and it counts as the dive's escape.
        verb, steps = me_device_attacks_input.compile_device(key, reason)
        self.assertEqual((verb, steps[0].kind, steps[0].sval), ("m", "staff", 4))
        self.assertIn(reason, EMERGENCY_ESCAPE_REASONS)

    def test_the_blind_summoner_board_escapes_before_the_cure(self):
        _policy, answers = self.recorded_answers()
        key, reason, snapshot = answers[SUMMONER_OPEN]
        self.assertTrue(snapshot.player.blind)
        self.assertEqual(snapshot.player.hp, 818)
        self.assertIn(EMPEROR, {monster.race_id for monster in snapshot.visible_monsters})
        self.assertEqual((key, reason), (ABSORBED_TELEPORT, ESCAPE))
        self.assertNotEqual(key, RECORDED[SUMMONER_OPEN][0])

    def test_the_sensed_t1_leave_casts_the_teleport_when_blind(self):
        policy, answers = self.recorded_answers()
        snapshot = answers[ONE_SHOT][2]
        policy.last_reason = None
        key = threat_tiers.sensed_t1_leave_key(policy, snapshot)
        self.assertEqual((key, policy.last_reason),
                         (ABSORBED_TELEPORT, threat_tiers.SENSED_LEAVE_PREFIX + "teleport:absorbed-power"))

    def test_the_low_hp_escape_read_casts_the_teleport_when_blind(self):
        policy, answers = self.recorded_answers()
        snapshot = answers[ONE_SHOT][2]
        self.assertLess(snapshot.player.hp, policy._low_hp_walk_threshold(snapshot.player.max_hp))
        policy.last_reason = None
        self.assertEqual((policy._low_hp_escape_read(snapshot), policy.last_reason),
                         (ABSORBED_TELEPORT, ESCAPE))

    # -- constructed variants of the recorded board ------------------------------------------

    def test_a_carried_staff_of_teleportation_is_used_blind(self):
        """CONSTRUCTED: no absorbed staff list; a Staff of Teleportation in the pack."""
        def staff(raw):
            item = dict(copy.deepcopy(raw["inventory"][0]), slot="m", tval=TVAL_STAFF, sval=4,
                        count=1, known=True, aware=True, fully_known=True, charging=False,
                        charges=10, pval=10, name="テレポートの杖 (10回分)", weight=50)
            raw["inventory"].append(item)
        _policy, answers = self.replay(change=staff, kinds=("wand", "rod"))
        key, reason, _snapshot = answers[ONE_SHOT]
        self.assertEqual((key, reason), ("um", "emergency:teleport-staff"))
        self.assertIn(reason, EMERGENCY_ESCAPE_REASONS)

    def test_a_readable_teleport_scroll_comes_first_on_a_one_shot_board(self):
        """CONSTRUCTED: sight restored on 20590 and the guardian off the board, so the absorbed
        *Destruction* (68 charges) and the absorbed teleport could both serve.  Owner 2026-11-08
        「即死の危険があるときは成功率の高いものを使うべきなので巻物によるテレポートを優先」."""
        policy, _answers = self.replay(until=SUMMONER_OPEN)
        raw = copy.deepcopy(self.boards[ONE_SHOT])
        raw["player"]["status"]["blind"] = False
        raw["player"]["can_see_own_grid"] = True  # false only because blind (geometry.cpp)
        raw["visible_monsters"] = [m for m in raw["visible_monsters"] if m["race_id"] != EMPEROR]
        raw["detected_monsters"] = [m for m in raw["detected_monsters"] if m["race_id"] != EMPEROR]
        snapshot = self.snapshot(policy, raw)
        self.assertTrue(threat_tiers.instant_death(policy, snapshot).holds)
        from hengbot import destruction_use
        self.assertTrue(destruction_use.holds_means(policy, snapshot))
        self.assertTrue(destruction_use._scene_holds(policy, snapshot))
        key = str(policy.choose_key(snapshot))
        scroll = next(item for item in raw["inventory"]
                      if item["tval"] == TVAL_SCROLL and item["sval"] == 9)
        self.assertEqual((key, policy.last_reason), ("r" + scroll["slot"], "emergency:teleport"))

    # -- the side defects (REPORT proposal 3) --------------------------------------------------

    def test_unknown_grids_do_not_hide_the_emperors_spells(self):
        """After the darkness storm the grids (14,61) and (16,61) between the emperor at (13,61)
        and the player at (17,61) are not on the board; the map memory of the boards before
        (the player walked them) knows them as floor, so they are no wall for its spells."""
        policy, answers = self.recorded_answers()
        snapshot = answers[ONE_SHOT][2]
        emperor = next(m for m in snapshot.visible_monsters if m.race_id == EMPEROR)
        self.assertEqual((emperor.position.y, emperor.position.x), (13, 61))
        between = [snapshot.grid_at(type(emperor.position)(y, 61)) for y in (14, 16)]
        self.assertTrue(all(grid is None or not grid.known for grid in between))
        remembered = [policy._remembered_grids.get(type(emperor.position)(y, 61)) for y in (14, 16)]
        self.assertTrue(all(grid is not None and grid.allows_los for grid in remembered))
        row = policy.threat_prediction(snapshot, [emperor], 1)["monsters"][0]
        self.assertGreater(row["operational_ranged_prediction"], 0)
        self.assertGreater(row["ranged_prediction"], 0)

    def test_a_spell_that_blinds_again_after_the_cure_does_not_make_it_futile(self):
        """20589 drinks the cure; the emperor's darkness storm blinds again (no blow named), so
        on 20590 the blindness is still treated: the HP recovery potion that also cures it."""
        policy, answers = self.replay(kinds=("wand", "rod"))
        self.assertEqual(answers[SUMMONER_OPEN][1], "emergency:cure-critical")
        key, reason, snapshot = answers[ONE_SHOT]
        self.assertEqual(policy._blind_cure_futile_floor, snapshot.floor_key)  # cured, blind again
        self.assertIsNone(policy._blind_cure_futile_blow)
        self.assertFalse(status_cure.cure_futile(policy, snapshot))
        self.assertEqual(reason, "emergency:cure-status-healing")

    # -- owner 2026-11-08 「盲目でも使う」 (*Destruction* while blind) ---------------------------

    def without_emperor(self, raw):
        """CONSTRUCTED: the guardian off the board (a guardian in the circle refuses the use)."""
        raw["visible_monsters"] = [m for m in raw["visible_monsters"] if m["race_id"] != EMPEROR]
        raw["detected_monsters"] = [m for m in raw["detected_monsters"] if m["race_id"] != EMPEROR]

    def test_the_absorbed_destruction_is_used_blind_before_the_teleport(self):
        policy, _answers = self.replay(until=SUMMONER_OPEN)
        raw = copy.deepcopy(self.boards[ONE_SHOT])
        self.without_emperor(raw)
        snapshot = self.snapshot(policy, raw)
        self.assertTrue(snapshot.player.blind)
        key = str(policy.choose_key(snapshot))
        self.assertEqual((key, policy.last_reason), ("mA3", "emergency:destruction:absorbed-power"))

    def test_confusion_still_refuses_destruction_and_the_teleport(self):
        """CONSTRUCTED: also confused (the m command refuses it, cmd-magiceat.cpp:463)."""
        policy, _answers = self.replay(until=SUMMONER_OPEN)
        raw = copy.deepcopy(self.boards[ONE_SHOT])
        self.without_emperor(raw)
        raw["player"]["status"]["confused"] = True
        snapshot = self.snapshot(policy, raw)
        from hengbot import destruction_use
        self.assertFalse(destruction_use.usable(policy, snapshot))
        self.assertIsNone(threat_tiers.blind_teleport_means(policy, snapshot))
        key = str(policy.choose_key(snapshot))
        self.assertFalse(key.startswith("mA"), (key, policy.last_reason))

    # -- owner 2026-11-08 「勝てないと分かれば離脱」 (question 1) -------------------------------

    def test_the_sensed_emperor_that_cannot_be_beaten_is_left_on_arrival(self):
        """20580: the emperor awake 13 away, the player inside its sensing radius; its
        contact tier is undecided past the cost cap, but the no-supply incoming damage is at
        least 1345 against HP 993, so it is T1 for the sensed leave (recorded: ``UCg``)."""
        policy, answers = self.replay(until=ARRIVAL)
        key, reason, snapshot = answers[ARRIVAL]
        emperor = next(m for m in snapshot.detected_monsters if m.race_id == EMPEROR)
        self.assertFalse(emperor.asleep)
        self.assertTrue(threat_tiers.inside_sensing(policy, snapshot, emperor))
        alone = threat_tiers.tiered(policy, snapshot, [emperor], contact=True)
        self.assertEqual((alone.tier, alone.skipped), (None, "cost"))
        self.assertGreaterEqual(alone.free_incoming_bounds[0], snapshot.player.hp)
        scroll = next(item for item in snapshot.inventory
                      if item.tval == TVAL_SCROLL and item.sval == 9)
        self.assertEqual((key, reason), ("r" + scroll.slot, threat_tiers.SENSED_LEAVE_PREFIX + "teleport"))
        self.assertNotEqual(key, RECORDED[ARRIVAL][0])


if __name__ == "__main__":
    unittest.main()
