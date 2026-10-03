"""Recorded rows/boards and explicit missing-checkpoint constructions."""
import ast
import gzip
import json
from dataclasses import replace
from pathlib import Path

from hengbot.model import parse_snapshot, Position
from hengbot.town_maps import TownMap
from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession

DATA = json.loads(gzip.decompress((Path(__file__).parent /
    'fixtures/s33-phase2-20261004.json.gz').read_bytes()))


def pin(line):
    return next(p for p in DATA['pins'] if p['line'] == line)


def board(line):
    # DECLARED CONSTRUCTED: the ~f cache is absent from the capture. Protocol
    # 2 suppresses only that startup request; item/map facts remain recorded.
    return replace(parse_snapshot(pin(line)['board']), protocol_version=2)


def town_map():
    m = DATA['town_map']
    return TownMap(name=m['name'], width=m['width'], height=m['height'],
        walkable=frozenset(Position(*p) for p in m['walkable']),
        stores={int(k): Position(*v) for k, v in m['stores'].items()},
        buildings={int(k): Position(*v) for k, v in m['buildings'].items()})


def session():
    text = pin(10489)['row']['claim']['goal']['expectation'][0]
    actions = []
    for action in ast.literal_eval(text):
        node = ast.parse(action, mode='eval').body
        actions.append(EquipmentTransaction(**{
            kw.arg: ast.literal_eval(kw.value) for kw in node.keywords}))
    return EquipmentTransactionSession(EquipmentTransactionPlan(tuple(actions), (), 0))
