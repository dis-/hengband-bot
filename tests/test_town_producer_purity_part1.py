import unittest

from town_producer_purity_matrix import assert_partition_is_pure


class TownProducerPurityPart1Test(unittest.TestCase):
    def test_candidate_town_producers_part1_are_pure(self):
        assert_partition_is_pure(self, 0)
