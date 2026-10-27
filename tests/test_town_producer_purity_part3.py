import tests  # noqa: F401  -- live runtime-file isolation, also for bare module runs

import unittest

from tests.gate_sample import sample
from town_producer_purity_matrix import (
    PARTITION_CELL_INDEXES, assert_partition_is_pure,
)


class TownProducerPurityPart3Test(unittest.TestCase):
    def test_candidate_town_producers_part3_are_pure(self):
        assert_partition_is_pure(
            self, 2, indexes=sample(list(PARTITION_CELL_INDEXES[2]))
        )
