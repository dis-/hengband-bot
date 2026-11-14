"""n1-a life-522's death (2026-11-14 19:35, 鉄獄49階) and the owner's two answers of 2026-11-14.

Analysis: C:/hengband-backups/pdca/captures/n1a-522-death-1114.  Boards:
tests/fixtures/teleport-follower-n1a-522-1114.json.xz
(tests/extract_teleport_follower_n1a_522_fixture.py): one board per live decision row from the
first shot at the hounds (turn 2916444) to the death (2916691), and the last town visit's board
before Home (2915372) with its Home page (2915708).  The fight's decisions are the public
``choose_key`` of one fresh policy replaying the recorded boards in order (``confirm_key_posted``
after each key, as the driver does).

Zombie warrior Lv40, max HP 1009.  At 2916659 the bot attacked 魔王『マレキス』 (race 628: Lv47,
TPORT, no RES_TELE) from a corner; 迷路の神『アイホート』 and three ショゴス (RES_TELE) arrived with
a crowd, and on the three 即死 boards 2916668 / 2916682 / 2916691 (HP 631, 563, 370) マレキス stood
beside the player: a follower (spells-teleport.cpp:392-411, ``teleport_monster_to`` brings it
along when ``randint1(100) <= 47``), so the 14 Teleportation scrolls were not an escape
(teleport_follower).  With no *Destruction* and no Teleport Other on it, the ladder quaffed Cure
Light Wounds three times and died.  マレキス alone reads a next-action p95 of 205-223.

Owner 2026-11-14, verbatim:
1. 「付いてくる敵だけで死なないなら読む」 -- *Destruction* first; without it, on the 即死 board with
   1-2 adjacent followers whose own p95 is below the HP, the Teleportation scroll is read before
   Teleport Other (teleport_follower.survivable_due / SURVIVABLE_REASON).
2. 「1本持ち歩く」 -- a non-Magic-Eater carries one Teleport Other device (a rod first, else the
   wand with the most charges), taken out of Home when there, never shelved (teleport_away_carry).
   The Home page of 2915708 held the rod and two wands (24 charges).

DECLARED RESTORED: the skill knowledge before each decision (tests/support/recorded.skill), as
the other recorded follower tests do.

DECLARED CONSTRUCTED (each named at its test): the HP lowered below the follower's p95; a
carried Wand of Teleport Other; a carried Staff of *Destruction* with the device skill raised;
the Home catalogue adopted from the recorded Home page (the live catalogue was complete; the
fresh replay of the visit diverges at its first Home deposit, so the binder is asked on the
recorded town board); the rod or the wands taken off that page; a Rod of Teleport Other in the
pack (the recorded pack's Rod of Recall re-labelled); the class changed to the Magic-Eater.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest

from hengbot import teleport_away_carry, teleport_follower
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.instant_death import instant_death
from hengbot.magic_eater_devices import PLAYER_CLASS_MAGIC_EATER
from hengbot.model import (
    SV_ROD_RECALL, SV_ROD_TELEPORT_AWAY, SV_SCROLL_TELEPORT, SV_STAFF_DESTRUCTION,
    SV_WAND_TELEPORT_AWAY, TVAL_ROD, TVAL_SCROLL, TVAL_STAFF, TVAL_WAND, parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import UNUSED_DIVE_LIMIT
from tests.support.recorded import EDIT, skill

FIXTURE = Path(__file__).with_name("fixtures") / "teleport-follower-n1a-522-1114.json.xz"
MALEKITH = 628
CORNERED = 2916659
HEALS = (2916668, 2916682, 2916691)
FIRST = HEALS[0]


def relabel(raw):
    for index, item in enumerate(raw["inventory"]):
        item["slot"] = chr(ord("a") + index)


def letter(raw, tval, sval):
    return next(item["slot"] for item in raw["inventory"]
                if item["tval"] == tval and item["sval"] == sval)


def device_like(raw, tval, sval, name, charges=0):
    """A pack device built on the recorded pack's Rod of Recall (same identification flags)."""
    rod = next(item for item in raw["inventory"]
               if item["tval"] == TVAL_ROD and item["sval"] == SV_ROD_RECALL)
    return dict(copy.deepcopy(rod), tval=tval, sval=sval, count=1, charges=charges, pval=charges,
                name=name, weight=15)


def on(turn, change):
    def apply(raw):
        if raw["turn"] == turn:
            change(raw)
    return apply


