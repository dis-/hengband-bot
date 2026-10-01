import os, subprocess, sys, pathlib
root=pathlib.Path('validation/batchfixA')
env=dict(os.environ,PYTHONPATH='src;tests;scripts')
for module in sys.argv[1:]:
    p=subprocess.run([sys.executable,'-m','unittest','tests.'+module],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log=p.stdout.decode('utf8','replace')
    (root/(module+'.log')).write_text(log,encoding='utf8')
    print(module,p.returncode,log[-650:],flush=True)
