"""The three n1-b deaths of 2026-11-08/09 and the owner's answers A-E of 2026-11-09.

Analysis: C:/hengband-backups/pdca/captures/deaths-1109/REPORT.txt.  Boards:
tests/fixtures/deaths-1109.json.xz (tests/extract_deaths_1109_fixture.py), one board per live
decision row; every decision here is the public ``choose_key`` of one fresh policy replaying the
recorded boards in order (``confirm_key_posted`` after each key, as the driver does).

- life-355 (Magic-Eater Lv38, Angband 80F, 2026-11-09 04:29): on arrival 13 Chiron locusts read
  即死 (p95 1404 >= HP 587) and the Teleportation scroll was read (dive emergency 1); on the
  landing an awake T1 inside its sensing radius was left with a second scroll (sensed-t1:teleport,
  uncounted), exploring went on, a third leave and a fourth read later landed it among the locusts.
- life-350 (Magic-Eater Lv19, Labyrinth 15F, 2026-11-08 20:45): three flee:scroll reads from the
  same orc pack (uncounted); then, T1, the summoner's three shots; then the Umber hulk's gaze
  confused it and Cure Critical Wounds went on the confusion three times, each re-confused at once.
- life-346 (Magic-Eater Lv30, Angband 19F, 2026-11-08 12:06): a クトーニアン (HOLD, BRAIN_SMASH)
  was sent away by the absorbed Teleport Away (T1), the floor went on, and it died paralysed.

Owner 2026-11-09:
 A 「全部の逃げを数える」: 「テレポート・フェイズ・階段など、敵から離れるために使った逃げは理由を
   問わず数え、2回で帰還する（歩いての後退は数えない）。」
 B 「即死はテレポートで逃げる。射線が通っていないなど即死ではない場合は破壊による排除を優先する。」
 C 「T1では撃たず離れる」
 D 「加速できていなければ加速を先に使う。HPが減っている時は体力回復を優先。」
 E 「麻痺敵に数え飛ばした階は帰還」: 「麻痺知らずが無い時、HOLD・脳攻撃を持つ敵も麻痺させる敵に
   数え、視線が通れば 09-18 の決まりで離れる。テレポート・アウェイで飛ばした T1 の敵がいる階は、
   クエストの外なら帰還する。」

DECLARED RECONSTRUCTION / RESTORED (pin_vacuity): the captures hold no ~f reply, so the skill
knowledge is supplied before each decision (as tests/test_dungeon_1031_recorded.py does); the
absorbed device lists the game last displayed (the town-arrival checkpoint's ``_me_device_lists``)
are shown to ``observe_lists`` before the first board, as the executor's menu reading would (the
live policy held them; the capture has no menu board); a fresh policy starts with no dive count
(life-355: 0 in town, as live; life-350: 0, the live count was 1).

DECLARED CONSTRUCTED (each named at its test): A's life-355 case shows the staff list without the
absorbed *Destruction* (so B's use does not take the recorded teleport's place) and walls the depth
gate off (``_missing_required_abilities``: the recorded depth_safety had nothing missing; without
*Destruction* listed, 80F would otherwise read a gap and return for that reason); C's T2/T3 case
raises the HP; D's Speed cases put a Potion of Speed in the pack; E's line-of-sight cases move the
クトーニアン on its first board; E's sent-away case grants Free Action and gives the next board the
beam's 「…が消え去った！」 in place of the recorded kill message.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import json
import lzma
from pathlib import Path
import unittest
from unittest import mock

from hengbot import destruction_use, fear_cover, sent_away_t1, status_cure, threat_tiers
from hengbot.cli import _PolicyObserverScope
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.me_device_attacks import observe_lists
from hengbot.model import (
    SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, SV_POTION_RESISTANCE, SV_POTION_SPEED,
    SV_SCROLL_TELEPORT, TVAL_POTION,
    TVAL_SCROLL, parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from tests.support.recorded import EDIT

FIXTURE = Path(__file__).with_name("fixtures") / "deaths-1109.json.xz"
RECALL = (70, 11)   # (tval, sval) of Word of Recall
TELEPORT = (TVAL_SCROLL, SV_SCROLL_TELEPORT)
DESTRUCTION_NAME = "*破壊*"
DESTRUCTION_REASON = "emergency:destruction:absorbed-power"
CHTHONIAN = 619


def skill(policy, raw):
    policy.consume_skill_knowledge({
        "player": {"level": raw["player"]["level"]},
        "knowledge": {"skills": [{"id": 1, "exp": 0}, {"id": 3, "exp": 0}]},
    })


def letter(raw, tval, sval):
    return next(item["slot"] for item in raw["inventory"]
                if item["tval"] == tval and item["sval"] == sval)


def from_turn(turn, *changes):
    """Apply ``changes`` to the boards from game turn ``turn`` on."""
    def change(raw):
        if raw["turn"] >= turn:
            for each in changes:
                each(raw)
    return change


def both(*changes):
    def change(raw):
        for each in changes:
            each(raw)
    return change


def at_turn(turn, *changes):
    def change(raw):
        if raw["turn"] == turn:
            for each in changes:
                each(raw)
    return change


def speed_potion(raw):
    """DECLARED CONSTRUCTED: two Potions of Speed after the carried potions, letters re-given."""
    inventory = raw["inventory"]
    at = max(index for index, item in enumerate(inventory) if item["tval"] == TVAL_POTION) + 1
    inventory.insert(at, {
        "ac": 0, "aware": True, "charges": 0, "charging": False, "count": 2,
        "damage_dice": {"num": 1, "sides": 1}, "fully_known": True, "inscription": "",
        "is_artifact": False, "is_bounty": False, "is_broken": False, "is_cursed": False,
        "is_ego": False, "is_equipment": False, "known": True, "known_flags": [],
        "name": "スピードの薬", "pval": 0, "slot": "?", "sval": SV_POTION_SPEED, "to_a": 0,
        "to_d": 0, "to_h": 0, "tval": TVAL_POTION, "weight": 4})
    for index, item in enumerate(inventory):
        item["slot"] = chr(ord("a") + index)


def free_action(raw):
    """DECLARED CONSTRUCTED: Free Action from the equipment."""
    raw["player"]["ability_sources"]["free_action"] = {
        "equipment": True, "permanent": False, "temporary": False}


def fear_resistance(raw):
    """DECLARED CONSTRUCTED: rFear from the equipment."""
    raw["player"]["ability_sources"]["resist_fear"] = {
        "equipment": True, "permanent": False, "temporary": False}


def hidden_supplies(raw):
    """DECLARED CONSTRUCTED: the Potions of Resistance and of Healing out of the pack, letters
    re-given."""
    inventory = raw["inventory"]
    inventory[:] = [item for item in inventory if not (
        item["tval"] == TVAL_POTION and item["sval"] in (SV_POTION_RESISTANCE, SV_POTION_HEALING))]
    for index, item in enumerate(inventory):
        item["slot"] = chr(ord("a") + index)


def at_depth(level):
    """DECLARED CONSTRUCTED: the floor's depth."""
    def change(raw):
        raw["floor"]["level"] = level
    return change


