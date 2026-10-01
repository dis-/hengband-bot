# Store chooser incident, 2026-10-01

Step 1: base 2f7f5ba0 already strips leading whitespace for the English
and Japanese store/Home chooser at input_executor.py:262-266. The recorded
213-column screen is classified ITEM_SOURCE, not rejected by that regex.
The rejection is input_executor.py:1316: _store_buy_continuations
(cli.py:2420-2436) owns quantity/confirmation/store only, after posting pk.
The observed chooser therefore has no owner to answer k.

Recognizer inventory at the base:
- input_executor.py:232-234 quantity: suffix search, column reported as zero.
- :244-266 Home equipment/deposit and store/Home chooser: suffixes or lstrip,
  column reported as zero. Japanese chooser regex is anchored after lstrip.
- :300-329 Home knowledge viewer: centered width-derived offset, and an
  explicit 80-column fallback; these are display geometry, not column-zero assumptions.
- :351-373 store/Home footer: centered width-derived offset but Python
  character slicing; replace with existing East-Asian display-cell slicing.
- :748-789 stock/page binding: already uses centered origin and cell slicing.

Recorded row zero begins with 66 spaces and (??:a-Z, ESC???) ???.
Recorded slot k is: k) ! 4?? ?????? 0.2 352.
No policy/replay decisions or EXPECTED_FIRST values are changed.
