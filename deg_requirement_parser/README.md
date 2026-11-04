# deg_requirement_parser

Module 4A, first stage. Turns USC's prose degree requirements into machine-checkable
requirement trees, one per programme, and combines them into one file for the whole
catalogue:

**[`catalogue/usc_degree_requirements_2026_2027.json`](catalogue/usc_degree_requirements_2026_2027.json)**

Code can load that file and answer "does this student's course list meet this programme's
requirements, and what's left?" without an LLM in the loop. Read [Where it might be
wrong](#where-it-might-be-wrong) before relying on it.

> [!NOTE]
> Generated with Claude (Claude Code), directed by Natalie. The taxonomy, prompt and checks
> follow Vishal's `FEEDBACK_phase1.md`; every task there is ticked with a note.

## The pipeline

```
catalogue_scraper/data/.../programs/*.txt      Francis's scrape: one file per programme (470)
        │  run_classifier.py                   numbers the lines, sends each file to Claude with
        │                                      docs/prompt_v2.txt + constraint_taxonomy.md
        ▼
out_v2/<stem>.json                             one requirement tree per programme
        │  check_results.py                    schema, citations, solver conversion, warnings
        │  check_bip.py, spot_check.py         right answers for test students; human review
        ▼
catalogue/usc_degree_requirements_2026_2027.json   build_catalogue.py: every programme that passes
```

## The format, in one paragraph

Each programme is a tree (`requirement_schema.json` is the contract; `constraint_taxonomy.md`
explains it with real examples). Leaves are `specific_course` ("take MATH 125") or `count`
("take 12 units of MUSC courses at 300 or above": an `eligible_if` in a fixed vocabulary plus
`thresholds`). Groups are `all_of` and `choose N`, and they nest, so tracks and "this course
or that pair" work. `of_which` checks put conditions on courses a node already uses ("of the
four electives, at least two at 400 level"). Each course fills one slot. Every top-level node
cites the catalogue lines it encodes (`source_lines`, `source_quote`). Anything not encoded is
listed in `unclassified` with a reason, so nothing is dropped silently.

## What's in the combined file

```json
{
  "catalogue_year": "2026-2027", "model": "claude-sonnet-5", "taxonomy_version": "2026-11-03",
  "counts": {"programmes_in_catalogue": 470, "classified": 470, "included": 0, "not_included": 0},
  "programmes": [
    {"stem": "102_economics_ba", "name": "Economics (BA)", "credential": "BA",
     "catalogue_url": "https://catalogue.usc.edu/preview_program.php?catoid=22&poid=31776",
     "content_sha256": "37d5dc19…",
     "requirements": {"program": "Economics (BA)", "status": "ok", "root": {"all_of": []}, "unclassified": []},
     "review": {"unresolved_terms": 0, "needs_data": [], "not_checked_by_code": [],
                "unclassified_by_reason": {"no_fit": 0, "out_of_scope": 1, "university_level": 0, "advisory": 1},
                "low_confidence_nodes": 0, "warnings": []}}
  ],
  "not_included": [{"stem": "…", "errors": ["…"]}]
}
```

`review` says, per programme, what code can't fully check: `unresolved` pools ("courses approved
by your adviser"), `needs_data` (pools that depend on `school` or `ge_category`, which need a
lookup table we don't have yet), and `not_checked_by_code` (the placeholder families
`course_reuse`, `sequencing`, `manual_review`, which the solver treats as met). A planner built
on this should say "check with your adviser" for those, never "done".

`content_sha256` is the hash of the scraped file. The line numbers in `source_lines` refer to
that exact version.

## Regenerating it

Everything runs from this folder. One full run costs about $30 on Sonnet 5 and takes about an
hour.

