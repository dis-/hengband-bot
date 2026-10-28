"""Record a command's actual exit status and UTF-8 output."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

out = Path(__file__).resolve().parent
root = out.parents[1]
name, *command = sys.argv[1:]
command = [sys.executable if value == 'PYTHON' else value for value in command]
env = dict(os.environ, PYTHONPATH='src;tests;scripts', PYTHONIOENCODING='utf-8',
           PYTHONPYCACHEPREFIX=str(out / 'pycache'))
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=root).strip()
started = time.monotonic()
with (out / (name + '.log')).open('w', encoding='utf-8') as stream:
    result = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
record = dict(head=head, command=command, code=result.returncode,
              seconds=round(time.monotonic() - started, 3), python=sys.version,
              finished=datetime.datetime.now().astimezone().isoformat())
(out / (name + '-result.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(record, ensure_ascii=False), flush=True)
raise SystemExit(result.returncode)
