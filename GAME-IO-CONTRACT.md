# GAME I/O CONTRACT — measured semantics of Hengband's input/snapshot boundary

Every entry below was discovered AFTER a fix failed live. Fixer prompts and fixtures MUST honour these;
a test world that contradicts one is invalid by construction. Sources are in `C:\hengband\src` (read-only
for bot fixers).

1. **Walking onto a shop tile ENTERS the shop.** There is no "standing outside on the tile" state after a
   movement step. An approach step is an entry. (`player-move.cpp` MPE path → `SPECIAL_KEY_STORE`.)
2. **Store entry schedules `flush()`**: `disturb()` at `player-move.cpp:240` with `flush_disturb` →
   `flush()` sets `inkey_xtra` → the store's first `inkey()` calls `term_flush()` which **discards all
   queued keys** (`input-key-acceptor.cpp:202-208`, `z-term.cpp:1760`). Therefore a composed key that
   crosses the entry boundary loses everything queued before the store opened. Keys posted while the
   store is already open are safe (measured: `5da…` deposits complete; 21 queued SPACEs vanished).
3. **The store loop emits exactly one store snapshot per processed key**, at the top of each iteration
   (`cmd-store.cpp:152`), BEFORE reading the next key.
4. **Entry is visible one snapshot late.** The snapshot immediately after the entering WAIT can still be
   `store: None` at the same turn; the store snapshot arrives next. "Same turn, still outside" is NOT
   evidence of entry failure — failure has an explicit message (「ドアに鍵がかかっている。」,
   `cmd-store.cpp:91`). The only "cannot go there" string in the game is the TRAVEL refusal
   (`cmd-travel.cpp:41`) — do not match it for store entry.
5. **Store item letters are page-relative** (`a` = `stock[store_top]`); SPACE pages forward and wraps to
   page 0; `-` pages back; on a single page SPACE prints 「これで全部です。」 and is still a valid key
   (`store-key-processor.cpp:68-106`). Digits and movement keys have no case in the store dispatcher and
   fall to `default:` → 「そのコマンドは店の中では使えません。」 (`:269-274`).
6. **Store snapshots carry `stock_num` / `page_top` / `page_size`** (emitter commit `1ce92ea709`).
   `page_size = store_bottom = 12 + min(40, hgt-24)`. A full page (letters a..Z) is NOT evidence the
   stock ends there — use `stock_num`.
7. **`~9` (knowledge: Home inventory) lists `store.stock[i]` in stock order** (`knowledge-self.cpp:214`),
   the SAME array/order as the store display (`bot-json-output.cpp:861`). Hence
   `page = i // page_size`, `letter = 'a'+(i%page_size)` (`'A'+…-26` above 26). The knowledge file's own
   12-per-page 「( N ページ )」 headers are its pagination, not the store's.
8. **Deposits/purchases of stacks with `number > 1` raise a quantity prompt** (`sell-order.cpp:97-103`,
   `input_quantity` at `asking-player.cpp:326`); cancelling returns 0 and aborts the operation. A
   composed key must answer the prompt exactly when it will appear.
9. **A modal Windows dialog (e.g. save refusal 「今はセーブすることは出来ません。」) blocks ALL game
   input** until dismissed; the JSONL freezes. Check for `#32770` dialogs before judging the bot stuck.
10. **Snapshots**: `player_turn` ≈ 5.1 MB dominated by `nearby_grids` (~10k cells); store snapshots omit
    the map (emitter commit `7861c38f86`, ~34 KB). The state file truncates at session start and bounds
    itself (`BOT_JSON_OUTPUT_MAX_BYTES`), so long-run evidence must be preserved promptly.

Both emitter commits are LOCAL-ONLY on the game repo (not pushed): `7861c38f86`, `1ce92ea709`.

11. **Wear/wield input is `w` plus the pack letter, followed by every prompt answer.** Most armour has
    no second prompt. Weapons and digging tools retain their `do_cmd_wield` hand answer (for example
    `wja`). Rings always open a second `choose_item(..., USE_EQUIP)` selector
    (`cmd-equipment.cpp:204-222`). Under the original keyset, select the main-ring endpoint with `(`
    and the sub-ring endpoint with `)`: the selector maps these keys to `e1`/`e2`
    (`floor-item-getter.cpp:824-842`), and `select_ring_slot` makes those endpoints exactly the two ring
    slots (`inventory-util.cpp:132-142`). Do not send the equipment letter `d`/`e`: `get_tag()` is
    consulted first (`floor-item-getter.cpp:797-842`), so a command-specific tag can consume the
    character before `label_to_equipment()` gets it. Thus a pack-`e` ring for the main ring is `we(`.
