# batchfixB

Base: a4e51bf9. Work is confined to bot-client-c2. Runtime jsonlog and other
worktrees are read-only. Every module runs in its own process.

## Step 1 observations

* guardian: six failures; first key/reason divergence index 2, captured
  `\x1b\x60n%. / shop:travel`, current `\x1b\x60n(. /
  equipment-transaction:travel-home`. Later bounce observations are not evidence
  of effects of that changed key. The dual-wield selector is under investigation.
* calibration live25: four subcases at extra weight 322 restore 1546 rather than
  1551. Before 19a6fd1f the module passes; after ammunition fitting the projected
  overweight debt also loses one ammunition unit. Cause: policy_home.py:63
  retention consults the unchanged full projected pack for each debt reduction.
* Home stage1: H1/H10 reject `ti` at executor admission; supplementary rejects
  `do`. Cause: input_executor.py:992-998 does not recognize the existing
  `policy:` owner envelope. Identical three failures reproduced on d7429e7b,
  so the premise that these passed on that revision is false. The causing
  admission guard is 28ee9a9a (git blame).
* Home alternation: first decision 591 selects k rather than b. Identical
  failure reproduced on d7429e7b. policy_home.py's complete-overload preference
  (6c8941cf, predating these merges) promotes an identification supply above
  ordinary surplus despite the declared category priority.
* Home stock-present: first changed board index 5 selects Home's ordinary
  withdrawal rather than Theoden's equipment withdrawal. The combat arithmetic
  pin also depends on the capture-time optimizer selection and is under audit.
* S3.3 r14: OFF trajectory hash differs (8a1bd0b05855aa06378b01f93a10a839bbec0352f4a9dcb9552312e73307df19).
  EXPECTED_FIRST and OFF_SHA remain untouched; the earlier equipment divergence
  must be resolved before the ownership gate can be measured.

Historical sources are read through git archive into a temporary directory
inside this worktree. No checkout of another worktree is performed.

No assertion edits or new UI classification have been made in Step 1.
