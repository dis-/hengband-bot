Live15 cause (step 1)

policy_equipment.py:2513-2525 composes rfa as a plan with source and target
gates, rather than posting all three keys. cli.py:2537 selects only one
localized prompt using prompt_japanese; cli.py:2562 passes that single string
to the executor. With English selected and the recorded Japanese read-scroll
screen, input_executor.py:1119-1131 rejects the source continuation. Only r
has been accepted; cli.py:2579 reports executor-barrier and the remaining fa
is dropped. Live13 starts at rf with a manually constructed target continuation,
so it bypasses the failing production source gate.

The fix will retain both authoritative localized prompt alternatives at the
executor boundary and pin the production CLI adapter with both recorded screens.
