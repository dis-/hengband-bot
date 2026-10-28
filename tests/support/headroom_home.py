"""Home command interpreter for consumable headroom continuations.

Extends the equipment Home fake with the game's p/g alias, quantity prompt
and ~9 catalogue. Inventory changes only after accepted item/quantity keys.
This is a constructed engine response, not a recording of the changed policy.
"""
import copy

from tests.support.faithful_home import FaithfulHomeGame


class HeadroomHomeGame(FaithfulHomeGame):
    transfer = None
    quantity_text = ""

    def _letters(self, values):
        return {chr(97 + i) if i < 26 else chr(65 + i - 26): item
                for i, item in enumerate(values)}

    def request(self, request):
        response = super().request(request)
        if request["op"] == "screen" and self.pending in {"deposit", "withdraw"}:
            response["result"]["lines"][0] = (
                "どのアイテムを置きますか?" if self.pending == "deposit"
                else "(アイテム:a-Z, ESCで中断) どのアイテムを取りますか?")
        return response

    def _select_transfer(self, kind, letter):
        values = self.pack if kind == "deposit" else self.pages[self.page]
        item = self._letters(values).get(letter)
        if item is None:
            self.message = "Illegal item choice"
            return
        if item.get("count", 1) > 1:
            self.transfer = (kind, item)
            self.quantity_text = ""
            self.pending = "quantity"
            self.message = f"いくつですか (1-{item['count']}): "
        else:
            self._transfer(kind, item, 1)

    def _deposit(self, letter):
        self._select_transfer("deposit", letter)

    def _withdraw(self, letter):
        self._select_transfer("withdraw", letter)

    def _transfer(self, kind, item, count):
        source = self.pack if kind == "deposit" else self.pages[self.page]
        destination = self.pages[self.page] if kind == "deposit" else self.pack
        if kind == "deposit" and len(self._items()) >= self.home_limit:
            self.message = "Your home is full."
            return
        if not 1 <= count <= item.get("count", 1):
            raise AssertionError("invalid transfer quantity")
        moved = copy.deepcopy(item)
        moved["count"] = count
        if count == item.get("count", 1):
            source.remove(item)
        else:
            item["count"] -= count
        destination.append(moved)
        self.pages[self.page].sort(key=self._sort_key)
        self.message = ""

    def _consume(self, keys):
        for key in keys:
            if self.pending == "quantity":
                self.trace.append(key)
                if key == "\r":
                    kind, item = self.transfer
                    self._transfer(kind, item, int(self.quantity_text or "1"))
                    self.pending = self.transfer = None
                elif key.isdigit():
                    self.quantity_text += key
                else:
                    raise AssertionError("quantity prompt consumed an invalid key")
            elif key == "~" and self.modal is None:
                self.trace.append(key)
                self.modal = "knowledge-menu"
            else:
                # p is Get only in the main store loop, never an item letter.
                super()._consume("g" if key == "p" and self.inside
                                 and self.pending is None and self.modal is None else key)

    def _state(self):
        state = super()._state()
        if self.inside:
            state["type"] = "store"
            state["store"].update(stock_num=len(self._items()), capacity=self.home_limit,
                                  page_size=52, page_top=0)
            state["store"]["items"] = [dict(item, letter=chr(97 + i) if i < 26
                                           else chr(65 + i - 26))
                                       for i, item in enumerate(self.pages[self.page])]
        else:
            state["type"] = "player_turn"
            state.pop("store", None)
        return state
