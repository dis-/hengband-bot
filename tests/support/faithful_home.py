"""Command-sensitive, source-derived Home fake for OperationExecutor tests.

Reconstructed inputs (the incident did not record them): STORE boards and stock
come from cmd-store.cpp's post-command emission; prompt text/shape and command
switch come from store-key-processor.cpp; overflow/refusal outcomes come from
cmd-store.cpp:170-184 and sell-order.cpp:69-118.  This is deliberately not an
incident transcript adapter.
"""
import json


def _screen(line0="", store=True):
    lines = [""] * 24
    lines[0] = line0
    if store:
        lines[20] = "You may: g) Get. d) Drop. w) Wield. t) Take off."
        lines[21] = " ESC) Exit from Building."
    return {"width": 80, "height": 24, "cursor": {"visible": True, "y": 20, "x": 0}, "lines": lines}


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
                 home_limit=80):
        self.pack = list(pack or [])
        self.equipment = dict(equipment or {})
        self.pages = [list(p) for p in (pages or [[]])]
        self.pack_limit, self.home_limit = pack_limit, home_limit
        self.page = 0
        self.inside = True
        self.pending = None
        self.trace = []
        self.turn = 1
        self.message = ""

    def socket_factory(self, *args, **kwargs): return _Socket(self)
    def _items(self): return [x for p in self.pages for x in p]
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
            if key == "\x1b": self.inside = False
            elif key in " -": self.page = (self.page + (1 if key == " " else -1)) % len(self.pages)
            elif key == "t": self.pending = "takeoff"
            elif key == "w": self.pending = "wield"
            elif key == "d": self.pending = "deposit"
            elif key == "g": self.pending = "withdraw"
            else: self.message = "That command does not work in stores."
        self.turn += 1
    def _takeoff(self, letter):
        slots = self._letters(sorted(self.equipment))
        if letter not in slots: self.message = "Illegal equipment choice"; return
        item = self.equipment.pop(slots[letter])
        if len(self.pack) < self.pack_limit: self.pack.append(item); return
        if len(self._items()) < self.home_limit:
            self.pages[self.page].append(item); self.pages[self.page].sort(key=lambda x: x["id"])
            self.message = "Your pack overflows! You drop it in your Home."
        else:
            self.pack.append(item); self.inside = False
            self.message = "Your pack is so full that you flee your home..."
    def _wield(self, letter):
        choices = self._letters(self.pack)
        if letter not in choices: self.message = "Illegal inventory choice"; return
        item = choices[letter]; self.pack.remove(item)
        old = self.equipment.get(item["slot"])
        self.equipment[item["slot"]] = item
        if old: self.pack.append(old)
    def _deposit(self, letter):
        choices = self._letters(self.pack)
        if letter not in choices: self.message = "Illegal inventory choice"; return
        if len(self._items()) >= self.home_limit:
            self.message = "Your home is full."; return
        item = choices[letter]; self.pack.remove(item); self.pages[self.page].append(item)
        self.pages[self.page].sort(key=lambda x: x["id"])
    def _withdraw(self, letter):
        choices = self._letters(self.pages[self.page])
        if letter not in choices: self.message = "Illegal store choice"; return
        item = choices[letter]; self.pages[self.page].remove(item); self.pack.append(item)
    def _state(self):
        state = {"turn": self.turn, "floor": {"dungeon_id": 0, "level": 0},
                 "player": {"gold": 0}, "inventory": self.pack,
                 "equipment": list(self.equipment.values()), "grid_map": {"runs": []},
                 "messages": [self.message] if self.message else []}
        if self.inside: state["store"] = {"store_type": 7, "items": self.pages[self.page]}
        return state
    def request(self, request):
        op = request["op"]
        if op == "keys":
            keys = request["keys"].replace("\\e", "\x1b")
            self._consume(keys); result = {"pushed": len(keys)}
        elif op == "screen":
            prompt = {"takeoff": "Take off which item?", "wield": "Wear/Wield which item?",
                      "deposit": "Drop which item?", "withdraw": "Get which item?"}.get(self.pending, self.message)
            result = _screen(prompt, self.inside)
        else: result = self._state()
        return {"id": request["id"], "ok": True, "result": result}
