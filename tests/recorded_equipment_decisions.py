"""Capture-time optimizer outputs are inputs of equipment-independent pins.

Declared wall, fixer-reconcile-prompt.txt STEP 2: historical boards confirm the
captured equipment choice, not today's corrected dual-wield choice. Only the
optimizer collaborator is frozen; transactions, ownership, readiness and town
remedies run normally. Missing input signatures fail closed.
"""

from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from functools import wraps
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from hengbot import equipment_optimizer, model, warrior_optimization

FIXTURE_SHA256 = {
    "guardian": "42412bcdbcde27fdd94d93b1e46d85011506fdc1e025c670c0977192ff60fb56",
    "overweight": "8ceeaf38f73218ea3aa96562c30fcf6173ad0b4d8573e70eccaf8cc2f991d516",
    "town": "8a8b62d1c8556b23782a0a9fa6f4a6c653f1f75001d2e7345f53dacc663e54bb",
    "live27": "eb8a8aa1fa6cbecad9d7e0b4541d8f86360cca9e966f981bde93af4e5e8eff53",
    "classC2": "ecfe01c2c70926975f8fde3e612f5380c27d80027cf4101018c939aabdfaa116",
}


def encode(value):
    if is_dataclass(value):
        return {"class": type(value).__name__, "fields": {
            field.name: encode(getattr(value, field.name)) for field in fields(value)}}
    if isinstance(value, (tuple, frozenset)):
        values = sorted(value, key=repr) if isinstance(value, frozenset) else value
        return {type(value).__name__: [encode(item) for item in values]}
    if isinstance(value, dict):
        return {key: encode(item) for key, item in value.items()}
    return value


def decode(value):
    if isinstance(value, dict):
        if "class" in value:
            cls = getattr(equipment_optimizer, value["class"], None)
            if cls is None:
                cls = getattr(model, value["class"])
            return cls(**{key: decode(item) for key, item in value["fields"].items()})
        if "tuple" in value:
            return tuple(decode(item) for item in value["tuple"])
        if "frozenset" in value:
            return frozenset(decode(item) for item in value["frozenset"])
        return {key: decode(item) for key, item in value.items()}
    return value


def input_signature(items, kwargs):
    # Candidate generation and wall-clock limits are implementation details;
    # catalog, depth, worn IDs and all requirement/ammunition inputs are facts.
    facts = {key: value for key, value in kwargs.items()
             if key not in {"candidate_loadouts", "timeout_seconds"}}
    return hashlib.sha256(json.dumps(encode((items, facts)), sort_keys=True,
                                    ensure_ascii=True).encode()).hexdigest()


@contextmanager
def recorded_equipment_decisions(name):
    path = Path(__file__).parent / "fixtures" / f"{name}.optimizer.json.gz"
    # R9: hash text content after CRLF normalization, independent of checkout.
    payload = gzip.decompress(path.read_bytes()).replace(b"\r\n", b"\n")
    if hashlib.sha256(payload).hexdigest() != FIXTURE_SHA256[name]:
        raise AssertionError(f"changed optimizer fixture: {name}")
    records = json.loads(payload)["results"]

    def recorded(items, evaluator, **kwargs):
        signature = input_signature(items, kwargs)
        if signature not in records:
            raise AssertionError(f"uncaptured optimizer input: {name} {signature}")
        return decode(records[signature])

    with patch.object(warrior_optimization, "optimize_loadout", recorded):
        yield


def frozen_equipment_replay(name):
    def decorate(function):
        @wraps(function)
        def replay(*args, **kwargs):
            with recorded_equipment_decisions(name):
                return function(*args, **kwargs)
        return replay
    return decorate
