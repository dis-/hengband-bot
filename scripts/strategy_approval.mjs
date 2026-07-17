#!/usr/bin/env node
// Phase 4: quest-strategy approval pipeline over the manual-test-runner.
//
//   node scripts/strategy_approval.mjs export [--only 34,18] [--data <dir>]
//     Writes <data>/test-items.json with one item per UNAPPROVED draft
//     (strategy/quests/QUEST_*.jsonc with approved:false), full gate/plan
//     details in the steps, so the user judges each in the browser UI.
//
//   node scripts/strategy_approval.mjs apply [--data <dir>]
//     Reads <data>/results.json. pass  -> approved:true + approved_note and
//     the id is added to strategy/approved.json (the test pin).
//                          fail/blocked -> feedback recorded in
//     strategy/approval-feedback.json for the re-derivation task; the draft
//     stays approved:false.
//
// Default --data: the manual-test-runner's own data dir
//   %USERPROFILE%/.claude/tools/manual-test-runner/data
// Runner: node %USERPROFILE%/.claude/tools/manual-test-runner/server.mjs
// (UI at http://localhost:8787/, auto-reloads test-items.json).

import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const questsDir = join(root, "strategy", "quests");
const approvedPath = join(root, "strategy", "approved.json");
const feedbackPath = join(root, "strategy", "approval-feedback.json");

const args = process.argv.slice(2);
const action = args[0];
const argValue = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const dataDir =
  argValue("--data") ??
  join(process.env.USERPROFILE ?? process.env.HOME, ".claude", "tools", "manual-test-runner", "data");

const stripJsonc = (text) =>
  text.replace(/^\s*\/\/.*$/gm, "").replace(/,(\s*[}\]])/g, "$1");

// r_idx -> Japanese monster name, scanned once from the game data (regex
// pass; the 14MB jsonc has trailing commas so a full JSON parse is not worth
// it for a name lookup).
const monraceNames = (() => {
  const path =
    argValue("--edit") ?? "C:/hengband/lib/edit/MonraceDefinitions.jsonc";
  const map = new Map();
  try {
    const text = readFileSync(path, "utf8");
    const re = /"id":\s*(\d+),\s*\r?\n\s*"name":\s*\{\s*\r?\n\s*"ja":\s*"([^"]+)"/g;
    for (const m of text.matchAll(re)) map.set(Number(m[1]), m[2]);
  } catch {
    /* names stay numeric when the game data is absent */
  }
  return map;
})();
const monsterLabel = (rIdx) =>
  monraceNames.has(rIdx) ? `${monraceNames.get(rIdx)}(${rIdx})` : String(rIdx);

const loadDrafts = () =>
  readdirSync(questsDir)
    .filter((f) => /^QUEST_\d+\.jsonc$/.test(f))
    .map((f) => ({
      file: join(questsDir, f),
      name: f,
      data: JSON.parse(stripJsonc(readFileSync(join(questsDir, f), "utf8"))),
    }));

const fmt = (v) => JSON.stringify(v, null, 0);

