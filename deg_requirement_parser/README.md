# deg_requirement_parser

Module 4A, first stage. Turns USC's prose degree requirements into structured constraint
records that the degree-plan engine can solve over.

## What's here

| File | What it is |
|---|---|
| `constraint_taxonomy.md` | The taxonomy: five constraint families, each with a description, its `details` shape, and real catalogue sentences paired with their JSON encoding. Fills the `{{TAXONOMY}}` placeholder in `docs/prompt_v1.txt`. |
| `run_classifier.py` | Reads a scraped programme `.txt`, builds the prompt, calls the Claude API, writes the raw response and the parsed JSON to `out/`. |
| `check_results.py` | Validates the output and writes `out/summary.csv`. |
| `check_taxonomy.py` | Validates every JSON example in the taxonomy against `requirement_schema.json`. Run after any taxonomy edit. |
| `bip.py`, `check_bip.py`, `golden/` | Converts program JSON to a BIP and runs hand-made students (known pass/fail) through the solver. Reports any requirement that didn't convert. |
| `eligibility.py` | `is_eligible(eligible_if, course_code)`: does one course meet a condition? True, False or `"unknown"`. |
| `spot_check.py` | Builds `out/review_sheet.md` for checking the output by hand. See *Reviewing output*. |
| `out/` | Generated. Raw responses, parsed JSON, run log, summary, review sheet. |

## Input and output

Input is Francis's catalogue scrape:
`catalogue_scraper/data/usc_undergrad_complete_catalogue_2026_2027/programs/*.txt`

Output per programme:
`out/<stem>.response.txt` (raw) and `out/<stem>.json` (parsed).

## Running it

Run everything from this folder with the virtual environment active:

```bash
cd deg_requirement_parser
source .venv/bin/activate
export ANTHROPIC_API_KEY=...           # never commit this
pip install -r requirements.txt  # anthropic, jsonschema, pulp

python run_classifier.py --dry-run     # build prompts, call nothing
python run_classifier.py --limit 1     # one programme, end to end
python run_classifier.py               # the 15-programme test set (Sonnet 5 by default)
python check_results.py                # validate structure, write out/summary.csv
python spot_check.py                   # review sheet for checking by hand, write out/review_sheet.md
```

After any edit to `constraint_taxonomy.md`, run the taxonomy check. The model copies the taxonomy's
examples, so each one must validate against `requirement_schema.json`, use no old-format keys, and
have an `eligible_if` that `eligibility.py` can evaluate:

```bash
python check_taxonomy.py               # every JSON example in the taxonomy; exits non-zero on failure
python check_taxonomy.py --dir examples  # the hand-encoded programs (should always pass)
python -m unittest test_taxonomy       # tests for the check itself and for is_eligible
```

To check that a program's JSON *means* the right thing, not just that it has the right shape, run the
golden cases. `bip.py` turns the JSON into a binary integer program (PuLP, CBC solver), reports anything
it couldn't convert, and solves it for hand-made students in `golden/` whose answers are known:

```bash
python check_bip.py                         # golden cases against examples/
python check_bip.py --program-dir out_v2    # the same cases against model output
python -m unittest test_bip                 # golden cases, plus deliberately wrong encodings that must be caught
```

`--budget` stops the run before it exceeds a dollar figure, default 50. Programmes that already
have output are skipped unless you pass `--force`.

## Reviewing output

Output is checked in two passes, because they catch different kinds of mistakes.

| Script | What it checks | How |
|---|---|---|
| `check_results.py` | **Structure.** Is the JSON valid, are required fields present, is every `family` a real taxonomy family, does `source_text` appear word for word in the catalogue? | Automatically. Exits non-zero on any problem, so it works as a pass/fail gate. |
| `spot_check.py` | **Meaning.** Did the model put each sentence in the right family, with the right counts, bounds and courses? | By hand. Code can't judge this, so the script lays the output out for a person to read. |

