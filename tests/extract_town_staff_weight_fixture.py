"""Extract tests/fixtures/town-staff-weight-1105/.

Source: n1-a life-482, the last town arrival before the 2026-11-05 02:12
owner-retired-burst stop (build bot-0b8f85035).  Written from the capture:

- policy.pkl.xz: the arrival checkpoint.
- journal.jsonl.xz: the recorded rows 0-66; row 66 is the first board the fixed
  code decides differently.
- continuation.jsonl.xz: CONSTRUCTED rows in the same format.  No recorded board
  exists past row 66 on the fixed path, so this tool applies each key the policy
  chooses to a small model of the pack, the Home and the shop pages recorded in
  the capture, up to the first key that leaves for the dungeon.
- character-calibration.json, character-dump.txt: the runtime files the arrival
  read; without them the equipment owner decides the Home differently.

    PYTHONPATH="src;tests;." python tests/extract_town_staff_weight_fixture.py <visit-dir>

Only this tool reads the capture; the committed test reads the fixtures alone.
"""
import tests  # noqa: F401 -- isolate runtime files before policy imports

import copy
import gzip
import json
import lzma
import re
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from hengbot.cli import _consume_response_sequence
from hengbot.model import parse_snapshot
from hengbot.policy import staged_prompt_chain_matches
from hengbot.town_arrival_checkpoint import CLI_LATCHES
from replay_town_arrival import adopt_calibration, decisions, journal, restore

FIXTURE = Path(__file__).with_name("fixtures") / "town-staff-weight-1105"
FIRST_CHANGED_ROW = 66
ROW_LIMIT = 40
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
TRAVEL_SYMBOLS = {"(": 7, "&": 5, "%": 4, "'": 6, "$": 3, "#": 2, '"': 1}
STEPS = {"1": (1, -1), "2": (1, 0), "3": (1, 1), "4": (0, -1),
         "6": (0, 1), "7": (-1, -1), "8": (-1, 0), "9": (-1, 1)}
HOME = 7
HOME_PAGE = 52
TVAL_STAFF, SV_IDENTIFY = 55, 5


def is_identify_staff(item):
    return (item["tval"], item.get("sval")) == (TVAL_STAFF, SV_IDENTIFY)


def stacks(left, right):
    if is_identify_staff(left) and is_identify_staff(right):
        return left["charges"] == right["charges"]
    return left["name"] == right["name"] and left["tval"] == right["tval"]


def rename(item):
    """The game shows an Identify stack's count in its name; signatures read it."""
    if is_identify_staff(item):
        count = f"{item['count']}x " if item["count"] > 1 else ""
        item["name"] = f"鑑定の杖 ({count}{item['charges']}回分)"


def add_item(items, item):
    for held in items:
        if stacks(held, item) and not held.get("is_equipment"):
            held["count"] += item["count"]
            rename(held)
            return
    rename(item)
    position = next((i for i, held in enumerate(items) if held["tval"] < item["tval"]), len(items))
    items.insert(position, item)