if (action === "export") {
  // --only selects the listed quests REGARDLESS of approval state (approved
  // drafts render as 確認用 items so the user can review/revoke them in the
  // same browser format); without --only, every pending draft exports.
  const only = argValue("--only")?.split(",").map(Number);
  const pending = loadDrafts().filter(
    (d) => (only ? only.includes(d.data.quest_id) : d.data.approved === false),
  );
  const items = pending.map((d) => {
    const q = d.data;
    const rf = q.required_force ?? {};
    const ep = q.engagement_plan ?? {};
    const nh = rf.no_healing_tier;
    const targets = (q.priority_targets ?? []).map(monsterLabel).join(" → ");
    const hold = ep.hold_position ? `[${ep.hold_position}]` : "なし(ランダム階)";
    const steps = [
      `■ ゲート(拘束): HP ${rf.min_hp} 以上 / 期待DPS ${rf.min_expected_dps ?? "未導出"} 以上 ※レベルは目安 Lv${rf.level_guideline}`,
    ];
    const throwing = Object.entries(rf.throwing_items ?? {})
      .map(([k, v]) => `${k === "lit_torch" ? "点火松明" : k} ${v}`)
      .join("・");
    steps.push(
      `■ 基本ゲート受注時の携行(必須): 加速 ${rf.speed_potions ?? 0}（条件付き使用）/ 治癒 ${rf.heal_potions ?? 0}${throwing ? ` / ${throwing}` : ""} / 耐性 ${
        (rf.resists ?? []).length ? (rf.resists ?? []).join("・") : "不要"
      }`,
    );
    if (nh) {
      steps.push(
        `■ 無保険ティア受注時 (HP ${nh.min_hp} + DPS ${nh.min_expected_dps}): 携行は 加速 ${nh.speed_potions ?? 0} / 治癒 ${nh.heal_potions ?? 0}${throwing ? ` / ${throwing}（弾薬は免除されない）` : ""}`,
      );
    }
    steps.push(
      `■ 優先ターゲット: ${targets || "なし"}`,
      `■ 陣取り: hold ${hold} / 撤退 ${q.abort_conditions?.allowed ? `可 (HP ${Math.round((q.abort_conditions?.hp_ratio ?? 0) * 100)}% で中断)` : "不可 (ONCE)"}`,
      `■ 開幕: ${ep.opening ?? ""}`,
    );
    if (ep.formation) steps.push(`■ 隊形: ${ep.formation}`);
    if (ep.ranged_softening) steps.push(`■ 投擲: ${ep.ranged_softening}`);
    // The rationale is an audit-trail paragraph; split it into sentence
    // bullets so a human can scan the arithmetic.
    for (const sentence of (rf.rationale ?? "").split(/(?<=\.)\s+/)) {
      if (sentence.trim()) steps.push(`・${sentence.trim()}`);
    }
    const approvedTag = q.approved ? "【承認済み・確認用】" : "";
    return {
      id: `strategy-QUEST_${q.quest_id}`,
      category: "クエスト戦略承認",
      title: `${approvedTag}Q${q.quest_id} ${q.name?.ja ?? ""} — ゲート: HP${rf.min_hp}/DPS${rf.min_expected_dps ?? "?"}`,
      steps,
      expected: q.approved
        ? "承認済みの内容確認。このままで良ければ合格。修正が必要なら失敗にして指示をフィードバック欄へ(承認は自動では取り消されません)。"
        : "値が妥当なら合格(=承認)。差し戻すなら失敗にして修正指示をフィードバック欄へ。",
    };
  });
  // Sentinel: marking this item pass = "入力完了" — a background watcher
  // notices it in results.json and Fable collects the batch automatically,
  // no chat message needed.
  items.push({
    id: "approval-batch-complete",
    category: "送信",
    title: "【入力完了】全項目の判断を終えたらこれを合格にする",
    steps: ["上の全項目に 合格/失敗+フィードバック を入力した後で押す"],
    expected: "これを合格にすると Fable が自動で結果を回収・適用します。",
  });
  const payload = {
    title: "クエスト戦略プロファイル承認",
    note: "合格=approved:true を適用。失敗=フィードバックを再導出タスクへ回す。最後に【入力完了】を合格に。",
    generatedAt: new Date().toISOString(),
    items,
  };
  writeFileSync(join(dataDir, "test-items.json"), JSON.stringify(payload, null, 2) + "\n");
  console.log(`exported ${items.length} pending draft(s) -> ${join(dataDir, "test-items.json")}`);
} else if (action === "apply") {
  const results = JSON.parse(readFileSync(join(dataDir, "results.json"), "utf8")).results ?? {};
  const approved = JSON.parse(readFileSync(approvedPath, "utf8"));
  const feedback = existsSync(feedbackPath)
    ? JSON.parse(readFileSync(feedbackPath, "utf8"))
    : { entries: [] };
  let applied = 0;
  for (const d of loadDrafts()) {
    const r = results[`strategy-QUEST_${d.data.quest_id}`];
    if (!r) continue;
    // "pending" with non-empty feedback = the user wrote revision notes
    // without pressing a verdict button; treat it as revision feedback.
    if (
      (r.status === "pending" || r.status === "fail" || r.status === "blocked") &&
      r.feedback
    ) {
      feedback.entries.push({
        quest_id: d.data.quest_id,
        status: r.status,
        feedback: r.feedback,
        at: r.updatedAt ?? new Date().toISOString(),
      });
      console.log(`feedback recorded for Q${d.data.quest_id}: ${r.feedback}`);
      continue;
    }
    if (r.status === "pass" && d.data.approved === false) {
      const note = `User approved via manual-test-runner ${r.updatedAt ?? new Date().toISOString()}.` +
        (r.feedback ? ` Feedback: ${r.feedback}` : "");
      // Textual edit keeps the JSONC comments intact.
      let text = readFileSync(d.file, "utf8");
      text = text.replace('"approved": false', '"approved": true');
      text = text.replace(/"approved_note":\s*"[^"]*"/, `"approved_note": ${JSON.stringify(note)}`);
      writeFileSync(d.file, text);
      if (!approved.approved.includes(d.data.quest_id)) approved.approved.push(d.data.quest_id);
      applied += 1;
      console.log(`approved Q${d.data.quest_id}`);
    }
  }
  approved.approved.sort((a, b) => a - b);
  writeFileSync(approvedPath, JSON.stringify(approved, null, 2) + "\n");
  writeFileSync(feedbackPath, JSON.stringify(feedback, null, 2) + "\n");
  console.log(`apply done (${applied} approval(s)). Run the suite to confirm the pin.`);
} else {
  console.error("usage: strategy_approval.mjs export|apply [--only ids] [--data dir]");
  process.exit(2);
}
