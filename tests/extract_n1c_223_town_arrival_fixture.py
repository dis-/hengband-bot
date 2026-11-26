"""Extract tests/fixtures/n1c-223-town-arrival-cl41-1127.json.gz (provenance beside it).

Source: n1-c life-223's town-arrival checkpoint of 2026-11-27 05:38 (turn 4054431), copied
read-only from the viewing server's jsonlog/town-arrival/20261127-053814.247559356-turn4054431/
to C:/hengband-backups/pdca/quest-value-1127/n1c-223-turn4054431/.  The fixture keeps the board
and the restored policy's absorbed-power lists (``_me_device_lists``): a Magic-Eater's board alone
reads as having no absorbed power.

    PYTHONPATH="src;tests;." python tests/extract_n1c_223_town_arrival_fixture.py <checkpoint dir> <out>
"""
import tests  # noqa: F401  -- isolate runtime files before policy imports

import gzip
import hashlib
import io
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from replay_town_arrival import restore
visit = Path(sys.argv[1])
with TemporaryDirectory() as raw:
    policy = restore(visit, Path(raw))
    lists = policy._me_device_lists
board = json.loads((visit / "board.json").read_text(encoding="utf-8"))
case = {"board": board, "me_device_lists": {kind: [value[0], value[1]] for kind, value in lists.items()}}
data = json.dumps(case, ensure_ascii=False, sort_keys=True).encode("utf-8")
buf = io.BytesIO()
with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as stream:
    stream.write(data)
Path(sys.argv[2]).write_bytes(buf.getvalue())
print(len(buf.getvalue()), hashlib.sha256((visit / "board.json").read_bytes()).hexdigest(), hashlib.sha256(data).hexdigest())