def lower_hp(hp):
    """DECLARED CONSTRUCTED: the HP below the follower's own next-action p95."""
    def change(raw):
        raw["player"]["hp"] = hp
    return change


def teleport_other_wand(raw):
    """DECLARED CONSTRUCTED: a carried Wand of Teleport Other (10 charges) at the pack's end."""
    raw["inventory"].append(device_like(raw, TVAL_WAND, SV_WAND_TELEPORT_AWAY,
                                        "テレポート・アウェイの魔法棒 (10回分)", 10))
    relabel(raw)


def destruction_staff(raw):
    """DECLARED CONSTRUCTED: a carried Staff of *Destruction* (5 charges), the device skill 130."""
    raw["inventory"].append(device_like(raw, TVAL_STAFF, SV_STAFF_DESTRUCTION,
                                        "*破壊*の杖 (5回分)", 5))
    relabel(raw)
    raw["player"]["skill_ratings"]["magic_device"]["value"] = 130


class Harness(unittest.TestCase):
    answers = None

    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")
        cls.recorded = {row["turn"]: row for row in cls.payload["decisions"]}

    def fresh(self, raw):
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(raw), self.races))
        return policy

    def replay(self, until=HEALS[-1], change=None):
        """Every recorded fight board up to game turn ``until`` (``change`` applied to each), one
        fresh policy; {turn: (raw, key, reason, snapshot, policy)}."""
        boards = self.payload["boards"]
        policy = self.fresh(boards[0])
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


class SurvivableTeleportRecordedTest(Harness):
    """Answer 1 on the recorded boards."""

    def test_the_replay_matches_the_live_decisions_before_the_follower_board(self):
        answers = self.recorded_answers()
        for turn, (_raw, key, reason, _snapshot, _policy) in answers.items():
            if turn <= CORNERED:
                self.assertEqual((key, reason),
                                 (self.recorded[turn]["key"], self.recorded[turn]["reason"]), turn)
        self.assertEqual({self.recorded[turn]["reason"] for turn in HEALS}, {"emergency:heal"})

    def test_the_first_heal_board_reads_teleportation(self):
        """2916668: マレキス the only follower, its p95 205 below HP 631 on the 即死 board, no
        *Destruction*, no Teleport Other: the Teleportation scroll, not Cure Light Wounds."""
        raw, key, reason, snapshot, policy = self.recorded_answers()[FIRST]
        followers = teleport_follower.followers(policy, snapshot)
        self.assertEqual([monster.race_id for monster in followers], [MALEKITH])
        self.assertTrue(self.recorded[FIRST]["instant_death"])
        self.assertTrue(instant_death(policy, snapshot).next_action)
        self.assertLess(instant_death(policy, snapshot, followers).next_action_p95,
                        snapshot.player.hp)
        self.assertEqual((key, reason), ("r" + letter(raw, TVAL_SCROLL, SV_SCROLL_TELEPORT),
                                         teleport_follower.SURVIVABLE_REASON))

    def test_the_cornered_attack_board_is_unchanged(self):
        """2916659 is no 即死 board (p95 217 against HP 819): the cornered attack stands."""
        _raw, key, reason, _snapshot, _policy = self.recorded_answers()[CORNERED]
        self.assertEqual((key, reason), ("8", "flee:cornered-attack"))


class SurvivableTeleportConstructedTest(Harness):
    """DECLARED CONSTRUCTED variants around the new rung."""

    def test_a_follower_that_can_kill_keeps_the_old_answer(self):
        """CONSTRUCTED: 2916668 at HP 200, below マレキス's own p95: no teleport is read beside it."""
        answers = self.replay(until=FIRST, change=on(FIRST, lower_hp(200)))
        _raw, _key, reason, snapshot, policy = answers[FIRST]
        followers = teleport_follower.followers(policy, snapshot)
        self.assertGreaterEqual(instant_death(policy, snapshot, followers).next_action_p95, 200)
        self.assertFalse(teleport_follower.survivable_due(policy, snapshot))
        self.assertNotEqual(reason, teleport_follower.SURVIVABLE_REASON)
        self.assertFalse((reason or "").startswith("emergency:teleport"), reason)

    def test_teleportation_goes_before_teleport_other(self):
        """CONSTRUCTED: a carried Wand of Teleport Other: the scroll is still read first (owner:
        「付いてくる敵だけで死なないなら読む」, before Teleport Other)."""
        answers = self.replay(until=FIRST, change=on(FIRST, teleport_other_wand))
        raw, key, reason, _snapshot, _policy = answers[FIRST]
        self.assertEqual((key, reason), ("r" + letter(raw, TVAL_SCROLL, SV_SCROLL_TELEPORT),
                                         teleport_follower.SURVIVABLE_REASON))

    def test_destruction_goes_first(self):
        """CONSTRUCTED: a carried Staff of *Destruction*: it is used before the teleport."""
        answers = self.replay(until=FIRST, change=on(FIRST, destruction_staff))
        raw, key, reason, _snapshot, _policy = answers[FIRST]
        self.assertNotEqual(reason, teleport_follower.SURVIVABLE_REASON)
        self.assertEqual(key, "u" + letter(raw, TVAL_STAFF, SV_STAFF_DESTRUCTION))


