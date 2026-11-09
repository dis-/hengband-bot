"""n1-a life-500's death (2026-11-09 19:00, オークの洞窟23階) and the owner's answer of 2026-11-09.

Analysis: C:/hengband-backups/pdca/captures/n1a-500-death-1109/REPORT.txt.  Boards:
tests/fixtures/teleport-follower-n1a-500-1109.json.xz (tests/extract_teleport_follower_1109_fixture.py),
one board per live decision row (decisions 15674-15774, the whole 23F visit); every decision here
is the public ``choose_key`` of one fresh policy replaying the recorded boards in order
(``confirm_key_posted`` after each key, as the driver does).

Warrior Lv45, max HP 1092.  A クトーニアン summoned 禁断の護り手 (id 746: TPORT, no RES_TELE,
speed +20, a blinding blow) beside the player (15769).  Live: Cure Critical Wounds, Healing, the
Teleportation scroll (15771), Healing, the scroll again (15773), Healing, dead; 禁断の護り手 stood
beside the player on each landing (spells-teleport.cpp:392-411 teleport_player: an adjacent awake
TPORT monster without RESIST_TELEPORT follows).  The Wand of Teleport Other (11 charges) was never
used.

Owner 2026-11-09, verbatim: 「*破壊*>テレポートアウェイ>戦闘　の順で対処」.

DECLARED RECONSTRUCTION (pin_vacuity): the capture holds no ~f reply, so the skill knowledge is
supplied before each decision (as tests/test_deaths_1109_recorded.py does).

DECLARED CONSTRUCTED (each named at its test): a Staff of *Destruction* with the device skill
raised (the warrior's 35 does not reach the 80% the staff needs); the wand taken out of the pack;
禁断の護り手 moved two cells off; the Teleportation scrolls swapped for Phase Door.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot import status_cure, teleport_follower, threat_tiers, worsens_kill
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import (
    SV_SCROLL_PHASE_DOOR, SV_SCROLL_TELEPORT, SV_STAFF_DESTRUCTION, SV_WAND_TELEPORT_AWAY,
    TVAL_SCROLL, TVAL_STAFF, TVAL_WAND, parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from test_esp_threat_rest_recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "teleport-follower-n1a-500-1109.json.xz"
GUARDIAN = 746            # 禁断の護り手
WOKE = 11910592           # decision 15756: the クトーニアン awake (ranged:fire-target)
SUMMONED = 11910738       # decision 15769: blind, 禁断の護り手 beside the player
FIRST_READ = 11910753     # decision 15771: sighted, the first Teleportation read
LANDED = 11910759         # decision 15772: blind, followed to (57,111)
SECOND_READ = 11910767    # decision 15773: the second read
LAST = 11910775           # decision 15774: blind at HP 12, followed again
FOLLOWED = (SUMMONED, 11910746, FIRST_READ, LANDED, SECOND_READ, LAST)
AWAY = teleport_follower.AWAY_REASON
# ディアボロ (id 1291): Lv66, speed +20, a blinding blow, no TPORT (does not follow).
NON_FOLLOWING_BLINDER = 1291


def skill(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })


def relabel(raw):
    for index, item in enumerate(raw["inventory"]):
        item["slot"] = chr(ord("a") + index)


def without_wand(raw):
    """DECLARED CONSTRUCTED: no Wand of Teleport Other in the pack (letters re-given)."""
    raw["inventory"] = [item for item in raw["inventory"]
                        if not (item["tval"] == TVAL_WAND and item["sval"] == SV_WAND_TELEPORT_AWAY)]
    relabel(raw)


def destruction_staff(raw):
    """DECLARED CONSTRUCTED: a Staff of *Destruction* after the wands, the device skill 130."""
    inventory = raw["inventory"]
    wand = next(item for item in inventory if item["tval"] == TVAL_WAND)
    staff = dict(copy.deepcopy(wand), tval=TVAL_STAFF, sval=SV_STAFF_DESTRUCTION, count=1,
                 charges=5, pval=5, name="*破壊*の杖 (5回分)", weight=50)
    inventory.insert(inventory.index(wand), staff)
    relabel(raw)
    raw["player"]["skill_ratings"]["magic_device"]["value"] = 130


def phase_only(raw):
    """DECLARED CONSTRUCTED: the Teleportation scrolls swapped for Phase Door."""
    for item in raw["inventory"]:
        if item["tval"] == TVAL_SCROLL and item["sval"] == SV_SCROLL_TELEPORT:
            item["sval"], item["name"] = SV_SCROLL_PHASE_DOOR, "ショート・テレポートの巻物"


def move_guardian(y, x):
    """DECLARED CONSTRUCTED: 禁断の護り手 and its map mark at (y, x)."""
    def change(raw):
        monster = next(m for m in raw["visible_monsters"] if m["race_id"] == GUARDIAN)
        monster["y"], monster["x"] = y, x
        cells = raw["grid_map"]["cells"]
        for cell in cells:
            if cell.get("m") == monster["index"]:
                del cell["m"]
        target = next((cell for cell in cells if (cell["y"], cell["x"]) == (y, x)), None)
        if target is None:
            cells.append({"m": monster["index"], "y": y, "x": x})
        else:
            target["m"] = monster["index"]
    return change


def letter(raw, tval, sval):
    return next(item["slot"] for item in raw["inventory"]
                if item["tval"] == tval and item["sval"] == sval)


class TeleportFollowerHarness(unittest.TestCase):
    answers = None

    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.payload["decisions"]}

    def replay(self, until=LAST, change=None):
        """Every recorded board up to game turn ``until`` (``change`` applied to each), one fresh
        policy; {turn: (raw, key, reason, snapshot)}."""
        boards = self.payload["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        answers = {}
        for raw in boards:
            if raw["turn"] > until:
                break
            raw = copy.deepcopy(raw)
            if change is not None:
                change(raw)
            skill(policy, raw)
            snapshot = parse_snapshot(copy.deepcopy(raw), self.races)
            key = policy.choose_key(snapshot)
            if key:
                policy.confirm_key_posted(key)
            answers[raw["turn"]] = (raw, str(key), policy.last_reason, snapshot)
        return policy, answers

    def recorded_answers(self):
        if type(self).answers is None:
            type(self).answers = self.replay()
        return type(self).answers


class FollowerRecordedTest(TeleportFollowerHarness):
    """The recorded boards: Teleport Other at 禁断の護り手, never a teleport read beside it."""

    def test_the_replay_matches_the_live_decisions_before_the_summons(self):
        """From the クトーニアン's waking (15756) to the summons the replay decides as live did
        (the first boards of the floor differ: a fresh policy has no exploration memory), up to
        15760, where plan step 11 shoots the summoner (WorsensWithTimeRecordedTest)."""
        _policy, answers = self.recorded_answers()
        for turn, (_raw, key, reason, _snapshot) in answers.items():
            if WOKE <= turn < RETREAT_OPEN:
                self.assertEqual((key, reason),
                                 (self.recorded[turn]["key"], self.recorded[turn]["reason"]), turn)

    def test_every_followed_board_aims_teleport_other_at_the_follower(self):
        policy, answers = self.recorded_answers()
        live = [self.recorded[turn]["reason"] for turn in FOLLOWED]
        self.assertEqual(live, ["emergency:cure-critical", "emergency:heal", "emergency:teleport",
                                "emergency:cure-status-healing", "emergency:teleport",
                                "emergency:cure-status-healing"])
        for turn in FOLLOWED:
            raw, key, reason, snapshot = answers[turn]
            followers = teleport_follower.followers(policy, snapshot)
            self.assertEqual([monster.race_id for monster in followers], [GUARDIAN], turn)
            wand = letter(raw, TVAL_WAND, SV_WAND_TELEPORT_AWAY)
            direction = policy._direction_key(snapshot.player.position, followers[0].position)
            self.assertEqual((key, reason), ("a" + wand + direction, AWAY), turn)
        # The blind boards too: the wand is zapped blind (zapwand-execution.cpp:122-129).
        self.assertTrue(answers[SUMMONED][3].player.blind)
        self.assertTrue(answers[LAST][3].player.blind)

    def test_no_teleport_counts_as_an_escape_beside_the_follower(self):
        policy, answers = self.recorded_answers()
        snapshot = answers[FIRST_READ][3]
        self.assertFalse(snapshot.player.blind)
        self.assertIsNone(policy._escape_scroll(snapshot))
        means = threat_tiers.assess(policy, snapshot).escape_means
        self.assertNotIn("teleport-scroll", means)
        self.assertTrue(threat_tiers.escape_restorable(policy, snapshot))


class FollowerConstructedTest(TeleportFollowerHarness):
    """DECLARED CONSTRUCTED variants for the owner's order and its edges."""

    def test_destruction_comes_before_teleport_other(self):
        """CONSTRUCTED: a reliable Staff of *Destruction* (オークの洞窟23階 is no fixed quest)."""
        _policy, answers = self.replay(until=SUMMONED, change=destruction_staff)
        raw, key, reason, snapshot = answers[SUMMONED]
        self.assertTrue(snapshot.player.blind)
        self.assertEqual((key, reason), ("u" + letter(raw, TVAL_STAFF, SV_STAFF_DESTRUCTION),
                                         "emergency:destruction"))

    def test_without_teleport_other_the_follower_is_fought_not_teleported_from(self):
        """CONSTRUCTED: no wand.  Sighted, the scroll is not read; the follower is struck."""
        _policy, answers = self.replay(until=FIRST_READ, change=without_wand)
        _raw, key, reason, snapshot = answers[FIRST_READ]
        self.assertFalse(snapshot.player.blind)
        self.assertNotEqual(reason, "emergency:teleport")
        self.assertNotIn(reason, ("emergency:phase", "emergency:recall"))
        self.assertIn(reason, ("emergency:heal", "emergency:cornered-attack"))

    def test_phase_door_is_followed_too(self):
        """CONSTRUCTED: no wand and Phase Door in place of Teleportation (teleport_player(10))."""
        def change(raw):
            without_wand(raw)
            phase_only(raw)
        _policy, answers = self.replay(until=FIRST_READ, change=change)
        _raw, _key, reason, _snapshot = answers[FIRST_READ]
        self.assertNotEqual(reason, "emergency:phase")

    def test_a_follower_two_cells_off_lets_the_scroll_be_read(self):
        """CONSTRUCTED: 禁断の護り手 two cells off on the first read's board (not adjacent)."""
        def change(raw):
            if raw["turn"] == FIRST_READ:
                move_guardian(raw["player"]["y"] - 2, raw["player"]["x"])(raw)
        policy, answers = self.replay(until=FIRST_READ, change=change)
        raw, key, reason, snapshot = answers[FIRST_READ]
        self.assertEqual(teleport_follower.followers(policy, snapshot), [])
        self.assertEqual((key, reason), ("r" + letter(raw, TVAL_SCROLL, SV_SCROLL_TELEPORT),
                                         "emergency:teleport"))



