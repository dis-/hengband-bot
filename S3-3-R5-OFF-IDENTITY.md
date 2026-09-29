# S3.3 R5 OFF identity against main b1fc3ad6

The merge of `main` into `s3-3-enforcement` is `147a15ac`. It had no textual
conflicts. The S3.3 switch `_town_claim_bar_enforced` stayed OFF for this
comparison. The archived main source and merged source each ran the named
recorded module in its own Python process. Each row below gives SHA-256 of the
compact JSON trace, with no sorting or omission. The first six modules trace
every `HengbotPolicy.choose_key` result as `[key, reason]`. The remaining
modules added or updated since `1fc93933` trace direct policy key producers as
`[method, key, reason]`. Both sides' module tests passed.

| Recorded module | Calls | Main SHA-256 | Merged SHA-256 |
| --- | ---: | --- | --- |
| unaffordable_claim_tour | 4275 | `e6be91099e88a243faa6832ecee3b07219d98ef660e5886a8d20c704928353aa` | `e6be91099e88a243faa6832ecee3b07219d98ef660e5886a8d20c704928353aa` |
| town_approach_retired | 2055 | `3031d47d8056764200795a80930ab4ef2014eb7f2cbee9dd46943adf8c683bff` | `3031d47d8056764200795a80930ab4ef2014eb7f2cbee9dd46943adf8c683bff` |
| overweight_home_unreachable | 6419 | `73b5cc9f6cfb1338aef0f0a3150646adaa9d3075f7672fdd2cc635d43bf82e6f` | `73b5cc9f6cfb1338aef0f0a3150646adaa9d3075f7672fdd2cc635d43bf82e6f` |
| home_withdraw_failed_stock_present | 40 | `bb0d6f961bd0d3e3123d4c1151d91d79066b6a8a29c7ed37a43bd01d740141f1` | `bb0d6f961bd0d3e3123d4c1151d91d79066b6a8a29c7ed37a43bd01d740141f1` |
| recall_read_cancel_pingpong | 18 | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` | `b21c0b3b423c886674960f5f3640424b8a51fc3d1f8215e31b3f61a5299bcef4` |
| stuck_prompt_staged_tail | 4 | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` | `c63d582c734f396b4b44a8bee67270c6a4df393e48455461a35622a872fff5c5` |
| first_dungeon_entrance_prompt | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| newchar_light_churn | 12 | `47bd5ffaa4575b9ad6f756aff98d76d971f55c1a94401027529f6c6ce0f09118` | `47bd5ffaa4575b9ad6f756aff98d76d971f55c1a94401027529f6c6ce0f09118` |
| newchar_light_loop | 2 | `1ac2702b387be5b9f681b3b1095d83e8e5c96580a463f614d1d81a3676d2f3f7` | `1ac2702b387be5b9f681b3b1095d83e8e5c96580a463f614d1d81a3676d2f3f7` |
| newchar_town_wander | 2 | `058937885e4b0f3296cd326e778e876aa89c41e37d0a8391dcbd3e1799c24f17` | `058937885e4b0f3296cd326e778e876aa89c41e37d0a8391dcbd3e1799c24f17` |
| quest34_target_dead | 22 | `78d988c30dfb69d8f87ce390ee9db259e3667a16845136ba21928dee4dbdce29` | `78d988c30dfb69d8f87ce390ee9db259e3667a16845136ba21928dee4dbdce29` |
| star_remove_curse_unused | 4 | `638de7ac00bbecdb540d12be843b58ef9b0675397ea1559424e4b57b998c4913` | `638de7ac00bbecdb540d12be843b58ef9b0675397ea1559424e4b57b998c4913` |
| town_home_candidate_stall | 7 | `2d3686c7ba6674d7d80ead0610ed25376fc810f4f7907fb1568bf01a304a7e63` | `2d3686c7ba6674d7d80ead0610ed25376fc810f4f7907fb1568bf01a304a7e63` |
| unseen_caster_death | 6 | `5ce6e50815dedbd0d622b09c7e870312243ffcb96c0c19425927260c6695898d` | `5ce6e50815dedbd0d622b09c7e870312243ffcb96c0c19425927260c6695898d` |

The first entrance module replays the recorded key through the input executor,
so it calls no policy key producer. Its source ordered prompt and posted key
assertions passed on both sides; its empty trace hash is shown explicitly so
it is not mistaken for a decision stream. The merged unseen caster module has
one additional restored checkpoint test, which emits no key and leaves the
direct key trace unchanged.

Main introduced `_unexplained_damage_streak`. A restored checkpoint without
that attribute is now pinned: observation starts its streak from zero.
