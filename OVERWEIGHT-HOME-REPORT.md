# overweight-home — 経路の到着が自宅の操作を止めていた件

担当: Opus 5.5（実装）。作業ツリー `C:\hengband\bot-client-ovw`（ブランチ overweight-home、基点 c4677d7a）。
ゲーム・ボット・他の作業ツリー・`C:\hengband\bot-client` には触れていない（jsonlog は読むだけ）。

## 証拠

- 06:16 の停止 `autorecover-20261002-061620-loop-detected.*`。決定ログには 2 つのプロセス（06:11:24 と
  06:14:06 の session-start）が丸ごと入っている。06:14:06 のプロセスを接続行から index 11（最初の
  `town:blocked:no-actionable-claim-owner`）まで `tests/fixtures/overweight-home-hold-20261002.*` に凍結した
  （抽出: `tests/extract_overweight_home_hold_fixture.py`、各決定の入力は `timing.jsonl_drain_records` の境界）。
- 本番コード（c4677d7a）で同じプロセスを公開応答経路（`_consume_response_sequence` → `choose_key`）で再生すると、
  index 0〜9 のキーと理由が実機と完全一致する（index 10 は町の入口から一歩退く方向だけ違う。理由は同じ。下記の壁）。
- 他の 6 件の `overweight-home-unreachable` 停止（22:24, 00:10, 01:05, 01:57, 04:25, 05:56）は全部、
  自宅での `home:route-claim-unfulfilled` または `home:scan-incomplete-open-page` の行で、保留させた holder が
  同じ決定で `reached` などで閉じた store-router の Reach 主張になっている（記録の `claim.errand_deferred` と
  `claim.closed_claim` を印字して確認）。これらは途中から始まる切り出しなので再生はしていない。

## STEP 1 の答え（記録から）

実測の重さ（06:16 の自宅の盤面、0.1 lb 単位）: 携行 1752、上限 `calc_weight_limit` 相当 1750（2 超過）。
依頼文の 1650 ではなかった（`_inventory_weight_limit`, `src/hengbot/policy_home.py:1113`、再生で印字）。

1. **自宅で預け入れが出なかった理由**
   - 預ける候補はあった。自宅の盤面で `_weight_deposit_candidates`（`policy_home.py:1195`）は
     `[k つるはし, j シャベル, i 鑑定の杖 2x3回, e 帰還 1 枚]`、`_overweight_home_deposit`（`:1338`）は
     k（150、単独で超過を解消）を選ぶ。
   - それを出す生産者 `_open_home_deposit_key`（`policy_home.py:2977`）は `_town_producer_entry`
     （`src/hengbot/policy.py` c4677d7a の 5938 行）で止められた。`_home_sequence_has_holder`（c4677d7a の 6804 行、
     live23 の ddebaf64 で追加）は、交差領域の強制（実機の `--enforce-crossarea-fundraising`）が有効で、
     自宅の訪問中に何か開いた町の用事の主張があれば holder とみなす。この時の現在の主張は claim 3
     （store-router、Reach、目標 (45,123) ＝ 自宅の入口）で、盤面ではもう到着している。それでも holder になり、
     `entry:_release_staged_store_operation`・`entry:_home_rearm_key`・`entry:_open_home_deposit_key` が
     全部保留された（記録の errand_deferred、token_would_admit=false）。
   - S3.3 ON なら `choose_key` が町の生産者に聞く前に到着を閉じる（`policy.py:2715` の
     「Finish an observed arrival or store entry before asking the next town producer」）が、
     S3.3 OFF では閉じない。claim 3 は同じ決定の出口でようやく `reached` で閉じた。
   - 結果、自宅の分岐は全部素通りし `home:route-claim-unfulfilled`（c4677d7a の `policy.py:9184`）で ESC。
     同時に自宅を「試行済み」にし（`home-capture-complete`）、未充足の 1 回を数えた。
   - 保留を外すと（再生で確認）同じ盤面の答えは `dk\x1b` `home:weight-overload-deposit`。
