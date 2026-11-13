"""n1-b life-392 (2026-11-13 19:52, オークの洞窟19階, Lv20): leave the faster confuser first.

Recorded (decision log): at turn 1124309, full HP 252/252, not confused, no resist_conf,
the <スラーネッシュ>の女悪魔 (race 319, speed +10 against the player's +0, two CLAW CONFUSE
blows) stood two cells away and the summoner shot fired (``fl4``, summoner:ranged-kill).  It
confused the player on that and every following board; the 13 Teleportation scrolls were
never readable again and the character died.

Owner 2026-11-14 「混乱する前に離れるだけ」 (option C of that question): without resist_conf and
not yet confused, a faster monster whose blows confuse and which reaches before the next
action is left by the player's own teleport instead of trading shots (confuser_contact): the
Teleportation scroll first, else the absorbed Teleportation or a Staff of Teleportation; with
none, today's rungs.  *Destruction* is not a leave.  Once confused, the current behaviour stands.

Source: tests/fixtures/n1b-392-confused-read-1113.json.gz (the confused-read pin's fixture,
tests/extract_n1b_392_confused_read_1113_fixture.py).  Every decision goes through the public
``choose_key``; a test says when it edits a board (DECLARED CONSTRUCTED).
DECLARED RESTORED: ``ABSORBED`` is the death's policy-state.json ``_me_staff_sequence.absorbed``
(C:/hengband-backups/pdca/captures/n1b-392-recall-confirm-1113/incident-captures/
20261113-195221-loop-detected); the boards carry no power list.  It holds no Teleportation.
"""
import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import copy
import unittest

from hengbot import confuser_contact, me_absorbed_substitutes
from hengbot.model import SV_SCROLL_TELEPORT, SV_STAFF_TELEPORTATION, TVAL_SCROLL, parse_snapshot
from tests.support.recorded import READ_PROMPT, prompt_screen
from tests.test_me_nokey_1031_recorded import PostedKey
from tests.test_n1b_392_confused_read_1113_recorded import CASE, TELEPORT_NAME, replay, slot

SHOT, FIRST_CONFUSED = 1124309, 1124323
DEMONESS = 319
ABSORBED = {"staff:10": 19, "staff:12": 12, "staff:13": 15, "staff:15": 14, "staff:5": 21,
            "staff:8": 19, "staff:9": 11, "wand:6": 12}


def without_teleport_scrolls(raw):
    raw["inventory"] = [item for item in raw["inventory"]
                        if not (item["tval"] == TVAL_SCROLL
                                and item.get("sval") == SV_SCROLL_TELEPORT)]


class RecordedRowsTest(unittest.TestCase):
    def test_recorded_rows(self):
        rows = {row["turn"]: (row["key"], row["reason"]) for row in CASE["decisions"]}
        self.assertEqual(rows[SHOT], ("fl4", "summoner:ranged-kill"))
        board = next(raw for raw in CASE["boards"] if raw["turn"] == SHOT)
        self.assertFalse(board["player"]["status"]["confused"])
        self.assertEqual((board["player"]["hp"], board["player"]["max_hp"]), (252, 252))
        self.assertFalse(board["player"]["ability_sources"]["resist_conf"]["equipment"])
        self.assertEqual([m["race_id"] for m in board["visible_monsters"]], [DEMONESS])
        knowledge = CASE["monraces"][str(DEMONESS)]
        self.assertEqual([blow["effect"] for blow in knowledge["blows"]].count("CONFUSE"), 2)
        self.assertGreater(knowledge["speed"], board["player"]["speed"])


