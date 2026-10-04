"""Extract the 21:07 inscription seam from immutable backup captures only."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
root=Path(r'C:\hengband-backups\state-logs\s33-phase2b-shadow-20261004')
stem='autorecover-20261004-210741-no-key-exhausted.'
data={'sources':{},'boards':{},'decisions':{},'posted':{}}
for suffix in ('bot-state-fixed.jsonl.gz','bot-decisions.jsonl.gz','bot-posted-characters.jsonl.gz'):
 p=root/(stem+suffix); data['sources'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest(); grid=None
 for n,line in enumerate(gzip.open(p,'rt',encoding='utf8'),1):
  row=json.loads(line); grid=row.get('grid_map',grid)
  if suffix.startswith('bot-state') and n in (77,78):
   row=copy.deepcopy(row); row.setdefault('grid_map',grid); data['boards'][str(n)]=row
  if suffix.startswith('bot-decisions') and n in (232,233,238,239): data['decisions'][str(n)]=row
  if suffix.startswith('bot-posted') and row.get('composed_key') == '{c@2\r': data['posted'][str(n)]=row
p=Path(__file__).resolve().parents[1] / 'tests/fixtures/home-surplus-inscription-20261004.json.gz'
p.write_bytes(gzip.compress(json.dumps(data,ensure_ascii=False).encode('utf8'),mtime=0))
print(hashlib.sha256(p.read_bytes()).hexdigest()); print('posted row count',len(data['posted']))
