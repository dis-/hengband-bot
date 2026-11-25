"""Freeze n1-c life-222's owned gear for the finale search pins (test_angband_finale_loadout).

Source (read-only): jsonlog/town-arrival/20261126-021210.789744179-turn9966212/policy.pkl, the
town-arrival checkpoint of 2026-11-26 02:12 (after Oberon, the finale preparation's check step
stopped as check:resist_shard).  The catalog's (``_equipment_catalog``) pieces the search reads
(``exploration_legal``), each its id and every InventoryItem field.
"""
import dataclasses
import gzip
import hashlib
import json
import pathlib
from pathlib import Path
import pickle
import sys


def extract(checkpoint):
    if sys.platform == "win32":
        pathlib.PosixPath = pathlib.WindowsPath  # the server's paths in the pickle
    with open(checkpoint / "policy.pkl", "rb") as source:
        state = pickle.load(source)
    items = []
    for owned in state["_equipment_catalog"].items:
        if not owned.exploration_legal:
            continue
        fields = dataclasses.asdict(owned.item)
        fields["known_flags"] = sorted(fields["known_flags"])
        items.append({"id": owned.id, "origin": owned.origin,
                      "equipped_slot": owned.equipped_slot, "item": fields})
    items.sort(key=lambda entry: entry["id"])
    payload = {"source": f"town-arrival/{checkpoint.name}/policy.pkl", "items": items}
    body = (json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n").encode("utf8")
    target = Path(__file__).parent / "fixtures/n1c-222-finale-catalog-20261126.json.gz"
    target.write_bytes(gzip.compress(body, mtime=0))
    print(len(items), hashlib.sha256(body).hexdigest())


if __name__ == "__main__":
    extract(Path(sys.argv[1]))
