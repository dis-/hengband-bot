"""Route-envelope pins for fixed-quest building approaches."""

import copy
import json
import unittest
from pathlib import Path

from hengbot.model import parse_snapshot
from hengbot.policy_constants import QUEST_STATUS_COMPLETED
from hengbot.policy_types import DecisionCandidate
from tests.test_quest_travel_progress import QuestTravelFixtureMixin


INCIDENT = Path(__file__).with_name("fixtures") / "quest-enter-approach-stage2f.jsonl"


class QuestBuildingApproachProgressPins(QuestTravelFixtureMixin, unittest.TestCase):
    @classmethod
    def _source(cls):
        with open(INCIDENT, encoding="utf-8") as stream:
            for line in stream:
                raw = json.loads(line)
                if (raw.get("type") == "player_turn"
                        and any(q.get("id") == 22
                                for q in raw.get("progress", {}).get("quests", []))):
                    return raw
        raise AssertionError("fixture has no player_turn")

    def _claim(self, y, x, turn):
        raw = copy.deepcopy(self._source())
        raw["turn"] = turn
        raw["player"].update({"y": y, "x": x})
        next(q for q in raw["progress"]["quests"] if q["id"] == 22)[
            "status"
        ] = QUEST_STATUS_COMPLETED
        return parse_snapshot(raw, self.monrace)

    def _candidate(self, policy, snapshot):
        # Enter the real public decision boundary to mint this decision's
        # identity, then invoke the producer under test before final-envelope
        # validation.  No candidate/declaration fields are hand assigned.
        selected = policy.choose_key(snapshot)
        if (isinstance(selected, DecisionCandidate)
                and selected.reason == "fixedquest:claim:approach"):
            self.assertTrue(
                policy._valid_quest_travel_declaration(snapshot, selected)
            )
            return selected
        policy._build_grid_index(snapshot)
        key = policy._fixed_quest_building_key(
            snapshot, 22, "fixedquest:claim", set_reward_pending=True
        )
        if policy.last_reason == "fixedquest:claim":
            return key
        self.assertIsInstance(
            key, DecisionCandidate,
            (snapshot.player.position, policy.last_reason),
        )
        self.assertTrue(policy._valid_quest_travel_declaration(snapshot, key))
        return key

    def test_incident_positions_have_strictly_decreasing_bfs_rank(self):
        starts = ((63, 98), (38, 90), (29, 82))
        delta = {
            "1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
            "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1),
        }
        measured = []
        for start in starts:
            ranks = []
            y, x = start
            for offset in range(80):
                policy = self._policy()
                key = self._candidate(
                    policy, self._claim(y, x, 2864686 + offset)
                )
                if not isinstance(key, DecisionCandidate):
                    self.assertEqual((str(key), policy.last_reason),
                                     ("3q\x1b", "fixedquest:claim"))
                    break
                ranks.append(key.route_declaration.bfs_rank)
                if ranks[-1] == 1:
                    break
                dy, dx = delta[str(key)]
                y, x = y + dy, x + dx
            self.assertTrue(all(b < a for a, b in zip(ranks, ranks[1:])), ranks)
            measured.append(ranks)
        self.assertTrue(all(values[-1] == 2 for values in measured), measured)

    def test_final_building_step_keeps_claim_tail(self):
        policy = self._policy()
        snapshot = self._claim(31, 98, 2867000)
        policy.choose_key(snapshot)
        policy._build_grid_index(snapshot)
        key = policy._fixed_quest_building_key(
            snapshot, 22, "fixedquest:claim", set_reward_pending=True
        )
        self.assertEqual(str(key), "3q\x1b")
        self.assertEqual(policy.last_reason, "fixedquest:claim")


if __name__ == "__main__":
    unittest.main()