2. **各重い山を誰が残しているか**（自宅の盤面の `_retention_reservation_detail`、再生で印字）
   - 鉄弾 63: `ammo:carry-plan` で 63 全部。10-01 の鉄弾預け入れ（`_ammo_procurement_target(for_retention=True)`,
     `policy_home.py:1128`）は、まず普通の保持超過（つるはし 150・シャベル 60・杖 i 100・帰還 5）を引いてから
     残りの超過を弾で削る作り。引いた後は 1437 で上限内なので目標は 99（63 全部を保持）。
     **今回は弾を預ける必要がない盤面なので、発火しなかったのは決定どおり**（保持超過が先）。
   - 採掘具: シャベル j・つるはし k は予約 0（`policy_home.py:998` は `mining_planned` の時だけ予約。
     fundraising mode None、所持金 17342 で mining_planned は偽）。09-18 の決定どおり預ける対象。
   - 鑑定の杖: g（9 回、予約 0、鑑定源の必要物資なので候補外）、h（2x8、`mana-device` で 2 予約、
     `policy_home.py:1029`）、i（2x3、`_find_surplus_identify_staff(for_weight_overload=True)` が余剰と判定し候補）。
     合計 31 回。i を預けても 25 回で 20 回以上を保つ。
   - 帰還: 自宅の盤面では `supply-ledger:recall`（`policy_home.py:896`）の required_departure が 9 で 1 枚余剰、
     index 11（店を回った後）では 10 になる（再生で印字）。この 1 枚は一時的な余剰。今回はつるはしが先に選ばれる。
3. **次の出発**: fundraising mode None（通常の潜行、計画深さ 20）。前の潜行がイークの洞穴 1F の資金稼ぎだったので
   採掘具を持ち帰っていた。
4. **その後に持ち主がいなくなる理由**: 自宅が `_town_store_attempted` に入り（試行済み）、未充足 2 回は上限 3 未満。
   `weight-overload` の需要は残るが、ルーターは自宅へ行かない（`_next_required_store_type` = None、再生で印字）。
   名前付き停止 `overweight-home-unreachable` は接近失敗が上限か上限による封鎖の時だけ（`policy_town.py:3131`）。
   そのため `_town_procurement_progress_key` が None、`stuck:wander` が町の進捗不変条件で
   `town:blocked:no-actionable-claim-owner`（`policy_town.py:1325`）の待ちになり、`probe` と交互に続いた。
   他の 6 件は同じ店で 2 回目の空振りが上限 3 に届き、名前付き停止になった。

## STEP 2 の修正（2 か所、しきい値・新しい属性なし）

1. **到着した経路は自宅の holder ではない**（`src/hengbot/policy.py`）
   - `_claim_reach_arrival`（`:4169`）: `_claim_exit_completion` が cell の Reach を閉じる証拠
     （目標マスに立つ、または目標が入口の店の中）を読むだけの関数に切り出し、`_claim_exit_completion` もこれを使う
     （振る舞いは同じ）。
   - `_claim_errand_hold(..., arrival_board=None)`（`:5618`）: 盤面が渡されたら、その盤面で到着済みの
     現在の Reach を holder にしない。
   - `_home_hold_board`（`:6836`）: S3.3 OFF の時だけ今の盤面を返す（ON は既に到着を閉じているので変えない）。
   - `_home_sequence_has_holder`（`:6846`）と `_defer_town_errand` → `_town_errand_deferral`（`:5879`, `:5839`）が
     その盤面を使う。保留の記録だけの経路（OFF、enforced=False）と S3.3 の影の判定は変えていない。
   - live23 の保護（Observe の目録の仕事、`CLAIM_OBSERVE_STORE_OPERATION`）は Reach ではないので変わらない。
2. **自宅の空振りの後は名前付き停止**（`src/hengbot/policy_town.py:1328`）
   - `no-actionable-claim-owner` になる所で、`weight-overload` の需要が残り、自宅が試行済み、まだ重量超過なら
     `town:blocked:overweight-home-unreachable`（既存の停止の形、`POLICY_FINAL_STOP_REASONS`）にする。
     09-03「本当に預け入れに失敗するならそれは停止するべき事案である」。もともと持ち主のない待ちだった決定だけが変わる。
   - 預けられる物が無い（残りが全部必要物資）場合は、従来どおり `weight-overload` の需要が立たず
     `town:blocked:departure-unsatisfiable`（名前付き停止。live36 のピンが既に固定）。

選択の順番は変えていない。既存の `_weight_deposit_candidates` の順（呪い装備 → 採掘予定でない採掘具 →
その他の保持超過 → 必要物資の超過）で、弾は普通の候補がある間は出ない。今回の盤面ではつるはし 1 本（150）だけで解消し、
必要物資は 1 つも減らない（09-03 #1）。採掘具は通常の潜行なので預ける（09-18）。
鉄弾は全部持ったまま（10-01: 超過分だけ預ける。今回は超過分が無い）。

## ピン（`tests/test_overweight_home_hold_recorded.py`、4 件）

