# クエスト戦略ドラフト規約

すべてのドラフト生成・修正はこの文書を唯一の規約として読む。

## 承認済みスキーマ

各 `strategy/quests/QUEST_<id>.jsonc` は `quest_id`、`name`、`approved`、`approved_note`、`engagement_plan`、`priority_targets`、`consumable_plan`、`abort_conditions`、`required_force`、`generated_by`、`generated_at` を持つ。`required_force` は `min_hp`、`min_expected_dps`、`level_guideline`、`resists`、`speed_potions`、`heal_potions`、`throwing_items`、`rationale` を持つ。投擲を使わない場合も `throwing_items: {}` とする。投擲を使う場合は、例えば `{"lit_torch": 5}` のように、戦術で実際に使う個数と外れ余裕を整数で記録し、計算を `rationale` に示す。`consumable_plan.other` の文章だけを個数の根拠にしてはならない。

`no_healing_tier` を設ける場合は `min_hp`、`min_expected_dps`、`heal_potions: 0`、`note` を持つ。`approved` と `strategy/approved.json` の変更は Phase 4 の `scripts/strategy_approval.mjs` だけが行う。

## 必要戦力

敵の実データと現在のキャラクター能力から計算する。速度、攻撃回数、AC は実値だけを使い、速度から行動数へ換算するときは双方の energy 係数を明記する。武器火力は、現在の能力値と攻撃回数を用いた、その戦略の `reference_ac` に対するプレイヤー1ターン当たり期待ダメージとする（2026-07-18 ユーザー決定・①案: 旧 AC 100 基準を廃止）。`reference_ac` は各戦略の `required_force` に必須フィールドとして記録し、拘束となる撃破対象（最も硬い実効目標）の実 AC を用いる。ゲート値の導出と実測が同じ尺度になるため、撃破ターン算術の D をそのまま `min_expected_dps` にできる。測定は二刀流の両手・ブランドを含む実装（fixer-70）で行う。

退却不能の ONCE クエストでは期待される一連の交戦被害を RAW HP の 50% 以内に収める。退却可能なら 70% までを交戦予算とし、それを超える前に中止する。回復薬は既定では消費せず保険として携行する。速度薬などの条件付き消耗品は `expected_damage_hp_ratio_min: 0.5` を満たす場合だけ使う。呪文で要件を満たせるのは成功率 90% 以上の場合だけとする。

## 回復薬なし段階

これは「戦術を維持したまま運だけが最悪」の段階であり、戦術崩壊の価格ではない。地形、隘路、距離管理は維持される一方、敵の命中率は 100%、ダメージダイスは最大、遠隔軟化は 0 とする。各敵の撃破ターンはその段階の `min_expected_dps` による遅い側の整数切上げで求め、その間の最大被害が RAW HP の 50% に収まる `min_hp` とする。戦術崩壊は `abort_conditions` と緊急解除に任せる。段階値が通常の拘束ゲートの十倍以上に膨らむ場合は、戦術失敗を混入していないか再検討する。

## 表記

人が読む文字列、特に `engagement_plan.*`、各 `note`、`consumable_plan.other`、`required_force.rationale` は日本語にする。座標、`r_idx`、フィールド名、式はそのまま表記してよい。
