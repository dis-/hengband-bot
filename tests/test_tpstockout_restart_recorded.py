"""Recorded outside-board attachment, not a serialized lifetime checkpoint.

Rebuild recorded supply, Home, alternate-dungeon and route/ledger facts on a
fresh primed policy. The conquest latch is the explicit committed-expedition
attachment also used by class C2. No readiness or selector is mocked.
Only the first divergent decision is asserted; no later historical board is
used as the effect of our new travel key.
"""
import tests  # noqa: F401 -- isolate all runtime writes
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from hengbot.model import parse_snapshot, _parse_items
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.policy import HengbotPolicy
from hengbot.policy_constants import SUPPLY_STORES
from test_esp_threat_rest_recorded import _policy, EDIT
from xbow_pref_walls import apply_shelf_wall

FIXTURES = Path(__file__).parent / 'fixtures'
ROUTES = FIXTURES / 'tpstockout-routes-20261002.json.gz'


def attachment(directory):
    capture = json.loads(gzip.decompress(
        (FIXTURES / 'tpstockout-20261002.json.gz').read_bytes()))
    routes = json.loads(gzip.decompress(ROUTES.read_bytes()))['captures']['023556']
    restart = max(i for i, row in enumerate(routes) if row.get('decision_sequence') == 1)
    routes = routes[restart:]
    policy = _policy(Path(directory), load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc'))
    policy._character_calibration_path.write_text(json.dumps(capture['calibration']), encoding='utf8')
    board = parse_snapshot(capture['board'], policy._monrace_knowledge)
    policy.prime(board)
    policy.consume_skill_knowledge({'knowledge': capture['knowledge']['skill_exp'],
                                   'player': capture['board']['player']})
    policy.consume_home_knowledge(tuple(_parse_items(capture['knowledge']['home']['items'], protocol=3)))
    destination = capture['decision']['over_extension']
    policy._alternate_dungeon = destination['alternate_dungeon_id']
    policy._target_dungeon_id = destination['target_dungeon_id']
    policy._deepest_level = board.dungeon_recall_depths[policy._target_dungeon_id]
    for store_type, raw in capture['shelves'].items():
        page = parse_snapshot(raw, policy._monrace_knowledge).store
        policy._town_supplier_stock[int(store_type)] = page
        policy._town_supplier_stock_observations[int(store_type)] = (
            policy._effective_town_id(board), raw['turn'])
    policy._conquest_committed = True
    policy._fundraising_cleared_for_conquest = True
    policy._yeek_conquest_processed = True
    equipment = capture['decision']['equipment_optimization']
    policy._equipment_optimization_last_depth = equipment['optimization_depth']
    policy._equipment_catalog.home_scan_complete = equipment['home_scan_complete']
    policy._char_dump_done_this_visit = True
    policy._town_was_in_town = True
    policy._observed_town_id = policy._effective_town_id(board)
    # Actual unfulfilled Home and observed shop exits in this restarted process.
    policy._town_store_attempted = {
        row['shopping_approach_store_type']: row['turn'] for row in routes
        if row['reason'] in {'home:route-claim-unfulfilled', 'shop:observe-and-leave'}
    }
    ledger = capture['decision']['departure_block']['town_ledger']
    for name in ('store_visits', 'approach_fails', 'unsatisfied_passes'):
        getattr(policy._town_visit_ledger, name).update({int(k): v for k, v in ledger[name].items()})
    policy._town_visit_ledger.need_attempts.update(ledger['need_attempts'])
    policy._refresh_carried_equipment_catalog(board)
    policy._home_candidate_waiting = capture['decision']['home_candidate_waiting']
    # Reconstruct the disposable plan from live needs, not a cached purchase.
    policy._town_errand_plan = policy._build_town_errand_plan(board, policy._enumerate_town_needs(board))
    policy._validated_character_calibration(board)
    return policy, board, capture


class StockedSupplierRestartTest(unittest.TestCase):
    def test_recorded_restart_and_checkpoint_travel_to_stocked_alchemist(self):
        self.assertEqual(hashlib.sha256(ROUTES.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
                         '4730d0e32b3eba2db712448bf1f293d573a07e09db2250da85e44a243bdac3ed')
        with TemporaryDirectory() as directory:
            policy, board, capture = attachment(directory)
            # Declared wall (tests/xbow_pref_walls.py): shelves without plain
            # bolts, so the 2026-10-02 crossbow swap does not apply here.
            apply_shelf_wall(policy)
            saved = checkpoint(policy)
            for subject in (policy, restore_checkpoint(HengbotPolicy, saved)):
                with self.subTest(restored=subject is not policy):
                    self.assertIsNone(board.store)
                    self.assertEqual(subject._count_teleport_scrolls(board), 4)
                    self.assertEqual(subject._supply_ledger(board, 20)['teleport'].required_departure, 15)
                    key = subject.choose_key(board)
                    print('TPSTOCKOUT FIRST DIVERGENCE live',
                          repr(capture['decision']['key']), capture['decision']['reason'],
                          'new', repr(key), subject.last_reason)
                    self.assertEqual(key, '\x1b`n%.')
                    self.assertEqual(subject.last_reason, 'shop:travel')
                    self.assertEqual(subject._shopping_approach_store_type, 4)

    def test_every_supply_supplier_has_a_registry_lookup_even_with_home_stock(self):
        counts = Counter(spec.category for spec in HengbotPolicy()._town_need_registry())
        for kind, category in (('recall', 'recall'), ('teleport', 'teleport'),
                               ('cure', 'cure-critical'), ('oil', 'oil'), ('food', 'food')):
            with self.subTest(kind=kind):
                self.assertEqual(counts[category], len(SUPPLY_STORES[kind]) + 1)


if __name__ == '__main__':
    unittest.main()