| テスト | 内容 | 修正前 | 修正後 |
| --- | --- | --- | --- |
| recorded_home_pass_was_held_by_the_arrived_route | 記録の事実（holder = claim 3 store-router、reached、index 11 の停止、departure_block） | 合格 | 合格 |
| routed_home_arrival_deposits_the_minimal_overload | 本番再生 0〜3。0〜2 は実機と一致、3 で `dk\x1b` / `home:weight-overload-deposit`。k だけ、1602 ≤ 1750、予約はすべて保持、鑑定 31 回、弾目標 99、claim 3 は reached で閉じる | 失敗（ESC / route-claim-unfulfilled） | 合格 |
| pre_fix_hold_reproduces_the_live_home_pass | 壁の検証: 修正前の保留で 0〜3 が実機と一致 | 合格 | 合格 |
| failed_home_pass_ends_in_the_named_overweight_stop | 壁 2 つで index 11 まで。0〜9 は実機と一致、11 で `5` / `town:blocked:overweight-home-unreachable` | 失敗（no-actionable-claim-owner） | 合格 |

宣言した壁: index 3 は修正前の保留（`_home_hold_board` → None）で実機のキーを再現。index 10 は入口から退く
マスの同点を、この切り出しに無い訪問履歴が決めている（再生 '1'、実機 '3'、理由は同じ）ので実機のキーを送る。
キーが変わった後の盤面は使っていない（R4）。修正後の預け入れの効果は観測ではなく計算（携行 1602 など）。

フィクスチャのハッシュは CRLF→LF 正規化後（R9）。新しい方策の属性は無いので R2（復元チェックポイント）の手当ては不要。
画面の分類は変えていないので R2（実画面）も対象外。EXPECTED_FIRST は触っていない。

単一の差し戻し確認（`src/hengbot/policy.py`・`policy_town.py` を c4677d7a に戻す）: 新モジュール 4 件中 2 件失敗（修正の 2 件）、
live27 は 2 件中 1 件失敗（新テスト）。戻した後はすべて合格（`reports/overweight-home-revert.txt`、`reports/overweight-home-pins.txt`）。

## 実行したテスト（1 プロセス 1 モジュール）

| モジュール | 件数 | 結果 |
| --- | ---: | --- |
| tests.test_overweight_home_hold_recorded（新規） | 4 | OK |
| tests.test_identify_staff_live27_recorded（壁と新テスト追加） | 2 | OK |
| tests.test_live36_weight | 7 | OK |
| tests.test_overweight_home_unreachable_recorded | 12 | OK |
| tests.test_departure_unsatisfiable_weight_recorded | 7 | OK |
| tests.test_ammo_surplus | 4 | OK |
| tests.test_home_disposal | 15 | OK |
| tests.test_home_equipment_disposal | 6 | OK |
| tests.test_classC_departure_remedies | 5 | OK |
| tests.test_classC2_departure_recorded | 9 | OK |
| tests.test_town_progress_invariant | 22 | OK |
| tests.test_live23_home_cycle（追加で実行） | 7 | OK |
| tests.test_crossarea_fundraising（追加で実行） | 12 | OK |
| tests.test_test_fakery_lint | 13 | OK |

出力は `reports/overweight-home-*.txt`。`scripts/assertion_change_audit.py --base c4677d7a`:
「No changed pre-existing assertions or forbidden test edits.」

### live27 への影響（既存ピンの変更）

`tests.test_identify_staff_live27_recorded` は修正後に一度失敗した（最初の差が 104 ではなく 63）。記録を印字すると、
live27 の index 63（2026-10-01 09:15:46）も同じ原因の `home:route-claim-unfulfilled` で、到着した store-router の
claim 48 が `queue-digging-tool-withdraw`（fundraising mode prepare、採掘の出発なので採掘具を持つ 09-18 の決定）を
含む自宅の生産者を全部保留していた。修正後の本番は 63 で `` / `home:queue-digging-tool-withdraw` を出す。
既存の assert は 1 つも変えていない。やったこと:
- 新テスト `test_routed_home_arrival_queues_the_mining_digger`: 本番で 0〜62 が実機と一致し、63 が上の答えになる。
- 既存テストに宣言した壁を 1 つ追加: index 63 だけ修正前の保留（`_home_hold_board` → None）で再生し、
  元の主題（104 の鑑定の杖の採掘）に行動が一致する盤面でたどり着くようにした。104 の結果は修正前と同じ。
この扱いでよいか、レビューで判断してください。

`scripts/first_divergence_s3_3.py`（stuck/withdraw のみ）:

| case/mode | 行 | OFF ハッシュ／最初の差 | 結果 |
| --- | ---: | --- | --- |
| stuck/off | 4 | c63d582c…（一致） | first_divergence なし |
| stuck/s33 | 4 | なし | trajectory_defect なし |
| withdraw/off | 34 | a9b34420…（一致） | first_divergence なし |
| withdraw/s33 | 4 | index 3、ESC / equipment-transaction:catalogue-leave-for-scan（期待どおり） | trajectory_defect なし |

## 実行していないもの（Claude 側で実行してください）

`scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`, `scripts/hunk_guard.py`,
`scripts/verify_scope.py`, `scripts/mutation_battery.py`, `tests.test_cli`, `tests.test_policy_town`,
`tests.test_policy_shop`, `tests.test_absorbing_states`, 長い記録再生（tour/town/overweight の first_divergence 全体）、
町の生産者の純粋性の部分、`first_divergence_s3_3.py` の stuck/withdraw 以外、全体スイート。
特に `tests.test_live23_home_cycle`、`tests.test_crossarea_fundraising`、`tests.test_calibration_*`（交差領域を有効にする
モジュール）は今回の変更（交差領域の自宅の保留）に直接関係するので全体テストで確認をお願いします。

## 実機のリスク

- 交差領域が有効な実機では、store-router で自宅に入った時、これまで止められていた自宅の生産者（預け入れ、
  中からの目録の取り直し、再武装など）がその場で動くようになる。S3.3 OFF で交差領域なしの時（多くのテスト）と、
  S3.3 ON の時の振る舞いに揃う。live23 の目録の保護（Observe）は残る。
- 帰還の巻物の予約が自宅の盤面（9）と店を回った後（10）で違う。今回は選ばれないが、帰還 1 枚だけで超過が
  解消する盤面では預けて買い戻す往復になり得る（別件、未修正）。
- 新しい名前付き停止は、自宅の空振りの後の持ち主のない待ちを止めるだけ。自宅で預け入れが本当に失敗し続ける
  別の原因があれば、ループ検出ではなく `overweight-home-unreachable` で止まる。

## コミット

- b9f139d4 test(overweight-home): 06:14 プロセスの凍結（STEP 1 の証拠）
- 2b50c90c fix(overweight-home): 到着した経路は自宅の訪問を保留しない（修正＋ピン＋live27）
- （この報告のコミット）

---

## 追補（レビュー gpt-6.1-sol「merge after fixes」の P1・P2、769595e0 の続き）

### P1: 自宅が試行済みというだけで名前付きの停止にしない（`src/hengbot/policy_town.py`）

- `_overweight_home_bound_exhausted`（新規、`_town_store_blocked_under_applicable_bound` の直前）: 自宅の既存の
  上限だけを見る。上限による封鎖、接近失敗が上限、未充足の回数が上限、自宅の訪問予算（300）の使い切り。
- 持ち主のない待ちになる所（`stuck:wander` を町の進捗不変条件が止める所）で、`weight-overload` の需要があり、
  重量超過で、自宅が試行済みで、上限が残っている場合: `_rearm_town_store_for_new_work(STORE_HOME)` で自宅を戻し、
  ルーターが自宅を選べば同じ決定で `shop:travel` で自宅へ向かう。預け入れが保留された・出されなかった回は、
  ここで再び自宅へ行く。空振りの回は既存どおり未充足として数えられるので、往復は上限 3 で止まる。
- 名前付きの停止 `town:blocked:overweight-home-unreachable` は、上限を使い切った時（または戻しが拒まれた時）だけ。
  09-03「本当に預け入れに失敗するならそれは停止するべき事案である。」
