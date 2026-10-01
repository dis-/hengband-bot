"""Extract unchanged incident boards/screen; never write recorder directories."""
import gzip
import hashlib
import json
from pathlib import Path


def extract():
    source = Path('C:/hengband/bot-client/jsonlog')
    destination = Path(__file__).with_name('fixtures') / 'live30-identify-normal'
    destination.mkdir(exist_ok=True)
    name = 'incident-20261001-1142-identify-normal-unrecognized.state.jsonl.gz'
    raw = (source / name).read_bytes()
    rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    for label, index in [('before-purchase', 296), ('before-identify', 298), ('staff-failed', 299)]:
        (destination / (label + '.json')).write_text(
            json.dumps(rows[index], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    screen_name = 'live-screen-20261001-1142-identify-normal-unrecognized.json'
    screen = (source / screen_name).read_bytes()
    (destination / 'recorded-quaff-screen.json').write_bytes(screen)
    (destination / 'provenance.json').write_text(json.dumps({
        'state_source': name, 'state_sha256': hashlib.sha256(raw).hexdigest(),
        'state_jsonl_lines': {'before-purchase': 297, 'before-identify': 299, 'staff-failed': 300},
        'screen_source': screen_name, 'screen_sha256': hashlib.sha256(screen).hexdigest(),
        'intermediate_screens': 'Not captured. Pins derive chooser rows from recorded inventory and protocol literals.'
    }, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    extract()
