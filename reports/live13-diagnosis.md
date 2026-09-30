# live13 diagnosis

Base: 56ca3272277fa7da843f4cb1c541db46ee3af9a3; fast-forward already current.

Recorded state at 513463 before purchase: f = identification staff (tval 55, sval 5). After purchase and at 513470: f = *Identify* scroll (70,13), g = staff. Thus rf used the correct current letter, not a stale purchase letter.

Posted-character rows for sequence 87 record the entire `rf/a` plus eight ESC characters as accepted. cli.py:3320-3331 records accepted segments, not per-character consumption by the game. They establish transport acceptance only; there are no intermediate live screens proving what consumed each character. The stopped screen shows the *Identify* equipment chooser and main-hand sword at a. No successful identification/result viewer is recorded. Claims that / toggled away, or that each ESC was consumed in this chooser, would exceed the evidence.

policy_equipment.py:2505-2518 blindly combines current source.slot, slash, fixed equipment slot letter, and eight ESC; unlike carried identification it never installs a staged prompt chain. input_executor.py:241 recognises only normal Identify, missing the literal full-identify prompt (spells-perception.cpp:171). The executor consequently stops as unknown after the already accepted macro.

floor-item-getter.cpp:296-303 selects equipment directly when no eligible pack item exists; :687-705 toggles / only when the other collection is allowed. The last visible pack items are fully_known, while equipped items are not: / is unnecessary for this recorded selection, and cannot be assumed to toggle to inventory. :642-644 handles a consumed ESC by ending the chooser. The persistent screen therefore does not establish that the accepted ESC tail was consumed there. Fix requires separate prompt barriers, selecting a directly on an equipment screen and toggling only on an inventory screen, with current-board source binding.

Visible evidence used: inventory slot, tval/sval/name/known; equipment slot and known state; exact row-zero prompt, equipment list label. No hidden item flags are introduced.

changed_preexisting_assertions: []
assertion_audit: No changed pre-existing assertions or forbidden test edits.
