# S3.3 live town and dungeon cycle, 2026-09-29

The 11:51:16–11:54:16 capture records repeated entrance travel, `descend`
(`>\ry`), immediate `fundraise:ascend` (`<`), Home equipment withdrawal,
equip, takeoff, and deposit, then a shop observation tour before another
entrance trip. The `descend` / `fundraise:ascend` pairs occur at decisions
29/30, 60/61, 111/112, 162/163, and 182/183. Home atomic withdrawals
occur at 13, 44, 79, 146, 166, and 186; the five later ones follow an
ascent. The first is already in progress when the window opens.

This cycle predates S3.3 enforcement. The 2026-09-28 23:35 capture was
recorded before S3.3 merged (merge commit 7117222f, 2026-09-29 11:20);
it has the same `town:travel-entrance` -> `descend` ->
`fundraise:ascend` -> Home `atomic-withdraw`/`equip`/`takeoff`/
`atomic-deposit` -> shop tour sequence. Its first repeated ascents are at
23:35:14, 23:35:28, 23:35:40, and 23:35:54. Thus ON did not introduce
the descent/ascent or equipment cycle. It did introduce the final stop:
decision 224 treated the still-open entrance Reach as a silent holder.

The alternating owners are the departure descent producer at
`src/hengbot/policy.py:9661` and the fundraising return producer at
`src/hengbot/policy_fundraising.py:305`. Each town visit also starts an
equipment transaction: the Home withdrawal composer is in
`src/hengbot/policy_home.py:1760-1810`, equip/takeoff dispatch in
`src/hengbot/policy_equipment.py:1668-1691`, and the Home deposit composer
in `src/hengbot/policy_home.py:2338-2353`. The route to the entrance is
emitted at `src/hengbot/policy.py:13288`.

Replay limit: the live capture has 2,132 state rows and 231 decision-log
rows (including its process header),
but its `policy-state.json` is a projection. It omits the claim register,
arbiter, equipment transaction session, and other policy history. The
snapshot ring is truncated. Therefore a faithful OFF/ON replay of this
window from the actual pre-decision policy state cannot be constructed.
I attempted a two-mode replay from the first recorded board with fresh
policies. Both modes reproduced decision 0 (`~f`, skill experience scan),
then diverged from the recording at decision 1 because the live policy's
prior response and latch history is missing. Feeding the recorded decision
0 key as posted caused both modes to raise `ProtocolSchemaError` on the
next board: the requested skill list was not present in the state log.
The earlier OFF capture gives a direct counterexample to ON as the cause of
the cycle; it does not prove byte identity for this particular window.

The short-travel stop is separate from the cycle. In the live capture,
decision 223 posted `town:travel-entrance` for (31,150) at distance 59.
The next board was (33,145), distance 5, and claim #140 remained awaiting.
The corrected holder resumes toward the same cell under its existing claim.
