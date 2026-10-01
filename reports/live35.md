# live35 diagnosis (step 1)

Recorded screen first: live-screen-20261001-1432-knowledge-scan-store-page.json shows the Home take-item chooser. Recorded decision 2674 posts Eg; 2675 posts ~9. The E map command was interpreted inside the Home command language.

- policy.py:9028 selects ESC / home:scan-incomplete-open-page for an incomplete Home page.
- policy_town.py:761 rejects ESC as progress unless the special filed/entry-operation cases apply. policy_town.py:1172 protects only two named open-store reasons. policy_town.py:1283 invokes procurement again.
- policy_town.py:1000 calls _mana_food_survival_override_key before the supplier fallback. policy_supply.py:1056 finds an edible charged device and composes E + slot without a store check; its later store branch cannot protect this early return. This turns the scan exit into survival:mana-absorb.
- Other producers: policy_supply.py:982 town eat composes E + slot without a store guard. policy_combat.py:1594 _emergency_item composes healing quaff/read actions without an entry store guard. policy.py:13909 _read_key does not close a store. policy.py:11237 rest and policy_town.py:5306 town:recover compose REST_MACRO without a local store guard. These ordinarily run after policy.py:9969 routes open stores, but procurement re-entry bypasses that routing.
- Detector _forbid_wait_while_damaged (policy_combat.py:313) checks store context and leaves first on damage (324); _flee_sustain_key (439) excludes stores. Recovery/no-wait map actions must not be invoked by a store-progress rewrite.

Rule: an observed store page owns its command language. The progress invariant preserves the store producer result and never enters map-command procurement on that page, for every survival/detector action, independent of reason or food type. Store exits remain their own ESC step; map decisions wait for an outside observation. No new policy attribute is needed.

Additional map producers and context checks (step 1 audit):

| Command | Producer sites | Local store check / production routing |
| --- | --- | --- |
| eat | policy_supply.py:985,1008,1060; policy.py:10724,11417; policy_combat.py:2042 | No local store check before eat. Normal _decide store routing at policy.py:9969 runs first; the procurement bypass caused the incident. |
| quaff | policy_combat.py:1717,1804,1906,2020; policy.py:14239 stat-gain | No entry store guard; normal store routing precedes these producers. Flee sustain excludes store/town at policy_combat.py:439. |
| read | policy.py:13909 _read_key; emergency read paths in policy_combat.py:_emergency_item | _read_key binds the scroll but does not check store context. Normal store routing prevents selection. |
| rest | policy.py:11237 | No local store condition in the rest predicate; normal store routing runs first. |
| recover | policy.py:10747; policy_town.py:5306 | No local store check around REST_MACRO; normal store routing runs first. |
| detector recovery | policy_combat.py:313 _forbid_wait_while_damaged | Explicit store exit at :324 before read/flee/attack replacement on damage. |
| detector oscillation | policy_navigation.py:551 | Excludes store/town at :559. |
| detector livelock | policy.py:9751 | No explicit store test; only repeats map movement reasons. Does not produce eat/quaff/read/rest. |

Step 2 changes: policy_town.py:1225 refuses boxed map breakout on an observed store page; :1278 preserves the original store result before procurement invokes map producers. Existing shelf continuation annotation and knowledge scan bookkeeping still execute. There is no mana-only exception, new attribute, threshold, or EXPECTED_FIRST edit.

The pin reconstructs the recorded exit reason at the real production procurement seam on the frozen incident boards (no producer mocks), with the actual screen and posted-character rows alongside it. The screen includes the Home take-item chooser, and the recorded edible device selector is g. The fixture includes SHA256 provenance of all four source files and is itself checksum-pinned. This is a seam replay, not a restoration of the post-incident policy dump as if it were a pre-incident checkpoint.