def blinder_in_place(raw):
    """DECLARED CONSTRUCTED: from the summons on, 禁断の護り手 is ディアボロ (fast, blinding blows,
    no TPORT): a blinder the teleport would leave behind."""
    if raw["turn"] >= SUMMONED:
        for monster in raw["visible_monsters"]:
            if monster["race_id"] == GUARDIAN:
                monster["race_id"] = NON_FOLLOWING_BLINDER


def resists_blindness(raw):
    """DECLARED CONSTRUCTED: resistance to blindness from the equipment."""
    raw["player"]["ability_sources"]["resist_blind"] = {
        "equipment": True, "permanent": False, "temporary": False}


class FasterBlinderConstructedTest(TeleportFollowerHarness):
    """Item 2 (design 4.2 「逃げる手段を取り戻すのが先」): blind beside a faster monster whose blows
    blind, the cure is undone before the next action; an escape usable blind goes first, and
    Teleport Other is one (zapwand-execution.cpp:122-129).  Live 15769 drank Cure Critical
    Wounds and was blind again on 15770."""

    def test_the_faster_blinder_is_sent_away_before_the_cure(self):
        policy, answers = self.replay(until=SUMMONED, change=blinder_in_place)
        raw, key, reason, snapshot = answers[SUMMONED]
        self.assertTrue(snapshot.player.blind)
        self.assertEqual(teleport_follower.followers(policy, snapshot), [])
        self.assertEqual([m.race_id for m in status_cure.outpacing_blinders(policy, snapshot)],
                         [NON_FOLLOWING_BLINDER])
        self.assertEqual(self.recorded[SUMMONED]["reason"], "emergency:cure-critical")
        self.assertEqual((key, reason), ("a" + letter(raw, TVAL_WAND, SV_WAND_TELEPORT_AWAY) + "8",
                                         teleport_follower.BLINDER_REASON))

    def test_with_resistance_to_blindness_nothing_changes(self):
        """CONSTRUCTED also: resistance to blindness; the blindness is no blinder's, the cure stays."""
        def change(raw):
            blinder_in_place(raw)
            resists_blindness(raw)
        policy, answers = self.replay(until=SUMMONED, change=change)
        _raw, _key, reason, snapshot = answers[SUMMONED]
        self.assertEqual(status_cure.outpacing_blinders(policy, snapshot), [])
        self.assertEqual(reason, "emergency:cure-critical")

    def test_sighted_the_scroll_is_read_as_before(self):
        """No follower: the sighted board reads Teleportation as live did (15771)."""
        _policy, answers = self.replay(until=FIRST_READ, change=blinder_in_place)
        raw, key, reason, _snapshot = answers[FIRST_READ]
        self.assertEqual((key, reason), ("r" + letter(raw, TVAL_SCROLL, SV_SCROLL_TELEPORT),
                                         "emergency:teleport"))



