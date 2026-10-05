"""Freeze only the named slice-1 pins; no policy replay or game execution."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path('C:/hengband-backups/state-logs')
OUTPUT = Path(__file__).parent / 'fixtures/owner-retirement-slice1-20261006.json.gz'


def row(path, number):
    with path.open('rb') as stream:
        for physical, raw in enumerate(stream, 1):
            if physical == number:
                return raw
    raise ValueError(f'{path}: missing physical row {number}')


def extract():
    pins = []
    for capture, directory, number, board_number in [
        ('c', 'mana-shop-wait-20261006-0724', 10751, 897),
        ('a', 'home-full-nosurplus-20261005-2356', 2521, None),
    ]:
        source = ROOT / directory / 'bot-decisions.jsonl'
        raw = row(source, number)
        pin = dict(capture=capture, source=str(source), physical_row=number,
                   row_sha256=hashlib.sha256(raw).hexdigest(),
                   decision_row_bytes=base64.b64encode(raw).decode(),
                   decision=json.loads(raw))
        if board_number is not None:
            source = source.with_name('bot-state-tail.jsonl')
            raw = row(source, board_number)
            pin.update(board_source=str(source), board_physical_row=board_number,
                       board_row_sha256=hashlib.sha256(raw).hexdigest(),
                       board_row_bytes=base64.b64encode(raw).decode(), board=json.loads(raw))
            assert pin['board']['turn'] == pin['decision']['turn']
        pins.append(pin)
    OUTPUT.write_bytes(gzip.compress((json.dumps(pins, ensure_ascii=False) + '\n').encode(), mtime=0))
    print('slice1 pins: c decision 10751/board 897; a decision 2521; no replay')


if __name__ == '__main__':
    extract()
