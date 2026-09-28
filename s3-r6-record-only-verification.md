# S3.3 R6: first divergence and record-only delegation

The two implementation steps are committed separately. Step 1 measured R5
before amendment #8; its table, fixture hashes, pre-decision state, and
frozen expected table are in `s3-first-divergence-before-8.md` and
`tests/test_ownership_s3_3_first_divergence.py`. The observed early
differences remain defects for later behavior steps; this round does not
change ON keys or reasons.

Commits: step 1 `e9373a43`; step 2 `582467fc`.

## Delegation records

Each explicit execution record carries `parent_claim_id` (or a same-decision
reservation), parent and delegate family, tuple work and purpose identities,
opening decision, expected effect, existing budget reference, lifecycle and
named ending. A reservation binds at the `choose_key` claim exit only when
that exit declares its requested parent; another owner cancels it by name.
Records and token checks are advisory in R6. The hold return value is unchanged.

| Opening site | Recorded work |
| --- | --- |
| Calibration strip and restore session installation | Exact session target and action identities, before the equipment executor gate. |
| Calibration deposit phase and Home composition | Eligible pack candidate signatures, then only a Home operation whose deposited signatures were registered in the calibration restore obligation. |
| Calibration restore-knowledge and restore-supplies phases | Scan epoch/requested signatures and the requested Home restore batch. |
| Equipment combat-weapon and identification Home filing | Exact requested signature, quantity, origin and purpose before the Home filing gate; a separately filed Home request is a top-level Home owner when there is no matching parent claim. |
| Filed Home errand needing knowledge | Exact filed purpose and scan epoch before knowledge selection. |
| Staged Home operation | Visit ID and immutable operation key for the tail; effect observation completes the child. |
| Store trip acceptance | Requester, purpose and store target before route assignment. The later buy/sell one-shot is recorded as a separate sequential operation. |

`requester_families` is recorded on each planned stop and preserved as a set
when its store visit is reused. Quest categories remain in
`need_categories`; their shop operation is represented by `shop-buy` because
quest is outside the S3 town errand family set. Missing requester evidence
remains an empty set. Older checkpoints lacking the new record and set fields
are covered by restored-policy tests.

## OFF identity and ON token admission

Each replay ran in its own Python process on the final R6 code. The six OFF
key/reason SHA-256 hashes equal `s3-r4-verification.md` exactly.

| Fixture | Decisions | OFF SHA-256 | ON deferrals | ON deferrals an exact token would admit | Token at named real interruption |
| --- | ---: | --- | ---: | ---: | ---: |
| Tour | 4267 | `d30b053bc9744336253c0b2235f7887dd3b4604bc09a86b715262c8377de5464` | 292 | 8 (calibration → equipment-txn) | 0 |
| Town approach | 2052 | `7fe5100909a3346355e5c0a9c4e66d649bae412987a46276040c077277f550b1` | 79 | 0 | 0 |
| Overweight Home | 3782 | `8e76a2056d587730d825bc367b0fc3812da13610809f96193b03445ef542758b` | 148 | 0 | 0 |
| Home withdraw | 34 | `a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9` | — | — | — |
| Recall cancel | 18 | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` | — | — | — |
| Stuck prompt | 4 | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | — | — | — |

The town measurement initially exposed a filing token at decision 1177 while
an equipment deposit was pending. Its exact identity was valid, but accepting
it would authorize a real interruption. The token check now rejects any
unfinished equipment session or posted, unobserved store operation. The final
replay reports zero such admissions. Generic outside Home scans at tour 3052
and overweight 3723 cannot borrow a filed knowledge token.

## Required module run

All 125 required `test_*.py` modules ran, one module per Python process,
with `PYTHONPATH=src;tests;scripts`: 4,042 tests passed, 0 failures. The
24 modules started before the final record-only edit were rerun on the final
code. `test_town_stall` discovers zero tests, as in the prior R4 run. Exact
per-module counts are in `s3-r6-test-counts.tsv`.