def move_monster(race_id, y, x):
    """DECLARED CONSTRUCTED: the monster and its map mark at (y, x)."""
    def change(raw):
        monster = next(m for m in raw["visible_monsters"] if m["race_id"] == race_id)
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


class DeathsRecordedHarness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(lzma.decompress(FIXTURE.read_bytes()).decode("utf-8"))
        cls.races = load_monrace_knowledge(EDIT / "MonraceDefinitions.jsonc")
        cls.dungeons = load_dungeon_knowledge(EDIT / "DungeonDefinitions.jsonc")

    def recorded(self, life):
        return {row["turn"]: row for row in self.payload[life]["decisions"]}

    def board(self, life, turn):
        return copy.deepcopy(next(raw for raw in self.payload[life]["boards"] if raw["turn"] == turn))

    def snapshot(self, policy, raw):
        skill(policy, raw)
        return parse_snapshot(copy.deepcopy(raw), self.races)

    def decide(self, policy, raw):
        key = policy.choose_key(self.snapshot(policy, raw))
        if key:
            policy.confirm_key_posted(key)
        return str(key), policy.last_reason

    def replay(self, life, until, change=None, *, without=()):
        """Every recorded board of ``life`` up to game turn ``until`` (``change`` applied to
        each), one fresh policy; {turn: (board, key, reason)}.  ``without``: power names left
        out of the displayed lists."""
        boards = self.payload[life]["boards"]
        policy = HengbotPolicy(monrace_knowledge=dict(self.races),
                               dungeon_knowledge=dict(self.dungeons))
        policy.prime(parse_snapshot(copy.deepcopy(boards[0]), self.races))
        # RESTORED: the displayed lists, oldest first (observe_lists starts over on a turn
        # going backwards).
        for kind, (turn, rows) in sorted(self.payload[life]["lists"].items(),
                                         key=lambda entry: entry[1][0]):
            rows = [row for row in rows if row["name"] not in without]
            shown = dict(copy.deepcopy(boards[0]), turn=turn,
                         _magic_eater_power_list={"kind": kind, "rows": rows})
            observe_lists(policy, parse_snapshot(shown, self.races))
        answers = {}
        for raw in boards:
            if raw["turn"] > until:
                break
            raw = copy.deepcopy(raw)
            if change is not None:
                change(raw)
            answers[raw["turn"]] = (raw, *self.decide(policy, raw))
        return policy, answers


