import subprocess,sys,os
from pathlib import Path
paths=['src/hengbot/policy.py','src/hengbot/policy_home.py','src/hengbot/policy_calibration.py']
saved={p:Path(p).read_bytes() for p in paths}
try:
 for p in paths: Path(p).write_bytes(subprocess.check_output(['git','show','08fef4dc:'+p]))
 env=dict(os.environ,PYTHONPATH='src;tests;scripts')
 result=subprocess.run([sys.executable,'-m','unittest','tests.test_calibration_live28'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 Path('validation/live28/pin-revert.log').write_bytes(result.stdout)
 print('single revert exit',result.returncode);print(result.stdout.decode('utf8',errors='replace')[-4500:])
 if result.returncode==0: raise SystemExit('ERROR: pin survived revert')
finally:
 for p,data in saved.items():Path(p).write_bytes(data)
