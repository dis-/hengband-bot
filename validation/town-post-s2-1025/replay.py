import collections,cProfile,gzip,json,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(r'C:\hengband-backups\state-logs')
import tempfile
SCRATCH=Path(tempfile.gettempdir())/'town-post-s2-replay'
CAPTURES={
'a1404':(next((ROOT/'n1a-ownerburst-1025').glob('*140428*')),'state.jsonl.gz','bot-decisions.jsonl.gz'),
'a1426':(next((ROOT/'n1a-ownerburst-1025').glob('*142631*')),'state.jsonl.gz','bot-decisions.jsonl.gz'),
'b':(ROOT/'n1b-town-osc-1025-1906','n1b-state-tail.gz','n1b-dec-tail.gz')}
def rows(path):
 result=[]
 with gzip.open(path,'rt',encoding='utf-8') as stream:
  for line,text in enumerate(stream,1):
   try:result.append((line,json.loads(text)))
   except json.JSONDecodeError:print('SKIP_PARTIAL',path.name,line)
 return result
def evidence():
 result={}
 for name,(root,state,decision) in CAPTURES.items():
  ds=[(n,d) for n,d in rows(root/decision) if 'decision_sequence' in d]
  result[name]={'counts':collections.Counter(d['reason'] for _,d in ds),'decisions':[]}
  for line,d in ds:
   c=d.get('claim') or {}
   result[name]['decisions'].append({'line':line,
    **{k:d.get(k) for k in ('time','decision_sequence','turn','reason','key','position','store_type','player','fundraising','town_plan','departure_block','store_visit','requested_owner','requested_store','acquire_result','home_candidate_waiting','timing','equipment_optimization','arbiter','shop_selector')},
    'claim':{k:c.get(k) for k in ('owner','claim_id','state','rung','execution','terminal_admission','closed_claim','errand_deferred')}})
 (SCRATCH/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
def replay(name,tag,limit='999'):
 import tests
 from hengbot.cli import _consume_response_sequence
 from hengbot.monrace_knowledge import load_monrace_knowledge
 from tests.test_esp_threat_rest_recorded import EDIT,_policy
 root,state,decision=CAPTURES[name]
 ds=[(n,d) for n,d in rows(root/decision) if 'decision_sequence' in d]
 states=rows(root/state)
 monrace=load_monrace_knowledge(EDIT/'MonraceDefinitions.jsonc')
 trace=[]
 with TemporaryDirectory() as directory:
  directory=Path(directory)
  policy=_policy(directory,monrace)
  policy._skill_exp_request_key=lambda board: None
  policy._crossarea_fundraising_enforced=True
  policy._in_store_ops_enabled=True
  cursor=0;board=None
  for line,d in ds:
   if len(trace)>=int(limit):break
   while cursor<len(states) and states[cursor][1].get('turn',0)<=d['turn']:
    _,raw=states[cursor]
    _,boards=_consume_response_sequence([json.dumps(raw,ensure_ascii=False)],policy,lambda key:True,monrace,knowledge_ledger_path=directory/'knowledge.jsonl')
    if boards:board=boards[-1]
    cursor+=1
   if board is None or board.turn!=d['turn']:continue
   profile=cProfile.Profile();start=time.perf_counter();profile.enable()
   key=policy.choose_key(board)
   profile.disable();elapsed=time.perf_counter()-start
   c=policy.decision_claim or {}
   record={'line':line,'sequence':d['decision_sequence'],'turn':d['turn'],
    'recorded':[d['key'],d['reason']],'actual':[str(key) if key is not None else None,policy.last_reason],
    'seconds':elapsed,'board_store':board.store.store_type if board.store else None,
    'board_position':[board.player.position.y,board.player.position.x],
    'admissions':getattr(policy,'_decision_terminal_admissions',[]),
    'claim':{k:c.get(k) for k in ('owner','state','rung')},
    'needs':list(getattr(policy,'_town_claim_categories',())),
    'plan':repr(getattr(policy,'_town_errand_plan',None))}
   trace.append(record)
   profile.dump_stats(str(SCRATCH/(tag+'-'+name+'-'+str(d['decision_sequence'])+'.prof')))
   print(json.dumps(record,ensure_ascii=False),flush=True)
   policy.confirm_key_posted(key)
 (SCRATCH/('replay-'+tag+'-'+name+'.json')).write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
if __name__=='__main__':
 SCRATCH.mkdir(parents=True,exist_ok=True)
 if sys.argv[1]=='evidence':evidence()
 else:replay(*sys.argv[1:])
