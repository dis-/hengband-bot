# Declarations r13: continuous replay paths

The r12 pins did not model the state reached by the continuous replay.

* Town index 59 / sequence 58: decision entry completes the Home visit claim.
  The plan still has a Home stop whose sole requester is `home-errand`, but the
  Home errand is `IDLE` with no request. The old pin kept the claim open, so
  it exercised holder deferral rather than the plan gate. The plan gate also
  omitted exploration, allowing `oscillating-probe`. The ON path now retires
  that satisfied stop before the ladder and gates exploration while a real
  plan stop remains. It reaches the frozen town row.
* Overweight index 3707 / sequence 3706: the entry wrapper has an armed and
  posted sequence 3705, but the visit has no posted store operation and no
  operation identity. The old pin checked the result gate alone. In the
  continuous path `_town_held_decision` treated its empty key as the holder's
  decision and skipped the progress invariant. An unbound entry wait now
  reaches procurement; any such empty wait still present at final emission
  stops with `ownership:declaration-missing:store-router`.

The r12 revision check reproduced both missing pin conditions: its plan gate
admitted the probe after the completed holder, and its holder check accepted
the unbound empty entry wait. It also lacked the finished Home stop cleanup.

## Fixture results

| Fixture | First difference | Trajectory defect | OFF / ON final gate counts | ON declaration gaps |
| --- | --- | --- | ---: | ---: |
| Town s33 | Index 1179, historical sequence 1177: `dl` / `equipment-transaction:deposit` | None | 52 / 0 | 0 |
| Overweight s33 | Index 3715, historical sequence 3714: ESC + backtick + `n%.` / `shop:travel` | `early-divergence` | 24 / 0 | 0 |

The overweight follow-on at index 3715 needs a design decision. Before that
decision, the Home plan stop is current (`[7, 4]`), `HomeVisit` is
`EXIT_PENDING`, and the `home-tail` delegation for the posted `de1\rESC`
operation is open. The recorded OFF action there is `rjp` /
`identify:device`, while the ON path defers identification and attempts
`shop:travel` to store 4. Identification cannot preempt the unfinished Home
visit under ruling #5, and the store-4 route also skips the Home plan stop.
The frozen overweight first-difference row 3724 cannot be reached while these
facts and the current plan-order rule both hold. A ruling is needed on whether
identification may preempt this Home tail, or the frozen expected first row
should move to the earlier corrected Home continuation after its route is
fixed. `EXPECTED_FIRST` was not edited.

Verification: `tests.test_declarations_r10` (7),
`tests.test_declarations_r11` (8), `tests.test_declarations_r12` (6), and
`tests.test_test_fakery_lint` (13) passed, one module per process. No full
suite, gate script, or other recorded replay was run.
