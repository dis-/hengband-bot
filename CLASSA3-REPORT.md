# Class A3

## Step 1: cause and owner/text audit (base 0d6349a7)

`src/hengbot/observed_input.py:141,145` binds all identify targets to
`IDENTIFY_ITEM_PROMPT` (normal Japanese/English). `src/hengbot/input_executor.py:1171-1180`
accepts full Japanese/English target text only for identify:full-equipped.
Thus carried identify:full stops at the captured full chooser after r,i.
Classifier lines 259-260 already recognize both forms.

Source text pairs (policy_identification.py:59-64):
- r: ??????????? / Read which scroll?
- u: ?????????? / Use which staff?
- z: ???????????? / Zap which rod?
Normal target: ?????????????? / Identify which item?
Full target: ???????*??*????? / *Identify* which item?

| Owner | Source | Target accepted before | Required target |
| --- | --- | --- | --- |
| identify:normal | r/u/z pair for actual command | normal | normal |
| identify:normal-equipped | r/u/z pair | normal | normal |
| identify:device | r/u/z pair | normal | normal |
| loot:identify-floor-item | r/u/z pair | normal | normal |
| identify:full | r (full scroll) | normal, incorrectly | full |
| identify:full-equipped | r (full scroll) | normal OR full, incorrectly | full |

Source gates depend on command, not owner: scroll/staff/rod use SOURCE_PROMPT.
Other scroll/staff/rod owners use the same source pair and no identify target;
identify:complete and identify:batch-complete are bookkeeping without a chooser.
Producers: policy_town.py:1946,2022,2102,2141; policy_equipment.py:2528;
policy.py:12266. Existing explicit chains use normal target tuples, including
full-equipped policy_equipment.py:2545, so executor normalization must cover them.

No new policy/checkpoint attributes. No EXPECTED_FIRST changes.

## Assertion audit

No changed pre-existing assertions or forbidden test edits.
