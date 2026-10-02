# oneshot-preempt: 組み立てた一発購入が自分の入口で引退させられる件

- 担当: Opus 5.5（実装）
- worktree: `C:\hengband\bot-client-oneshot`、ブランチ `oneshot-preempt`、起点 `a96480df`
- コミット: `a3888884`（記録の凍結）、`608d80dd`（修正＋ピン）、この報告のコミット
- 実機停止: 2026-10-02 09:03:33 / 09:04:14 / 09:27:34 `town:blocked:owner-retired`（S3.3 OFF、交差領域の資金稼ぎ ON）

## 結論（短く）

止まった原因は「町の進捗の不変条件が購入を横取りした」ことではない。**町の調停役（arbiter）が、組み立てたばかりの一発購入をそれ自身の最初の決定で引退させ**、
その引退が店の訪問を閉じて、送るはずだった購入の後半（`pl9\r\r\x1b`）を捨てたことが原因。

引退の理由は shop-buy の繰り返し検出（recurrence）。shop-buy の進捗ベクトルは「金・持ち物などの持続的な事実」だけで、
**どの店の棚の仕事か** を含んでいなかった。そのため、自宅の予定停止を片付ける決定（理由 `shop:observed-operation-uncomposable`、
`shop:observe` 接頭辞で shop-buy 家族に入る）と、その後の武器屋の一発購入が「同じ仕事の2回目」と数えられ、
2回で上限（`TOWN_CYCLE_BREAK_LIMIT`=2）に達して引退した。

修正は、shop-buy の進捗ベクトルに「行動している棚（店の番号）」を加えたこと。店の巡回役（store-router）が自分の歩行距離を
ベクトルに入れているのと同じ形。同じ棚での繰り返しは今までどおり同じベクトルになり、既存の繰り返し検出と予算で止まる。
新しいしきい値・定数・方策の属性は追加していない。

## STEP 1: 記録からの原因（file:line）

凍結した記録: 09:04:14 停止の 09:03:38 起動のプロセス（決定 0〜18、`tests/extract_oneshot_preempt_fixture.py`）。
本番コードで 0〜18 の全キーと理由が実機と一致して再生できた（`test_pre_fix_vector_reproduces_every_live_key`、
修正前のベクトルを壁として使用）。

店の番号は印字で確認（R1）: `TOWN_TRAVEL_STORE_SYMBOLS = ('!', '"', '#', '$', '%', '&', "'", '(')`、
`STORE_WEAPON=2`（`#`）、`STORE_TEMPLE=3`（`$`）、`STORE_HOME=7`（`(`）、`TOWN_CYCLE_BREAK_LIMIT=2`、`STORE_STUCK_LIMIT=8`。

