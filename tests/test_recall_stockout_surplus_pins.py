from __future__ import annotations

import gzip
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.home_disposal import HomeDisposalState
from hengbot.model import parse_snapshot
from hengbot.policy import HengbotPolicy


FIXTURE = Path(__file__).parent / "fixtures" / "recall-stockout-surplus-incident.jsonl.gz"


def replay_to_home_return(policy: HengbotPolicy):
    knowledge = {}
    decisions = []
    final_snapshot = None
    with gzip.open(FIXTURE, "rt", encoding="utf-8-sig") as stream:
        for index, line in enumerate(stream, 1):
            raw = json.loads(line)
            if raw.get("type") == "knowledge":
                knowledge.update(raw.get("knowledge", {}))
                continue
            snapshot = parse_snapshot(raw, knowledge)
            key = policy.choose_key(snapshot)
            decisions.append((index, snapshot.turn, key, policy.last_reason))
            final_snapshot = snapshot
            if index == 24:
                break
    return decisions, final_snapshot


class RecallStockoutSurplusPins(unittest.TestCase):
    def _state(self, root: Path, transactions=()):
        history = root / "home-withdraw-history.jsonc"
        history.write_text(
            json.dumps({"version": 1, "dungeon_recall_count": 0,
                        "transactions": list(transactions)}),
            encoding="utf-8",
        )
        return HomeDisposalState(
            history,
            root / "home-disposal-decisions.jsonc",
            root / "queue.json",
            root / "events.jsonl",
        )

    def test_home_surplus_incident_real_producer(self):
        """Public rows 1-24 produce and consume the bound deposit on one policy."""
        with TemporaryDirectory() as directory:
            decisions, snapshot = replay_to_home_return(
                HengbotPolicy(home_disposal_state=self._state(Path(directory)))
            )
        self.assertEqual(decisions[-1][2:], ("5", "home:atomic-deposit"))
        self.assertEqual(snapshot.turn, 2856373)

    def test_future_history_does_not_suppress_surplus(self):
        """A future deposit record is history, not a surplus-selection veto."""
        with TemporaryDirectory() as empty_dir, TemporaryDirectory() as future_dir:
            ordinary, _ = replay_to_home_return(
                HengbotPolicy(home_disposal_state=self._state(Path(empty_dir)))
            )
            future = ({"action": "deposit", "signature": ["future", 75, 99],
                       "turn": 2856373},)
            with_history, _ = replay_to_home_return(
                HengbotPolicy(
                    home_disposal_state=self._state(Path(future_dir), future)
                )
            )
        self.assertEqual(ordinary[-1][2:], ("5", "home:atomic-deposit"))
        self.assertEqual(with_history[-1][2:], ordinary[-1][2:])

    def test_identify_first_and_no_open_home_unbound_deposit(self):
        """The captured pre-Home producer acts before the later bound deposit."""
        with TemporaryDirectory() as directory:
            decisions, _ = replay_to_home_return(
                HengbotPolicy(home_disposal_state=self._state(Path(directory)))
            )
        first_disposal = next(i for i, row in enumerate(decisions)
                              if row[3] == "inventory:destroy-disposable-item")
        deposit = next(i for i, row in enumerate(decisions)
                       if row[3] == "home:atomic-deposit")
        self.assertLess(first_disposal, deposit)
        self.assertNotIn(
            "home:route-claim-unfulfilled", [row[3] for row in decisions]
        )


if __name__ == "__main__":
    unittest.main()
