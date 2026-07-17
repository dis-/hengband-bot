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
  const only = argValue("--only")?.split(",").map(Number);
  const pending = loadDrafts().filter(
    (d) => d.data.approved === false && (!only || only.includes(d.data.quest_id)),
  );
  const items = pending.map((d) => {
    const q = d.data;
    const rf = q.required_force ?? {};
    return {
      id: `strategy-QUEST_${q.quest_id}`,
      category: "クエスト戦略承認",
      title: `Q${q.quest_id} ${q.name?.ja ?? ""} の戦略を承認するか`,
      steps: [
        `拘束ゲート: min_hp=${rf.min_hp} / min_expected_dps=${rf.min_expected_dps} (目安Lv ${rf.level_guideline})`,
        `携行: 加速${rf.speed_potions ?? 0} 治癒${rf.heal_potions ?? 0} 耐性=${fmt(rf.resists ?? [])}`,
        `交戦計画: ${q.engagement_plan?.opening ?? ""}`,
        `hold=${fmt(q.engagement_plan?.hold_position ?? null)} / 優先=${fmt(q.priority_targets ?? [])} / 撤退=${q.abort_conditions?.allowed ? "可" : "不可"}(hp<${q.abort_conditions?.hp_ratio})`,
        `根拠: ${rf.rationale ?? ""}`,
      ],
      expected:
        "値が妥当なら合格(=承認)。差し戻すなら失敗にして修正指示をフィードバック欄へ。",
    };
  });
  const payload = {
    title: "クエスト戦略プロファイル承認",
    note: "合格=approved:true を適用。失敗=フィードバックを再導出タスクへ回す。",
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
    } else if (r.status === "fail" || r.status === "blocked") {
      feedback.entries.push({
        quest_id: d.data.quest_id,
        status: r.status,
        feedback: r.feedback ?? "",
        at: r.updatedAt ?? new Date().toISOString(),
      });
      console.log(`feedback recorded for Q${d.data.quest_id}: ${r.feedback ?? "(none)"}`);
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