A file can pass `check_results.py` and still be wrong. For example, a Distribution Bounds rule encoded as Course Selection is valid JSON with a real family name, and only a human reading the sentence will catch it.

**What `spot_check.py` produces.** It writes `review_sheet.md` into the output folder. For each programme it shows:

- a summary line: status, number of constraints, number of unclassified items, and the count per family
- the **unclassified text**, listed first, so you can spot requirements the model skipped
- a table with one row per constraint: the catalogue sentence, the family and details the model chose, its confidence, and a blank **verdict** column

Rows are sorted low confidence first, since that is where mistakes usually are.

**How to review.**

1. Run `python spot_check.py` (add `--out-dir <folder>` for a specific model run, `--only <stem>` for one programme, or `--low-only` to skip high-confidence rows).
2. Open `review_sheet.md` and fill in each verdict:
   - `OK`: family and details both match the sentence
   - `WRONG FAMILY`: the sentence belongs to a different family
   - `WRONG DETAILS`: the family is right but a count, bound, pool or course is wrong
3. Also read the unclassified list. If a skipped sentence is a real requirement, treat it as a wrong row.
4. Look at the family totals at the top. A large share of Manual Review usually means the taxonomy is missing examples.

**Turning the review into fixes.** Each wrong row becomes a new example in `constraint_taxonomy.md`, placed under the family it should have been, with the sentence and its correct JSON. (see *Tuning* below). Then re-run only the affected programmes with `--only <stem> --force` and review again. Change one thing at a time so you can tell which change helped.

Treat the test set as ready for a full run when `check_results.py` passes and nearly every row on the review sheet is marked `OK`.

## Choosing a model

Prices per million tokens (input / output), with the estimated cost for all 470 programmes:

| Model | Price | Est. full run |
|---|---|---|
| `claude-haiku-4-5` | $1 / $5 | ~$8 |
| `claude-sonnet-5` (default, recommended) | $2 / $10 | ~$16 |
| `claude-opus-5` | $5 / $25 | ~$40 |
| `claude-sonnet-4-5` (previous default) | $3 / $15 | ~$25 |

The 15-programme test set costs roughly $1 on Sonnet 5.  Iterate on the test set and do the full `--all` run once.

## Cost tracking

The printed cost and the `--budget` limit (default $50) use the per-model prices in `MODEL_PRICES` at the top of `run_classifier.py`.  If you pass a model that isn't in that table, the script stops and asks for prices.  Either add the model to the table or pass `--price-in` and `--price-out`.  Check the [pricing page](https://platform.claude.com/docs/en/models/overview) when prices change; the numbers only drive the local estimate, not billing.

## Comparing models without overwriting results

`--force` overwrites existing output.  To compare models side by side, give each run its own folder with `--out-dir`, then point the checkers at the same folder:

```bash
python run_classifier.py --model claude-sonnet-5 --out-dir out_sonnet5
python run_classifier.py --model claude-opus-5   --out-dir out_opus5

python check_results.py --out-dir out_sonnet5
python spot_check.py    --out-dir out_sonnet5
```

Each folder has its own `run_log.csv`, which records the model and cost for every call.  Note that `run_log.csv` is rewritten on each run, so it only covers the programmes processed in the latest run.

## Tuning

When a programme comes back wrong, fix it by adding the failing sentence to
`constraint_taxonomy.md` as a new example under the right family, not by adding rules to the
prompt. Change one thing at a time and keep the previous prompt version so the comparison is
real.

## Known limitations

- `PROGRAMS_DIR` in both scripts hardcodes `catalogue_scraper/`. That folder is due to be
  renamed to `degree_requirements_scraper`; it is one constant at the top of each file.
- Programme names are derived from filenames. If any read badly, switch to the `name` column of
  the scraper's `index.csv`.
- The classifier is called as a plain message and the JSON is extracted from the response text.
  Binding a generated JSON Schema to a tool call would enforce the shape rather than check it
  afterwards; `check_results.py` covers the gap for now.
