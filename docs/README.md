# docs/ — the decision-ladder page

A static page that shows the rungs of `CLAIM_LADDER` in the order `_decide`
consults them, with the number of times the live bot actually decided at each
rung drawn over them.  Live at <https://dis-.github.io/hengband-bot/>.

The sources live here, on `main`; GitHub Pages serves the `gh-pages` branch,
which holds only `index.html`, `data/ladder.json` and `.nojekyll`.  Keeping
the two apart means publishing the page never pushes unrelated work on
`main`.  To rebuild and publish in one step:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\publish_ladder_page.ps1
```

Nothing here is written by hand except `index.html`.  The data comes from the
code and from the decision logs:

```sh
python scripts/build_ladder_page.py          # -> docs/data/ladder.json
```

| source | what it contributes |
|---|---|
| `src/hengbot/claim_ladder.py` | the rungs, their order, rank, family and reason prefixes |
| `src/hengbot/*.py` | each producer's file, line and docstring |
| `src/hengbot/policy.py` | the comment above a rung's `_decide` call site, when it has no docstring |
| `jsonlog/*bot-decisions.jsonl[.gz]` | how often each rung answered, with its reasons, objectives and keys |

The generator takes `--log-glob` (repeatable, relative to `bot-client`) to
count a narrower set of runs, and `--out` to write elsewhere:

```sh
python scripts/build_ladder_page.py --log-glob 'jsonlog/bot-decisions.jsonl'
```

Regenerate after a ladder change, and after a run worth publishing; commit the
refreshed `docs/data/ladder.json` with it.  The page links each rung to its
source at the commit the data was built from, so a stale `ladder.json` still
points at code that matches it.

To look at it locally: `python -m http.server --directory docs` (the page
fetches `data/ladder.json`, so `file://` will not do).
