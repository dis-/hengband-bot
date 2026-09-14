"""Command-sensitive, source-derived Home fake for OperationExecutor tests.

Reconstructed inputs (the incident did not record them): STORE boards and stock
come from cmd-store.cpp's post-command emission; prompt text/shape and command
switch come from store-key-processor.cpp; overflow/refusal outcomes come from
cmd-store.cpp:170-184 and sell-order.cpp:69-118.  This is deliberately not an
incident transcript adapter.
"""
import json

from hengbot.policy_constants import EQUIPMENT_SLOT_KEY


def _screen(line0="", store=True, items=()):
    lines = [""] * 24
    lines[0] = line0
    cursor = {"visible": True, "y": 20, "x": 0}
    if store:
        lines[20] = "You may: g) Get an item. d) Drop an item. w) Wield. t) Take off."
        lines[21] = " ESC) Exit from Building."
        for index, item in enumerate(items[:16]):
            label = item.get("name") or item.get("id") or item.get("slot") or "item"
            lines[3 + index] = f"{chr(97 + index)}) {label}"
    else:
        lines[1] = "Human"
        lines[10] = " " * 20 + "@"
        lines[23] = " " * 72 + "Surf."
        cursor = {"visible": False, "y": 10, "x": 20}
    return {"width": 80, "height": 24, "cursor": cursor, "lines": lines}


class _Socket:
    def __init__(self, game): self.game, self.buf = game, bytearray()
    def settimeout(self, value): pass
    def close(self): pass
    def sendall(self, payload):
        response = self.game.request(json.loads(payload))
        self.buf.extend((json.dumps(response) + "\n").encode())
    def recv(self, size):
        result = bytes(self.buf[:size]); del self.buf[:size]
        return result


class FaithfulHomeGame:
    """Small Home interpreter: prompts consume tails; effects follow commands."""
    def __init__(self, *, pack=None, equipment=None, pages=None, pack_limit=23,
                 home_limit=80, inside=True, state_template=None):
        self.pack = list(pack or [])
        self.equipment = dict(equipment or {})
        self.pages = [list(p) for p in (pages or [[]])]
        self.pack_limit, self.home_limit = pack_limit, home_limit
        self.page = 0
        self.inside = inside
        self.state_template = dict(state_template or {})
        self.pending = None
        self.trace = []
        self.queued = ""
        self.entries = int(inside)
        self.reentries = 0
        self.exits = 0
        self.turn = 1
        self.message = ""

    def socket_factory(self, *args, **kwargs): return _Socket(self)
    @staticmethod
    def _decode(notation):
        named = {"e": "\x1b", "s": " ", "r": "\r", "n": "\n",
                 "t": "\t", "b": "\b", "\\": "\\", "^": "^"}
        out, index = "", 0
        while index < len(notation):
            if notation[index] == "\\":
                index += 1
                if notation[index] == "x":
                    out += chr(int(notation[index + 1:index + 3], 16)); index += 2
                else:
                    out += named[notation[index]]
            elif notation[index] == "^":
                index += 1; out += chr(ord(notation[index]) & 31)
            else:
                out += notation[index]
            index += 1
        return out
    def _items(self): return [x for p in self.pages for x in p]
    @staticmethod
    def _sort_key(item):
        return (str(item.get("id", "")), str(item.get("name", "")),
                str(item.get("slot", "")))
    def _letters(self, values): return {chr(97 + i): value for i, value in enumerate(values)}
    def _consume(self, keys):
        for key in keys:
            self.trace.append(key)
            if self.pending:
                kind = self.pending
                self.pending = None
                if kind == "takeoff": self._takeoff(key)
                elif kind == "wield": self._wield(key)
                elif kind == "deposit": self._deposit(key)
                elif kind == "withdraw": self._withdraw(key)
                continue
            if key == "\x1b":
                if self.inside:
                    self.exits += 1
                self.inside = False
            elif key == "5" and not self.inside:
                if self.entries:
                    self.reentries += 1
                self.inside = True
                self.entries += 1
            elif key in " -": self.page = (self.page + (1 if key == " " else -1)) % len(self.pages)
            elif key == "t": self.pending = "takeoff"
            elif key == "w": self.pending = "wield"
            elif key == "d": self.pending = "deposit"
            elif key == "g": self.pending = "withdraw"
            else: self.message = "That command does not work in stores."
        self.turn += 1
    def _takeoff(self, letter):
        slots = {
            key: slot for slot, key in EQUIPMENT_SLOT_KEY.items()
            if slot in self.equipment
        }
        if letter not in slots: self.message = "Illegal equipment choice"; return
        item = self.equipment.pop(slots[letter])
        if len(self.pack) < self.pack_limit: self.pack.append(item); return
        if len(self._items()) < self.home_limit:
            self.pages[self.page].append(item); self.pages[self.page].sort(key=self._sort_key)
            self.message = "Your pack overflows! You drop it in your Home."
        else:
            self.pack.append(item); self.inside = False
            self.message = "Your pack is so full that you flee your home..."
    def _wield(self, letter):
        choices = self._letters(self.pack)
        if letter not in choices: self.message = "Illegal inventory choice"; return
        item = choices[letter]; self.pack.remove(item)
        equipment_slot = {
            19: "bow", 30: "feet", 35: "outer", 36: "body",
            39: "light",
        }.get(item.get("tval"), item.get("slot"))
        old = self.equipment.get(equipment_slot)
        item["slot"] = equipment_slot
        self.equipment[equipment_slot] = item
        if old: self.pack.append(old)
    def _deposit(self, letter):
        choices = self._letters(self.pack)
        if letter not in choices: self.message = "Illegal inventory choice"; return
        if len(self._items()) >= self.home_limit:
            self.message = "Your home is full."; return
        item = choices[letter]; self.pack.remove(item); self.pages[self.page].append(item)
        self.pages[self.page].sort(key=self._sort_key)
    def _withdraw(self, letter):
        choices = self._letters(self.pages[self.page])
        if letter not in choices: self.message = "Illegal store choice"; return
        item = choices[letter]; self.pages[self.page].remove(item); self.pack.append(item)
    def _state(self):
        state = dict(self.state_template)
        pack = []
        for index, item in enumerate(self.pack):
            current = dict(item)
            current["slot"] = chr(97 + index)
            pack.append(current)
        state.update({"turn": self.turn,
                      "floor": state.get("floor", {"dungeon_id": 0, "level": 0}),
                      "player": state.get("player", {"gold": 0}),
                      "inventory": pack,
                      "equipment": list(self.equipment.values()),
                      "grid_map": state.get("grid_map", {"runs": []}),
                      "messages": [self.message] if self.message else []})
        if self.inside: state["store"] = {"store_type": 7, "items": self.pages[self.page]}
        return state
    def request(self, request):
        op = request["op"]
        if op == "keys":
            keys = self._decode(request["keys"])
            # The control ACK proves only FIFO insertion.  The next hook is
            # what lets the game consume the posted bytes.
            self.trace.append(("accepted", keys))
            self.queued += keys
            result = {"pushed": len(keys)}
        elif op == "screen":
            if self.queued:
                queued, self.queued = self.queued, ""
                self._consume(queued)
            prompt = {"takeoff": "Take off which item?", "wield": "Wear/Wield which item?",
                      "deposit": "Drop which item?", "withdraw": "Get which item?"}.get(self.pending, self.message)
            result = _screen(prompt, self.inside, self.pages[self.page] if self.inside else ())
        else: result = self._state()
        return {"id": request["id"], "ok": True, "result": result}