class EveryEscapeCountsRecordedTest(DeathsRecordedHarness):
    """A: a relocating escape from enemies counts; the second of a dive returns to town."""

    def test_life355_the_sensed_t1_teleport_is_the_second_escape_and_returns(self):
        recorded = self.recorded("life-355")
        self.assertEqual((recorded[4229931]["reason"], recorded[4229931]["instant_death"]),
                         ("emergency:teleport", True))
        self.assertEqual(recorded[4229938]["reason"], "sensed-t1:teleport")
        self.assertEqual([recorded[turn]["reason"] for turn in (4229941, 4229948)],
                         ["me-power:after-destruction:map-area", "explore"])
        # DECLARED CONSTRUCTED: no absorbed *Destruction* (B would use it on 4229938) and the
        # depth gate walled off (the recorded depth_safety: nothing missing).
        # DECLARED CONSTRUCTED too: the T1s left on 4229938 read as in the line of fire.  As
        # recorded none has one (test_escape_count_1111_recorded), and owner 2026-11-13
        # 「射線にT1が入っていない=感知しただけはカウントしない」 counts it only then.
        def in_line_of_fire(policy, snapshot, strong):
            setattr(policy, threat_tiers.IN_LINE_OF_FIRE, True)
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()),                 mock.patch.object(threat_tiers, "note_line_of_fire", in_line_of_fire):
            policy, answers = self.replay("life-355", 4229948, without=(DESTRUCTION_NAME,))
        self.assertEqual(answers[4229931][2], "emergency:teleport")
        self.assertEqual(answers[4229938][2], "sensed-t1:teleport")
        # The second relocation of the 80F dive: the landing's emergency ladder takes the Speed
        # dose the return owes (the escape speed rule), then Word of Recall is read.
        self.assertTrue(answers[4229941][2].startswith("emergency:quaff-speed"), answers[4229941])
        raw, key, reason = answers[4229948]
        self.assertEqual(reason, "return:recall")
        self.assertEqual(key, "r" + letter(raw, *RECALL))
        self.assertEqual(policy._last_return_trigger, "emergency-repeat")

    def test_life350_the_second_flee_scroll_returns_and_a_walk_does_not_count(self):
        recorded = self.recorded("life-350")
        self.assertEqual([recorded[turn]["reason"] for turn in (969853, 969939, 969947, 969961)],
                         ["flee:scroll", "flee", "flee:scroll", "flee:scroll"])
        self.assertEqual(recorded[969971]["reason"], "refill-light")
        policy, answers = self.replay("life-350", 969971)
        self.assertEqual(answers[969853][2], "flee:scroll")
        # The walking flee of 969939 is no escape: the board after it starts no return.
        self.assertEqual(answers[969939][2], "flee")
        self.assertEqual(answers[969947][2], "flee:scroll")
        raw, key, reason = answers[969971]
        self.assertEqual(reason, "return:recall")
        self.assertEqual(key, "r" + letter(raw, *RECALL))

    def test_life350_one_flee_scroll_and_a_walk_do_not_return(self):
        policy, answers = self.replay("life-350", 969947)
        self.assertEqual(answers[969853][2], "flee:scroll")
        self.assertEqual(answers[969939][2], "flee")
        self.assertFalse(policy._returning_to_town)


