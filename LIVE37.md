# live37: recorded Home scan gate finding

Base: b24fd077. Worktree: bot-client-decl-r3b, branch live37.

## Step 1

The recorded holders are store-router Reach claims 2566 (decision 3106,
14:45:29) and 8583 (decision 9682, 16:09:48). Both name (37,91),
`route:store:37,91`, `route.resume`; their visits have purpose `shopping`,
store_type 4, phase `entering`, requester `shop-buy`, no posted store operation.
The preceding recorded key is `7`, from (37,91) to (36,90). These facts were
printed from the two decision logs; the frozen extracts retain the original
records. This is Alchemist shopping, not a Home catalogue acquisition.

There is **no skipped entry gate on either recorded row**. The outside scan
at policy.py:8302-8376 calls `_defer_town_errand("home-scan", "outside-scan")`
at policy.py:8328. Both recorded claims contain the corresponding
`errand_deferred` row with the correct holder id and `token_would_admit: false`.
The OFF gate records this but returns false (policy.py:5861-5885); ON refuses
the producer. The scan is foreign work and must remain deferred under ON.
No new router catalogue dependency is justified by these records.

The false positive is at policy.py:6865-6870: shadow judges the emitted OFF
key as if it survived ON entry, without considering the gate actually
consulted before producing it. The planned correction binds the scan entry
verdict to its candidate key and checks this evidence in the shadow census.
An ungated key must still report `ownership:gate-missing:home-scan`.

The supplied first state capture is truncated: its first turn is 1301327,
after the incident turn 1271646; it contains 1858 rows. No board for decision
3106 exists there. The first case can therefore pin the recorded claim/gate
seam, not claim a complete public-policy replay. The second capture contains
the real boards at turns 1419549 and 1419557. Later boards following a changed
ON key will not be consumed (R4).

Running s33_shadow_report on decompressed, frozen decision extracts reports
one `ownership:gate-missing:home-scan` per incident. That script reads plain
JSONL, not gzip; directly passing gzip silently reports zero decisions.

No screen classification or modal continuation is changed (R2). No
EXPECTED_FIRST edits, assertion edits, thresholds, or new policy attributes.

assertion_audit (verbatim): `No changed pre-existing assertions or forbidden test edits.`
changed_preexisting_assertions: []
