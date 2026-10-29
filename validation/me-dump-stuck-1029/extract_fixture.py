"""Preserve the two Linux stops and the independently measured Windows waits."""
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CAPTURES = Path(r"C:\hengband-backups\magic-eater-captures-1029")
MEASUREMENT = Path(r"C:\hengband-backups\me-dump-diagnosis-1029")


def main():
    stops = sorted((CAPTURES / "me-a").rglob("control-at-stop.json.gz"))
    data = {"linux_stops": [], "measured": {}}
    for path in stops:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            stop = json.load(stream)
        data["linux_stops"].append({"screen": stop["screen"], "state": stop["state"]})
    with gzip.open(stops[0].with_name("state.jsonl.gz"), "rt", encoding="utf-8") as stream:
        data["linux_preamble"] = [json.loads(line) for line in stream][:-1]
    for name, filename in (("magic_eater", "ME_TEST-trace.json"),
                           ("warrior_template", "WARRIOR-trace.json")):
        rows = json.loads((MEASUREMENT / filename).read_text(encoding="utf-8"))
        data["measured"][name] = rows[:16]
        data["measured"][name + "_options"] = rows[17]["screen"]
    path = CAPTURES / "wx-a/life-001/jsonlog/bot-posted-characters.jsonl"
    posted = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    data["warrior_control_keys"] = [row["character"] for row in posted
                                    if row["decision"].get("sequence") == 3]
    path = ROOT / "tests/fixtures/me-dump-stuck-20261029.json.gz"
    path.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode("utf-8"), mtime=0))
    print(path.name, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