| index | 実機のキー / 理由 | 何が起きたか |
| ---: | --- | --- |
| 7 | `5 pW13\r\x1b` / `home:atomic-withdraw` | 自宅から取り出し |
| 8 | `6` / `town:entrance-step-off:shop:observed-operation-uncomposable` | 自宅の予定停止を片付けて入口から降りる。arbiter は理由 `shop:observed-operation-uncomposable` を shop-buy として記録（producer_owner shop-buy）。(shop-buy, ベクトル V) の1回目 |
| 9 | `` \x1b`n#. `` / `shop:travel` | 武器屋（店2）へ |
| 10 | `\x1b` / `town-progress-invariant:continue-observed-shop` | 店2の棚を観察して出る（鉄弾 l 3金、弾 90/99） |
| 11 | `5` / `shop:one-shot-buy` | 外で棚から一発購入を組み立て（dispatch `5`、後半 `pl9\r\r\x1b`）。金・持ち物は 8 から変わらず、(shop-buy, V) の2回目 → 繰り返し → 引退。引退が店の訪問を閉じ、後半を捨てた |
| 12 | `\x1b` / `continue-observed-shop` | `5` で開いた店2の画面は「回復した観察の訪問」（visit_origin `shop-handler-recovery`）になり、また出る |
| 13〜17 | `$` へ移動、出る、`5` await-entry、出る、`5` await-entry | 寺院（店3）。shop-buy は繰り返し上限のままなので帰還の巻物の一発購入が組めず、巡回役の `shop:travel:await-entry` の `5` で2回入って2回出る |
| 18 | `5` / `town:blocked:owner-retired` | 停止 |

本番コードでの数え（計測用の差し込みで印字）: index 8 `shop-buy vec 07dd99cf rec 1`、index 11 `shop-buy vec 07dd99cf prev 07dd99cf rec 2`
→ `progress False, budget_remaining 0, retired ['shop-buy']`。

問いへの答え:

1. **欲しい・買える・在庫のある購入がなぜ `5` を送るのか**: 一発購入は設計どおり「外で `5`（入店）を送り、店の画面が出たら束ねた後半を送る」2段。
   `5` 自体は正しい（`policy_shop.py:5057`、`next_step="shop.one-shot.dispatch"`, `continuation="shop.one-shot.send"`）。
   失敗は同じ決定で arbiter が shop-buy を引退させ（`town_arbiter.py:466-467` 繰り返し判定、`:525-528` 引退と `close_visit(owner, "arbiter-retired")`）、
   訪問ごと後半を捨てたこと。次の店の画面では `_release_staged_store_operation`（`policy_shop.py:314`）が返す後半がない。
2. **なぜ不変条件の continue-observed-shop が購入を横取りするのか**: 横取りしていない。店の中の画面は観察専用で、購入を選ばず必ず出る
   （`policy.py:10148-10160`「Observation visit: never select or answer an item prompt here.」→ `shop:observe-and-leave`）。
   不変条件（`policy_town.py:1302-1314`）はその ESC に「欲しい購入がある棚から出る＝一発購入の運搬段階」と名前を付け替え、
   診断 `TOWN_PROGRESS_INVARIANT_DEFECT` を記録するだけで、キーは変えない。shop_selector の `rejection_reason: "preempted"` は
   「出たキーが購入キーではない」という診断上の分類（`policy_shop.py:2121`）。
3. **寺院の await-entry `5` はなぜ入らないのか**: 入っている（index 16 は店3の画面）。入った画面が観察専用で、束ねた後半がない
   （shop-buy が繰り返し上限で一発購入を組めなかった）ので、また出た。`shop:travel:await-entry` は `policy_shop.py:4864`。
4. **allow_set [] の意味**: 不変条件の記録で固定の空タプル（`policy_town.py:1311`、`"allow_set": ()`）。この分岐は許可メンバーの例外を
   一切使わないという意味で、今回の判断には関係しない。

実機ログの裏付け（`bot-decisions.jsonl.1` と `bot-decisions.jsonl` の全行を走査）: 本日の `shop:one-shot-buy`（入店の `5`）20件のうち
引退したのは3件で、3件とも直前が `town:entrance-step-off:shop:observed-operation-uncomposable`。この自宅の降り口は全期間で3回だけで、
3回とも次の一発購入が引退した。引退しなかった17件の前には、この shop-buy の決定がない。

## STEP 2: 修正

`src/hengbot/policy_town.py`
- `_town_arbiter_progress_vector`: owner が `shop-buy` の時、持続的な事実に `("shelf", "shop-buy", floor_key, 店の番号)` を加える。
- `_shop_buy_shelf_store`（新しい読み取り専用の補助）: 開いている店の画面 → その決定の店の訪問 → 観察済みの棚 → 近づいている店、の順で店の番号を読む。

効果: 自宅の降り口（棚 7）と武器屋の一発購入（棚 2）は別の仕事になり、11 は `progress True`、引退しない。同じ棚での繰り返しは
同じベクトルなので、今までどおり2回目で繰り返し、予算8で引退する。shop-buy の引退キーは進捗ベクトルなので、別の棚では別のキーになる
（寺院の購入は武器屋での引退に縛られない）。shop-sell は今回の形が観測されていないので変えていない。

ルール: しきい値・定数の追加なし、要求の変更なし、方策の属性の追加なし（R2 の復元チェックポイント手当は不要）。理由とその家族の対応表
（`tests/fixtures/t1-reason-attribution.json`）は変えていない。

## ピン（`tests/test_oneshot_preempt_recorded.py`）

| テスト | 内容 | 修正前 | 修正後 |
| --- | --- | --- | --- |
| `test_recorded_one_shot_retired_at_its_own_entry` | 記録の形（8 は shop-buy、11 の引退、12 の回復訪問、15/17 の await-entry、18 の停止、棚の 鉄弾 l 3金、allow_set []） | 合格 | 合格 |
| `test_pre_fix_vector_reproduces_every_live_key` | 壁（棚の部分を外す）で 0〜18 の全キーが実機と一致 | 合格 | 合格 |
| `test_weapon_smith_one_shot_keeps_its_tail_and_buys` | 本番で 0〜11 が実機と一致、11 は引退せず `progress True`、12（最初の差、実機 ESC）で `pl9\r\r\x1b` / `shop:one-shot-buy`（`shop.one-shot.send`、店2、l=鉄弾 3金） | **失敗** | 合格 |
| `test_temple_entry_composes_and_releases_the_recall_purchase` | 0〜14 を壁で再生、15 で `5` / `shop:one-shot-buy`（実機は同じ `5` の await-entry、後半 `pl1\r\r\x1b`）、16（最初の差）で店3の画面に `pl1\r\r\x1b`（l=帰還の詔の巻物 231金） | **失敗** | 合格 |

R4: 最初にキーが変わる決定（12、寺院は 16）で止めている。15 は実機も修正後も `5` なので、16 の盤面は同じキーの結果。
数量: 弾 90/99 → 9、帰還 8/9 → 1（既存の `_purchase_quantity` の値。実機の 11 の記録も `[2, "pl9\r\r\x1b"]`）。

単一の取り消し確認（`reports/oneshot-preempt-revert.txt`）: `src/hengbot/policy_town.py` だけを戻すと修正ピン2件が失敗
（`(True, False, None) != (False, True, None)`、`('5', 'shop:travel:await-entry') != ('5', 'shop:one-shot-buy')`）、他2件は合格。

R9: ピンのハッシュは CRLF→LF 正規化後の値。
R1: `scripts/assertion_change_audit.py --base a96480df` → 「No changed pre-existing assertions or forbidden test edits.」

注意（較正ファイル）: 09:03:38 のプロセスが読んだ `character-calibration.json` は 09:27 の別プロセスに上書きされて残っていない。
05:51 のファイル（`overweight-home-hold-20261002.character-calibration.json`、同じ種族・職業・Lv・能力値・base_hp）を使い、
0〜18 が実機と完全に一致することで妥当性を確認した。

## 検証（1プロセス1モジュール）

| モジュール | 結果 |
| --- | --- |
| tests.test_oneshot_preempt_recorded | 4 OK |
| tests.test_town_progress_invariant | 22 OK |
| tests.test_overweight_home_hold_recorded | 4 OK |
| tests.test_tpstockout_restart_recorded | 2 OK |
| tests.test_unaffordable_claim_tour_recorded | 7 OK（566秒） |
| tests.test_town_approach_retired_recorded | 8 OK |
| tests.test_storewhich_recorded | 2 OK |
| tests.test_live35_store_page | 3 OK |
| tests.test_classC_departure_remedies | 5 OK |
| tests.test_town_arbiter（直接触った領域なので追加） | 29 OK |
| tests.test_test_fakery_lint | 13 OK |

`scripts/first_divergence_s3_3.py`（stuck/withdraw のみ）:

| case/mode | 行 | OFF ハッシュ／最初の差 | 結果 |
| --- | ---: | --- | --- |
| stuck/off | 4 | c63d582c…（一致） | first_divergence なし |
| stuck/s33 | 4 | なし | trajectory_defect なし |
| withdraw/off | 34 | a9b34420…（一致） | first_divergence なし |
| withdraw/s33 | 4 | index 3、ESC / equipment-transaction:catalogue-leave-for-scan（期待どおり） | trajectory_defect なし |

出力は `reports/oneshot-preempt-*`。

## 実行していないもの（Claude 側で実行してください）

`scripts/test_parallel_runner.py`, `scripts/test_timing_runner.py`, `scripts/hunk_guard.py`, `scripts/verify_scope.py`,
`scripts/mutation_battery.py`, `tests.test_cli`, `tests.test_policy_town`, `tests.test_policy_shop`, `tests.test_absorbing_states`,
長い記録再生（tour/town/overweight の first_divergence 全体）、町の生産者の純粋性の部分、`first_divergence_s3_3.py` の stuck/withdraw 以外、全体スイート。
shop-buy の進捗ベクトルに触れたので、特に次は全体テストで確認をお願いします: `tests.test_town_arbiter_suppression`、
`tests.test_alchemist_observed_shop_alternation`、`tests.test_shop_one_shot`、`tests.test_live23_home_cycle`、
`tests.test_identify_staff_live27_recorded`、`tests.test_home_withdraw_failed_stock_present_recorded`、
`tests.test_departure_unsatisfiable_weight_recorded`、`tests.test_live36_weight`、`tests.test_calibration_*`、`tests.test_crossarea_fundraising`。

## 実機のリスク

- shop-buy の引退は「同じ棚で2回」になる。別の店の棚へ移ると shop-buy の引退は解ける（引退キーが棚ごと）。店から店への往復の
  繰り返しは既存の店間移動の検出（`_visit_transfers`）と detectors 家族の繰り返しで止まる想定だが、実機で観測していない。
- 不変条件の `TOWN_PROGRESS_INVARIANT_DEFECT` という印は、正常な観察→退出にも付いたまま（今回は変えていない）。診断の読み手が
  誤解しやすいので、名前の見直しは別件の提案。
