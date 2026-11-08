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

from hengbot import destruction_use, status_cure
from hengbot.dungeon_knowledge import load_dungeon_knowledge
from hengbot.me_device_attacks import observe_lists
from hengbot.model import (
    SV_POTION_CURE_CRITICAL, SV_POTION_HEALING, SV_POTION_SPEED, SV_SCROLL_TELEPORT, TVAL_POTION,
    TVAL_SCROLL, parse_snapshot,
)
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from test_esp_threat_rest_recorded import EDIT

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
        with mock.patch.object(HengbotPolicy, "_missing_required_abilities",
                               lambda self, *args, **kwargs: frozenset()):
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


if __name__ == "__main__":
    unittest.main()
