"""n1-c life-201's death (2026-11-12 16:56, 鉄獄30階) and the owner's answer of 2026-11-12.

Analysis: C:/hengband-backups/pdca/captures/n1c-201-death-1112.  Boards:
tests/fixtures/teleport-follower-pack-n1c-201-1112.json.xz
(tests/extract_teleport_follower_pack_1112_fixture.py), one board per live decision row (decisions
24233-24286, the last visit); every decision here is the public ``choose_key`` of one fresh policy
replaying the recorded boards in order (``confirm_key_posted`` after each key, as the driver does).

Magic-Eater Lv31, max HP 369.  At 24280 the emergency ladder read Teleportation (no follower
beside the player then) and landed among 13 ウィル・オー・ウィスプ (race 582: Lv37, speed +20,
INVISIBLE, PASS_WALL, TPORT, no RES_TELE).  From 24281 to 24286 2-4 of them stood beside the
player and the rest 1-6 cells off; the 11-09 order (「*破壊*>テレポートアウェイ>戦闘」) cast the
absorbed Teleport Other at one a turn while the HP fell 259 -> 55, dead with 13 Teleportation
scrolls.  spells-teleport.cpp:392-411 ``teleport_player`` brings each adjacent awake TPORT
monster without RESIST_TELEPORT along through ``teleport_monster_to`` (:192-201) with the race
level as the power: ``randint1(100) > power`` leaves it behind, so a Lv37 wisp follows 37 times
in 100.

Owner 2026-11-12, verbatim: 「*破壊*前にテレポート追尾の群れに踏み込むのはレアケース。対応を個別に
決めるのであれば、テレポート追尾が3体以上で致死的なときは破壊の次にテレポートを優先して試す。
テレポートすることによって数が減ることが見込めるためである。」  With 2 or fewer the 11-09 order stands;
the heal rule on landing stays as it is (heal first only when it out-heals the next action).

DECLARED RESTORED (pin_vacuity): the absorbed powers the live policy held, from the death's
policy-state.json (``_me_staff_sequence.absorbed``; no power list is on the boards), and the skill
knowledge before each decision (as tests/test_teleport_follower_1109_recorded.py does).

DECLARED CONSTRUCTED (each named at its test): wisps taken off the board (the control with 2);
the Teleportation scrolls taken out with an absorbed Staff of Teleportation added, and with none;
a carried Staff of *Destruction* with the device skill raised.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot import me_absorbed_substitutes, me_staff_sequence, teleport_follower
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.model import (
    SV_SCROLL_TELEPORT, SV_STAFF_DESTRUCTION, SV_STAFF_TELEPORTATION, TVAL_SCROLL, TVAL_STAFF,
    parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.threat_escape import SV_SCROLL_TELEPORT_LEVEL
from tests.support.recorded import EDIT, skill

FIXTURE = Path(__file__).with_name("fixtures") / "teleport-follower-pack-n1c-201-1112.json.xz"
WISP = 582
# The death's policy-state.json, _me_staff_sequence.absorbed (wand:3 is Teleport Other).
ABSORBED = {"staff:10": 30, "staff:12": 16, "staff:13": 15, "staff:15": 14, "staff:22": 8,
            "staff:29": 5, "staff:5": 26, "staff:8": 33, "staff:9": 11, "wand:3": 12, "wand:6": 12}
THREAT = 1936856         # decision 24277: resist-potion:quaff
LANDING_READ = 1936878    # decision 24280: emergency:teleport, landed among the wisps
PACK = (1936884, 1936890, 1936893, 1936898, 1936902, 1936907)   # decisions 24281-24286
FIRST = PACK[0]
LAST = PACK[-1]
AWAY_CAST = teleport_follower.AWAY_REASON + me_absorbed_substitutes.CAST_SUFFIX


def relabel(raw):
    for index, item in enumerate(raw["inventory"]):
        item["slot"] = chr(ord("a") + index)


def letter(raw, tval, sval):
    return next(item["slot"] for item in raw["inventory"]
                if item["tval"] == tval and item["sval"] == sval)


def only_wisps(indices, turn):
    """DECLARED CONSTRUCTED: on board ``turn`` the wisps other than ``indices`` (and their map
    marks) are gone."""
    def change(raw):
        if raw["turn"] != turn:
            return
        gone = {m["index"] for m in raw["visible_monsters"]
                if m["race_id"] == WISP and m["index"] not in indices}
        raw["visible_monsters"] = [m for m in raw["visible_monsters"] if m["index"] not in gone]
        for cell in raw["grid_map"]["cells"]:
            if cell.get("m") in gone:
                del cell["m"]
    return change


def without_teleport_scrolls(raw):
    """DECLARED CONSTRUCTED: no Teleportation or Teleport Level scroll in the pack (letters
    re-given); Phase Door stays."""
    raw["inventory"] = [item for item in raw["inventory"]
                        if not (item["tval"] == TVAL_SCROLL
                                and item["sval"] in (SV_SCROLL_TELEPORT, SV_SCROLL_TELEPORT_LEVEL))]
    relabel(raw)


def without_teleportation(raw):
    """DECLARED CONSTRUCTED: no Teleportation scroll; the Teleport Level scroll stays."""
    raw["inventory"] = [item for item in raw["inventory"]
                        if not (item["tval"] == TVAL_SCROLL and item["sval"] == SV_SCROLL_TELEPORT)]
    relabel(raw)


def destruction_staff(raw):
    """DECLARED CONSTRUCTED: a carried Staff of *Destruction* first, the device skill 130."""
    scroll = next(item for item in raw["inventory"] if item["tval"] == TVAL_SCROLL)
    staff = dict(copy.deepcopy(scroll), tval=TVAL_STAFF, sval=SV_STAFF_DESTRUCTION, count=1,
                 charges=5, pval=5, name="*破壊*の杖 (5回分)", weight=50)
    raw["inventory"].insert(raw["inventory"].index(scroll), staff)
    relabel(raw)
    raw["player"]["skill_ratings"]["magic_device"]["value"] = 130


class PackHarness(unittest.TestCase):
    answers = None

    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.payload["decisions"]}

    def replay(self, until=LAST, change=None, absorbed=None):
        """Every recorded board up to game turn ``until`` (``change`` applied to each), one fresh
        policy; {turn: (raw, key, reason, snapshot, policy)}."""
        boards = self.payload["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        me_staff_sequence.state(policy).absorbed = dict(absorbed or ABSORBED)
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
            answers[raw["turn"]] = (raw, str(key), policy.last_reason, snapshot, policy)
        return answers

    def recorded_answers(self):
        if type(self).answers is None:
            type(self).answers = self.replay()
        return type(self).answers


class PackRecordedTest(PackHarness):
    """The recorded boards 24281-24286: the Teleportation read, not one Teleport Other a turn."""

    def test_the_replay_matches_the_live_decisions_up_to_the_landing(self):
        """From the Resistance potion (24277) to the landing read (24280) the replay decides as
        live did.  Earlier boards differ: a fresh policy has no rod list, no memory of the
        floor's new-floor powers (me_power_floor), so it casts them and shoots by other means."""
        answers = self.recorded_answers()
        for turn, (_raw, key, reason, _snapshot, _policy) in answers.items():
            if THREAT <= turn <= LANDING_READ:
                self.assertEqual((key, reason),
                                 (self.recorded[turn]["key"], self.recorded[turn]["reason"]), turn)
        self.assertEqual(self.recorded[LANDING_READ]["reason"], "emergency:teleport")

    def test_every_pack_board_reads_teleportation(self):
        answers = self.recorded_answers()
        self.assertEqual({self.recorded[turn]["reason"] for turn in PACK}, {AWAY_CAST})
        for turn in PACK:
            raw, key, reason, snapshot, policy = answers[turn]
            followers = teleport_follower.followers(policy, snapshot)
            pack = teleport_follower.pack(policy, snapshot)
            # 2-4 adjacent; the engaged pack (adjacent, or beside the player before its next
            # action) is 3 or more on every board.
            self.assertTrue(2 <= len(followers) <= 4, (turn, len(followers)))
            self.assertGreaterEqual(len(pack), teleport_follower.PACK_MIN, turn)
            self.assertEqual({monster.race_id for monster in pack}, {WISP}, turn)
            self.assertTrue(self.recorded[turn]["instant_death"], turn)
            self.assertFalse(snapshot.player.blind or snapshot.player.confused, turn)
            self.assertEqual((key, reason),
                             ("r" + letter(raw, TVAL_SCROLL, SV_SCROLL_TELEPORT),
                              teleport_follower.PACK_REASON), turn)


