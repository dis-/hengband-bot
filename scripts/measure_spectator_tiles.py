"""Offline capture reconstruction, not a synchronized live-screen benchmark.

Usage: python scripts/measure_spectator_tiles.py CAPTURE --definitions LIB/EDIT
The capture contains state.jsonl.gz and control-at-stop.json.gz. Its fixed
stop screen is paired with each recorded state; no panel or colours are invented.
Glyph comparison uses default definition characters, ignoring colour/prefs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import itertools
import json
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory

from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import _strip_jsonc
from hengbot.protocol import BOARD_SNAPSHOT_TYPES
from hengbot.spectator import SPECTATE_FRAMES_MAX_BYTES, SpectatorWriter
from hengbot.spectator_tiles import INDEX_ALPHABET


def definitions(path, filename, key):
    data = json.loads(_strip_jsonc((path / filename).read_text(encoding="utf-8")))
    return {row["id"]: row["symbol"]["character"] for row in data[key]}


def compare(tiles, screen, terrain, monsters):
    counts = Counter()
    examples = Counter()
    width = tiles.get("index_width", 1)
    for r, row in enumerate(tiles["rows"], tiles["origin"][0]):
        for col in range(len(row) // width):
            counts["map_cells"] += 1
            code = row[col * width:(col + 1) * width]
            if "." in code:
                continue
            index = 0
            for digit in code:
                index = index * 64 + INDEX_ALPHABET.index(digit)
            feat, lighting, race, item, player = tiles["palette"][index]
            # Player and top items cover terrain; they are not terrain/monster
            # renderings. Item tval alone is insufficient for an exact glyph.
            if player or (item is not None and race is None):
                counts["player_or_item"] += 1
                continue
            expected = monsters.get(race) if race is not None else terrain.get(feat)
            if expected is None:
                counts["unknown_definition"] += 1
                continue
            actual = screen["lines"][r].ljust(screen["width"])[col + tiles["origin"][1]]
            counts["compared"] += 1
            if actual != expected:
                counts["disagree"] += 1
                examples[f"{expected!r}->{actual!r}"] += 1
    return counts, examples


def capacity(frames):
    """Repeat the measured window through the real writer until first rotation."""
    with TemporaryDirectory() as directory:
        writer = SpectatorWriter(Path(directory) / "spectate.json")
        previous = 0
        for frame in itertools.cycle(frames):
            writer._append_frame(frame)
            size = writer.frames_path.stat().st_size
            if size < previous:
                return {"before_rotation": writer.last_frame - 1,
                        "after_rotation": len(writer.frames_path.read_bytes().splitlines()),
                        "after_rotation_bytes": size}
            previous = size


def measure(capture, terrain, monsters):
    control = json.loads(gzip.decompress((capture / "control-at-stop.json.gz").read_bytes()))
    screen = control["screen"]
    frames, sizes, gzip_sizes = [], [], []
    cells, examples, skipped = Counter(), Counter(), Counter()
    stop_match = None
    with TemporaryDirectory() as directory:
        writer = SpectatorWriter(Path(directory) / "spectate.json", clock=lambda: 1000.)
        with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
            for sequence, line in enumerate(stream, 1):
                state = json.loads(line)
                if state.get("type") not in BOARD_SNAPSHOT_TYPES:
                    skipped[state.get("type", "missing")] += 1
                    continue
                snapshot = parse_snapshot(state, {})
                writer.observe(snapshot, "6", "capture-reconstruction", sequence, screen,
                               state_line=line, append_frame=True, defer_frame=True)
                frame = writer.pending_frame
                if frame is None:
                    raise RuntimeError(f"projection failed at state {sequence}")
                frames.append(frame)
                data = (json.dumps(dict(frame, frame=sequence), ensure_ascii=False) + "\n").encode("utf-8")
                sizes.append(len(data))
                gzip_sizes.append(len(gzip.compress(data, compresslevel=5, mtime=0)))
                if "tiles" in frame:
                    counts, mismatches = compare(frame["tiles"], screen, terrain, monsters)
                    cells.update(counts)
                    examples.update(mismatches)
                    stopped = control.get("state", {})
                    if (state.get("turn") == stopped.get("turn") and
                            state.get("clock") == stopped.get("clock") and
                            all(state["player"].get(axis) == stopped.get("player", {}).get(axis)
                                for axis in ("y", "x"))):
                        stop_match = {"state_sequence": sequence, "turn": state.get("turn"),
                                      "cells": dict(counts), "examples": dict(mismatches)}
        panel_counts = writer.tile_panel_counts
    emitted = sum("tiles" in frame for frame in frames)
    return {"capture": capture.name, "method": "states + fixed stop screen",
            "frames": len(frames), "skipped_non_board": dict(skipped), "frames_with_tiles": emitted,
            "tile_share": emitted / len(frames), "panel_outcomes": panel_counts,
            "screen": [screen["width"], screen["height"]], "attrs": "attrs" in screen,
            "cells": dict(cells), "disagreement_share_compared": cells["disagree"] / cells["compared"] if cells["compared"] else None,
            "disagreement_share_map": cells["disagree"] / cells["map_cells"] if cells["map_cells"] else None,
            "disagreement_examples": dict(examples.most_common(12)),
            "last_board_matching_control_turn_clock_position": stop_match,
            "plain_bytes_per_frame": statistics.mean(sizes),
            "gzip5_bytes_per_frame": statistics.mean(gzip_sizes),
            "log_budget_bytes": SPECTATE_FRAMES_MAX_BYTES, "log_capacity": capacity(frames)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, nargs="+")
    parser.add_argument("--definitions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    terrain = definitions(args.definitions, "TerrainDefinitions.jsonc", "terrains")
    monsters = definitions(args.definitions, "MonraceDefinitions.jsonc", "monsters")
    results = [measure(capture, terrain, monsters) for capture in args.captures]
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