CHTHONIAN = 619
RETREAT_OPEN = 11910642   # decision 15760: summoner:retreat, the クトーニアン 6 cells off
RETREAT_NEAR = 11910654   # decision 15761: summoner:retreat, 3 cells off
HELD = 11910665           # decision 15762: melee, the クトーニアン beside the player


def low_hp(raw):
    """DECLARED CONSTRUCTED: HP 300 of 1092 on the 15760 board (below the low-HP line)."""
    if raw["turn"] == RETREAT_OPEN:
        raw["player"]["hp"] = 300


class WorsensWithTimeRecordedTest(TeleportFollowerHarness):
    """Item 3, threat tiers plan step 11 (design 4.4, 10a, OQ-1 option A, OQ-10, D2)."""

    def test_the_summoner_that_dies_harmlessly_is_shot_not_retreated_from(self):
        """15760: the クトーニアン (S_DEMON) 6 cells off; the free shots kill it in 5 turns and the
        projection of every visible hostile over them is 0 (no path: it digs, no line of fire),
        within 10% of HP 1092.  Live: summoner:retreat."""
        policy, answers = self.recorded_answers()
        raw, key, reason, snapshot = answers[RETREAT_OPEN]
        self.assertEqual(self.recorded[RETREAT_OPEN]["reason"], "summoner:retreat")
        chthonian = next(m for m in snapshot.visible_monsters if m.race_id == CHTHONIAN)
        self.assertEqual(threat_tiers.worsens_kinds(policy, chthonian), ("summon",))
        self.assertTrue(worsens_kill.harmless(policy, snapshot, chthonian))
        # The fire command aimed at it (the attack keeps its own reason).
        self.assertTrue(key.startswith("f") and reason.startswith("ranged:fire"), (key, reason))

    def test_a_summoner_that_would_cost_damage_takes_the_cover_step_first(self):
        """15761: 3 cells off the projection over the 5 kill turns (205) passes 10% of HP 1092,
        so it is not killed 被害無く and is decided 「離れる」 (owner 2026-11-09 Q1, 「倒しきれない敵と
        同じに離れる」).  But the player stands in open ground with a cover step: owner 2026-11-09
        「前からの2つを先に」 (「遮蔽に隠れる・通路で待つが使える場面ではそれを使い、使えない時だけ
        離れる」): the 11-06 cover step answers, as live did (summoner:retreat)."""
        policy, answers = self.replay(until=RETREAT_NEAR)  # the memory as of that board
        _raw, key, reason, snapshot = answers[RETREAT_NEAR]
        chthonian = next(m for m in snapshot.visible_monsters if m.race_id == CHTHONIAN)
        self.assertFalse(worsens_kill.harmless(policy, snapshot, chthonian))
        self.assertTrue(threat_tiers.worsens_left(policy, snapshot, [chthonian]))
        self.assertTrue(policy._summoner_shelter_applies(snapshot, [chthonian]))
        self.assertIsNot(threat_tiers.leave_due(policy, snapshot, [chthonian]), True)
        self.assertEqual((key, reason), (self.recorded[RETREAT_NEAR]["key"], "summoner:retreat"))

    def test_beside_the_player_no_shelter_answers_and_it_is_left(self):
        """15762: the クトーニアン beside the player: no cover step (adjacent) and no choke wait
        (within 2 cells); the decided 「離れる」 is the flee rung's Teleportation (it is faster:
        no walk).  Live: melee."""
        policy, answers = self.replay(until=HELD)
        raw, key, reason, snapshot = answers[HELD]
        chthonian = next(m for m in snapshot.visible_monsters if m.race_id == CHTHONIAN)
        self.assertEqual(self.recorded[HELD]["reason"], "melee")
        self.assertFalse(policy._summoner_shelter_applies(snapshot, [chthonian]))
        self.assertIs(threat_tiers.leave_due(policy, snapshot, [chthonian]), True)
        self.assertEqual((key, reason), ("r" + letter(raw, TVAL_SCROLL, SV_SCROLL_TELEPORT),
                                         "flee:scroll"))

    def test_once_left_it_stays_left_when_it_would_die_harmlessly(self):
        """CONSTRUCTED: on 15762 the クトーニアン's health reads almost dead, so it would now die
        被害無く.  Decided 「離れる」 on 15761, the side is held (「一度離れると決めたら境に余裕を
        持って保つ」): the leave goes on, no kill.  Control: with it not shown on 15760-15761 (no
        side decided), the same board kills it."""
        def weak(raw):
            if raw["turn"] == HELD:
                for monster in raw["visible_monsters"]:
                    if monster["race_id"] == CHTHONIAN:
                        monster["health"] = "almost_dead"
        policy, answers = self.replay(until=HELD, change=weak)
        raw, key, reason, snapshot = answers[HELD]
        chthonian = next(m for m in snapshot.visible_monsters if m.race_id == CHTHONIAN)
        self.assertTrue(worsens_kill.harmless(policy, snapshot, chthonian))
        self.assertTrue(threat_tiers.worsens_left(policy, snapshot, [chthonian]))
        self.assertEqual(reason, "flee:scroll")

        def unseen_then_weak(raw):
            weak(raw)
            if RETREAT_OPEN <= raw["turn"] < HELD:
                raw["visible_monsters"] = [m for m in raw["visible_monsters"]
                                           if m["race_id"] != CHTHONIAN]
        policy, answers = self.replay(until=HELD, change=unseen_then_weak)
        _raw, key, reason, snapshot = answers[HELD]
        chthonian = next(m for m in snapshot.visible_monsters if m.race_id == CHTHONIAN)
        self.assertFalse(threat_tiers.worsens_left(policy, snapshot, [chthonian]))
        self.assertEqual((key, reason), (policy._direction_key(snapshot.player.position,
                                                               chthonian.position), "melee"))

    def test_below_the_low_hp_line_the_rung_does_not_act(self):
        """CONSTRUCTED: HP 300 on 15760 (OQ-10: below the low-HP line the 11-06 escape wins)."""
        policy, answers = self.replay(until=RETREAT_OPEN, change=low_hp)
        _raw, _key, reason, snapshot = answers[RETREAT_OPEN]
        self.assertLess(snapshot.player.hp, policy._low_hp_walk_threshold(snapshot.player.max_hp))
        self.assertFalse(worsens_kill.kill_first(policy, snapshot, snapshot.visible_monsters))
        # The 11-06 low-HP summoner escape (teleport or recall, not a step) answers instead.
        self.assertEqual(reason, "emergency:teleport")


if __name__ == "__main__":
    unittest.main()