- 06:16 の記録（未充足 2 回、預け入れは一度も出ていない）の index 11 は、`5` 停止ではなく
  `\x1b`n(.` / `shop:travel` になる（実機のキーと最初に食い違う所。ここで再生を止める）。

### P2: 自宅の中でも出発時に読む帰還 1 枚を残す（`src/hengbot/policy_supply.py`・`policy_town.py`）

- 原因（再生で印字）: 自宅の中か外かではなかった。`_supply_ledger` は「今、帰還の行き先がある」時だけ出発で読む
  1 枚を足す。06:16 では目標のダンジョン 1 の着地が安全条件で拒まれており、行き先なし → 必要数 9。
  index 10 の `town:unsafe-recall-fallback` が安全な別のダンジョン 7 に切り替えた後は行き先あり → 10。
  自宅（index 3）は切り替え前なので 9 で、帰還 1 枚が余剰に見えていた。
- 修正: `_town_recall_destination(..., safety_gate=False)` を足し、帳簿の +1 だけがこれを使う。着地が拒まれた
  目標も、出発時には安全な着地に切り替えて帰還を 1 枚読むので、切り替えの前後で必要数が同じになる
  （09-20「目標＋出発で読む1枚」）。歩いて入る出発（イークの洞穴の浅い階、採掘、クエストの歩き入り、
  未踏のダンジョン）は従来どおり +1 しない。
- 06:16 の盤面: 自宅の中（index 3）と出発盤面（index 11）の両方で required_departure 10、帰還の予約 10。
  預ける候補は `[k, j, i]` になり、帰還は候補から外れた。選ばれる預け入れは変わらず k（つるはし）1 本。

### ピン（`tests/test_overweight_home_hold_recorded.py`、6 件）

| テスト | 修正前（769595e0） | 修正後 |
| --- | --- | --- |
| unposted_home_deposit_routes_home_again（index 11 → `shop:travel` で自宅へ、自宅の試行済みは解除） | 失敗（`5` overweight-home-unreachable） | 合格 |
| exhausted_home_bound_ends_in_the_named_overweight_stop（同じ盤面で未充足／接近失敗を上限にした反実仮想 → 名前付き停止） | 合格（停止を保つピン） | 合格 |
| recall_reservation_inside_home_matches_departure_board（index 3 と 11 で 10/10） | 失敗（index 3 が 9/9） | 合格 |
| routed_home_arrival_deposits_the_minimal_overload | 失敗（帰還の予約 9） | 合格 |
| 他 2 件（記録の事実、壁の検証） | 合格 | 合格 |

差し戻し確認の出力は `reports/overweight-home-followup-revert.txt`。

変更した既存の assert（769595e0 で入れた自分のピン。`assertion_change_audit --base 769595e0` の出力どおり）:
- `test_routed_home_arrival_deposits_the_minimal_overload`: 帰還の予約 `("e", 10, 9)` → `("e", 10, 10)`、
  候補 `["k","j","i","e"]` → `["k","j","i"]`。理由: P2（09-20 の決定。出発時の 1 枚は余剰ではない）。
- `test_failed_home_pass_ends_in_the_named_overweight_stop` を 2 つに分けた: 記録の盤面（上限が残る）は自宅へ戻る、
  上限を使い切った盤面は従来の名前付き停止。理由: P1（09-03 の決定は「本当に失敗した」時の停止）。

### 実行したテスト（1 プロセス 1 モジュール）

| モジュール | 件数 | 結果 |
| --- | ---: | --- |
| tests.test_overweight_home_hold_recorded | 6 | OK |
| tests.test_identify_staff_live27_recorded | 2 | OK |
| tests.test_live36_weight | 7 | OK |
| tests.test_overweight_home_unreachable_recorded | 12 | OK |
| tests.test_departure_unsatisfiable_weight_recorded（壁と新テスト追加） | 8 | OK |
| tests.test_recall_stockout_set_end_recorded | 5 | OK |
| tests.test_recall_stockout_surplus_pins | 8 | OK |
| tests.test_home_disposal | 15 | OK |
| tests.test_town_progress_invariant | 22 | OK |
| tests.test_test_fakery_lint | 13 | OK |

出力は `reports/overweight-home-followup-*.txt`。

### P2 が既存ピン departure_unsatisfiable_weight に与えた影響

`tests.test_departure_unsatisfiable_weight_recorded` の H1 再生が最初の実行で失敗した（食い違いが index 68 から）。
印字した事実: index 68（seq 67）は目標 Angband（ダンジョン 1）の着地が安全条件で拒まれていて
（安全条件つきの行き先 None、外すと "angband"）、実機は帰還を 1 枚買い（`pi1`）、index 115（seq 114）で
出発用の 1 枚をもう一度買っていた（`pi1`）。修正後の本番は 68 で 2 枚まとめて買う（`pi2`）。09-20 の決定どおり。
既存の assert は変えていない。やったこと:
- 新テスト `test_production_buys_the_departure_recall_with_the_target`: 本番で 0〜67 が実機と一致し、68 が `pi2`。
  修正を戻すと `pi1` で失敗する。
- H1 の再生に宣言した壁: 修正前の帰還の必要数（安全条件つきの行き先）で再生し、元の主題に行動が一致する盤面で届く。

### 実機のリスク（追補）

- 着地が安全条件で拒まれている目標で、安全な切り替え先も無い場合、帰還を 10 枚持とうとしてから
  `no-safe-recall-destination` で止まる（以前は 9 枚で止まった）。停止の形は変わらない。
- 自宅で預け入れが出ないまま戻る原因が他に残っていれば、自宅への往復が最大 3 回続いてから名前付きの停止になる。
