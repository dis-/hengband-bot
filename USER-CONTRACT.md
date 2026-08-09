# USER CONTRACT — the user's standing directives, verbatim, with their enforcing gates

This file transcribes directives the user has issued. It adds nothing and narrows nothing.
Reviewers MUST diff every fix against this file. A fix that conditions, scopes, or weakens any entry
without a fresh user decision is a spec violation regardless of its tests.

| # | Directive (verbatim) | Enforced by |
|---|---|---|
| 1 | 「売却に関して『事前に銘を刻んだものだけを売る』」— そのような抜け道（数量・回数の条件付け）は許容されていない | `scripts/sale_key_lint.py` (letter-composed sale keys fail the build); pins in `tests/test_policy.py` (single-item sale is inscription-bound; no-inscription → no sale) |
| 2 | 「装備一覧から最適化処理が潜行可能深度を判定する」— 外部要因（帰還深度・ザック数・所持金）で目標が揺らいではならない | derived-depth pins (`test_selected_loadout_derives_the_deepest_satisfied_band`, `test_owned_loadout_depth_is_not_inferred_from_recall_destinations`) |
| 3 | 「このbotは店内で判断することが致命的に苦手…店内で判断することを極力避けなければならない」→ ワンショット原則 | `policy.py` store-context rule (Home selection never decided in the store loop); StoreVisit state machine; derived-address withdrawal (no in-store observation) |
| 4 | 「無思慮な反復試行を禁止」— 直前の投函の効果を観測せずに店コマンドを再投函しない（原子的な複数キー投函自体は可） | no-double-entry pins; no-progress cycle refusal at the emission boundary (state equivalence, not counters) |
| 5 | 訪問回数の上限54はユーザ認可（「まずは処理を完遂させること。効率化はその後」）— Home限定・ハード | `CALIBRATION_HOME_VISIT_LIMIT` + ceiling pins + `equipment-work-home-route-exhausted` terminal |
| 6 | recall在庫なしでダンジョンに入らない（採掘徒歩は例外）; 緊急免除なし | departure invariant + escape-kit floor rules (see memory: bot-recall-entry-invariant) |
| 7 | フェアプレイ: プレイヤーに見えない情報をエミッタから出さない。静的 lib/edit は既知として可。見せた情報を減らす/整理するのは可 | reviewer gate on emitter diffs |
| 8 | 仕様変更は提案まで。明示承認なしに実装・dispatch しない。答え済みの明確化はロック | reviewer process (memory: spec-change-propose-not-implement, spec-fidelity-no-narrowing) |
| 9 | 完了した行為だけを報告（ツール実行が先、過去形は後） | reviewer process (memory: report-only-completed-actions) |
| 10 | 診断は成果物を引用（コード読解は「起こり得る」までしか証明しない） | reviewer process (memory: diagnosis-must-cite-artifacts) |
| 11 | 割り当て済み作業の途中で確認を求めない。承認の門は新規・未依頼の範囲のみ | reviewer process (memory: dont-ask-mid-task) |
| 12 | 安全管理として、最悪の場合は元の装備に戻す。ただし復元は最後の手段であり、最適化は完走が本義 | restore-on-abandon + `test_completing_optimization_performs_zero_restores` |
| 13 | 最適化は深度優先の帯降下（案2, 2026-08-10承認）:「打撃性能が極端に下がる場合は一つ帯を下げて試行」— 帯集合の打撃スコアが無制約最良の 1/2 を割ったら一帯降りる。r=1/2 はユーザの数。≤19帯は要求ゼロで必ず成立（裸への回帰経路なし）。能力の証拠は known_flags＋内在のみ | SOL-TASK-depth-first-optimization.md → band-descent pins (queued) |

Scenario transfer (depth-first remediation, 2026-08-10): constrained
`depth_override=31` optimizer results now publish the authoritative classified
band ceiling `chosen_depth=39`, rather than echoing the requested floor.  No
`src/` caller supplies `depth_override`; the transferred unit scenario is
`EquipmentOptimizerTest.test_constrained_depth_reports_classified_band_ceiling`.
The existing bounded 51-item search scenario now gives its lantern positive
fuel so it continues to model a usable mandatory light under the restored gate.

Scenario transfer (ability-source remediation, 2026-08-10): the former
`test_depth34_recall_is_refused_for_the_four_missing_gates` used the post-landing
`abilities-depth34-town.json` and is replaced by two truthful public-decision
scenarios. `test_depth34_pre_recall_town_snapshot_refuses_public_departure` uses
`abilities-depth34-pre-recall-town.json` to cover the Angband departure refusal;
`test_depth34_landed_snapshot_starts_public_resist_gap_recovery` uses the renamed
`abilities-depth34-landed-dungeon.json` to cover the 34F recovery recall. The
permanent-source scenario keeps its coverage under the existing test name. The
former danger-membership scenario is renamed
`test_real_status_and_resistance_consumers_see_parsed_abilities` and now invokes
the production melee-status consumer while retaining the resistance-profile
assertions. New unique scenarios cover contaminated fallback depth and hashable
per-source/flat `PlayerState` inputs; no test scenario is deleted.

Gaps (directives without an automated gate yet): #2 lacks a stability pin over pack-count/gold variation
(recall-depth variation is pinned); a consolidated `tests/test_user_contract.py` that names each entry is
queued. Until then this table is the checklist.

## Scenario transfer when decision paths change

Deleting or rebuilding a decision path requires a scenario-transfer list in the fix event. The list MUST
name every scenario covered by the old path's tests and identify the test where each scenario now lives.
The reviewer MUST diff the implementation and test changes against that list; a missing scenario or an
unidentified destination blocks the change.
