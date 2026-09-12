# Behavioral hunk revert matrix

Each patch is a forward diff for exactly the named implementation hunk.  The
supervisor may copy the patched tree, run `git apply -R --ignore-whitespace`,
and execute the listed pin.  Constructed scenarios are not historical replays.

| Patch | Pin(s) expected to fail after lone reverse-apply | Why |
|---|---|---|
| `D1-1.patch` | P1b procurement/retention/identify cases | Removes the single OR-composed protection authority. |
| `D1-2.patch` | P1a, P2 | Removes typed shared rung matching and purchase-emission provenance. |
| `D1-3.patch` | P1b | The verified destroy boundary again permits a protected candidate. |
| `D1-4.patch` | P1c, P3c | Disposable/overflow selection can again nominate procurement-protected items. |
| `D1-5.patch` | P3a | Town dominated-item disposal bypasses the verified gate and does not clear refusal state. |
| `D1-6.patch` | P3b | Home disposal bypasses the verified gate and loses its refusal reason. |
| `D1-7.patch` | P3c producer and CLI assertions | Free<4 with no legal disposal falls through instead of producing the exact visible terminal. |
| `D2-1.patch` | P4a, P5 | Active-recall blockers re-derive raw free slots and reject the valid four-slot certificate. |
| `D2-2.patch` | docstring inspection only | Restores the false duplicate-authority premise; this is descriptive and has no behavioral failure claim. |
| `D2-3.patch` | P4b, P4c | A contradictory blocker consumes recall instead of stopping before the read; CLI registration/banner disappear. |
| `D3-1a.patch` | P7b, P7c, P8a/P8c | Arbiter storage, purge, and selection revert to full resource vectors, allowing self-clear. |
| `D3-1b.patch` | P7b, P8a/P8c | Removes the departure-only closed clearance key and its retained/excluded fields. |
| `D3-1c.patch` | P7c, P8a/P8c | Policy call sites stop supplying canonical keys and stop refreshing retired owners before veto. |
| `D3-2.patch` | P6 posted/general substitution cases | The progress detector may again replace a consuming read with a purchase that only repairs that read. |

Reverse-check and round-trip verification on 2026-09-12: all 14 patches returned
exit 0 for `git apply -R --check --ignore-whitespace`; each then reverse-applied
and forward-applied with exit 0.  The before/after binary-diff hash was
`0103ef6f22cc0d28ea97ea47a852deb041075436` in both states.
