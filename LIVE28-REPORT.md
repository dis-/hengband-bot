Live28 step 1 ? main 08fef4dc

Evidence is copied verbatim into tests/fixtures/live28-calibration-restore-20261001.jsonl.gz (state rows from turn 932800 onward). No live files were modified.

The false absent signature is `???? (21??)`, tval 55, sval 5. The first recorded withdrawal (decision 15200, turn 933258) includes `pu` for the 21-charge staff. Its response at 933266 carries that exact staff. The 4-charge staff remains Home at index 11 as `???? (2x 4??)`; its movement identity is unchanged (05c11698dbca6008). The 21-charge movement identity is 5a1cc9e61dd59af6. Thus neither consumption, identification nor the extra weapon equip caused the missing target.

Root: src/hengbot/policy_home.py:2217 selects the first owner with either equal signature OR equal tval/sval. After the two-charge staff is discharged, observation of the 21-charge staff incorrectly discharges the earlier four-charge debt. The 21-charge debt survives both withdrawals and reaches the typed terminal. src/hengbot/policy_home.py:1974 additionally excludes merged stack names from batch candidates despite the movement match at :81. The single withdrawal success in src/hengbot/policy.py:7853 has the same broad owner selection.

Probe: validation/live28/probe.py reproduces the exact first macro, then prints outstanding 21-charge and ammo debt, with the recorded second macro `5pN99\r\x1b`. The extra equip `way` restores the mace to sub_hand; final equipment and initial equipment have the same weapons. Earlier withdrawal already satisfied the 21-charge target, but not the four-charge target.

No pre-existing assertions changed. DO-NOT-RUN checks remain pending for Claude.
