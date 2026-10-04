"""Run recorded regression pins against base-source copies, never revert the worktree."""
import json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation'/'homefull3'
BASE='f7dfbcb1'
FILES=['policy.py','policy_home.py','claim_goal_typing.py']
PINS=[
 'test_homefull3_recorded.RecordedHomeFull3Test.test_A_released_partial_deposit_keeps_home_owner_with_detected_townspeople',
 'test_homefull3_recorded.RecordedHomeFull3Test.test_B_first_outside_home_withdraws_instead_of_routing_to_alchemist',
 'test_homefull3_recorded.RecordedHomeFull3Test.test_C_stale_catalogue_has_owner_declared_request_and_wait',
 'test_homefull3_recorded.ConstructedDiscardTest.test_D_autodestroy_first_and_waits_for_destroy_effect_before_deposit',
 'test_homefull3_recorded.ConstructedDiscardTest.test_D_unknown_is_identified_then_revalidated_before_destroy',
]
results=[]
for mode in ['base','without_town_handoff_fix','without_knowledge_owner_fix','without_destruction']:
 target=OUT/('source-final-'+mode)/'src'
 if target.exists():
  raise SystemExit(f'refusing to overwrite existing source copy: {target}')
 shutil.copytree(ROOT/'src',target,ignore=shutil.ignore_patterns('__pycache__'))
 if mode=='base':
  for name in FILES:
   data=subprocess.check_output(['git','show',f'{BASE}:src/hengbot/{name}'],cwd=ROOT)
   (target/'hengbot'/name).write_bytes(data)
 elif mode=='without_town_handoff_fix':
  path=target/'hengbot'/'policy.py';text=path.read_text(encoding='utf8')
  text=text.replace('and not self._physical_hostiles(snapshot)):', 'and not any(monster.hostile for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters))):')
  text=text.replace('and not self._physical_hostiles(snapshot)\n                and self._home_atomic_deposit_pending', 'and not any(monster.hostile for monster in (*snapshot.visible_monsters, *snapshot.detected_monsters))\n                and self._home_atomic_deposit_pending')
  path.write_text(text,encoding='utf8')
 elif mode=='without_knowledge_owner_fix':
  # Restore all C changes from the base, retaining A/B and destruction logic.
  path=target/'hengbot'/'policy.py';text=path.read_text(encoding='utf8')
  start=text.index('        if (snapshot.in_town and self._home_errand.needs_knowledge\n',text.index('    def _decide('))
  end=text.index('        if (snapshot.in_town and snapshot.store is None\n',start)
  text=text[:start]+text[end:]
  text=text.replace('                return self._home_errand_knowledge_key(snapshot)\n            else:', '                self.last_reason = self._home_errand.reason("request-knowledge")\n            else:')
  path.write_text(text,encoding='utf8')
  path=target/'hengbot'/'policy_home.py';text=path.read_text(encoding='utf8')
  text=text.replace('            if self._home_errand.active:\n                return self._home_errand_knowledge_key(snapshot)\n','')
  path.write_text(text,encoding='utf8')
 elif mode=='without_destruction':
  path=target/'hengbot'/'policy_home.py';text=path.read_text(encoding='utf8')
  start=text.index('                discard = [candidate for stock in self._home_knowledge_items')
  end=text.index('            signature = self._item_signature(item)',start)
  text=text[:start]+('                self._town_blocked_reason = "home-full-no-sellable-surplus"\n'
                    '                return self._town_blocked_key(snapshot)\n'
                    '            item, store_type, _value = max(candidates, key=lambda result: result[2])\n')+text[end:]
  path.write_text(text,encoding='utf8')
 selected=PINS if mode=='base' else PINS[:2] if mode=='without_town_handoff_fix' else PINS[2:3] if mode=='without_knowledge_owner_fix' else PINS[3:]
 env={**os.environ,'PYTHONPATH':os.pathsep.join(map(str,(target,ROOT,ROOT/'tests',ROOT/'scripts'))),'PYTHONUTF8':'1'}
 run=subprocess.run([sys.executable,'-X','utf8','-m','unittest',*selected],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8')
 (OUT/('revert-'+mode+'.log')).write_text(run.stdout,encoding='utf8')
 result={'mode':mode,'exit_code':run.returncode,'pins':len(selected),'summary':run.stdout[-1800:]}
 results.append(result);print(json.dumps(result),flush=True)
 if run.returncode==0:
  raise SystemExit(f'revert-proof failed: {mode} unexpectedly passed')
(OUT/'revert-results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
