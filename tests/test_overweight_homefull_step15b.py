"""Step 1.5b pins over immutable 10-08 captures.

DECLARED CONSTRUCTED: no policy checkpoints were captured. Unit relief/retry
bindings isolate the recorded seams. After a changed command, store pages,
inscription/removal effects, rebought stacks and mining state are constructed
external alternatives; no selector, retention or departure gate is replaced.
"""
from __future__ import annotations

import copy
from dataclasses import replace
import gzip
import hashlib
import json
import pickle
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import tests  # noqa: F401
from hengbot.cli import _consume_response_sequence, _PolicyObserverScope
from hengbot.item_reservation import reserved_item_command
from hengbot.model import parse_snapshot, _parse_items, STORE_HOME, STORE_ALCHEMIST
from hengbot.policy_state import normalize_policy_state
from hengbot.policy_constants import POLICY_FINAL_STOP_REASONS
from test_esp_threat_rest_recorded import EDIT, _policy
from hengbot.monrace_knowledge import load_monrace_knowledge
from test_equipment_homefull_step15a import post

FIXTURE = Path(__file__).parent / 'fixtures/step1.5b-overweight.json.gz'
FIXTURE_SHA256 = 'a9b78bf70843cb35ab40f5f26539dc14549dd9bd8162c522708f48d631cb87f4'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
CAPTURES = json.loads(gzip.decompress(FIXTURE.read_bytes()))


