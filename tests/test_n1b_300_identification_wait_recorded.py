"""n1-b life-300 2026-11-03 02:23 town:blocked:unmet:home_candidate_resolved.

The Outpost visit of the Lv23 warrior (build 38c599427) had done every stop
of its plan; the Home armour ドルイドのサイ皮よろい (-1) [8,+11] (+1), known
but not fully known, still waited for *Identify* (identification_need
"full", home_candidate_waiting).  No owner answered the board, so the town
end stepped off the Temple entrance (``1``) and stopped under
town:blocked:unmet:home_candidate_resolved (``5``); the bot then retired the
character.

Owner decisions (identification_wait): 「鑑定不能品…があっても出発は許可する。
次回以降帰還時鑑定を試みる。」 (2026-09-02), 「鑑定待ちでも止めない」
(2026-09-13).  The town end releases the identification wait for this visit
and the forced visit departure reads Word of Recall; the deferred armour is
retried on the next return.  Every decision is the public ``choose_key`` on
the recorded visit's rows, the departure key goes through the production
executor.
Fixture: tests/extract_n1b_300_identification_wait_fixture.py.
DECLARED RECONSTRUCTED: the knowledge replies are consumed by the policy's
knowledge methods in the order the ring holds them (the dispatcher's request
bookkeeping is not replayed), so the middle of the visit runs its own route;
the recorded stop recurs on the recorded last boards.
"""

import tests  # noqa: F401 -- isolate runtime files for a bare-module run

import gzip
import json
import unittest
from pathlib import Path

from hengbot.model import _parse_items
from tests import test_input_executor as executor_pins
from tests.test_me_nokey_1031_recorded import PostedKey
from tests.test_recall_dungeon_prompt_recorded import READ_PROMPT, chooser_screen
from test_hourly_0700_1102_recorded import RecordedTownPolicy


FIXTURE = Path(__file__).with_name("fixtures") / "identification-wait-n1b-300-1103.json.gz"
STEP_OFF, STOP = 756143, 756154
ARMOUR = "ドルイドのサイ皮よろい (-1) [8,+11] (+1)"


def _case():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class IdentificationWaitDepartsTest(RecordedTownPolicy, PostedKey):
    @classmethod
    def setUpClass(cls):
        cls.case = _case()

    def drive(self):
        """Decide every recorded row of the visit; keep the last two answers."""
        case, policy, answers, seen = self.case, None, {}, set()
        for raw in case["rows"]:
            if raw["type"] == "knowledge":
                if policy is not None and raw["knowledge"]["category"] == "home":
                    policy.consume_home_knowledge(
                        tuple(_parse_items(raw["knowledge"]["items"], protocol=3)))
                continue
            if raw["type"] == "player_turn":
                if raw["turn"] in seen:
                    continue
                seen.add(raw["turn"])
            if policy is None:
                policy = self.primed(raw, case["home"]["knowledge"]["items"], case["skill"])
            board = self.board(policy, raw)
            key = policy.choose_key(board)
            if raw["type"] == "player_turn" and raw["turn"] in (STEP_OFF, STOP):
                answers[raw["turn"]] = (key, policy.last_reason, raw)
            if key:
                policy.confirm_key_posted(key)
        return policy, answers

    def test_recorded_stop(self):
        rows = {(row["turn"], row["reason"]): row for row in self.case["decisions"]}
        self.assertEqual(rows[(STEP_OFF, "town:entrance-step-off:town:end-step-off")]["key"], "1")
        stop = rows[(STOP, "town:blocked:unmet:home_candidate_resolved")]
        self.assertEqual((stop["key"], stop["identification_need"],
                          stop["home_candidate_waiting"]), ("5", "full", True))
        self.assertEqual(stop["failed"], ["home_candidate_resolved", "identification_need_clear"])
        # Carried on arrival, deposited at decision 12829 (``dq``, turn 755635).
        packs = {row["turn"]: [item["name"] for item in row["inventory"]]
                 for row in self.case["rows"] if row["type"] == "player_turn"}
        self.assertIn(ARMOUR, packs[754636])
        self.assertNotIn(ARMOUR, packs[STOP])

    def test_identification_wait_departs_on_the_current_loadout(self):
        policy, answers = self.drive()
        self.assertEqual(answers[STEP_OFF][:2], ("1", "town:entrance-step-off:town:end-step-off"))
        key, reason, raw = answers[STOP]
        # Recorded: '5' town:blocked:unmet:home_candidate_resolved.
        self.assertEqual((key, reason), ("rda", "town:repetition-depart:recall"))
        self.assertIn((ARMOUR, 36, 8), policy._deferred_home_items)
        self.post(policy, raw, key,
                  (executor_pins.prompt_screen(READ_PROMPT), chooser_screen()))


if __name__ == "__main__":
    unittest.main()