class ConfuserLeaveTest(PostedKey):
    def test_the_shot_board_reads_teleportation_through_the_executor(self):
        """Recorded: ``fl4`` summoner:ranged-kill; now Teleportation before the claws."""
        policy, raw, key = replay(SHOT)
        self.assertEqual((key, policy.last_reason),
                         ("r" + slot(raw, TELEPORT_NAME), confuser_contact.REASON))
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual([m.race_id for m in confuser_contact.confusers(
            policy, snapshot, snapshot.visible_monsters)], [DEMONESS])
        self.post(policy, raw, key, screens=(prompt_screen(READ_PROMPT),))

    def test_without_the_scroll_the_absorbed_teleportation_is_cast(self):
        """DECLARED CONSTRUCTED: the 1124309 board without the Teleportation scrolls, the
        restored absorbed powers with a Staff of Teleportation added (10 charges)."""
        absorbed = dict(ABSORBED, **{f"staff:{SV_STAFF_TELEPORTATION}": 10})
        policy, _raw, key = replay(SHOT, without_teleport_scrolls, absorbed=absorbed)
        power = me_absorbed_substitutes.POWERS[me_absorbed_substitutes.TELEPORTATION]
        self.assertEqual((key, policy.last_reason),
                         (power.key, confuser_contact.REASON + me_absorbed_substitutes.CAST_SUFFIX))

    def test_control_without_any_teleport_the_shot_stays(self):
        """DECLARED CONSTRUCTED: the 1124309 board without the Teleportation scrolls and the
        restored absorbed powers (no Teleportation): no teleport means, today's shot."""
        policy, _raw, key = replay(SHOT, without_teleport_scrolls, absorbed=ABSORBED)
        self.assertEqual((key, policy.last_reason), ("fl4", "summoner:ranged-kill"))

    def test_control_with_resist_confusion_the_shot_stays(self):
        """DECLARED CONSTRUCTED: the 1124309 board with resist_conf from equipment."""
        def resist(raw):
            raw["player"]["ability_sources"]["resist_conf"]["equipment"] = True
        policy, _raw, key = replay(SHOT, resist)
        self.assertEqual((key, policy.last_reason), ("fl4", "summoner:ranged-kill"))

    def test_control_not_faster_the_shot_stays(self):
        """DECLARED CONSTRUCTED: the 1124309 board with the player as fast as the demoness (the
        boundary) and faster than it (a slower confuser)."""
        for margin in (0, 1):
            with self.subTest(margin=margin):
                def hasted(raw):
                    raw["player"]["speed"] = CASE["monraces"][str(DEMONESS)]["speed"] + margin
                policy, _raw, key = replay(SHOT, hasted)
                self.assertNotEqual(policy.last_reason, confuser_contact.REASON)
                self.assertFalse(key.startswith("r"), (key, policy.last_reason))

    def test_control_adjacent_not_faster_no_leave(self):
        """DECLARED CONSTRUCTED: the 1124309 board with the demoness moved next to the player
        (x 24 -> 25) and the player as fast as it.  Adjacent, its blow always reaches
        (paralyzer_contact.in_contact), so only the speed comparison keeps the leave away:
        the owner's rule is for a confuser faster than the player."""
        def adjacent_as_fast(raw):
            raw["player"]["speed"] = CASE["monraces"][str(DEMONESS)]["speed"]
            # The position is read from the map's monster cell (model.parse_snapshot).
            cell = next(cell for cell in raw["grid_map"]["cells"] if cell.get("m"))
            cell["x"] = raw["visible_monsters"][0]["x"] = raw["player"]["x"] - 1
        policy, raw, _key = replay(SHOT, adjacent_as_fast)
        snapshot = parse_snapshot(copy.deepcopy(raw), policy._monrace_knowledge)
        self.assertEqual([m.distance for m in snapshot.visible_monsters], [1])
        self.assertNotEqual(policy.last_reason, confuser_contact.REASON)

    def test_once_confused_the_cure_stays(self):
        """After confusion the current behaviour: the cure potion, no leave."""
        policy, _raw, key = replay(FIRST_CONFUSED)
        self.assertEqual((key, policy.last_reason), ("qc", "emergency:cure-critical"))

    def test_control_confused_without_cures_no_read(self):
        """DECLARED CONSTRUCTED: the 1124309 board confused, the Cure Critical Wounds and Healing
        potions taken out (the cures run out).  A confused player cannot read (cmd-read.cpp
        do_cmd_read_scroll: cmd_limit_confused), so the leave stays out and today's rungs answer."""
        cures = {36, 37}  # SV_POTION_CURE_CRITICAL, SV_POTION_HEALING

        def confused_no_cures(raw):
            raw["player"]["status"]["confused"] = True
            raw["inventory"] = [item for item in raw["inventory"]
                                if item["tval"] != 75 or item.get("sval") not in cures]
        policy, _raw, key = replay(SHOT, confused_no_cures)
        self.assertNotEqual(policy.last_reason, confuser_contact.REASON)
        self.assertFalse(key.startswith("r"), (key, policy.last_reason))


if __name__ == "__main__":
    unittest.main()
