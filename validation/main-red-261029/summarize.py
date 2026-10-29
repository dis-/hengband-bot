"""Print the chronological failure matrix and its transition points."""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
commits = ['78deea2ac'] + subprocess.check_output(
    ['git', 'rev-list', '--first-parent', '--reverse', '78deea2ac..eebc99f0e'],
    cwd=root, text=True).splitlines()
previous = {}
for commit in commits:
    path = out / (commit[:9] + '.json')
    if not path.exists():
        continue
    rows = json.loads(path.read_text(encoding='utf-8'))
    status = {name: not row['errors'] and not row['failures'] for name, row in rows.items()}
    print(commit[:9], ''.join('P' if good else 'F' for good in status.values()))
    for name, good in status.items():
        if previous.get(name, True) and not good:
            print(' FIRST FAILURE:', name)
        elif not previous.get(name, True) and good:
            print(' RECOVERED:', name)
    previous = status
