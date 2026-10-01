# live35 diagnosis (step 1)

Recorded screen first: live-screen-20261001-1432-knowledge-scan-store-page.json shows the Home take-item chooser. Recorded decision 2674 posts Eg; 2675 posts ~9. The E map command was interpreted inside the Home command language.

- policy.py:9028 selects ESC / home:scan-incomplete-open-page for an incomplete Home page.
- policy_town.py:757 rejects ESC as progress unless the special filed/entry-operation cases apply. policy_town.py:1180 protects only two named open-store reasons. policy_town.py:1276 invokes procurement again.
- policy_town.py:1000 calls _mana_food_survival_override_key before the supplier fallback. policy_supply.py:1056 finds an edible charged device and composes E + slot without a store check; its later store branch cannot protect this early return. This turns the scan exit into survival:mana-absorb.
- Other producers: policy_supply.py:982 town eat composes E + slot without a store guard. policy_combat.py:1594 _emergency_item composes healing quaff/read actions without an entry store guard. policy.py:13909 _read_key does not close a store. policy.py:11237 rest and policy_town.py town:recover compose REST_MACRO without a local store guard. These ordinarily run after policy.py:9969 routes open stores, but procurement re-entry bypasses that routing.
- Detector _forbid_wait_while_damaged (policy_combat.py:313) checks store context and leaves first on damage (324); _flee_sustain_key (439) excludes stores. Recovery/no-wait map actions must not be invoked by a store-progress rewrite.

Rule: an observed store page owns its command language. The progress invariant preserves the store producer result and never enters map-command procurement on that page, for every survival/detector action, independent of reason or food type. Store exits remain their own ESC step; map decisions wait for an outside observation. No new policy attribute is needed.