class TeleportOrDestructionRecordedTest(DeathsRecordedHarness):
    """B: 即死 reads Teleportation; off the 即死 board *Destruction* removes the threat it
    could not see awake (``destruction_use.leave_key``)."""

    def test_the_instant_death_board_reads_teleportation_with_destruction_at_hand(self):
        policy, answers = self.replay("life-355", 4229927)
        raw = self.board("life-355", 4229931)
        snapshot = self.snapshot(policy, raw)
        # *Destruction* would serve this board (13 awake locusts in view inside the radius) ...
        self.assertTrue(destruction_use.usable(policy, snapshot))
        key, reason = self.decide(policy, raw)
        # ... but 即死 (p95 1404 >= HP 587) reads the scroll (owner 2026-11-08 scroll_first).
        self.assertEqual(reason, "emergency:teleport")
        self.assertEqual(key, "r" + letter(raw, *TELEPORT))

    def test_the_sensed_t1_leave_destroys_what_it_does_not_see_awake(self):
        recorded = self.recorded("life-355")
        self.assertEqual((recorded[4229938]["reason"], recorded[4229938]["instant_death"]),
                         ("sensed-t1:teleport", False))
        policy, answers = self.replay("life-355", 4229938)
        raw = answers[4229938][0]
        # Every awake monster of the board is detected only.
        self.assertFalse([m for m in raw["visible_monsters"] if not m["asleep"]])
        self.assertTrue([m for m in raw["detected_monsters"] if not m["asleep"]])
        self.assertEqual(answers[4229938][2], DESTRUCTION_REASON)

    def test_the_ladder_off_the_instant_death_board_destroys_the_sleeping_t1(self):
        recorded = self.recorded("life-355")
        self.assertEqual((recorded[4230087]["reason"], recorded[4230087]["tier"],
                          recorded[4230087]["instant_death"]), ("emergency:teleport", "T1", False))
        # DECLARED CONSTRUCTED: the pack's Resistance and Healing hidden on the board before
        # (4230081) only.  Since the supply plan's healing credit and the resisted reserve (owner
        # 2026-11-11 「回復と悲観側のずれを全部」), the awake race 741 there reads T2 with the
        # recorded pack (``test_the_board_before_reads_the_awake_one_t2_with_the_pack``), so the
        # sensed T1 leave this pin's board follows is not taken; hiding the supplies on that board
        # alone keeps it T1 as recorded.
        policy, answers = self.replay("life-355", 4230087, at_turn(4230081, hidden_supplies))
        self.assertEqual(answers[4230081][2], "sensed-t1:teleport")
        raw = answers[4230087][0]
        self.assertTrue(all(m["asleep"] for m in raw["visible_monsters"]))
        self.assertEqual(answers[4230087][2], DESTRUCTION_REASON)


    def test_the_board_before_reads_the_awake_one_t2_with_the_pack(self):
        """Owner 2026-11-11 (the supply plan's healing credit and resisted reserve): race 741
        alone, judged from contact as the sensed T1 leave judges it, is T2 with the recorded
        pack and T1 without its Resistance and Healing; the recorded pack's board is not left."""
        policy, _answers = self.replay("life-355", 4230073)
        for change, tier in ((None, threat_tiers.T2), (hidden_supplies, threat_tiers.T1)):
            raw = self.board("life-355", 4230081)
            if change is not None:
                change(raw)
            snapshot = self.snapshot(policy, raw)
            monster = next(m for m in (*snapshot.visible_monsters, *snapshot.detected_monsters)
                           if m.race_id == 741)
            with _PolicyObserverScope(policy):
                result = threat_tiers.assess(policy, snapshot, [monster], contact=True)
            self.assertEqual(result.tier, tier)
        policy, answers = self.replay("life-355", 4230081)
        self.assertNotEqual(answers[4230081][2], "sensed-t1:teleport")


class T1LeavesTheSummonerRecordedTest(DeathsRecordedHarness):
    """C: outside quests a T1 engagement leaves before the summoner's three shots."""

    def test_the_t1_engagement_leaves_instead_of_shooting(self):
        recorded = self.recorded("life-350")
        self.assertEqual((recorded[970232]["reason"], recorded[970232]["tier"]),
                         ("summoner:ranged-kill", "T1"))
        policy, answers = self.replay("life-350", 970232)
        raw, key, reason = answers[970232]
        self.assertEqual(reason, "flee:scroll")
        self.assertEqual(key, "r" + letter(raw, *TELEPORT))

    def test_a_sturdier_player_still_shoots(self):
        def sturdier(raw):
            raw["player"]["hp"] = raw["player"]["max_hp"] = 2000
        # DECLARED CONSTRUCTED: the HP of the last boards raised, so the engagement is no T1.
        policy, answers = self.replay("life-350", 970232, from_turn(970187, sturdier))
        self.assertEqual(answers[970232][2], "summoner:ranged-kill")


