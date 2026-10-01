import gzip,json,re
from hengbot.policy import HengbotPolicy
from hengbot.model import parse_snapshot,_parse_items,STORE_HOME
raw=list(map(json.loads,gzip.open('tests/fixtures/live28-calibration-restore-20261001.jsonl.gz','rt',encoding='utf8')))
def board(t):return parse_snapshot(next(r for r in raw if r.get('turn')==t and r.get('type')=='player_turn'),{})
p=HengbotPolicy();p._calibration_redress_loaded=True;p._crossarea_fundraising_enforced=True;p._calibration_phase='deposit'
for t,m in [(932862,'dhdg2\rdf10\rde15\rdddc4\rdb10\rda5\r'),(932877,'dh2\rdgdfde2\rdd2\rdcdbda6\r'),(932879,'dc99\rdbda')]:
 b=board(t)
 for slot,n in re.findall(r'd([a-z])(\d*\r)?',m):p._home_deposit_key(b,next(i for i in b.inventory if i.slot==slot),forced_count=int(n) if n else 1)
p._calibration_phase='restore-supplies';p._home_page_size=52
print('DEBT',p._calibration_restore_signatures)
for t,after in [(933258,933266),(933266,933277)]:
 page=next(r for r in raw if r.get('turn')==t and r.get('knowledge',{}).get('category')=='home');p.consume_home_knowledge(tuple(_parse_items(page['knowledge']['items'])));p._shopping_approach_store_type=STORE_HOME
 k=p._atomic_home_withdraw_key(board(t),board(t).player.position);print('KEY',repr(k));print('PENDING',[(x[0],x[3]) for x in p._home_atomic_withdraw_pending[4]])
 p._observe_calibration_restore_batch(board(after),p._home_atomic_withdraw_pending);print('DEBT AFTER',p._calibration_restore_signatures)
for sig in p._calibration_restore_signatures:
 print('MISSING',sig,p._calibration_restore_move_identities.get(sig));print('CARRIED',[(i.name,p._calibration_restore_item_matches(sig,i),i.charges,i.count) for i in board(933277).inventory if i.tval==sig[1]])

