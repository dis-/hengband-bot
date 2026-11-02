"""Recorded equipment-transaction sessions from the S3.3 batch seam pins.

A1159:262 and A1702:232 (and the other pins of the fixture) carry the actual
immutable action plan of their board in the claim goal's expectation; this
rebuilds that plan as the session the board was deciding with.
"""
import ast
import gzip
import json
from pathlib import Path

from hengbot.equipment_transaction_planner import EquipmentTransaction, EquipmentTransactionPlan
from hengbot.equipment_transaction_session import EquipmentTransactionSession

FIXTURE = Path(__file__).parent / "fixtures/s33-batch-seams-20261003.json.gz"


def captured_session(stamp, line):
    pins = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    pin = next(pin for pin in pins if stamp in pin["source"] and pin["line"] == line)
    actions = []
    for text in pin["row"]["claim"]["goal"]["expectation"]:
        if "EquipmentTransaction(" not in text:
            continue
        for action in ast.literal_eval(text):
            node = ast.parse(action, mode="eval").body
            actions.append(EquipmentTransaction(**{
                keyword.arg: ast.literal_eval(keyword.value) for keyword in node.keywords}))
    return pin, EquipmentTransactionSession(EquipmentTransactionPlan(tuple(actions), (), 0))
