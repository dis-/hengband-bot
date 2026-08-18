from pathlib import Path
import unittest

from hengbot.policy import HengbotPolicy
from trajectory_harness import replay_checkpoint_trajectory


class TownRestockStallTrajectoryTest(unittest.TestCase):
    FIXTURE = (
        Path(__file__).parent
        / "fixtures"
        / "town-restock-stall-hungry-checkpoints.jsonl.gz"
    )

    def test_hungry_character_escapes_recall_restock_owner_alternation(self):
        transcript = replay_checkpoint_trajectory(
            HengbotPolicy,
            self.FIXTURE,
            (2331, 2333),
            forbidden_reasons={
                "town:blocked:restocked-recall-store-unreachable",
                "town:wait-restock:temple",
            },
            required_reason_prefix="town:blocked:survival-mana-no-charges",
        )
        self.assertEqual(len(transcript), 2)
        self.assertTrue(all(key == "5" for _reason, key in transcript))

    def test_mana_device_reserve_releases_stale_home_route(self):
        fixture = (
            Path(__file__).parent
            / "fixtures"
            / "food-store-unreachable-checkpoints.jsonl.gz"
        )
        transcript = replay_checkpoint_trajectory(
            HengbotPolicy,
            fixture,
            (220, 221, 223, 242),
            forbidden_reasons={
                "town:blocked:restocked-food-store-unreachable",
            },
            required_reason_prefix="shop:",
        )
        self.assertEqual(len(transcript), 4)
        self.assertTrue(all(
            reason == "shop:travel" and key == "\x1b`n&."
            for reason, key in transcript
        ))


if __name__ == "__main__":
    unittest.main()
