from pathlib import Path
import unittest

from hengbot.policy import HengbotPolicy
from trajectory_harness import replay_checkpoint_trajectory


class HungryManaPurchaseTrajectoryTest(unittest.TestCase):
    FIXTURE = (
        Path(__file__).parent
        / "fixtures"
        / "hungry-mana-purchase-block-checkpoints.jsonl.gz"
    )

    def test_hungry_mana_owner_takes_over_recorded_purchase_cycle(self):
        transcript = replay_checkpoint_trajectory(
            HengbotPolicy,
            self.FIXTURE,
            (1, 22, 23, 26, 79),
            forbidden_reasons={
                "survival:shop-approach",
                "town:cycle-break",
                "town:blocked:repetition",
            },
            required_reason_prefix="survival:mana-home-",
        )
        self.assertIn(
            "survival:mana-home-travel",
            {reason for reason, _key in transcript},
        )


if __name__ == "__main__":
    unittest.main()