class TownModel:
    """The pack, the Home and the shop pages the keys act on."""

    def __init__(self, rows, row, shelves, entrances):
        lines = [json.loads(line) for entry in rows[:row + 1] for line in entry["inputs"]]
        current = json.loads(rows[row]["line"] or rows[row]["inputs"][-1])
        self.outside = next(line for line in reversed(lines) if line["type"] == "player_turn")
        self.store_line = next(line for line in reversed(lines) if line["type"] == "store")
        self.home = copy.deepcopy(next(
            line["knowledge"]["items"] for line in reversed(lines)
            if line["type"] == "knowledge" and line["knowledge"].get("category") == "home"))
        self.pack = copy.deepcopy(current["inventory"])
        self.gold = current["player"]["gold"]
        self.turn = current["turn"]
        self.position = (current["player"]["y"], current["player"]["x"])
        self.store = current["store"]["store_type"] if current["type"] == "store" else None
        self.page = 0
        self.shelves = shelves
        self.entrances = entrances

    def board(self):
        board = copy.deepcopy(self.outside if self.store is None else self.store_line)
        board.update(turn=self.turn, inventory=copy.deepcopy(self.pack), messages=[])
        board["player"]["gold"] = self.gold
        board["player"]["y"], board["player"]["x"] = self.position
        board["type"] = "player_turn" if self.store is None else "store"
        board["input_context"] = {"item_list": None, "kind": "command", "prompt": "",
                                  "shopping": self.store is not None}
        if self.store is None:
            board.pop("store", None)
        elif self.store == HOME:
            page = self.home[self.page * HOME_PAGE:(self.page + 1) * HOME_PAGE]
            board["store"] = {
                "capacity": 240, "page_size": HOME_PAGE, "page_top": self.page * HOME_PAGE,
                "stock_num": len(self.home), "store_type": HOME,
                "items": [{**{k: v for k, v in item.items() if k != "slot"}, "letter": LETTERS[i]}
                          for i, item in enumerate(page)]}
        else:
            board["store"] = copy.deepcopy(self.shelves[self.store])
        return board

    def knowledge(self):
        line = copy.deepcopy(self.outside)
        line.update(type="knowledge", turn=self.turn, inventory=copy.deepcopy(self.pack))
        line["knowledge"] = {"category": "home", "menu_key": "9",
                             "items": [{**item, "slot": i} for i, item in enumerate(self.home)]}
        return line

    def enter_at_entrance(self):
        self.store = next((s for s, at in self.entrances.items() if at == self.position), None)
        self.page = 0

    def quantity(self, key, at):
        match = re.match(r"(\d+)\r", key[at:])
        return (int(match.group(1)), at + match.end()) if match else (None, at)

    def take(self, letter, quantity):
        if self.store == HOME:
            index = self.page * HOME_PAGE + LETTERS.index(letter)
            shelf_item = self.home[index]
            count = min(quantity or shelf_item["count"], shelf_item["count"])
            item = {k: v for k, v in shelf_item.items() if k != "slot"}
            item["count"] = count
            shelf_item["count"] -= count
            rename(shelf_item)
            if not shelf_item["count"]:
                self.home.pop(index)
        else:
            shelf = self.shelves[self.store]["items"]
            shelf_item = next(item for item in shelf if item["letter"] == letter)
            count = quantity or 1
            item = {k: v for k, v in shelf_item.items() if k not in ("letter", "price")}
            item["count"] = count
            self.gold -= shelf_item.get("price", 0) * count
        add_item(self.pack, item)
        self.reslot()

    def put(self, slot, quantity):
        item = next(held for held in self.pack if held["slot"] == slot)
        count = quantity or item["count"]
        add_item(self.home, {**{k: v for k, v in item.items() if k != "slot"}, "count": count})
        item["count"] -= count
        rename(item)
        if not item["count"]:
            self.pack.remove(item)
        self.reslot()

    def reslot(self):
        for index, item in enumerate(self.pack):
            item["slot"] = LETTERS[index]

    def apply(self, key):
        """Apply one posted key; return the extra response lines it produced."""
        extra, at = [], 0
        self.turn += 10
        while at < len(key):
            char = key[at]
            if key.startswith("~9", at):
                extra.append(self.knowledge())
                at += 2
            elif char == "\x1b":
                self.store = None
                at += 1
            elif self.store is None:
                if key.startswith("`n", at):
                    self.store = TRAVEL_SYMBOLS[key[at + 2]]
                    self.position = self.entrances[self.store]
                    self.page = 0
                    at += 4
                elif char == "5":
                    self.enter_at_entrance()
                    at += 1
                else:
                    self.position = (self.position[0] + STEPS[char][0],
                                     self.position[1] + STEPS[char][1])
                    self.enter_at_entrance()
                    at += 1
            elif char == " ":
                self.page += 1
                at += 1
            elif char == "p":
                quantity, after = self.quantity(key, at + 2)
                self.take(key[at + 1], quantity)
                at = after + (key[after:after + 1] == "\r")
            elif char == "d":
                quantity, after = self.quantity(key, at + 2)
                self.put(key[at + 1], quantity)
                at = after
            else:
                raise ValueError(f"unmodelled key {key!r}")
        return extra


