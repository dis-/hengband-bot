# S3.3 first divergence before amendment #8 behavior changes

Measured on the R5 policy, before the record-only #8 edits. Each ON replay
uses the same fixture walls as OFF and stops at the first changed key **or**
reason. `scripts/first_divergence_s3_3.py` checks the entire OFF key/reason
stream against the six R4 SHA-256 pins before it starts ON. All six passed.
The tour fixture stores historical keys/reasons but omits decision sequences;
its historical sequence below uses the OFF replay counter on the corresponding
board. `ESC` is `\x1b`, `CR` is `\r`.

| Fixture (SHA-256) | List index | Historical / new sequence | Historical and OFF key / reason | ON key / reason | Pre-decision parent; session; operation; delegates |
| --- | ---: | --- | --- | --- | --- |
| Tour `ee4c27fa348569fe8274767cbfc9c1ce76a4f54cf8a102768216cb42995c024d` | 2643 | 2641 / 2641 | `~9 ESC` / `home:request-knowledge-scan` | `ESC` / `home:scan-incomplete-open-page` | Both: store-router #2292 active Reach (45,123); no session; Home visit #2292 entering, unposted, no operation identity; delegates `[]`. |
| Town approach `249feeff221d652c51bb8b56d9c4ec021ce17bd309f39b17d9d53f940e106093` | 1179 | 1177 / 1177 | `ESC` / `home-errand:filed:combat-weapon` | `ESC` / `home:store-context-exit` | Both: equipment-txn #584 active transaction Observe, pending deposit action in session opened at 1175; Home visit #584 operating, posted, operation identity absent; delegates `[]`. |
| Overweight Home `f0eee9ea489edb276f7deed60696140ace323c301a465ec88201a89d5f8dae9a` | 6 | 6 / 6 | `~9 ESC ESC` / `home:request-knowledge-scan` | `\x1b\x60n%.` / `shop:travel` | Both: departure #5 active Terminal (`town:unsafe-recall-fallback`); no session or visit; delegates `[]`. |
| Home withdraw `041b395d5882c9eeee2232fb82ce98686bb955a0250b23f0c2f8c7b06330019a` | 3 | 3 / 3 | `~9 ESC` / `home:request-knowledge-scan` | `5` / `ownership:holder-complete` | Both: equipment-txn #3 active store-entry Observe; Home visit #3 entering, unposted, no operation identity; no session; delegates `[]`. |
| Recall cancel `b68d2fdf326b6639dea2ad51581a06ddaac3516d00184cb9794eea3a8e206867` | — | — | No ON/OFF difference in 18 decisions | — | — |
| Stuck prompt `e47a45e211b2d7f5e2c98873e3a1c56789f0b597de5be80eacb9169a1f27918a` | — | — | No ON/OFF difference in 4 decisions | — | — |

The fixed expected first-difference table is in
`tests/test_ownership_s3_3_first_divergence.py`. It precedes policy fixes:

| Fixture | Expected first ON difference, list index / historical sequence | Expected key / reason | Current classification |
| --- | --- | --- | --- |
| Tour | 2705 / 2701, after the declared index-2701 historical harness difference | `2` / `melee` with route suspension | Early difference at 2643; defect. |
| Town approach | 1179 / 1177 | `5` / `equipment-transaction:atomic-deposit` | Right row, wrong key and reason; defect. |
| Overweight Home | 3724 / 3723, beyond declared historical differences at 3702/3706/3707 | `3` / `shop:approach` | Early difference at 6; defect. |
| Home withdraw | No designed ON difference | — | Unexpected difference at 3; defect. |
| Recall cancel | No designed ON difference | — | Matches. |
| Stuck prompt | No designed ON difference | — | Matches. |

The expected table applies to continuous replay only. The later design §5
boards (tour 3037/3052 and town 1922/1947/1957/1958) remain isolated
counterfactual acceptance scenarios after the first divergence.
