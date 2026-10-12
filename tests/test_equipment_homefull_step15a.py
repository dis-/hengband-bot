"""Step 1.5a pins. Immutable captures plus explicitly constructed continuations.

DECLARED CONSTRUCTED: no checkpoint or character dump file was captured.
Replay begins on a fresh policy at s1. After the first changed command, boards
are constructed alternatives, and the missing equipped C dump is rebuilt from
visible stat/equipment fields. No optimizer or departure predicate is mocked.
"""
from __future__ import annotations

from dataclasses import replace
import copy
import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from hengbot.policy_types import TownNeed
import unittest
from types import SimpleNamespace

import tests  # noqa: F401
from hengbot.cli import _consume_response_sequence
from hengbot.character_sheet import displayed_modifier, parse_character_sheet, derive_equipped_calibration
from hengbot.equipment_optimizer import equipment_identity, equipment_move_identity
from hengbot.equipment_transaction_planner import (
    EquipmentTransaction, EquipmentTransactionPlan, PHASE_EQUIP, PHASE_HOME_PREPARE,
)
from hengbot.equipment_transaction_session import EquipmentTransactionSession, EquipmentTransactionObservation
from hengbot.model import parse_snapshot, STORE_HOME, TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL
from hengbot.policy import HengbotPolicy, staged_prompt_chain_matches
from hengbot.policy_constants import CHARACTER_DUMP_MACRO
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
from hengbot.model import Position, _parse_items
from hengbot.warrior_equipment_evaluator import modify_stat_value
from hengbot.warrior_optimization import WarriorOptimizationPreparation, current_loadout
from hengbot.latch_onset_capture import checkpoint, restore_checkpoint
from test_esp_threat_rest_recorded import _policy, EDIT
from hengbot.monrace_knowledge import load_monrace_knowledge

FIXTURE = Path(__file__).parent / 'fixtures/step1.5a-equipment-homefull.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == '0983fc092cca64be34d7400d3ed9d9e6327d6662e4aeaa4be93feaf9a09502ae'
CAPTURES = json.loads(gzip.decompress(FIXTURE.read_bytes()))
PACKSPACE_FIXTURE = Path(__file__).parent / 'fixtures/packspace-depart-20261012.json.gz'
PACKSPACE_CAPTURE = json.loads(gzip.decompress(PACKSPACE_FIXTURE.read_bytes()))
EQTXN_RESERVED_PINS = json.loads(gzip.decompress(
    (Path(__file__).parent / 'fixtures/eqtxn-reserved-20261012.json.gz').read_bytes()
))


def dump_bytes(raw, character, monrace=None):
    # DECLARED CONSTRUCTED external C dump, not a captured file. The total
    # intrinsic adjustment is inferred from visible Base/Top and known pvals;
    # its split among race/class/personality is immaterial to this owner pin.
    board = parse_snapshot(raw, monrace)
    lines = ['Base Actual Current abcdefghijkl@']
    for index, name in enumerate(('STR', 'INT', 'WIS', 'DEX', 'CON', 'CHR')):
        base = board.player.stat_max[index]
        top = raw['player']['stats'][name.lower()]['top']
        total = next(n for n in range(-30, 31) if modify_stat_value(base, n) == top)
        equipment = sum(i.pval for i in board.equipment if index in i.known_flags)
        intrinsic = total - equipment
        def printed(value):
            return str(value) if value <= 18 else '18/***' if value >= 238 else f'18/{value-18}'
        lines.append(f'{name}:' + f'{printed(base):>6}{intrinsic:>3}{0:>3}{0:>3}'
                     + f'{displayed_modifier(base, top, intrinsic):>3}{printed(top):>7}{"":>7}')
    lines += [f'Level: {board.player.level}', f'HP: {board.player.hp}/{board.player.max_hp}',
              f'AC: [0,{board.player.ac}]']
    for label, key in (('Race','race_title'), ('Class','class_title'), ('Personality','personality_title')):
        lines.append(f'{label}: {character[key]}')
    lines.append('[Character Equipment]')
    slots = ('main_hand','sub_hand','bow','main_ring','sub_ring','neck','light','body','outer','head','arms','feet')
    lines += [f'{chr(97+slots.index(i.slot))}) {i.name}' for i in board.equipment if i.is_equipment]
    return ('\r\n'.join(lines)+'\r\n').encode('cp932')


def post(policy, key):
    policy.confirm_key_posted(key)
    chain = policy.peek_staged_prompt_chain()
    if chain is not None and staged_prompt_chain_matches(chain, key):
        policy.commit_staged_prompt_chain(chain, key)


