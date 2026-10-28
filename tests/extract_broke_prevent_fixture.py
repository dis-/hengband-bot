"""Extract issue #47 pins from copied captures; never contact a running game.

Only available raw records at named decision turns, and decision evidence, are
retained. Truncated recorder copies are resumed at the first complete gzip
member (the recorder appends one member per row).
"""
from pathlib import Path
import gzip
import io
import json

B = Path(r"C:\hengband\bot-client\state-logs\n1b-life192-broke-1026")
A = Path(r"C:\hengband-backups\state-logs\c4a-morivant-broke-1026\captures\20261026-083838-town-blocked-walk-in-entrance-unavailable")
CAP = B / "incident-captures/20261026-160604-town-blocked-walk-in-entrance-unavailable"
TURNS = {2894772, 2895339, 2895380, 2895403, 2895429, 2895451,
         2933932, 2940687, 2941535, 2941543, 2942109}

def rows(path):
    raw = path.read_bytes()
    start = raw.find(b"\x1f\x8b\x08")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw[start:])) as stream:
            for line in stream:
                try:
                    yield json.loads(line)
                except ValueError:
                    pass
    except EOFError:
        pass

if __name__ == "__main__":
    result = {"a": list(rows(A / "state.jsonl.gz")), "b": [], "decisions": []}
    for path in sorted((CAP / "snapshots").glob("*.gz")):
        if "150134" in path.name:
            continue
        for row in rows(path):
            if row.get("turn") in TURNS:
                result["b"].append(row)
    for line in (B / "jsonlog/bot-decisions.jsonl").open(encoding="utf-8"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("turn") in TURNS:
            result["decisions"].append({key: row.get(key) for key in (
                "turn", "reason", "key", "player", "fundraising", "store_type",
                "procurement_requirements", "position", "time")})
    target = Path(__file__).parent / "fixtures/broke-prevent-20261026.json.gz"
    target.write_bytes(gzip.compress(json.dumps(result, ensure_ascii=False).encode("utf-8"), mtime=0))
    print(target.name, len(result["a"]), len(result["b"]), len(result["decisions"]))