def acknowledge(policy, key):
    if key:
        policy.confirm_key_posted(key)
        chain = policy.peek_staged_prompt_chain()
        if chain is not None and staged_prompt_chain_matches(chain, key):
            policy.commit_staged_prompt_chain({"outcome": "released", "posted": key})


def continuation(visit, rows):
    """Decide row FIRST_CHANGED_ROW on, each board built from the previous key."""
    shelves, entrances = {}, {}
    for sibling in sorted(visit.parent.iterdir()):
        for entry in journal(sibling):
            for line in map(json.loads, entry["inputs"]):
                if line["type"] == "store":
                    store_type = line["store"]["store_type"]
                    entrances[store_type] = (line["player"]["y"], line["player"]["x"])
                    shelves[store_type] = copy.deepcopy(line["store"])
    built = []
    with TemporaryDirectory() as raw:
        scratch = Path(raw)
        policy = restore(visit, scratch)
        calibration = visit / "sidecars" / "_character_calibration_path"
        if calibration.is_file():
            adopt_calibration(policy, calibration, scratch)
        steps = list(decisions(policy, visit, scratch))
        for _recorded, supply in steps[:FIRST_CHANGED_ROW]:
            board = supply()
            acknowledge(policy, policy.choose_key(board))
        board = steps[FIRST_CHANGED_ROW][1]()
        model = TownModel(rows, FIRST_CHANGED_ROW, shelves, entrances)
        for _ in range(ROW_LIMIT):
            key = policy.choose_key(board)
            acknowledge(policy, key)
            if built:
                built[-1].update(key=key, reason=policy.last_reason)
            if policy.last_reason == "town:travel-entrance":
                return built
            extra = model.apply(key or "")
            line = model.board()
            built.append({
                "inputs": [json.dumps(item, ensure_ascii=False) for item in (*extra, line)],
                "cli_latches": {name: None if name == "_me_power_refresh_pending" else False
                                for name in CLI_LATCHES},
                "store_screen_verified": True if model.store is not None else None,
                "line": None,
            })
            _consume_response_sequence(
                [item + "\n" for item in built[-1]["inputs"]], policy, lambda _key: True,
                policy._monrace_knowledge, parse_snapshots=False,
                knowledge_ledger_path=scratch / "knowledge.jsonl")
            policy.observe_store_screen(built[-1]["store_screen_verified"])
            board = parse_snapshot(line, policy._monrace_knowledge)
    raise SystemExit("the constructed visit did not reach the dungeon entrance")


def write_rows(path, rows):
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_bytes(lzma.compress(text.encode("utf-8"), preset=9 | lzma.PRESET_EXTREME))


def main() -> None:
    visit = Path(sys.argv[1])
    rows = journal(visit)
    FIXTURE.mkdir(parents=True, exist_ok=True)
    (FIXTURE / "policy.pkl.xz").write_bytes(lzma.compress(
        (visit / "policy.pkl").read_bytes(), preset=9 | lzma.PRESET_EXTREME))
    write_rows(FIXTURE / "journal.jsonl.xz", rows[:FIRST_CHANGED_ROW + 1])
    write_rows(FIXTURE / "continuation.jsonl.xz", continuation(visit, rows))
    (FIXTURE / "character-calibration.json").write_bytes(
        (visit / "sidecars" / "_character_calibration_path").read_bytes())
    (FIXTURE / "character-dump.txt").write_bytes(
        (visit / "sidecars" / "_character_dump_path").read_bytes())


if __name__ == "__main__":
    main()