class EquipmentHomeFullStep15aTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        # F3's persisted visit ledger is private to each recorded replay.
        runtime = patch.dict('os.environ', {'HENGBOT_RUNTIME_DIR': str(self.directory)})
        runtime.start()
        self.addCleanup(runtime.stop)

    def test_packspace_capture_stages_before_departure_stop(self):
        # Captured endpoint on b8f5ac67: all independent departure values were
        # true, but the all-at-once equipment plan ended the town visit.
        decision = PACKSPACE_CAPTURE['blocked_decision']
        self.assertEqual(decision['reason'], 'town:blocked:departure-unsatisfiable')
        self.assertEqual(decision['turn'], 639606)
        self.assertEqual(decision['inventory'], {'used': 18, 'free': 5})
        self.assertEqual(
            decision['equipment_optimization']['search_catalog_origins'],
            {'equipped': 7, 'pack': 2, 'home': 17},
        )
        self.assertEqual(decision['equipment_optimization']['blockers'],
                         ['pack-space-required:3'])
        self.assertEqual(decision['equipment_optimization']['transaction_actions'], 15)
        self.assertEqual(decision['departure_block']['failed'], ['equipment_departure_ready'])
        values = decision['departure_block']['values']
        self.assertFalse(values['equipment_departure_ready'])
        self.assertTrue(all(
            value for key, value in values.items()
            if key != 'equipment_departure_ready'
        ))

        # Replay the captured board, Home contents, and acknowledged character
        # sheet through the real optimizer and transaction producer.
        raw = PACKSPACE_CAPTURE['outside_board']
        board = parse_snapshot(raw, self.monrace)
        home = parse_snapshot(PACKSPACE_CAPTURE['home_board'], self.monrace)
        policy = self.policy()
        policy.prime(board)
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        policy.consume_skill_knowledge(PACKSPACE_CAPTURE['skill_exp'])
        policy._character_dump_path.write_bytes(
            dump_bytes(raw, PACKSPACE_CAPTURE['character'])
        )
        # DECLARED CONSTRUCTED C response: the capture omitted its original
        # dump envelope, so derive calibration from the captured board and the
        # reconstructed sheet using the production calibration validator.
        policy._calibration_dump_pending = {
            'baseline': None, 'started_ns': 1, 'sequence': None,
        }
        envelope = dict(raw, sequence=1)
        policy.observe_character_snapshot(
            PACKSPACE_CAPTURE['character'], envelope=envelope
        )
        policy._complete_character_dump(board)
        board = policy._with_cached_skill_exp(board)
        policy.consume_home_knowledge(tuple(home.store.items))
        preparation = policy._prepare_equipment_optimization(board)
        session = policy._equipment_transaction_session
        self.assertIsNotNone(preparation)
        self.assertIsNotNone(session)
        self.assertTrue(session.executable)
        self.assertIn(session.current_action.kind, {'withdraw', 'takeoff'})
        first_action = session.current_action
        home = replace(
            home, turn=board.turn, inventory=board.inventory,
            equipment=board.equipment, player=board.player, floor=board.floor,
        )
        key = policy._equipment_transaction_home_key(home)
        self.assertIsNotNone(key)
        post(policy, key)
        self.assertEqual(session.pending_action, first_action)
        self.assertNotIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)

    def test_constructed_home_full_closure_requires_an_unfittable_staged_step(self):
        # DECLARED CONSTRUCTED: the captured board has Home capacity, while
        # this variant supplies a full-Home observation and a planner result
        # whose first staged action cannot fit in the pack.
        board = self.board()
        policy = self.policy()
        policy.prime(board)
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        current = current_loadout(policy._equipment_catalog.items)
        blockers = ('pack-space-required:2',)
        preparation = WarriorOptimizationPreparation(
            current,
            SimpleNamespace(best=SimpleNamespace(loadout=current)),
            EquipmentTransactionPlan((), blockers, 25),
            blockers,
        )
        policy._equipment_optimization_preparation = preparation
        policy._equipment_transaction_session = None
        epoch = policy._town_visit_epoch
        # TEST_FAKERY_LINT_ALLOW: declared constructed capacity-failure pin; the
        # real planner/optimizer replay is covered by the captured-board test above.
        with patch.object(policy, '_prepare_equipment_optimization', return_value=preparation), \
             patch.object(policy, '_home_is_full', return_value=True), \
             patch.object(policy, '_current_worn_loadout_confirmed', return_value=True):
            self.assertTrue(policy._equipment_departure_ready(board))
        closure = policy._equipment_transaction_visit_closure
        self.assertEqual(closure['epoch'], epoch)
        self.assertEqual(closure['reason'], 'pack-space-home-full')
        self.assertEqual(closure['loadout_id'], ','.join(sorted(current.item_ids)))
        self.assertEqual(closure['blockers'], list(blockers))
        self.assertEqual(closure['turn'], board.turn)

        # DECLARED CONSTRUCTED control: same blocker with Home room keeps the
        # visible equipment gate. Each reverted predicate below must fail.
        for home_full, confirmed, step_blockers, active_session in (
            (False, True, blockers, None),
            (True, False, blockers, None),
            (True, True, ('equipment-transaction-failed',), None),
            (True, True, blockers, object()),
        ):
            control = self.policy()
            control.prime(board)
            control._equipment_optimization_preparation = preparation
            control._equipment_transaction_session = active_session
            candidate = replace(preparation, blockers=step_blockers)
            with patch.object(control, '_prepare_equipment_optimization', return_value=candidate), \
                 patch.object(control, '_home_is_full', return_value=home_full), \
                 patch.object(control, '_current_worn_loadout_confirmed', return_value=confirmed):
                self.assertFalse(control._equipment_departure_ready(board))
            self.assertIsNone(control._equipment_transaction_visit_closure)

    def policy(self):
        policy = _policy(self.directory, self.monrace)
        policy._character_calibration_path.unlink()
        policy._character_dump_path = self.directory / 'dump.txt'
        policy._confirmed_loadout_path = self.directory / 'confirmed.json'
        policy._in_store_ops_enabled = True
        policy._town_claim_bar_enforced = True
        policy._crossarea_fundraising_enforced = True
        return policy

    def board(self, stamp='20261008-134416', *, home=False):
        rows = CAPTURES[stamp]['bot-state-fixed']['rows']
        raw = next(r for r in reversed(rows) if r['type'] == ('store' if home else 'player_turn')
                   and (not home or r['store']['store_type'] == STORE_HOME))
        return parse_snapshot(raw, self.monrace)

    def deposit_session(self, board, *, kind='deposit', phase=PHASE_HOME_PREPARE):
        # DECLARED CONSTRUCTED unit transaction over a captured pack item.
        item = next(i for i in board.inventory if i.is_equipment)
        action = EquipmentTransaction(phase, kind, 'pack:'+equipment_identity(item)+':0',
                                      item_identity=equipment_identity(item),
                                      move_identity=equipment_move_identity(item))
        return EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 0))

    def closed_policy(self):
        board = self.board()
        policy = self.policy()
        policy.prime(board)
        policy._mark_equipment_home_full_unavailable(board)
        return policy, board

    def failure_preparation(self, policy, board):
        # DECLARED CONSTRUCTED unit failed preparation; no fabricated best result.
        policy._equipment_catalog.refresh_carried(board.inventory, board.equipment)
        preparation = WarriorOptimizationPreparation(
            current_loadout(policy._equipment_catalog.items), None, None,
            ('equipment-transaction-failed',))
        policy._equipment_optimization_preparation = preparation
        policy._equipment_optimizer_input_key = 'declared-unit-observed-carried-input'
        return preparation

    def replay_incident(self, stamp, indices, start, prefix_length):
        capture = CAPTURES[stamp]
        rows = capture['bot-state-fixed']['rows']
        decisions = capture['bot-decisions']['rows']
        policy = self.policy()
        policy._town_claim_bar_enforced = False  # recorded CLI mode
        policy.request_game_save()
        policy.request_character_dump()
        policy.prime(parse_snapshot(rows[indices[0]], self.monrace))
        character = next(r['character'] for r in rows[start:] if r['type']=='character')
        last = start-1
        reasons = []
        for n, index in enumerate(indices[:prefix_length]):
            segment = copy.deepcopy(rows[last+1:index+1])
            for r in segment:
                if r['type']=='character':
                    # DECLARED CONSTRUCTED missing external dump/envelope.
                    r['sequence'] = index
                    policy._character_dump_path.write_bytes(dump_bytes(rows[index], r['character'], self.monrace))
                if r.get('knowledge',{}).get('category')=='skill_exp':
                    policy.consume_skill_knowledge(r)
            _consume_response_sequence([json.dumps(r) for r in segment], policy,
                lambda _: True, self.monrace, knowledge_ledger_path=self.directory/'knowledge.jsonl')
            board = parse_snapshot(rows[index], self.monrace)
            key = policy.choose_key(board)
            self.assertEqual((key, policy.last_reason),
                             (decisions[n]['key'], decisions[n]['reason']), (stamp,n+1))
            reasons.append(policy.last_reason)
            post(policy, key)
            last = index
        # Consume the unchanged response to the final matching command. From
        # this first different command onward, all responses below are
        # DECLARED CONSTRUCTED: stationary boards, real page contents, actual
        # purchases/removals and full-Home refusals. No policy state is seeded.
        index = indices[prefix_length]
        segment = copy.deepcopy(rows[last+1:index+1])
        for r in segment:
            if r['type']=='character':
                # DECLARED CONSTRUCTED missing external C dump/envelope.
                r['sequence'] = index
                policy._character_dump_path.write_bytes(dump_bytes(rows[index], r['character'], self.monrace))
        _consume_response_sequence([json.dumps(r) for r in segment], policy,
            lambda _: True, self.monrace, knowledge_ledger_path=self.directory/'knowledge.jsonl')
        raw = copy.deepcopy(rows[index])
        pages = {r['store']['store_type']:r['store'] for r in reversed(rows[start:]) if r['type']=='store'}
        home = next(r for r in reversed(rows) if r.get('knowledge',{}).get('category')=='home')
        # DECLARED CONSTRUCTED reuse of 134643's observed Alchemist page for
        # Step 1.5b's new F3 response after the first divergent command.
        from test_overweight_homefull_step15b import CAPTURES as OVERWEIGHT_CAPTURES
        alchemist = next(r['store'] for r in reversed(OVERWEIGHT_CAPTURES['20261008-134643']['bot-state-fixed']['rows'])
                         if r['type'] == 'store' and r['store']['store_type'] == 4)
        pages[4] = alchemist
        # DECLARED CONSTRUCTED other buyer pages after the changed command.
        # Keep the recorded page dimensions; these empty shop shelves only
        # receive F3 sales selected by the real store acceptance predicate.
        for buyer in (0, 2, 3, 5, 6, 8):
            if buyer not in pages:
                pages[buyer] = dict(alchemist, store_type=buyer, items=[], stock_num=0)
        equipment_home_entries = 0
        completion_reason = None
        for sequence in range(80):
            board = parse_snapshot(raw, self.monrace)
            policy.observe_store_screen(board.store is not None)
            key = policy.choose_key(board)
            reason = policy.last_reason
            reasons.append(reason)
            if reason=='equipment-transaction:approach-home':
                equipment_home_entries += 1
            if reason in POLICY_FINAL_STOP_REASONS:
                break
            if reason == 'town:overweight-surplus-sold:home-full' and not policy._inventory_overweight(board):
                completion_reason = reason
            # F3 can settle before equipment's next registry arbitration.
            # Continue public choose_key through the real retirement, rather
            # than seeding its flags or discarding the retirement assertion.
            if completion_reason is not None and policy._equipment_retired_worn_item_ids:
                break
            self.assertIsNotNone(key, (stamp, reasons))
            post(policy, key)
            raw['turn'] += 11
            raw['messages'] = []
            if key.startswith('~9'):
                policy.consume_home_knowledge(tuple(_parse_items(home['knowledge']['items'], protocol=3)))
            elif key.startswith('Cf'):
                policy.observe_character_snapshot(character)
                policy._character_calibration = derive_equipped_calibration(
                    parse_character_sheet(dump_bytes(raw, character, self.monrace)),
                    policy.with_known_skill_exp(parse_snapshot(raw, self.monrace)), character,
                    sequence=sequence+100, session_id=policy._calibration_session_id)
                policy._character_calibration_loaded = True
            elif key.startswith('{'):
                # DECLARED CONSTRUCTED actual inscription response.
                tag = policy._batch_sell_pending['entries'][0]['tag']
                target = next(i for i in board.inventory if i.slot == key[1])
                for item in raw['inventory']:
                    if item['slot'] == target.slot:
                        item['name'] = policy._sale_item_identity(target)[0]+' {@'+str(tag)+'}'
                        item['inscription'] = '@'+str(tag)
            elif key.startswith('d') and raw.get('store') and raw['store']['store_type'] != STORE_HOME:
                # DECLARED CONSTRUCTED accepted F3 surplus-sale effect.
                pending = policy._overweight_surplus_disposal['pending']
                target = next(i for i in board.inventory if policy._sale_item_identity(i) == pending['identity'])
                count = pending['count']
                raw['inventory'] = [dict(i, count=i['count']-count) if i['slot'] == target.slot else i
                                    for i in raw['inventory'] if i['slot'] != target.slot or i['count'] > count]
                raw['player']['gold'] += count*75
            elif key.startswith('01k'):
                raw['inventory'] = [i for i in raw['inventory'] if i['slot']!=key[3]]
                for slot, item in enumerate(raw['inventory']):
                    item['slot'] = chr(97+slot)
            elif key.startswith('p') and raw.get('store'):
                # The recorded staff purchase effect, including weight and
                # charges, is an external response to the new purchase key.
                ware = next(i for i in board.store.items if i.letter==key[1])
                recorded = next(i for i in rows[indices[-1]]['inventory']
                    if (i['tval'],i['sval'])==(ware.tval,ware.sval) and i.get('charges')==ware.charges)
                item = copy.deepcopy(recorded)
                item['slot'] = chr(97+len(raw['inventory']))
                raw['inventory'].append(item)
                raw['player']['gold'] -= ware.price
                if key.endswith('\x1b'):
                    raw.pop('store',None); raw['type']='player_turn'
            elif key.startswith('d') and raw.get('store') and raw['store']['store_type']==STORE_HOME:
                raw.pop('store',None); raw['type']='player_turn'
                raw['messages']=['Your home is full']
            elif key.startswith('\x1b'):
                raw.pop('store',None); raw['type']='player_turn'
                if key.startswith('\x1b`n'):
                    store = ord(key[key.index('`n')+2])-33
                    self.assertIn(store, pages, (stamp,key,reason))
                    pos = policy._town_map.stores[store]
                    raw['player'].update(x=pos.x,y=pos.y)
                    raw['store']=copy.deepcopy(pages[store]);raw['type']='store'
            elif key in ('1','2','3','4','6','7','8','9'):
                dy,dx={'1':(1,-1),'2':(1,0),'3':(1,1),'4':(0,-1),'6':(0,1),'7':(-1,-1),'8':(-1,0),'9':(-1,1)}[key]
                raw['player']['x']+=dx;raw['player']['y']+=dy
            elif key not in ('5','\x13',''):
                self.fail((stamp,'unmodeled command',key,reason,reasons))
            if key in ('1','2','3','4','6','7','8','9','5') and not raw.get('store'):
                pos = Position(raw['player']['y'],raw['player']['x'])
                store = next((s for s,door in policy._town_map.stores.items() if door==pos),None)
                if store is not None:
                    raw['store']=copy.deepcopy(pages[store]);raw['type']='store'
        self.assertEqual(completion_reason, 'town:overweight-surplus-sold:home-full', (stamp,reasons))
        self.assertLessEqual(equipment_home_entries, 1)
        self.assertNotIn('equipment-transaction:home-route-repeat-terminal', reasons)
        self.assertTrue(policy._equipment_retired_worn_item_ids)
        self.assertEqual(policy._equipment_home_deposit_tombstone['reason'],
                         'town:work-closed:impossible:equipment-transaction:home-full')
        self.assertFalse(policy._inventory_overweight(board))

    def test_pin1_recorded_134416_from_process_start(self):
        self.replay_incident('20261008-134416',
            [41,43,46,47,49,50,51,52,53,54,56,57,59,61,62,65,66,67,70,71,73,74,75,76,77,78,79],39,1)

    def test_pin1_recorded_191943_from_process_start(self):
        self.replay_incident('20261008-191943',
            [49,51,53,57,59,61,62,65,66,68,69,70,71,73,74],47,1)

    def test_pin2_nonoverweight_confirmed_loadout_departure(self):
        policy, board = self.closed_policy()
        # DECLARED CONSTRUCTED: a lighter pack; the current worn kit is unchanged.
        board = replace(board, inventory=tuple(replace(i, weight=0) for i in board.inventory),
                        recall_depth=49, dungeon_recall_depths={k: min(v,49) for k,v in board.dungeon_recall_depths.items()})
        preparation = self.failure_preparation(policy, board)
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        depth = policy._equipment_departure_destination_depth(board)
        self.assertFalse(policy._inventory_overweight(board))
        self.assertFalse(policy._missing_required_abilities(board, depth))
        self.assertTrue(policy._safe_optional_equipment_failure_departure(board, preparation))
        self.assertTrue(policy._retire_actionless_equipment_failure(board))
        policy._confirm_optional_equipment_failure_departure(board, '>')
        record = policy._equipment_optional_failure_departure
        self.assertEqual(record['reason'], 'optional-optimization-failure-confirmed-loadout')
        self.assertTrue(record['posted'])
        self.assertEqual(record['item_ids'], sorted(policy._equipment_retired_worn_item_ids))

    def test_pin4_rearm_forgiveness_and_relief_preserve_tombstone(self):
        policy, board = self.closed_policy()
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        policy._town_turn_arbiter.forgive_retirement()
        policy._set_town_store_attempted(STORE_HOME, board.turn, 'other-home-owner')
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        # DECLARED CONSTRUCTED completed relief with no remaining deposits.
        policy._home_full_relief = {'deposits': (), 'remaining': 1,
                                   'sale': (('declared removed surplus',75,1), 4, 0),
                                   'withdrawn': True, 'mode': 'destroy',
                                   'town': policy._effective_town_id(board)}
        policy._home_full_relief_key(board)
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        self.assertIsNone(policy._home_full_relief)

    def test_pin5_observed_space_clears_tombstone(self):
        policy, board = self.closed_policy()
        home = self.board(home=True)
        policy._record_observed_home_addresses(home)
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        # DECLARED CONSTRUCTED external Home capacity change.
        roomy = replace(home, store=replace(home.store, stock_num=home.store.capacity-1))
        policy._record_observed_home_addresses(roomy)
        self.assertFalse(policy._equipment_home_full_refused_this_visit())

    def test_pin5_new_visit_clears_tombstone(self):
        policy, board = self.closed_policy()
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        policy.observe_town_visit_epoch(False, board.turn+1)
        policy.observe_town_visit_epoch(True, board.turn+2)
        self.assertFalse(policy._equipment_home_full_refused_this_visit())

    def test_pin6_restart_full_page_refires_without_refusal(self):
        policy = self.policy()
        home = self.board('20261008-191943', home=True)
        policy.prime(home)
        policy._record_observed_home_addresses(home)
        policy._equipment_transaction_session = self.deposit_session(home)
        key = policy._equipment_transaction_home_key(home)
        self.assertEqual(key, '\x1b')
        self.assertEqual(policy.last_reason, 'equipment-transaction:deposit-home-full')
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        self.assertIsNone(policy._equipment_transaction_session)

    def test_posted_equipment_deposit_full_message_sets_tombstone(self):
        policy = self.policy()
        home = self.board(home=True)
        policy.prime(home)
        session = self.deposit_session(home)
        policy._equipment_transaction_session = session
        # DECLARED CONSTRUCTED posted deposit and actual refusal response;
        # the legacy weight-deposit ledger is deliberately absent.
        observation = EquipmentTransactionObservation.create(in_home=True,
            pack_identities=tuple(equipment_identity(i) for i in home.inventory))
        self.assertTrue(session.dispatch(session.current_action, observation))
        outside = replace(home, store=None, messages=('Your home is full',))
        policy._observe_home_atomic_deposit_outside(outside)
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        self.assertIn('deposit-refused', session.blockers)
        self.assertIsNone(policy._home_atomic_deposit_pending)

    def test_pin7_equip_only_still_executes_and_withdrawn_item_stays(self):
        policy, board = self.closed_policy()
        session = self.deposit_session(board, kind='equip', phase=PHASE_EQUIP)
        # DECLARED CONSTRUCTED pack item assigned to its legal wearable slot.
        action = replace(session.current_action, target_slot='main_hand')
        session = EquipmentTransactionSession(EquipmentTransactionPlan((action,), (), 0))
        policy._equipment_transaction_session = session
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        inventory = board.inventory
        key = policy._equipment_transaction_town_key(board)
        self.assertTrue(key.startswith('w'), (key, policy.last_reason))
        self.assertEqual(policy.last_reason, 'equipment-transaction:equip')
        self.assertEqual(board.inventory, inventory)

    def test_pin8_deeper_missing_abilities_blocks_departure(self):
        policy, board = self.closed_policy()
        # DECLARED CONSTRUCTED actual recall landing at 81F, without +25 speed.
        board = replace(board, recall_depth=81,
                        dungeon_recall_depths={k:81 for k in board.dungeon_recall_depths})
        preparation = self.failure_preparation(policy, board)
        self.assertTrue(policy._missing_required_abilities(board, 81))
        self.assertFalse(policy._safe_optional_equipment_failure_departure(board, preparation, destination_depth=81))
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        self.assertEqual(policy._equipment_departure_destination_depth(board), 81)
        self.assertTrue(policy._retire_actionless_equipment_failure(board))
        # DECLARED CONSTRUCTED pending recall command targeting the observed
        # 81F landing; final confirmation must still refuse its missing kit.
        policy._read_binding = (TVAL_SCROLL, SV_SCROLL_WORD_OF_RECALL, 'declared recall')
        policy._pending_recall_dungeon_id = board.recall_dungeon_id
        policy._confirm_optional_equipment_failure_departure(board, 'rh')
        self.assertIsNone(policy._equipment_optional_failure_departure)
        self.assertFalse(policy._dungeon_entry_allowed(board, via_recall=True, destination_depth=81))
        self.assertEqual(policy.last_reason, 'depth-gate:destination-81:missing-destruction,speed+25,telepathy')

    def test_pin3_recorded_s9_s10_does_not_repost_or_approach(self):
        rows = CAPTURES['20261007-044510']['bot-decisions']['rows']
        self.assertEqual(rows[8]['reason'], 'equipment-transaction:deposit-home-full')
        self.assertEqual(rows[9]['reason'], 'equipment-transaction:atomic-deposit')
        states = CAPTURES['20261007-044510']['bot-state-fixed']['rows']
        home = parse_snapshot(states[43], self.monrace)
        outside = parse_snapshot(states[44], self.monrace)
        policy = self.policy()
        policy.prime(home)
        # DECLARED CONSTRUCTED: absent checkpoint; the captured next deposit
        # is rebuilt over the recorded pack, using the homefull3 pattern.
        policy._equipment_transaction_session = self.deposit_session(home)
        policy._record_observed_home_addresses(home)
        self.assertEqual(policy._equipment_transaction_home_key(home), '\x1b')
        self.assertEqual(policy.last_reason, rows[8]['reason'])
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        policy._equipment_transaction_session = self.deposit_session(outside)
        policy._equipment_transaction_town_key(outside)
        self.assertNotIn(policy.last_reason, (
            'equipment-transaction:atomic-deposit', 'equipment-transaction:approach-home'))
        self.assertTrue(policy._equipment_home_full_refused_this_visit())

    def test_pin4_suppliers_and_other_home_owners_keep_the_route(self):
        policy, board = self.closed_policy()
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        equipment = [TownNeed(STORE_HOME, category, 'home-first')
                     for category in ('equipment-work', 'equipment-transaction')]
        # DECLARED CONSTRUCTED supplier inputs: isolate category filtering,
        # with the real map, reachability, stock and supply evaluators intact.
        with patch.object(policy, '_departure_blocking_town_needs', return_value=equipment):
            supplier, exhausted = policy._departure_supplier_core(board)
        self.assertNotEqual(supplier, STORE_HOME)
        for category in ('identify-staff', 'identification-withdrawal', 'weight-overload'):
            needs = [*equipment, TownNeed(STORE_HOME, category, 'home-first')]
            with patch.object(policy, '_departure_blocking_town_needs', return_value=needs):
                self.assertEqual(policy._departure_supplier_core(board)[0], STORE_HOME)
        for owner in ('home-visit', 'home-errand'):
            self.assertIsNotNone(policy._shopping_approach_step(board, STORE_HOME, requester=owner))
        self.assertIsNotNone(policy._overweight_home_deposit(board))
        self.assertTrue(policy._equipment_home_full_refused_this_visit())

    def test_tombstone_retires_equipment_while_independent_deposit_settles(self):
        policy, board = self.closed_policy()
        self.failure_preparation(policy, board)
        # DECLARED CONSTRUCTED independent overweight Home command awaiting
        # its actual effect. Closing equipment must not grant its departure.
        item = board.inventory[0]
        policy._home_atomic_deposit_pending = (
            ((policy._item_signature(item), item.count, 1),), None, board.turn, 0)
        self.assertTrue(policy._retire_actionless_equipment_failure(board))
        self.assertTrue(policy._equipment_retired_worn_item_ids)
        policy._confirm_optional_equipment_failure_departure(board, '>')
        self.assertIsNone(policy._equipment_optional_failure_departure)
        self.assertFalse(policy._equipment_optional_failure_pending['posted'])

    def test_restoration_and_withdrawn_pack_record_survive_closure(self):
        policy = self.policy()
        board = self.board()
        policy.prime(board)
        equipment = [i for i in board.inventory if i.is_equipment]
        withdrawn, deposited = equipment[:2]
        # DECLARED CONSTRUCTED interrupted transaction: the observed pack has
        # its confirmed Home take, while a different item needs depositing.
        take = EquipmentTransaction(PHASE_HOME_PREPARE, 'withdraw', 'declared-take',
                    item_identity=equipment_identity(withdrawn), move_identity=equipment_move_identity(withdrawn))
        put = EquipmentTransaction(PHASE_HOME_PREPARE, 'deposit', 'declared-put',
                    item_identity=equipment_identity(deposited), move_identity=equipment_move_identity(deposited))
        session = EquipmentTransactionSession(EquipmentTransactionPlan((take, put), (), 0))
        session.index = 1
        policy._equipment_transaction_session = session
        policy._equipment_transaction_owned_items = [(equipment_move_identity(withdrawn), 'main_hand')]
        policy._mark_equipment_home_full_unavailable(board)
        record = policy._equipment_home_deposit_tombstone
        self.assertEqual(record['withdrawn_item_ids'], [equipment_identity(withdrawn)])
        self.assertTrue(policy._close_full_home_equipment_deposit(board, session))
        restore = policy._equipment_transaction_session
        self.assertTrue(policy._equipment_transaction_restoring)
        self.assertEqual([a.phase for a in restore.plan.actions], [PHASE_EQUIP])
        self.assertIn(withdrawn, board.inventory)
        self.assertFalse(policy._retire_actionless_equipment_failure(board))
        policy._mark_equipment_home_full_unavailable(board)
        self.assertIs(policy._equipment_home_deposit_tombstone, record)

    def test_fresh_optimizer_and_rearm_reject_only_home_deposit_plan(self):
        policy = self.policy()
        board = self.board()
        # DECLARED CONSTRUCTED unused, fully known pack armour: the actual
        # planner deposits it before the selected Home light withdrawal.
        armour = next(i for i in board.equipment if i.slot=='feet')
        surplus = replace(armour, slot='r', name='Declared useless boots',
                          pval=0, to_a=-100, known_flags=frozenset(),
                          is_ego=False, is_artifact=False)
        board = replace(board, inventory=(*board.inventory, surplus))
        policy.prime(board)
        rows = CAPTURES['20261008-134416']['bot-state-fixed']['rows']
        skill = next(r for r in reversed(rows) if r.get('knowledge',{}).get('category')=='skill_exp')
        policy.consume_skill_knowledge(skill)
        board = policy.with_known_skill_exp(board)
        home = next(r for r in reversed(rows) if r.get('knowledge',{}).get('category')=='home')
        from hengbot.model import _parse_items
        catalogue = tuple(_parse_items(home['knowledge']['items'], protocol=3))
        policy.consume_home_knowledge(catalogue)
        character = next(r['character'] for r in reversed(rows) if r['type']=='character')
        # DECLARED CONSTRUCTED missing C dump, derived from captured visible
        # stats. This is a computed observation, never a fake optimizer result.
        raw = next(r for r in reversed(rows) if r['type']=='player_turn')
        policy.observe_character_snapshot(character)
        policy._character_calibration = derive_equipped_calibration(
            parse_character_sheet(dump_bytes(raw, character)), policy.with_known_skill_exp(board),
            character, sequence=1, session_id=policy._calibration_session_id)
        policy._character_calibration_loaded = True
        policy._record_observed_home_addresses(self.board(home=True))
        policy._mark_equipment_home_full_unavailable(board)
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        policy._refresh_carried_equipment_catalog(board)
        preparation = policy._prepare_equipment_optimization(board)
        self.assertEqual(preparation.blockers, ('equipment-transaction-failed',))
        self.assertIsNone(preparation.transaction)
        self.assertTrue(policy._equipment_home_full_refused_this_visit())
        policy._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        policy._equipment_optimization_signature = None
        preparation = policy._prepare_equipment_optimization(board)
        self.assertEqual(preparation.blockers, ('equipment-transaction-failed',))
        self.assertIsNone(policy._equipment_transaction_session)
        self.assertNotIn(STORE_HOME, policy._town_visit_ledger.blocked_stores)

    def test_restore_defaults_and_preserves_tombstone(self):
        policy, board = self.closed_policy()
        restored = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        restored._rearm_town_store_for_new_work(STORE_HOME, release_visit_bound=True)
        self.assertTrue(restored._equipment_home_full_refused_this_visit())
        del policy._equipment_home_deposit_tombstone
        upgraded = restore_checkpoint(HengbotPolicy, checkpoint(policy))
        self.assertFalse(upgraded._equipment_home_full_refused_this_visit())

    def test_eqtxn_reserved_capture_pins_close_unexecutable_home_work_once(self):
        # Captured pins: A's `di` refusal and B's reserved torch deposit. Boards
        # used to drive the direct policy seam below are DECLARED CONSTRUCTED.
        scene_a = EQTXN_RESERVED_PINS['A']
        self.assertEqual(scene_a[1]['key'], 'di')
        self.assertEqual(scene_a[2]['reason'], 'home:identify-staff-reserve-unavailable')
        self.assertEqual(scene_a[3]['reason'],
                         'town:entrance-step-off:equipment-transaction:home-route-unavailable')
        self.assertTrue(any(row['reason'] == 'equipment-transaction:home-route-repeat-terminal'
                            for row in scene_a))

        scene_b = EQTXN_RESERVED_PINS['B']
        self.assertEqual(scene_b[0]['reason'], 'equipment-transaction:travel-home')
        self.assertEqual(scene_b[1]['reason'], 'equipment-transaction:retain-reserved')
        self.assertEqual(scene_b[1]['deposit_keep_conflict']['reserving_branch'],
                         'carry-strategy:lit_torch')

        # DECLARED CONSTRUCTED continuation: preserve a live Home deposit action,
        # then feed the captured retained-item verdict through the real Home seam.
        policy = self.policy()
        home = self.board(home=True)
        # DECLARED CONSTRUCTED roomy Home page for the reservation refusal.
        home = replace(home, store=replace(
            home.store, stock_num=home.store.capacity - 1
        ))
        policy.prime(home)
        # The source fixture also contains an unrelated Home-full observation.
        policy._home_capacity_observation = None
        policy._equipment_home_deposit_tombstone = None
        policy._equipment_transaction_session = self.deposit_session(home, phase=PHASE_HOME_PREPARE)
        with patch.object(policy, '_retention_reservation', return_value=1):
            self.assertEqual(policy._equipment_transaction_home_key(home), '\x1b')
        closure = policy._equipment_transaction_visit_closure
        self.assertEqual(closure['reason'], 'retain-reserved')
        self.assertEqual(closure['epoch'], policy._town_visit_epoch)
        self.assertIsNone(policy._equipment_transaction_session)

        # DECLARED CONSTRUCTED outside-Home board: the closure blocks optimizer
        # replanning for this epoch, and a new town epoch releases the latch.
        outside = replace(home, store=None)
        policy.observe_town_visit_epoch(True, outside.turn)
        self.assertIsNone(policy._prepare_equipment_optimization(outside))
        self.assertIsNone(policy._equipment_transaction_session)
        policy.observe_town_visit_epoch(False, outside.turn + 1)
        policy.observe_town_visit_epoch(True, outside.turn + 2)
        self.assertIsNone(policy._equipment_transaction_visit_closure)

    def test_eqtxn_missing_deposit_is_visit_bounded(self):
        # DECLARED CONSTRUCTED missing target on the captured Home board.
        policy = self.policy()
        board = self.board(home=True)
        # DECLARED CONSTRUCTED capacity observation; this pin is about a
        # missing planned item, not Home-full recovery.
        board = replace(board, store=replace(
            board.store, stock_num=board.store.capacity - 1
        ))
        policy.prime(board)
        action = EquipmentTransaction(
            PHASE_HOME_PREPARE, 'deposit', 'pack:missing:0',
            item_identity='captured-item-no-longer-carried',
        )
        session = EquipmentTransactionSession(
            EquipmentTransactionPlan((action,), (), 0), physical_context='home'
        )
        policy._equipment_transaction_session = session
        self.assertEqual(policy._equipment_transaction_home_key(board), '\x1b')
        self.assertEqual(policy.last_reason, 'equipment-transaction:deposit-missing')
        self.assertEqual(policy._equipment_transaction_visit_closure['reason'], 'deposit-missing')
        self.assertIsNone(policy._equipment_transaction_session)
        # DECLARED CONSTRUCTED same town board: no replacement plan this visit.
        self.assertIsNone(policy._prepare_equipment_optimization(board))
        self.assertIsNone(policy._equipment_transaction_session)


if __name__ == '__main__':
    unittest.main()