class OverweightHomeFullStep15bTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monrace = load_monrace_knowledge(EDIT / 'MonraceDefinitions.jsonc')

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.env = patch.dict('os.environ', {'HENGBOT_RUNTIME_DIR': str(self.directory)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def policy(self, board):
        policy = _policy(self.directory, self.monrace)
        policy.prime(board)
        return policy

    def raw(self, stamp, turn=None, home=False):
        rows = CAPTURES[stamp]['bot-state-fixed']['rows']
        return next(r for r in reversed(rows)
                    if r['type'] == ('store' if home else 'player_turn')
                    and (turn is None or r['turn'] == turn)
                    and (not home or r['store']['store_type'] == STORE_HOME))

    def stock(self, policy, stamp):
        rows = CAPTURES[stamp]['bot-state-fixed']['rows']
        row = next(r for r in reversed(rows) if r.get('knowledge', {}).get('category') == 'home')
        policy.consume_home_knowledge(tuple(_parse_items(row['knowledge']['items'], protocol=3)))

    def relief(self, policy, board):
        # DECLARED CONSTRUCTED unit binding; captured pack, counts and full
        # catalogue remain unchanged, and the real relief selector runs.
        first = policy._overweight_home_deposit(board)
        self.assertIsNotNone(first)
        entries = tuple((policy._item_signature(i), i.count, n)
                        for i, n in policy._home_deposit_batch(board, first))
        policy._begin_home_full_relief(board, entries, refused=True)

    def sale_board(self, board, stamp='20261008-134643'):
        # DECLARED CONSTRUCTED reuse of the recorded Alchemist page at s28.
        row = next(r for r in reversed(CAPTURES[stamp]['bot-state-fixed']['rows'])
                   if r['type'] == 'store' and r['store']['store_type'] == STORE_ALCHEMIST)
        return replace(board, store=parse_snapshot(row, self.monrace).store)

    def dispose(self, policy, board):
        """Real producer + real sale inscription; constructed game effects."""
        sold = []
        for _ in range(30):
            if getattr(policy, '_overweight_surplus_disposal', None) is None:
                break
            key = policy._overweight_surplus_sale_key(board)
            self.assertNotIn(policy.last_reason, POLICY_FINAL_STOP_REASONS)
            self.assertIsNotNone(key)
            post(policy, key)
            state = policy._overweight_surplus_disposal
            pending = state.get('pending') if state else None
            if key.startswith('{'):
                # DECLARED CONSTRUCTED inscription response, preserving the
                # sale identity and merging the game's display annotation.
                tag = policy._batch_sell_pending['entries'][0]['tag']
                board = replace(board, inventory=tuple(
                    replace(i, name=policy._sale_item_identity(i)[0]+' {@'+str(tag)+'}',
                            inscription='@'+str(tag))
                    if policy._sale_item_identity(i) == pending['identity'] else i
                    for i in board.inventory))
            elif pending and pending.get('posted'):
                # DECLARED CONSTRUCTED accepted sale/removal and its gold
                # delta. Count comes from the real _batch_sale_entry.
                count = pending['count']
                identity = pending['identity']
                sold.append((identity, count))
                board = replace(board, player=replace(board.player, gold=board.player.gold+count*75),
                    inventory=tuple(replace(i, count=i.count-count)
                        if policy._sale_item_identity(i) == identity else i
                        for i in board.inventory
                        if policy._sale_item_identity(i) != identity or i.count > count))
            if board.store is None or key == '\x1b':
                board = self.sale_board(board)
                if pending is not None:
                    candidates = policy._overweight_surplus_candidates(board)
                    candidate = next((c for c in candidates if policy._sale_item_identity(c[2]) == pending['identity']), None)
                    if candidate and candidate[4]:
                        # DECLARED CONSTRUCTED shop response for the selected
                        # real buyer; page dimensions reused from Alchemist.
                        board = replace(board, store=replace(board.store, store_type=candidate[4][0]))
        return board, sold

    def test_pin1_175411_open_full_page_relief_then_surplus_sale(self):
        rows = CAPTURES['20261008-175411']['bot-state-fixed']['rows']
        # Last session begins at s1; no constructed policy state. Normal
        # consumers supply the s1 census; the first differing command is s2.
        board = parse_snapshot(rows[54], self.monrace)
        policy = self.policy(board)
        _consume_response_sequence([json.dumps(r) for r in rows[51:55]], policy,
            lambda _: True, self.monrace, knowledge_ledger_path=self.directory/'knowledge.jsonl')
        for r in rows[51:55]:
            if r.get('knowledge', {}).get('category') == 'skill_exp':
                policy.consume_skill_knowledge(r)
        key = policy.choose_key(board)
        self.assertEqual((key, policy.last_reason), ('5', 'home:weight-overload-deposit'))
        post(policy, key)
        _consume_response_sequence([json.dumps(r) for r in rows[55:57]], policy,
            lambda _: True, self.monrace, knowledge_ledger_path=self.directory/'knowledge.jsonl')
        home = parse_snapshot(rows[56], self.monrace)
        key = policy.choose_key(home)
        self.assertNotEqual(key, 'dodi6\rda16\r\x1b')
        self.assertIsNone(policy._home_atomic_deposit_pending)
        self.assertIsNotNone(policy._home_full_relief)
        # DECLARED CONSTRUCTED Home census returned to the changed relief scan.
        self.stock(policy, '20261008-175411')
        policy._home_full_relief_key(home)
        self.assertIsNotNone(getattr(policy, '_overweight_surplus_disposal', None))
        board, sold = self.dispose(policy, self.sale_board(home))
        self.assertFalse(policy._inventory_overweight(board))
        self.assertIn((policy._sale_item_identity(home.inventory[0]), 16), sold)
        record = [json.loads(line) for line in (self.directory/'overweight-surplus-disposal.jsonl').read_text(encoding='utf8').splitlines()]
        self.assertTrue(any(r['reason'] == 'town:overweight-surplus-sold:home-full' and r['count'] == 16 for r in record))
        self.assertTrue(all(r['home_stock'] == 240 for r in record))

    def test_pin2_134816_equipment_block_does_not_block_overload_retry(self):
        board = parse_snapshot(self.raw('20261008-134816', 15798164, home=True), self.monrace)
        policy = self.policy(board)
        self.stock(policy, '20261008-134816')
        policy._mark_equipment_home_full_unavailable(board)
        self.relief(policy, board)
        # DECLARED CONSTRUCTED retry at the s12 refusal, same inventory.
        policy._home_full_retry_deposits = policy._home_full_relief['deposits']
        policy._home_full_relief = None
        key = policy._home_full_relief_key(board)
        self.assertIsNotNone(key)
        self.assertIsNotNone(getattr(policy, '_overweight_surplus_disposal', None))
        self.assertTrue(policy._equipment_home_full_refused_this_visit())

    def test_pin3_090841_mandatory_overload_not_deferred(self):
        board = parse_snapshot(self.raw('20261008-090841', 15650566, home=True), self.monrace)
        policy = self.policy(board)
        self.stock(policy, '20261008-090841')
        # DECLARED CONSTRUCTED missing mode-mine policy binding at this seam.
        policy._fundraising_mode = 'mine'
        self.relief(policy, board)
        policy._defer_home_full_deposit(board)
        self.assertIsNone(policy._home_full_retry_deposits)
        self.assertIsNotNone(getattr(policy, '_overweight_surplus_disposal', None))
        # DECLARED CONSTRUCTED restored mode-mine binding at the recorded
        # 090841 seam. Both Dwarf pickaxes/counts/qualities are captured.
        policy._fundraising_mode = 'mine'
        candidates = policy._overweight_surplus_candidates(board)
        # Both captured tools are required by the existing two-digger mining
        # retention. Calling the weaker one a spare cannot release it.
        self.assertFalse(any(c[2].is_digging_tool for c in candidates))
        self.assertEqual([policy._retention_surplus(board,i) for i in board.inventory if i.is_digging_tool], [0,0])
        # DECLARED CONSTRUCTED third digging tool, weaker than the two captured
        # tools. This tests an actual surplus without reducing the count gate.
        item = next(i for i in board.inventory if i.is_digging_tool and i.pval == 6)
        extra = replace(item, slot='m', pval=5, name=item.name.replace('(+6)', '(+5)'))
        # DECLARED CONSTRUCTED weight-only isolation: the third tool alone
        # exceeds STR index 0's limit. Counts/retention of the two required
        # tools and every supply remain unchanged; cheaper arrows cannot end
        # this particular disposal before the tool is exercised.
        extra = replace(extra, weight=600)
        board = replace(board, inventory=(*tuple(replace(i, weight=0) for i in board.inventory), extra),
                        equipment=tuple(replace(i, weight=0) for i in board.equipment),
                        player=replace(board.player, stat_index=(0,*board.player.stat_index[1:])))
        candidates = policy._overweight_surplus_candidates(board)
        spare = [c for c in candidates if c[2].is_digging_tool]
        self.assertEqual([(c[2].slot,c[3]) for c in spare], [('m',1)])
        after, sold = self.dispose(policy, self.sale_board(board))
        self.assertIn((policy._sale_item_identity(extra),1), sold)
        self.assertFalse(policy._inventory_overweight(after))
        self.assertEqual(sorted(i.pval for i in after.inventory if i.is_digging_tool), [6,7])

    def test_pin4_recorded_nonfull_pack_does_not_destroy_identify_staff(self):
        for stamp, turn in (('20261008-134200', 15796137),
                            ('20261008-134200', 15796149),
                            ('20261008-134643', 15796877)):
            with self.subTest(stamp=stamp, turn=turn):
                board = parse_snapshot(self.raw(stamp, turn), self.monrace)
                policy = self.policy(board)
                self.stock(policy, stamp)
                self.relief(policy, board)
                key = policy._home_full_relief_key(board)
                self.assertNotEqual(policy.last_reason, 'home:full-destroy-surplus')
                self.assertFalse(bool(key and key.startswith('01k')))

    def speed_only(self):
        home = parse_snapshot(self.raw('20261008-175411', home=True), self.monrace)
        # DECLARED CONSTRUCTED only speed surplus has disposal weight; required
        # supplies still have their recorded counts, offense and defense.
        home = replace(home, inventory=tuple(replace(i, weight=0) if i.slot != 'a' else i
                                            for i in home.inventory),
                       equipment=tuple(replace(i, weight=0) for i in home.equipment),
                       player=replace(home.player, stat_index=(0,*home.player.stat_index[1:])))
        # DECLARED CONSTRUCTED speed stack weighs 104, limit at STR index 0 is
        # 500; increase only its physical per-unit weight to create overload.
        home = replace(home, inventory=tuple(replace(i, weight=20) if i.slot == 'a' else i for i in home.inventory))
        policy = self.policy(home)
        self.stock(policy, '20261008-175411')
        self.relief(policy, home)
        policy._home_full_relief_key(home)
        return policy, home

    def test_pin5_mining_kit_and_rebought_signature_loop(self):
        # Captured s28-32 pack after buying the six mining detection scrolls.
        kit = parse_snapshot(self.raw('20261008-134643'), self.monrace)
        full_page = parse_snapshot(self.raw('20261008-134643', home=True), self.monrace)
        # DECLARED CONSTRUCTED pending stockout remedy and reuse of the full
        # Home page at the s24-28 seam, without changing the purchased kit.
        kit = replace(kit, store=full_page.store)
        kit_policy = self.policy(kit)
        self.stock(kit_policy, '20261008-134643')
        kit_policy._identify_staff_mining_plan = True
        self.relief(kit_policy, kit)
        kit_policy._home_full_relief_key(kit)
        self.assertIsNotNone(getattr(kit_policy, '_overweight_surplus_disposal', None))
        self.assertFalse(any(c[2].is_treasure_detection_scroll or c[2].is_digging_tool
                             or c[2].is_light or c[2].tval == 80
                             for c in kit_policy._overweight_surplus_candidates(kit)))
        policy, home = self.speed_only()
        self.assertIsNotNone(getattr(policy, '_overweight_surplus_disposal', None))
        # DECLARED CONSTRUCTED pending stockout remedy at the s24-28 seam.
        policy._identify_staff_mining_plan = True
        candidates = policy._overweight_surplus_candidates(home)
        self.assertFalse(any(c[2].is_treasure_detection_scroll or c[2].is_digging_tool or c[2].is_light
                             for c in candidates))
        board, sold = self.dispose(policy, self.sale_board(home))
        self.assertEqual(sold, [(policy._sale_item_identity(home.inventory[0]),16)])
        # DECLARED CONSTRUCTED necessary purchase re-arms the same surplus.
        rebought = replace(home, store=None, turn=home.turn+100)
        self.relief(policy, rebought)
        policy._home_full_relief_key(rebought)
        self.assertEqual(policy.last_reason, 'town:blocked:overweight-surplus-rebuy-loop')

    def test_pin6_fresh_process_preserves_epoch_and_loop_ledger(self):
        policy, home = self.speed_only()
        self.assertIsNotNone(getattr(policy, '_overweight_surplus_disposal', None))
        board, _ = self.dispose(policy, self.sale_board(home))
        epoch = policy._town_visit_epoch
        # DECLARED CONSTRUCTED restart/rebuy board; child is a fresh process,
        # not a cloned current policy. Durable visit epoch and signatures load.
        raw = copy.deepcopy(self.raw('20261008-175411'))
        (self.directory/'restart.json').write_text(json.dumps(raw), encoding='utf8')
        (self.directory/'restart-board.pkl').write_bytes(pickle.dumps(home))
        rows = CAPTURES['20261008-175411']['bot-state-fixed']['rows']
        census = next(r for r in reversed(rows) if r.get('knowledge', {}).get('category') == 'home')
        (self.directory/'restart-home.json').write_text(json.dumps(census), encoding='utf8')
        program = '''import sys,json,pickle
from pathlib import Path
sys.path[:0]=[sys.argv[2],sys.argv[2]+'/src',sys.argv[2]+'/tests']
import tests
from test_esp_threat_rest_recorded import _policy,EDIT
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.model import parse_snapshot,_parse_items
m=load_monrace_knowledge(EDIT/'MonraceDefinitions.jsonc')
p=_policy(Path(sys.argv[1]),m)
b=pickle.loads((Path(sys.argv[1])/'restart-board.pkl').read_bytes())
p.prime(b)
h=json.loads((Path(sys.argv[1])/'restart-home.json').read_text())
p.consume_home_knowledge(tuple(_parse_items(h['knowledge']['items'],protocol=3)))
i=p._overweight_home_deposit(b)
p._begin_home_full_relief(b,tuple((p._item_signature(t),t.count,n) for t,n in p._home_deposit_batch(b,i)),refused=True)
p._home_full_relief_key(b)
print(json.dumps({'epoch':p._town_visit_epoch,'sold':getattr(p,'_overweight_surplus_ledger',{}).get('sold',[]),'reason':p.last_reason}))
'''
        script = self.directory/'restart_probe.py'
        script.write_text(program, encoding='utf8')
        result = subprocess.run([sys.executable, str(script), str(self.directory), str(Path(__file__).resolve().parents[1])],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        restored = json.loads(result.stdout.strip())
        self.assertEqual(restored['epoch'], epoch)
        self.assertEqual(restored['reason'], 'town:blocked:overweight-surplus-rebuy-loop')
        self.assertEqual(restored['sold'], [list(policy._sale_item_identity(home.inventory[0]))])

    def test_pin7_insufficient_surplus_stops_immediately(self):
        home = parse_snapshot(self.raw('20261008-175411', home=True), self.monrace)
        # DECLARED CONSTRUCTED unsheddable equipment weight; no item counts or
        # departure targets change, surplus cannot cover this physical excess.
        home = replace(home, equipment=tuple(replace(i, weight=i.weight+5000) for i in home.equipment))
        policy = self.policy(home)
        self.stock(policy, '20261008-175411')
        self.relief(policy, home)
        policy._home_full_relief_key(home)
        self.assertEqual(policy.last_reason, 'town:blocked:overweight-home-full-no-legal-relief')

    def test_pin8_partial_destroy_sink_retains_counts_and_files_are_isolated(self):
        policy, home = self.speed_only()
        self.assertIsNotNone(getattr(policy, '_overweight_surplus_disposal', None))
        item = home.inventory[0]
        key = reserved_item_command(policy, home, 'overweight-surplus', item, 'shop-sell')
        self.assertEqual(key, '016ka')
        self.assertEqual(item.count-policy._retention_surplus(home,item),10)
        self.dispose(policy, self.sale_board(home))
        self.assertTrue((self.directory/'overweight-surplus-disposal.jsonl').exists())
        restored = copy.deepcopy(policy)
        for attribute in ('_home_store_block_owner','_overweight_surplus_disposal','_overweight_surplus_ledger',
                          '_overweight_surplus_record_path','_overweight_surplus_ledger_path'):
            del restored.__dict__[attribute]
        restored._policy_state_version = 4  # DECLARED CONSTRUCTED old checkpoint.
        normalize_policy_state(restored)
        self.assertIsNone(restored._overweight_surplus_disposal)
        self.assertEqual(restored._overweight_surplus_ledger, {'epoch':None,'sold':[]})
        # DECLARED CONSTRUCTED unbuyable junk in the recorded speed slot. The
        # real store acceptance gates prove that every store refuses it.
        junk = replace(item, tval=1, sval=1, name='declared unbuyable junk', count=26)
        outside = replace(home, store=None, inventory=(junk,*home.inventory[1:]))
        self.relief(policy, outside)
        key = policy._home_full_relief_key(outside)
        self.assertEqual(key, '026ka')
        post(policy, key)
        effect = replace(outside, inventory=outside.inventory[1:])
        # A telemetry evaluator reaches the real effect observer; both policy
        # bindings and durable sidecars must roll back byte-for-byte.
        ledger = self.directory/'overweight-surplus-ledger.json'
        audit = self.directory/'overweight-surplus-disposal.jsonl'
        before = (ledger.read_bytes(), audit.read_bytes())
        with _PolicyObserverScope(policy):
            policy._overweight_surplus_sale_key(effect)
        self.assertEqual((ledger.read_bytes(),audit.read_bytes()),before)
        policy._overweight_surplus_sale_key(effect)
        self.assertEqual(policy.last_reason, 'town:overweight-surplus-destroyed:home-full')
        record = json.loads(audit.read_text(encoding='utf8').splitlines()[-1])
        self.assertEqual((record['count'],record['price'],record['weight_after']), (26,0,0))