class PackConstructedTest(PackHarness):
    """DECLARED CONSTRUCTED variants: the ≤2 control and the order around the teleport."""

    def test_two_followers_keep_the_11_09_order(self):
        """CONSTRUCTED: on 24281 only the 2 adjacent wisps 35 and 57 remain (70 and every other
        wisp taken off): Teleport Other at one of them, as live (11-09)."""
        answers = self.replay(until=FIRST, change=only_wisps({35, 57}, FIRST))
        _raw, key, reason, snapshot, policy = answers[FIRST]
        self.assertEqual(len(teleport_follower.followers(policy, snapshot)), 2)
        self.assertEqual(len(teleport_follower.pack(policy, snapshot)), 2)
        self.assertEqual(reason, AWAY_CAST)
        self.assertTrue(key.startswith("mBd"), key)

    def test_three_adjacent_followers_alone_are_a_pack(self):
        """CONSTRUCTED: on 24281 only the 3 adjacent wisps remain: the teleport."""
        answers = self.replay(until=FIRST, change=only_wisps({35, 57, 70}, FIRST))
        raw, key, reason, snapshot, policy = answers[FIRST]
        self.assertEqual(len(teleport_follower.pack(policy, snapshot)), 3)
        self.assertEqual((key, reason), ("r" + letter(raw, TVAL_SCROLL, SV_SCROLL_TELEPORT),
                                         teleport_follower.PACK_REASON))

    def test_destruction_comes_before_the_teleport(self):
        """CONSTRUCTED: a reliable Staff of *Destruction* on 24285 (鉄獄30階 is no fixed quest).
        24285 is a board whose scene admits the use (destruction_use._scene_holds): on 24281-24284
        a hit from an unseen wisp refuses it (``_awake_in_view``), and the teleport answers."""
        turn = PACK[4]

        def change(raw):
            if raw["turn"] == turn:
                destruction_staff(raw)
        answers = self.replay(until=turn, change=change)
        raw, key, reason, snapshot, policy = answers[turn]
        self.assertGreaterEqual(len(teleport_follower.pack(policy, snapshot)),
                                teleport_follower.PACK_MIN)
        self.assertEqual((key, reason), ("u" + letter(raw, TVAL_STAFF, SV_STAFF_DESTRUCTION),
                                         "emergency:destruction"))

    def test_without_teleportation_the_teleport_level_scroll_is_read(self):
        """CONSTRUCTED: no Teleportation scroll from 24281: the ladder's other teleport scroll,
        Teleport Level (``teleport_level`` leaves the floor; nothing follows it)."""
        def change(raw):
            if raw["turn"] >= FIRST:
                without_teleportation(raw)
        answers = self.replay(until=FIRST, change=change)
        raw, key, reason, _snapshot, _policy = answers[FIRST]
        self.assertEqual((key, reason), ("r" + letter(raw, TVAL_SCROLL, SV_SCROLL_TELEPORT_LEVEL),
                                         teleport_follower.PACK_REASON))

    def test_without_the_scroll_the_absorbed_teleportation_is_cast(self):
        """CONSTRUCTED: no teleport scroll, an absorbed Staff of Teleportation (from 24281)."""
        def change(raw):
            if raw["turn"] >= FIRST:
                without_teleport_scrolls(raw)
        absorbed = dict(ABSORBED, **{f"staff:{SV_STAFF_TELEPORTATION}": 10})
        answers = self.replay(until=FIRST, change=change, absorbed=absorbed)
        _raw, key, reason, _snapshot, _policy = answers[FIRST]
        power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        self.assertEqual((key, reason), (power.key, teleport_follower.PACK_REASON
                                         + me_absorbed_substitutes.CAST_SUFFIX))

    def test_without_any_teleport_teleport_other_answers(self):
        """CONSTRUCTED: no teleport scroll and no teleport device: the 11-09 order."""
        def change(raw):
            if raw["turn"] >= FIRST:
                without_teleport_scrolls(raw)
        answers = self.replay(until=FIRST, change=change)
        _raw, _key, reason, snapshot, policy = answers[FIRST]
        self.assertIsNone(teleport_follower.pack_teleport_means(policy, snapshot))
        self.assertEqual(reason, AWAY_CAST)


if __name__ == "__main__":
    unittest.main()