```bash
cd deg_requirement_parser
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt                  # anthropic, jsonschema, pulp
export ANTHROPIC_API_KEY=...                     # or put it in a git-ignored .env; never commit it

python check_taxonomy.py                         # the taxonomy's examples are valid (run after any edit)
python run_classifier.py --dry-run --limit 1     # build one prompt, call nothing; read it in out/
python run_classifier.py --out-dir out_v2        # the 15-programme test set, about $1
python check_results.py --out-dir out_v2         # every file must pass
python check_bip.py --program-dir out_v2         # test students get the right answers
python spot_check.py --out-dir out_v2            # out_v2/review_sheet.md, to read by hand

python run_classifier.py --all --force --out-dir out_v2 --budget 45 --concurrency 6   # all 470
python check_results.py --out-dir out_v2
python build_catalogue.py --out-dir out_v2       # writes catalogue/usc_degree_requirements_2026_2027.json
```

`--budget` stops the run before it spends more. Programmes that already have output are
skipped unless you pass `--force`. A programme that fails (a reply that isn't valid JSON twice,
or a check error) is left out of the combined file and listed under `not_included`; re-run it
with `--only <stem> --force`.

**For a new catalogue year:** re-scrape with `catalogue_scraper`, update `PROGRAMS_DIR` in
`run_classifier.py` and `check_results.py` (and the year in `build_catalogue.py`), and run the
steps above. Because sources are cited by line number, old output can't be reused against a
new scrape: the content hash will have changed.

## Where it might be wrong

The checks catch wrong *shapes* and wrong *citations* automatically. They can't catch a wrong
*reading* of a sentence. These are the known limits, roughly most to least important:

RESULTS_PLACEHOLDER

## Changing the taxonomy

When the output gets a sentence wrong, add that sentence as a new example in
`constraint_taxonomy.md`, with its correct encoding, rather than adding rules to the prompt.
The model copies examples. Then:

```bash
python check_taxonomy.py                              # every example still valid and convertible
python run_classifier.py --out-dir out_v2 --only <stem> --force
python check_results.py --out-dir out_v2
```

Change one thing at a time so you can tell what helped. Questions waiting on Vishal are in
`taxonomy_open_questions.md`.

## Files

| File | What it is |
|---|---|
| `requirement_schema.json` | The contract: exactly what a valid programme looks like. |
| `constraint_taxonomy.md` | The explanation, with real catalogue sentences and their encodings. Sent to the model on every call. |
| `examples/` | Five programmes encoded by hand (Vishal). The reference for what's right. |
| `docs/prompt_v2.txt` (repo root) | The prompt. `prompt_v1.txt` is the old list format, kept for comparison. |
| `run_classifier.py` | Numbers each file's lines, calls the Claude API, writes `<out-dir>/<stem>.json`. Sets `status` from the unclassified reasons and retries a reply that isn't valid JSON. |
| `check_results.py` | Every check on the output; writes `summary.csv`. Exits non-zero on any error. |
| `check_taxonomy.py` | The same checks on every example in the taxonomy. |
| `bip.py`, `check_bip.py`, `golden/` | Turns a programme into a solvable integer program and runs hand-made students with known answers through it. |
| `eligibility.py` | `is_eligible(eligible_if, course_code)`: True, False or "unknown". |
| `spot_check.py` | `review_sheet.md`: each node next to the catalogue text it cites, for reading by hand. |
| `build_catalogue.py` | Combines a checked run into the single catalogue file. |
| `out_v2/` | The run behind the combined file: one JSON and raw reply per programme, `summary.csv`, `run_log.csv`. |
| `catalogue/` | The combined file. |
| `FEEDBACK_phase1.md`, `taxonomy_rewrite_plan.md`, `taxonomy_open_questions.md` | Vishal's feedback with the task list ticked, the rewrite plan, open questions. |
| `out_sonnet5_40/` | The earlier 40-programme run in the old list format. Kept for comparison only. |

## Choosing a model

Prices per million tokens (input / output). The test set and the full run used Sonnet 5.

| Model | Price | Full run (estimate) |
|---|---|---|
| `claude-haiku-4-5` | $1 / $5 | ~$15 |
| `claude-sonnet-5` (default) | $2 / $10 | ~$30 |
| `claude-opus-5` | $5 / $25 | ~$75 |

The prices only drive the local estimate and `--budget`; check the pricing page when they
change. To compare models, give each run its own `--out-dir`.
