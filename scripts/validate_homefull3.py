"""Run only the authorized related modules, each in its own sequential process."""
import json,os,pathlib,re,subprocess,sys,time
root=pathlib.Path(__file__).resolve().parents[1]
out=root/'validation'/'homefull3';out.mkdir(parents=True,exist_ok=True)
modules=['test_policy_home','test_policy_shop','test_home_full_relief_recorded','test_home_deposit_hang_recorded','test_homefull3_recorded','test_home_full_await_knowledge_recorded','test_home_route_release_recorded','test_home_errand','test_home_disposal','test_home_equipment_disposal','test_ownership_s3_3_delegation_record','test_ownership_s3_3_first_divergence','test_ownership_s3_3_live_short_route']
modules += [p.stem for p in sorted((root/'tests').glob('test_s33_*.py'))]
modules += ['test_execution_declaration','test_test_fakery_lint','test_policy_town']
if len(sys.argv) > 1:
 modules = sys.argv[1:]
results_path = out/'test-results.json'
results = json.loads(results_path.read_text(encoding='utf8')) if results_path.exists() else []
for module in modules:
 print('START',module,flush=True);start=time.monotonic()
 env={**os.environ,'PYTHONPATH':os.pathsep.join(map(str, (root, root/'src', root/'tests', root/'scripts'))),'PYTHONUTF8':'1'}
 run=subprocess.run([sys.executable,'-X','utf8','-m','unittest',module],cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8')
 (out/(module+'.log')).write_text(run.stdout,encoding='utf8')
 count=re.search(r'Ran (\d+) tests?',run.stdout)
 result={'module':module,'exit_code':run.returncode,'tests':int(count[1]) if count else None,'seconds':round(time.monotonic()-start,2),'summary':run.stdout[-1500:] if run.returncode else run.stdout.strip().splitlines()[-1]}
 results = [entry for entry in results if entry['module'] != module]
 results.append(result);results_path.write_text(json.dumps(results,indent=2),encoding='utf8')
 print('RESULT',json.dumps(result),flush=True)
 if run.returncode: print(run.stdout[-6000:],flush=True)
