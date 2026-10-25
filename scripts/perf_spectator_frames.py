"""Offline spectator cost probe; only a private fixture TCP server is contacted.

PYTHONPATH=src python scripts/perf_spectator_frames.py --iterations 300
Measures Python client, loopback fixture response, projection and disk I/O.
It does not measure the live game's screen hook scheduling or C++ rendering.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socketserver
import statistics
import tempfile
import threading
import time

from hengbot.control_client import ControlClient
from hengbot.model import parse_snapshot
from hengbot.monrace_knowledge import load_monrace_knowledge
from hengbot.spectator import SpectatorWriter

ROOT = Path(__file__).resolve().parents[1]


def summary(samples):
    ordered = sorted(samples)
    return {"mean_ms": round(statistics.mean(samples), 4),
            "median_ms": round(statistics.median(samples), 4),
            "p95_ms": round(ordered[int((len(ordered) - 1) * .95)], 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=300)
    args = parser.parse_args()
    fixture = ROOT / "tests/fixtures/screen-20260920-levelup-stat-prompt.json"
    screen = json.loads(fixture.read_text(encoding="utf-8"))
    state_line = (ROOT / "tests/fixtures/spectator-board.json").read_text(encoding="utf-8")
    snapshot = parse_snapshot(json.loads(state_line), load_monrace_knowledge(
        Path("C:/hengband/lib/edit/MonraceDefinitions.jsonc")))

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                request = json.loads(line)
                if request.get("op") != "screen":
                    raise ValueError("probe only permits fixture screen reads")
                result = dict(screen)
                if not request.get("attrs"):
                    result.pop("attrs", None)
                self.wfile.write((json.dumps({"id": request["id"], "ok": True,
                                              "result": result}, ensure_ascii=False)
                                  + "\n").encode("utf-8"))
                self.wfile.flush()

    results = {"iterations_per_case": args.iterations, "fixture": fixture.name,
               "width": screen["width"], "height": screen["height"],
               "fixture_bytes": len(json.dumps(screen, ensure_ascii=False).encode("utf-8"))}
    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = ControlClient(server.server_address[1], request_budget=5, retries=0)
        try:
            for attrs in (False, True):
                for _ in range(10):
                    assert client.request("screen", term=0, attrs=attrs) is not None
                samples = []
                for _ in range(args.iterations):
                    start = time.perf_counter()
                    assert client.request("screen", term=0, attrs=attrs) is not None
                    samples.append((time.perf_counter() - start) * 1000)
                results["request_attrs_" + str(attrs).lower()] = summary(samples)
            with tempfile.TemporaryDirectory(prefix="spectate-probe-") as directory:
                for name, frames, screen_client in (("compatibility_throttled", False, client),
                                                     ("frames_cached_screen", True, None),
                                                     ("frames_with_colour_request", True, client)):
                    root = Path(directory) / name
                    root.mkdir()
                    writer = SpectatorWriter(root / "spectate.json", clock=lambda: 100.0)
                    writer.observe(snapshot, "6", "probe", 0, screen,
                                   state_line=state_line, screen_client=screen_client,
                                   append_frame=frames)
                    samples = []
                    for sequence in range(1, args.iterations + 1):
                        start = time.perf_counter()
                        writer.observe(snapshot, "6", "probe", sequence, screen,
                                       state_line=state_line, screen_client=screen_client,
                                       append_frame=frames)
                        samples.append((time.perf_counter() - start) * 1000)
                    results[name] = summary(samples)
        finally:
            client.close()
            server.shutdown()
            thread.join(timeout=5)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
