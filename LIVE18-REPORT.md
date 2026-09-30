# Live18 identify result recognition

Base: `676e8aec`, fast-forwarded from main before work, branch `decl-r3b`.

Cause: the base's `src/hengbot/input_executor.py:253-259` required 20 or 15
leading spaces. Identification preserves the character side panel on those
rows. The recorded heading starts at display column 20 but character index 17;
the final marker starts at display column 15 after the stats panel.

Fix: `_text_at_cell` at `src/hengbot/input_executor.py:85` slices using the
existing East Asian W/F two-cell convention and rejects an interior wide-glyph
boundary. The heading at line 264 and page/final markers at lines 268-272 now
check their literals at columns 20 and 15, irrespective of the side panel.
Japanese and English literals use the same path. No new policy attributes.

Other recognizers checked (current file:line):

| Recognition | Location in src/hengbot/input_executor.py | Assessment |
| --- | --- | --- |
| Centered character footer and filename/confirmation | 201-215 | Full character modal; prefix is centered blank margin, not retained side panel. |
| Knowledge menu | 281-284 | Full centered menu, not retained side panel. |
| File viewer | 296-297 | Full centered file display, not retained side panel. |
| Store menu | 348-351 | Centered full store display, not retained side panel. |
| Building menu | 364-367 | Centered full building display, not retained side panel. |
| Row-zero item/source/direction/name prompts | 217-260 | Written from column zero; no nonzero blank-prefix assumption. |
| Store stock/page evidence | 709-775 | Already slices display cells with `_cells`. |

Only the three identify literal checks share the retained-side-panel defect.

The copied recorded JSON is byte-identical to the read-only live-screen source:
SHA-256 `d586dc89652348d93acc295673dd13395cab1c484e9955d84f50e1299c21474a`.
The page variant is explicitly derived by replacing only row 10 with its
unchanged left prefix plus `-- 続く --`. The live sender, production policy,
executor and faithful transport harness post `r`, `f`, `a`, then Escape for the
recorded final viewer; with the derived page they post Space then Escape.
Both complete. Additional pin covers both languages and wrong/wide boundaries.

Fail-before/pass-after: the valid single revert check restored the complete
executor file from `676e8aec`, ran only the new pin, and restored the fixed file
in `finally`. Both recorded sender cases stopped after `r,f,a` with
`owner=identify:full-equipped phase=continuation ... unowned unknown:
unrecognized`; the literal pin also failed (three assertion failures, two test
methods). Fixed code passes both methods. An initial invalid attempt failed at
import because the test imported the new helper; that dependency was removed
before the valid behavioral revert check.

Verification used Python 3.13 at
`C:/Users/user/AppData/Local/Programs/Python/Python313/python.exe`, with
`PYTHONPATH=src;tests;scripts`, one module per process:

| Module | Result |
| --- | --- |
| tests.test_live18_identify_result | 2 passed |
| tests.test_live17_identify_observation | 2 passed |
| tests.test_live15_identify_source | 2 passed |
| tests.test_live13_full_equipped_identify | 1 passed |
| tests.test_input_executor | 72 passed; 1 error: missing existing jsonlog/incident-20260919-2230-recall-depth-prompt.jsonl |
| tests.test_test_fakery_lint | 13 passed |

Authorized S3.3 fixture exceptions, separate processes:

| Fixture | OFF identity | ON first divergence | trajectory_defect |
| --- | --- | --- | --- |
| stuck | 4 rows, c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5 | None, as expected | null |
| withdraw | 34 rows, a9b344206bbbfda56f3f0a7797d6a9156ee029d2118163ef44e9f57fc9cc8fa9 | index/sequence 20: rkc / town:enchant-launcher-todam → Escape + `n%. / shop:travel, as expected | null |

Both fixture processes exited zero. EXPECTED_FIRST unchanged. No forbidden
runner, live bot/game action, or jsonlog write. Existing untracked
`.live8b-revert.py` left untouched.

Commits: `16de6aab` (step 1 fix), `45922505` (step 2 pins and recorded fixture).

{"topic":"live18","implementer":"gpt-6.1-sol","base":"676e8aec","commits":["16de6aab","45922505"],"revert_pin":"behavioral-fail-before-pass-after","tests_passed":92,"tests_errors":1,"error":"missing-existing-recall-depth-capture","s33_stuck":"expected-no-divergence","s33_withdraw":"expected-divergence-at-20","expected_first_changed":false}
