"""DECLARED CONSTRUCTED bounty continuation on recorded route boards.

The CLI checkpoint is absent. Static Outpost geometry is retained in the
fixture. Install only the recorded bounty work and a repeated procurement
fingerprint; choose_key dispatches the real producer and result arbiter.
Each board is an independent seam, never command-effect replay after divergence.
"""
import unittest
from dataclasses import replace
import tests  # noqa: F401
from hengbot.claim_register import reach
from hengbot.model import Position
from hengbot.policy import HengbotPolicy
from s33_phase2_fixtures import board, town_map


def bounty_policy(snapshot, enforced):
    policy = HengbotPolicy(town_map=town_map())
    policy.prime(snapshot)
    policy._home_knowledge_current = True
    policy._equipment_catalog.home_scan_complete = True
    office = Position(25, 71)  # recorded building_type 13
    claim = policy._claim_register.declare('quest-request',
        reach((office.y, office.x)), floor=snapshot.floor_key)
    policy._claim_register.declare_execution(claim.claim_id,
        producer='quest-request', work_id='normal-step4-bounty', state='acting',
        next_step='bounty.resume', continuation='bounty.resume',
        expected_effect='bounty-removed', budget_ref='quest-request')
    policy._town_progress_history().append(policy._town_progress_fingerprint(snapshot))
    return policy


class BountyRouteTest(unittest.TestCase):
    def test_arbiter_measures_bfs_distance_on_recorded_boards(self):
        snapshot = board(11498)
        policy = bounty_policy(snapshot, True)
        route = policy._town_map_goal_route(snapshot, Position(25, 71))
        # DECLARED CONSTRUCTED effect of our changed first step. Do not use
        # the historical 11500 board: the old invariant returned to supplier.
        advanced = replace(snapshot, player=replace(snapshot.player, position=route.first_step))
        distances = []
        for current in (snapshot, advanced):
            policy = bounty_policy(current, True)
            policy.choose_key(current)
            vector = policy._town_arbiter_progress_vector(current, 'bounty:approach')
            distances.append(vector[-1][-1])
        self.assertEqual(distances, [11, 10])


if __name__ == '__main__':
    unittest.main()
