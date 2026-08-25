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
10. **Snapshots use `grid_map`, not `nearby_grids`, in the current wire format.** A measured town
    `player_turn` snapshot is approximately 27,577 B (formerly 6,371,071 B), including a 17,362 B
    grid payload. The grid is now approximately 63% of the snapshot, so claims that it accounts for
    more than 99% of the bytes are obsolete. Measured dungeon-row reduction varies with floor size and
    cell count (1.44x at 12 cells up to 44.94x at 1,361 cells); no single factor describes it. Store snapshots omit the map. The state file truncates
    at session start and bounds itself (`BOT_JSON_OUTPUT_MAX_BYTES`), so preserve long-run evidence
    promptly.

The emitter campaign chain (eleven commits, 52c86e0732..899fbee927 plus the two earlier local commits 7861c38f86, 1ce92ea709) is LOCAL-ONLY on the game repo until pushed; the running exe may not match the source tree.

10a. **Travel point selection is modal and its symbol list is game-internal.** `` ` `` enters
    `do_cmd_travel`; when an old non-player goal exists, `n` declines the "continue travel?"
    prompt, otherwise point selection receives and ignores the non-direction `n`
    (`cmd-travel.cpp:15-24`, `grid-selector.cpp:201-274`). In the selector, shifted store
    symbols search the marked acceptable-target vector (`grid-selector.cpp:34-68, 102-112,
    231-247`). If no symbol match exists, the cursor is reset to the player
    (`grid-selector.cpp:153-162`). `.` at the player clears the byte but does not select a
    point, so the selector remains open; Escape is what exits it (`grid-selector.cpp:216-230`).
    The emitted `grid_map` cell set is not proof that the selector's live candidate vector will
    accept a symbol: the turn-4684095 artifact disclosed marked Home `(45,123)`, yet the posted
    `(` selection made no movement and consumed no turn. Bot recovery must therefore bound an
    observed failed issue rather than claim it can predict selector reachability.

10b. **State that the bot's own action necessarily changes must never count as progress.** The
    `evidence-home-queue-withdraw-loop` incident survived owner expectations because leaving and
    re-entering Home changed store context; owner progress is instead floor, position, gold,
    experience, pack, and equipment.
    Loop-fix acceptance replays must deliver the full captured JSONL sequence through the live
    dispatcher; filtering synthetic inputs by snapshot type is forbidden.

11. **Wear/wield input is `w` plus the pack letter, followed by every prompt answer.** Most armour has
    no second prompt. Weapons and digging tools retain their `do_cmd_wield` hand answer (for example
    `wja`). Rings always open a second `choose_item(..., USE_EQUIP)` selector
    (`cmd-equipment.cpp:204-222`). Under the original keyset, select the main-ring endpoint with `(`
    and the sub-ring endpoint with `)`: the selector maps these keys to `e1`/`e2`
    (`floor-item-getter.cpp:824-842`), and `select_ring_slot` makes those endpoints exactly the two ring
    slots (`inventory-util.cpp:132-142`). Do not send the equipment letter `d`/`e`: `get_tag()` is
    consulted first (`floor-item-getter.cpp:797-842`), so a command-specific tag can consume the
    character before `label_to_equipment()` gets it. Thus a pack-`e` ring for the main ring is `we(`.

12. **Landmine: composed pack selectors must remain lowercase; do not reintroduce uppercase
    selectors.** `get_tag()` only examines inscribed items and accepts a command-specific letter tag
    when the inscription has at least three bytes and its command and tag bytes match
    (`inventory-util.cpp:95-128`). Numeric sale bindings such as `@0`/`@1` are allocated and emitted as
    numeric tags (`policy.py:18084-18110`, `policy.py:18146-18167`), so their numeric selector path
    cannot collide with a letter selector (`inventory-util.cpp:115-119`). Conversely, an uppercase
    selector for which no tag was found opens the mandatory `Try <item>?` verification
    (`floor-item-getter.cpp:873-877`). That prompt does not treat an arbitrary wrong byte as an abort:
    `input_check_strict()` accepts only `y`/`Y`, `n`/`N`, or Escape and otherwise calls `bell()` and
    loops (`inventory-util.cpp:237-248`, `asking-player.cpp:198-292`). The remaining bytes of a
    composed key then land in the verification prompt and desynchronize the command. Therefore read,
    quaff, eat, refill, wield, fire, throw, device, destroy, inscribe, drop, identify, enchant, and
    remove-curse composers must emit the pack label exactly as its lowercase inventory letter.

13. **`~9` leaves two invisible input owners open and must be closed after its response as `ESC ESC`.** The
    knowledge command reads its menu key directly and dispatches `9` to the Home snapshot and
    `do_cmd_knowledge_home()` without leaving its loop (`cmd-knowledge.cpp:27-33, 65-74, 111-114,
    171-174`). Home then enters `FileDisplayer` (`knowledge-self.cpp:189-205, 238-241`). The viewer
    reads another key at `show-file.cpp:323`; a plain `9` reaches its no-op `default:` at
    `show-file.cpp:453-455`, and only ESC, `<`, or `q` exits (`show-file.cpp:503-513`). Thus the
    2026-08-14 bytes `~9` at 13:22:25.424/25.449 armed the viewer, and the claim-approach `9` at
    13:22:25.945 was consumed there with no turn, message, movement, or prompt in JSON. One ESC
    returns to the still-open knowledge menu and a second ESC leaves that menu. This is not repeat
    count: count entry starts only on command-loop `0`, echoes `Count:`, and returns the first
    non-digit (`input-key-requester.cpp:170-223`). It is not a BOT_PLAY keymap either: keymaps are
    expanded only by the command requester (`input-key-requester.cpp:71-98`), while the viewer calls
    `inkey_special()` itself. `do_cmd_walk()` was never reached; only after its direction succeeds
    does it set energy and execute movement (`cmd-move.cpp:344-371`). The response dispatcher
    therefore closes the producer-owned viewer and menu before any later policy key can be
    interpreted. The existing stalled-command Escape recovery closes the same viewer when no
    response arrives, so response-timed closure remains bounded by that grace.

14. **Decode the current grid wire without inventing cells.** `grid_map` has the shape
    `{cells, h, palette, runs, unsafe_rows, w}` and may additionally contain `schema_error`.
    `w` and `h` duplicate `floor.width` and `floor.height`. `palette[i]` is the four-tuple
    `[terrain_id, flag_bits, terrain_bits, known]`; `known` is currently always 1. Each run is
    `[y, x0, len, palette_index]`, is
    row-local, has `len >= 1`, and is ordered by ascending `y` then `x0`. Runs describe the complete
    emitted cell set. `found_items` rows are deliberately not required to be covered by a run. Do not
    fill gaps or introduce a sentinel for uncovered coordinates. JSON object key ordering is
    non-contractual.

    `cells` is the sparse sidecar keyed by `y` and `x`. Decode its short keys as follows: `m` is
    `monster_index`, `o` is `object_count`, `t` is `object_tvals`, `s` is `store_number`, `e` is
    `entrance_dungeon_id`, `q` is `quest_id`, `b` is `building_type`, and `p` is
    `building_special`. `t` is present when `o` is present. A cell without sidecar data defaults to
    `monster_index=0`, `object_count=0`, and `object_tvals=[]`; sparse terrain metadata remains absent.
    `cells[].o` means that something is present, including gold; the key is emitted only when the
    count is greater than zero (so `o >= 1` whenever present). `found_items` has rows `[y, x, count, tval...]` and reports known item classes while
    excluding gold. These are separate authorities and consumers must never cross-populate them.
    During hallucination they also use different subwindows: `cells[].t` is redacted, while
    `found_items` is not.
    The present-but-empty map is exactly
    `{"cells":[],"h":H,"palette":[],"runs":[],"unsafe_rows":null,"w":W}`. It still counts as an
    observed map. An ABSENT grid_map key (store snapshots; pre-campaign rows) means the map was NOT
    observed (grids_observed false).

15. **Treat the grid bit tables as append-only wire definitions.** Append new bits at the end. Never
    reorder existing bits.

    | Flag bit | Name |
    | ---: | --- |
    | 0 | `mark` |
    | 1 | `cave_known` |
    | 2 | `lite` |
    | 3 | `view` |
    | 4 | `room` |
    | 5 | `unsafe` |
    | 6 | `glow` |
    | 7 | `mnlt` |
    | 8 | `mndk` |

    Palette flag fields use ordinary numbered bits. This packing is distinct from the LSB-first
    hexadecimal digit packing used by `unsafe_rows`. As an interim same-commit capability proxy,
    flag bits 6 through 8 are meaningful if and only if the `found_items` key is present. This rule
    remains in force until the wire gains an explicit capability marker.

    | Terrain bit | Name |
    | ---: | --- |
    | 0 | `building` |
    | 1 | `can_dig` |
    | 2 | `door` |
    | 3 | `down_stairs` |
    | 4 | `entrance` |
    | 5 | `floor` |
    | 6 | `has_gold` |
    | 7 | `los` |
    | 8 | `move` |
    | 9 | `permanent` |
    | 10 | `quest_enter` |
    | 11 | `quest_exit` |
    | 12 | `stairs` |
    | 13 | `store` |
    | 14 | `trap` |
    | 15 | `tunnel` |
    | 16 | `up_stairs` |
    | 17 | `wall` |

16. **Separate remembered knowledge from display marking.** Palette `known` means
    `is_grid_known_to_bot` (#5516): the game remembers the grid. The display axis remains flag bit 0,
    `mark`. A known-only cell (`known=1`, `mark=0`) may be emitted and may carry truthful terrain.
    Offline analyses spanning wire eras must also account for the flight recorder's `known_cells`
    changing from an integer to `{"known": N, "marked": M}`.

17. **Treat `schema_error` as a failed observation, not an empty floor.** `schema_error: true`
    accompanies only an empty `grid_map`. On this degraded return the emitter still populates the
    `unsafe_rows` and `found_items` side planes; by supervisor decision, the consumer discards both
    planes together with the map. The parser sets the map-observed state to false and surfaces
    `grid_map_schema_error` in decision records. A normal empty map without the marker remains an
    observed map.

18. **Consume own-grid visibility as a three-valued campaign field.** Every current snapshot type
    carries boolean `player.can_see_own_grid`, equal to `!no_lite(player_ptr)`. It is the light gate for
    reading scrolls - and ONLY that conjunct: the wild-mode, arena, and confusion read gates live
    elsewhere. Blindness implies false, so the field is not an independent signal from player.blind. Pre-campaign rows omit it, so consumers must distinguish absent, false, and true.
    `player.light_radius` is a separate signed int32 field. It may be zero or negative and must not be
    inferred from, or substituted for, `can_see_own_grid`.

19. **Decode the swap-2 side fields without manufacturing knowledge.** Underground `unsafe_rows` is
    a list of exactly `h` lowercase-hex strings, each exactly `ceil(w / 4)` digits. Within each hex
    digit the lowest-order bit is the leftmost cell. Bit 1 means the cell is unreached and therefore
    possibly trapped; it does not mean "a trap is here". The key is three-valued: absent for an older
    emitter, null when unavailable (including the surface), and a list when emitted underground.
    Reject the whole plane on any row-count, width, digit, or value mismatch. Never pad a short row:
    a fabricated zero would falsely clear an unreached possibly-trapped cell. Consumers may additionally
    validate that border bits and unused pad bits are always zero (the emitter produces these
    invariants). Payload sizes, including JSON
    framing, vary with dimensions: 198x66 is 3,499 B, 66x66 is 1,321 B, and 132x22 is 793 B; no single
    size describes the field.

    `floor.feeling` is an integer from 0 through 10 on Hengband's inverted scale: larger values are
    safer, value 2 is the most dangerous, and 0 means no information (including on the surface).
    Validate the range and reject invalid values rather than clamping them. Values 9 and 10 share the
    white display colour. Feeling text must be interpreted through the per-character text table; it is
    not a universal numeric-to-string mapping. `player.light_radius` follows the signed-int32 and
    independence rules in section 18. `found_items` and flag bits 6 through 8 follow sections 14 and
    15, including their authority, hallucination, and interim capability-proxy rules.

20. **Use `emitter-timing-c2.log` as the serialization timing sidecar.** Each line records `type`,
    `turn`, `build_us`, `dump_us`, `write_us`, and `bytes`. The emitter places it beside the configured
    JSON output, truncates it once per session when first opened, appends one flushed line per snapshot,
    and disables it after two failed open attempts.
