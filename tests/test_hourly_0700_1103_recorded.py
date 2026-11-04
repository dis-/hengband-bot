"""The 2026-11-03 07:0x-07:5x viewing-bot stops (hourly-0700-1103).

Each class pins one root on its recorded rows; only the game's replies to
newly posted keys are constructed (marked DECLARED CONSTRUCTED) and facts the
capture keeps outside the rows are marked DECLARED RECONSTRUCTED.
Fixture: tests/extract_hourly_0700_1103_fixtures.py.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import _parse_items
from tests import test_me_nokey_1031_recorded as _test_me_nokey_1031_recorded
import test_hourly_0700_1102_recorded as _test_hourly_0700_1102_recorded


FIXTURE = Path(__file__).with_name("fixtures") / "hourly-0700-1103.json.gz"


def _cases():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class WornIdentificationWaitTest(_test_hourly_0700_1102_recorded.RecordedTownPolicy, _test_me_nokey_1031_recorded.PostedKey):
    """n1-a life-468 07:26:49 town:blocked:survival:identify_staff_ready.

    The Lv18 warrior (build 7219d480d) came back to the Outpost from 13F
    with 18 of the 20 Identify-staff charges a planned depth of 10 or more
    needs.  It wore two items waiting for *Identify* that no shop sold: the
    battle axe and the crossbow.  On every board the refused worn-item
    identification asked for the source again, because its deferral was a
    Home deferral that the carried-catalog refresh of the next board
    released; while that need was live the town need registry returned
    before the Identify staff, the black market and the ammunition, so the
    router saw no claim, and only the later terminal bookkeeping of the same
    decision released the wait.  With the Weapon Smiths, the Black Market and
    the Magic shop still in the plan, the town end stepped off the Temple
    entrance (``2``) and stopped (``5``).  The deferral is now held by the
    visit's unidentifiable-carried set and the router reads the needs the
    release frees on the same board.  Every decision is the public
    ``choose_key`` on the recorded rows; the travel goes through the
    production executor.
    DECLARED RECONSTRUCTED: the ring's only Home list (turn 426075) primes
    the policy at the previous visit's first board (424653); the knowledge
    replies are consumed in ring order (the dispatcher's bookkeeping is not
    replayed), and the 13F trip between the visits is represented by its
    last boards only.
    """

    STEP_OFF = 431478

    @classmethod
    def setUpClass(cls):
        cls.case = _cases()["identify_staff"]

    def drive(self):
        case, policy, answers, seen = self.case, None, {}, set()
        rows = case["rows"]
        for index, raw in enumerate(rows):
            if raw["type"] == "knowledge":
                category = raw["knowledge"]["category"]
                if policy is not None and category == "home":
                    policy.consume_home_knowledge(
                        tuple(_parse_items(raw["knowledge"]["items"], protocol=3)))
                if policy is not None and category == "skill_exp":
                    level = next(row["player"]["level"] for row in rows[index:]
                                 if row["type"] == "player_turn")
                    policy.consume_skill_knowledge({**raw, "player": {"level": level}})
                continue
            if raw["type"] not in ("player_turn", "store"):
                continue
            if raw["type"] == "player_turn":
                if raw["turn"] in seen:
                    continue
                seen.add(raw["turn"])
            if policy is None:
                policy = self.primed(raw, case["home"]["knowledge"]["items"], case["skill"])
                policy._in_store_ops_enabled = True  # live argv (--in-store-shop-ops)
            board = self.board(policy, raw)
            # The executor verifies the store page on screen (cli.py).
            policy.observe_store_screen(True if raw["type"] == "store" else None)
            key = policy.choose_key(board)
            if raw["type"] == "player_turn":
                answers[raw["turn"]] = (key, policy.last_reason, raw)
            if raw["turn"] == self.STEP_OFF:
                return policy, answers
            if key:
                policy.confirm_key_posted(key)
        raise AssertionError("the recorded step-off board was not reached")

    def test_recorded_stop(self):
        step_off, stop = self.case["decisions"]
        self.assertEqual((step_off["turn"], step_off["key"], step_off["reason"]),
                         (self.STEP_OFF, "2", "town:entrance-step-off:town:end-step-off"))
        self.assertEqual((stop["key"], stop["reason"], stop["failed"]),
                         ("5", "town:blocked:survival:identify_staff_ready",
                          ["identify_staff_ready"]))
        self.assertEqual(stop["town_plan"]["stops"],
                         ["Black Market", "Weapon Smiths", "Magic Shop"])
        (admission,) = stop["terminal_admission"]
        self.assertEqual((admission["terminal"][0], admission["codes"]),
                         ("identify-equipped", ["no-identification-source"]))
        board = [row for row in self.case["rows"]
                 if row["type"] == "player_turn" and row["turn"] == self.STEP_OFF][0]
        charges = sum(item["charges"] * item["count"] for item in board["inventory"]
                      if (item["tval"], item["sval"]) == (55, 5))
        self.assertEqual(charges, 18)

    def test_the_freed_needs_route_to_the_next_plan_stop(self):
        policy, answers = self.drive()
        key, reason, raw = answers[self.STEP_OFF]
        # Recorded: '2' town:entrance-step-off:town:end-step-off, then '5'.
        self.assertEqual((key, reason), ("\x1b`n#.", "shop:travel"))
        self.assertIn("identify-staff", policy._town_claim_categories)
        # The recorded terminal's battle axe stays deferred for the visit.
        (axe,) = [item for item in self.board(policy, raw).equipment
                  if item.slot == "main_hand"]
        self.assertEqual([policy._item_signature(axe)],
                         [tuple(each) for each in
                          self.case["decisions"][1]["terminal_admission"][0]["terminal"][1]])
        self.assertIn(policy._item_signature(axe), policy._town_unidentifiable_carried_sigs)
        self.post(policy, raw, key)


if __name__ == "__main__":
    unittest.main()