class TeleportAwayCarryTest(Harness):
    """Answer 2 on the recorded town board and Home page."""

    def town(self, home_change=None, board_change=None):
        town = self.payload["town"]
        board_raw = copy.deepcopy(town["board"])
        if board_change is not None:
            board_change(board_raw)
        home_raw = copy.deepcopy(town["home"])
        if home_change is not None:
            home_change(home_raw)
        board = parse_snapshot(board_raw, self.races)
        policy = self.fresh(board_raw)
        # DECLARED CONSTRUCTED: the recorded Home page adopted as the complete catalogue.
        policy._adopt_home_catalogue(tuple(parse_snapshot(home_raw, self.races).store.items))
        return policy, board

    def test_the_home_rod_is_taken_out(self):
        """The recorded pack holds no Teleport Other device; the Home rod is bound, one."""
        policy, board = self.town()
        self.assertIsNone(teleport_away_carry.carried_device(board))
        self.assertTrue(policy._queue_home_catalogue_shortages(board))
        self.assertEqual(policy._home_pending_item[1:], (TVAL_ROD, SV_ROD_TELEPORT_AWAY))
        self.assertEqual(policy._home_pending_quantities[policy._home_pending_item], 1)

    def test_without_the_rod_the_wands_are_taken_out(self):
        """CONSTRUCTED: the rod taken off the Home page: the wand stack (24 charges) is bound."""
        def no_rod(raw):
            raw["store"]["items"] = [
                item for item in raw["store"]["items"]
                if (item["tval"], item.get("sval")) != (TVAL_ROD, SV_ROD_TELEPORT_AWAY)]
        policy, board = self.town(home_change=no_rod)
        self.assertTrue(policy._queue_home_catalogue_shortages(board))
        self.assertEqual(policy._home_pending_item[1:], (TVAL_WAND, SV_WAND_TELEPORT_AWAY))

    def test_a_carried_rod_takes_nothing_and_is_never_shelved(self):
        """CONSTRUCTED: a Rod of Teleport Other in the pack, unused for UNUSED_DIVE_LIMIT dives
        (the idle-item rule shelved the live rod 2026-11-13): reserved, not a deposit."""
        def rod(raw):
            raw["inventory"].append(device_like(raw, TVAL_ROD, SV_ROD_TELEPORT_AWAY,
                                                "テレポート・アウェイのロッド"))
            relabel(raw)
        policy, board = self.town(board_change=rod)
        carried = teleport_away_carry.carried_device(board)
        self.assertEqual((carried.tval, carried.sval), (TVAL_ROD, SV_ROD_TELEPORT_AWAY))
        home_rod = next(item for item in policy._home_knowledge_items
                        if (item.tval, item.sval) == (TVAL_ROD, SV_ROD_TELEPORT_AWAY))
        self.assertEqual(teleport_away_carry.home_missing(policy, board, home_rod), 0)
        policy._item_idle_dives[policy._item_signature(carried)] = UNUSED_DIVE_LIMIT
        self.assertEqual(policy._retention_reservation_detail(board, carried),
                         (1, teleport_away_carry.RETENTION_BRANCH))
        self.assertFalse(policy._home_deposit_candidate(carried, board))

    def test_the_magic_eater_is_outside_the_rule(self):
        """CONSTRUCTED: the class changed to the Magic-Eater: nothing is taken out for it."""
        def magic_eater(raw):
            raw["player"]["class_id"] = PLAYER_CLASS_MAGIC_EATER
        policy, board = self.town(board_change=magic_eater)
        home_rod = next(item for item in policy._home_knowledge_items
                        if (item.tval, item.sval) == (TVAL_ROD, SV_ROD_TELEPORT_AWAY))
        self.assertEqual(teleport_away_carry.home_missing(policy, board, home_rod), 0)


if __name__ == "__main__":
    unittest.main()
