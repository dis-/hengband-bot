"""Extract the D33 fixed-quest stop boards (2026-10-30 viewing captures).

Q34 sequence door (n1-c lives 030 and 039, zombie Magic-Eater Lv6): every
recorded board at the door's approach cell, from the first pick to the
quest:blocked:q34-sequence-door-locked board (201 each).  The grid maps of
these boards repeat; each distinct one is stored once and referenced.

Q31 retake/sweep alternation (n1-a lives 419 and 423, 5 loop-detected stops):
the board on which the off-plan Huorn was visible and the bot retook the hold,
the following board (the reply to the posted key), the recorded decision rows
of both, and the quest latches of the policy checkpoint written at the stop
(cleared fixed targets and surveyed cells).

Q2 wall breach (n1-a life-422): the Telmora board approaching the Q2 request
with a one-charge Stone to Mud wand, its following board, and the last in-quest
board (quest:blocked:q2-breach-tool at [7,47]).

Q34 opening wait (n1-a life-426, Lv1 in the Outpost): the last two recorded
boards of the first stall capture and the decision row of every recorded board.
"""
import gzip
import hashlib
import json
import zlib
from pathlib import Path

ROOT = Path(r"C:\hengband-backups\pdca\captures")
OUT = Path(__file__).with_name("fixtures") / "quest-stops-20261030.json.gz"
DOORS = {
    "n1-c/life-030": ROOT / "unfixed-24h-1031/n1-c/life-030/incident-captures"
    / "20261030-190719-quest-blocked-q34-sequence-door-locked",
    "n1-c/life-039": ROOT / "n1c-1030-2230/life-039/incident-captures"
    / "20261030-215114-quest-blocked-q34-sequence-door-locked",
}
# (capture, retake-hold board turn): the Huorn visible from the west column.
SWEEPS = {
    "n1-a/life-419/012515": (ROOT / "unfixed-24h-1031/n1-a/life-419/incident-captures"
                             / "20261030-012515-loop-detected", 476088),
    "n1-a/life-419/012541": (ROOT / "unfixed-24h-1031/n1-a/life-419/incident-captures"
                             / "20261030-012541-loop-detected", 478538),
    "n1-a/life-423/072744": (ROOT / "unfixed-24h-1031/n1-a/life-423/incident-captures"
                             / "20261030-072744-loop-detected", 625334),
}
# The Q34 opening owner's stall (n1-a life-426): the last two recorded boards.
OPENING = (ROOT / "unfixed-24h-1031/n1-a/life-426/captures"
           / "20261030-080840-stall-opening-q-wait")
# Q2 wall breach (n1-a life-422, Telmora): the board on which the Q2 request
# was approached with a one-charge Stone to Mud wand, its following board, and
# the in-quest board waiting at [7,47] with the wand empty.
Q2 = (ROOT / "unfixed-24h-1031/n1-a/life-422/incident-captures"
      / "20261030-060855-loop-detected", 760788)
DECISION_FIELDS = ("decision_sequence", "turn", "reason", "key", "position")


def snapshots(capture):
    """Decode the multi-member gzip tail from its first member header."""
    data = (capture / "snapshots" / "snapshots-current.jsonl.gz").read_bytes()
    data = data[data.find(b"\x1f\x8b\x08"):]
    text = b""
    while data:
        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        text += stream.decompress(data)
        data = stream.unused_data
    rows = []
    for line in text.split(b"\n"):
        if line.strip():
            row = json.loads(line)
            if row.get("type") != "knowledge":
                rows.append(row)
    return rows


def decisions(capture):
    rows = []
    with (capture / "decision-tail.jsonl").open(encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # The tail is cut at a byte offset: only its first line can
                # be partial.
                if number == 0:
                    continue
                raise
            if "reason" in row:
                rows.append({field: row.get(field) for field in DECISION_FIELDS})
    return rows


def sources(capture):
    return {name: hashlib.sha256((capture / name).read_bytes()).hexdigest()
            for name in ("decision-tail.jsonl", "policy-state.json",
                         "snapshots/snapshots-current.jsonl.gz")}


def door_case(capture):
    boards = [row for row in snapshots(capture)
              if row["floor"].get("quest_id") == 34]
    approach = (boards[-1]["player"]["y"], boards[-1]["player"]["x"])
    start = len(boards)
    while start and (boards[start - 1]["player"]["y"],
                     boards[start - 1]["player"]["x"]) == approach:
        start -= 1
    run = boards[start:]
    grid_maps = []
    for board in run:
        if board["grid_map"] not in grid_maps:
            grid_maps.append(board["grid_map"])
        board["grid_map"] = grid_maps.index(board["grid_map"])
    by_turn = {row["turn"]: row for row in decisions(capture)}
    return {
        "sources": sources(capture),
        "boards": run,
        "grid_maps": grid_maps,
        "decisions": [by_turn[board["turn"]] for board in run if board["turn"] in by_turn],
    }


def sweep_case(capture, turn):
    boards = snapshots(capture)
    index = next(i for i, row in enumerate(boards) if row["turn"] == turn)
    latches = json.loads((capture / "policy-state.json").read_text(
        encoding="utf-8"))["modes_and_latches"]
    by_turn = {row["turn"]: row for row in decisions(capture)}
    return {
        "sources": sources(capture),
        "board": boards[index],
        "following": boards[index + 1],
        "decisions": [by_turn[boards[i]["turn"]] for i in (index, index + 1)],
        "cleared_targets": latches["_quest_strategy_cleared_targets"]["31"],
        "surveyed": latches["_quest_strategy_surveyed_placements"]["31"],
    }


def opening_case(capture):
    with gzip.open(capture / "state.jsonl.gz", "rt", encoding="utf-8") as stream:
        boards = [row for row in map(json.loads, filter(str.strip, stream))
                  if "player" in row]
    with gzip.open(capture / "bot-decisions.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.startswith("{")]
    by_turn = {row["turn"]: {field: row.get(field) for field in DECISION_FIELDS}
               for row in rows if "reason" in row}
    return {
        "sources": {name: hashlib.sha256((capture / name).read_bytes()).hexdigest()
                    for name in ("state.jsonl.gz", "bot-decisions.jsonl.gz")},
        "board": boards[-2],
        "following": boards[-1],
        "decisions": [by_turn[board["turn"]] for board in boards
                      if board["turn"] in by_turn],
    }


def q2_case(capture, turn):
    boards = snapshots(capture)
    index = next(i for i, row in enumerate(boards) if row["turn"] == turn)
    by_turn = {row["turn"]: row for row in decisions(capture)}
    return {
        "sources": sources(capture),
        "board": boards[index],
        "following": boards[index + 1],
        "stop_board": boards[-1],
        "decisions": [by_turn[boards[i]["turn"]] for i in (index, -1)],
    }


def main():
    fixture = {
        "q2": q2_case(*Q2),
        "opening": opening_case(OPENING),
        "doors": {name: door_case(path) for name, path in DOORS.items()},
        "sweeps": {name: sweep_case(path, turn) for name, (path, turn) in SWEEPS.items()},
    }
    with gzip.open(OUT, "wt", encoding="utf-8") as stream:
        json.dump(fixture, stream, ensure_ascii=False, separators=(",", ":"))
    print(OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