class ConfusedAgainRecordedTest(DeathsRecordedHarness):
    """D: confused again right after a cure on the 即死 board: Speed first, Healing when HP is
    down (a loss of at least 1/3 of max HP, status_cure._heavy_loss)."""

    def test_the_recorded_relapse_cures_with_healing_once_hp_is_down(self):
        recorded = self.recorded("life-350")
        self.assertEqual([(recorded[turn]["reason"], recorded[turn]["key"])
                          for turn in (970252, 970258, 970272)],
                         [("emergency:cure-critical", "qb")] * 3)
        policy, answers = self.replay("life-350", 970272)
        # The first confusion: the cheap cure.
        self.assertEqual(answers[970252][1:], ("qb", "emergency:cure-critical"))
        # Confused again right after it, HP 168/243 (a loss below 1/3): no Speed carried, the
        # cheap cure again.
        raw = answers[970258][0]
        self.assertIn("やっと混乱がおさまった。", raw["messages"])
        self.assertEqual(answers[970258][1:], ("qb", "emergency:cure-critical"))
        # HP 77/243: Healing, which also ends the confusion.
        raw, key, reason = answers[970272]
        self.assertEqual(reason, "emergency:cure-status-healing")
        self.assertEqual(key, "q" + letter(raw, TVAL_POTION, SV_POTION_HEALING))

    def test_a_carried_speed_potion_is_drunk_first_on_the_relapse(self):
        policy, answers = self.replay("life-350", 970258, from_turn(970252, speed_potion))
        # Not on the first confusion: no relapse yet.
        raw, key, reason = answers[970252]
        self.assertEqual((key, reason),
                         ("q" + letter(raw, TVAL_POTION, SV_POTION_CURE_CRITICAL),
                          "emergency:cure-critical"))
        raw, key, reason = answers[970258]
        self.assertEqual(reason, status_cure.RELAPSE_SPEED_REASON)
        self.assertEqual(key, "q" + letter(raw, TVAL_POTION, SV_POTION_SPEED))


class SpellParalyserRecordedTest(DeathsRecordedHarness):
    """E: a HOLD / BRAIN_SMASH caster is a paralyser; in sight it is left by the 09-18 rung."""

    # Owner 2026-11-11 「恐怖・盲目の呪文を持つ相手で耐性が無い時は T2 にしない」: the クトーニアン
    # casts SCARE and life-346 has no rFear, so alone it reads T1 (T2 before).  Owner 2026-11-12
    # 「巻物の手当てを先にする」: the 09-18 scroll still goes before the absorbed Teleport Away
    # (me_powers ``_status_rung_first``), so the recorded board is left by scroll as before; with
    # rFear (DECLARED CONSTRUCTED, ``fear_resistance`` on every board) it reads T2 and the same
    # scroll answers.

    def test_the_chthonian_beside_the_player_is_left_by_scroll(self):
        recorded = self.recorded("life-346")
        self.assertEqual(recorded[1623935]["reason"], "me-power:unbeatable-in-range:teleport-away")
        policy, answers = self.replay("life-346", 1623935)
        raw, key, reason = answers[1623935]
        self.assertEqual(reason, "status-threat:scroll")
        self.assertEqual(key, "r" + letter(raw, *TELEPORT))

    def test_with_rfear_the_chthonian_is_left_by_scroll_too(self):
        policy, answers = self.replay("life-346", 1623935, fear_resistance)
        raw, key, reason = answers[1623935]
        self.assertEqual(reason, "status-threat:scroll")
        self.assertEqual(key, "r" + letter(raw, *TELEPORT))

    def test_without_rfear_the_fear_casting_chthonian_reads_t1_alone(self):
        policy, answers = self.replay("life-346", 1623935)
        raw, key, reason = answers[1623935]
        snapshot = self.snapshot(policy, raw)
        chthonian = next(m for m in snapshot.visible_monsters if m.race_id == CHTHONIAN)
        with _PolicyObserverScope(policy):
            alone = threat_tiers.assess(policy, snapshot, [chthonian])
        self.assertEqual((alone.tier, alone.t2_withheld),
                         (threat_tiers.T1, (fear_cover.FEAR_WITHHELD,)))

    def test_in_line_of_sight_two_cells_away_it_is_left_too(self):
        # DECLARED CONSTRUCTED: the クトーニアン two cells down the corridor, a clear line, not
        # in melee reach (speed +20 against +16: one action, two cells).
        policy, answers = self.replay("life-346", 1623935,
                                      at_turn(1623935, move_monster(CHTHONIAN, 28, 101)))
        raw, key, reason = answers[1623935]
        self.assertEqual(reason, "status-threat:scroll")
        self.assertEqual(key, "r" + letter(raw, *TELEPORT))

    def test_behind_the_wall_it_is_not(self):
        # DECLARED CONSTRUCTED: the クトーニアン past the corridor's wall, no clear line; the
        # floor at the Free Action depth (20F), where the shallow rule of 2026-11-09 (n1-a
        # life-501 「浅い階層で見かけたら逃げる」) does not apply; rFear as above.
        policy, answers = self.replay("life-346", 1623935, both(
            fear_resistance, at_turn(1623935, move_monster(CHTHONIAN, 24, 104)), at_depth(20)))
        self.assertEqual(answers[1623935][2], "melee")

    def test_behind_the_wall_without_rfear_the_t1_is_left(self):
        # DECLARED CONSTRUCTED: as above without rFear: the クトーニアン alone is T1 (owner
        # 2026-11-11), awake inside its sensing radius, and is left.
        policy, answers = self.replay("life-346", 1623935, both(
            at_turn(1623935, move_monster(CHTHONIAN, 24, 104)), at_depth(20)))
        self.assertEqual(answers[1623935][2], "sensed-t1:stairs")

    def test_behind_the_wall_on_the_recorded_19f_it_is_left_at_sight(self):
        # DECLARED CONSTRUCTED: as above, on the recorded 19F: above the Free Action depth the
        # クトーニアン in view is left at sight by the up stairs the player stands on.
        policy, answers = self.replay("life-346", 1623935,
                                      at_turn(1623935, move_monster(CHTHONIAN, 24, 104)))
        self.assertEqual(answers[1623935][1:], ("<", "shallow-paralyzer:stairs"))

    def test_free_action_keeps_it_no_paralyser(self):
        policy, answers = self.replay("life-346", 1623935, from_turn(1623935, free_action))
        self.assertNotEqual(answers[1623935][2], "status-threat:scroll")


