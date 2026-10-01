"""Preserve route telemetry from all three supervisor captures, read-only."""
import gzip
import hashlib
import json
from pathlib import Path

SOURCE = Path(r'C:\hengband\bot-client\jsonlog')
DEST = Path(__file__).parent / 'fixtures/tpstockout-routes-20261002.json.gz'


def main():
    captures = {}
    sources = {}
    for stamp in ('021728', '023427', '023556'):
        name = f'autorecover-20261002-{stamp}-loop-detected.bot-decisions.jsonl.gz'
        data = (SOURCE / name).read_bytes()
        sources[name] = hashlib.sha256(data).hexdigest()
        captures[stamp] = [json.loads(line) for line in gzip.decompress(data).splitlines()]
    DEST.write_bytes(gzip.compress(json.dumps(dict(sources=sources, captures=captures),
                                            ensure_ascii=False).encode('utf8'), mtime=0))
    print(DEST.name, hashlib.sha256(DEST.read_bytes().replace(b'\r\n', b'\n')).hexdigest())


if __name__ == '__main__':
    main()
