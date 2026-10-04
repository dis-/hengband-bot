"""Sequential focused modules only. Never starts a live process or full suite."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.shadow3-validation'
MODULES = (
    'test_shadow3_recorded', 'test_ownership_s3_3_delegation_record',
    'test_ownership_s3_3_first_divergence', 'test_ownership_s3_3_live_short_route',
    'test_s33_batch_admission', 'test_s33_batch_context', 'test_s33_batch_reconciliation',
    'test_s33_batch_replay', 'test_s33_phase2_equipment', 'test_s33_phase2_idle',
    'test_s33_phase2_quest', 'test_s33_shadow', 'test_s33_shadow_recorded', 'test_s33_shadow_report',
    'test_policy_shop', 'test_policy_home', 'test_loot_triage',
    'test_town_loot_store_20260926_recorded', 'test_home_full_relief_recorded',
    'test_equipment_deposit_owner_recorded', 'test_equipment_transaction_session',
    'test_equipment_transaction_planner', 'test_shop_one_shot',
    'test_store_reentry_recorded', 'test_resume_inside_store', 'test_travel_interrupted_store_await',
    'test_execution_declaration', 'test_first_divergence_declarations',
    'test_home_knowledge_scan', 'test_town_producer_purity',
)


def run(modules):
    OUT.mkdir(exist_ok=True)
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(map(str,
        (ROOT/'src', ROOT/'tests', ROOT/'scripts')))}
    results = []
    for module in modules:
        if module == 'test_policy_town':
            now = datetime.datetime.now()
            if now.time() < datetime.time(19, 20):
                raise RuntimeError('test_policy_town prohibited before 19:20 local')
        started_at = datetime.datetime.now().astimezone().isoformat()
        start = time.monotonic()
        with (OUT/(module+'.txt')).open('w', encoding='utf8') as log:
            result = subprocess.run([sys.executable, '-m', 'unittest', module, '-v'],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        entry = {'module': module, 'exit': result.returncode,
                 'started_at': started_at,
                 'ended_at': datetime.datetime.now().astimezone().isoformat(),
                 'seconds': round(time.monotonic()-start, 2)}
        results.append(entry)
        with (OUT/'results.jsonl').open('a', encoding='utf8') as log:
            log.write(json.dumps(entry)+'\n')
        print(json.dumps(entry), flush=True)
    return any(r['exit'] for r in results)


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:] or MODULES))