class SentAwayT1RecordedTest(DeathsRecordedHarness):
    """E: a T1 sent away by Teleport Away returns to town outside quests."""

    VANISHED = "天上界ドレイクが消え去った！"

    def test_a_t1_sent_away_returns(self):
        # DECLARED CONSTRUCTED: Free Action (so the クトーニアン of 1623935 is no paralyser and
        # the floor goes on as recorded); the board after the beam prints its vanishing.
        def vanished(raw):
            raw["messages"] = [self.VANISHED]

        def change(raw):
            from_turn(1623935, free_action)(raw)
            at_turn(1623951, vanished)(raw)
        policy, answers = self.replay("life-346", 1623951, change)
        raw, key, reason = answers[1623943]
        self.assertEqual(reason, sent_away_t1.THREAT_REASON)
        target = next(m for m in raw["visible_monsters"] if m["race_id"] == 504)
        self.assertFalse(target["asleep"])
        raw, key, reason = answers[1623951]
        self.assertEqual(policy._last_return_trigger, sent_away_t1.TRIGGER)
        # The town return takes the up staircase underfoot (the board's [26,101]).
        self.assertEqual((key, reason), ("<", "return:ascend"))

    def test_no_vanishing_no_return(self):
        # The recorded board after the beam: the drake was killed in melee, nothing vanished.
        # Owner 2026-11-09 (n1-a life-500 Q1, 「倒しきれない敵と同じに離れる」): with Free Action
        # the クトーニアン (a summoner, no paralyser then) is left on 1623935 too, by the absorbed
        # Teleport Away; DECLARED CONSTRUCTED: its 「…消え去った！」 on 1623943 is taken off, so
        # only the drake's beam is under test here.
        def change(raw):
            from_turn(1623935, free_action)(raw)
            if raw["turn"] == 1623943:
                raw["messages"] = [m for m in raw["messages"] if not m.endswith(sent_away_t1.VANISHED)]
        policy, answers = self.replay("life-346", 1623951, change)
        self.assertEqual(answers[1623943][2], sent_away_t1.THREAT_REASON)
        self.assertNotEqual(policy._last_return_trigger, sent_away_t1.TRIGGER)
        self.assertFalse(answers[1623951][2].startswith("return:"), answers[1623951][1:])


if __name__ == "__main__":
    unittest.main()
