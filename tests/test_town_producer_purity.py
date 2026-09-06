"""Keep the split T3 purity matrix complete and importable."""

import unittest

from town_producer_purity_matrix import (
    assert_partitions_complete,
)


class TownProducerPurityGateTest(unittest.TestCase):
    def test_purity_partitions_cover_every_cell_once(self):
        assert_partitions_complete(self)

if __name__ == "__main__":
    unittest.main()
