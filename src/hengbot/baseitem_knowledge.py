"""Static base-item costs loaded from Hengband's JSONC definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hengbot.model import InventoryItem
from hengbot.monrace_knowledge import _strip_jsonc


def load_baseitem_costs(path: Path) -> dict[tuple[int, int], int]:
    data: dict[str, Any] = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    costs: dict[tuple[int, int], int] = {}
    for entry in data.get("baseitems", data.get("items", [])):
        kind = entry.get("itemkind", entry)
        costs[(int(kind["type_value"]), int(kind["subtype_value"]))] = int(
            entry.get("cost", kind.get("cost", 0))
        )
    return costs


def find_baseitem_definitions(start: Path | None = None) -> Path | None:
    relative = Path("lib") / "edit" / "BaseitemDefinitions.jsonc"
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for root in (current, *current.parents):
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def item_base_cost(
    item: InventoryItem, costs: dict[tuple[int, int], int]
) -> int | None:
    """Return base cost only when the item's base kind is player-known."""
    if not item.aware or item.sval < 0:
        return None
    return costs.get((item.tval, item.sval))
