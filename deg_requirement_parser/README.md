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
  "counts": {"programmes_in_catalogue": 470, "classified": 470, "included": 443, "not_included": 27},
  "programmes": [
    {"stem": "102_economics_ba", "name": "Economics (BA)", "credential": "BA",
     "catalogue_url": "https://catalogue.usc.edu/preview_program.php?catoid=22&poid=31776",
     "content_sha256": "37d5dc19…",
     "requirements": {"program": "Economics (BA)", "status": "ok", "root": {"all_of": []}, "unclassified": []},
     "review": {"unresolved_terms": 0, "needs_data": [], "not_checked_by_code": [],
                "unclassified_by_reason": {"no_fit": 0, "out_of_scope": 1, "university_level": 0, "advisory": 1},
                "low_confidence_nodes": 0, "warnings": []}}
  ],
  "not_included": [{"stem": "153_music_ba", "errors": ["…"], "error_count": 6}]
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

Everything runs from this folder. The full run behind the current file cost $13.98 on Sonnet 5
(effort `low`, 6 calls at a time) and took 23 minutes for all 470 programmes.

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

python run_classifier.py --all --force --out-dir out_v2 --budget 25 --concurrency 6   # all 470
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
*reading* of a sentence.

**The run, in numbers** (`out_v2/summary.csv`, 3 November 2026):

| | Programmes | Share |
|---|---|---|
| In the catalogue scrape | 470 | |
| Pass every check, so in the combined file | 443 | 94% |
| Fail a check, so listed under `not_included` | 27 | 6% |
| Fully checkable by code: status `ok`, nothing `unresolved`, no `school`/`ge_category` lookups, no placeholder leaves | 220 | 47% |

So for about half the catalogue a planner can say "done" or "still needed" for every
requirement. For the rest, some part needs a person. In order of how much that matters:

1. **27 programmes failed a check and aren't in the file.** Nine have a `source_quote` that
   isn't on the cited lines. Most of the rest break the schema: `all_of` and `choose` on the
   same node, `not` inside `eligible_if`, a nested node with `source_lines` but no `id`, or a
   placeholder course code like `MPxx 153`. Occupational Therapy (162) and Music (153) are
   among them. A re-run usually gives a different answer, so try
   `python run_classifier.py --out-dir out_v2 --only <stem> --force`, then
   `check_results.py` and `build_catalogue.py` again. The current list is under
   `not_included` in the combined file, and `check_results.py --out-dir out_v2 --verbose`
   prints every error.
2. **The checks test shape and citations, not meaning.** A tree can pass every check and still
   misread a sentence (a wrong count, a missing course, `all_of` where the text says "or").
   The full run redid every programme, so a tree reviewed on the 15-programme test run is not
   the tree in the file. On the full run, Computer Science, Business Administration (042),
   Animation and Digital Arts (BFA) and the 3-D Animation minor read right. History (124) did
   not: it puts geographic and temporal breadth in separate slots, though the catalogue says
   "a single course may fulfill both a geographic and temporal requirement", and it drops
   "at least two must be 400-levels". The solver would tell a History major who used one course
   for both that they need more courses. No check flags it. The golden students (`golden/`,
   15 cases on 3 programmes) all get the right answer from the full run's trees. That is a
   small sample of 470.
   `spot_check.py --out-dir out_v2` writes `out_v2/review_sheet.md`, every node next to the
   text it cites, for more reading.
3. **Requirements the model couldn't encode (`no_fit`).** 56 programmes (12%) have at least one
   sentence in `unclassified` with reason `no_fit`, 68 sentences in all, and so have status
   `partial`. Some are real gaps: per-category caps inside a pool ("at most 4 units of 490x"),
   fractions ("no more than half from one department", Q3), mutual exclusions between two
   courses, hours of fieldwork, location rules. Others only restate requirements encoded
   elsewhere, so `partial` overstates a few. Read each programme's `no_fit` entries before
   trusting it.
4. **Placeholder leaves the solver treats as met.** 146 programmes have at least one
   `manual_review` (183 leaves: gates, portfolio reviews, internships), `sequencing` (33) or
   `course_reuse` (13) leaf. The solver adds no constraint for these, so they always come out
   met. They are listed per programme in `review.not_checked_by_code`. Show them as "ask your
   adviser", never "done".
5. **Pools code can't evaluate yet.** 185 `unresolved` pool terms in 110 programmes ("courses
   approved by the adviser", "any course from DANC 180-189") can't be checked. A few more need
   a lookup table that doesn't exist yet: `school` (10 leaves) and `ge_category` (3 leaves),
   Q5. These are in `review.needs_data`; the solver answers "unknown" for them.
6. **Course codes are matched exactly.** The catalogue writes GE and other designations as
   suffixes (`MATH 118gx`, `BUAD 310g`, `AMST 101gmw`); 830 distinct suffixed codes appear in
   the file. `eligibility.py` compares the whole string, so a course list has to use the same
   spelling. Check how STARS and any other source write these codes, normalise both sides the
   same way before matching, and keep `L` (lab) and `a`/`b` (sequence) suffixes, which name
   different courses.
7. **Department limits and fractions aren't encoded.** `count_by: "departments"` needs a
   prefix-to-department table (Q5), and a threshold takes an absolute value, so a share of a
   total can't be written (Q3). Rules like these are in `unclassified` or in a node's `note`.
8. **"Any course" is `{"level_min": 0}`.** Free electives ("32 units of free electives") are a
   count leaf that every course passes (40 leaves). Because each course fills one slot, these
   leaves take only courses that nothing else uses, which is the intended reading. A dedicated
   term would read better (Q7).
9. **Possible double counting (warnings).** 129 warnings in 77 included programmes say two
   count leaves accept the same course. Each course fills one slot, so if the catalogue meant
   "these may overlap", the solver will ask for more courses than the student needs. If it
   meant one requirement is a subset of another, the right encoding is an `of_which` check.
   Either way the tree needs a human look. 63 more warnings flag nesting deeper than four
   levels, which is legal but harder to read.
10. **One programme was empty.** Consumer Behavior (Interdisciplinary) minor (260) came back
    with no nodes at all, status `failed`.
11. **What the file leaves out by design.** Grades, GPA, residency, admission, placement and
    exam waivers are `out_of_scope` (Phase 2). University-wide rules (128 units, GE) are
    `university_level` and are checked elsewhere. The `school` header field is empty in the
    scrape, so it is `null` in the file.

## Demo page

`demo/` builds a static page for showing the pipeline: pick a programme, see the catalogue
text next to its tree, hover a requirement to highlight the lines it cites, and for five
programmes try a made-up student. The page has no degree logic. `demo/build_demo.py` runs each
student in `demo/students.json` through `bip.py` and writes every verdict into
`demo/data/` (generated, not committed). Students marked `golden` reuse a `golden/` case
unchanged; `--check` compares them with the golden answers.

```bash
python demo/build_demo.py --check                # writes demo/data/, needs the combined file
cd demo && python -m http.server 8000            # then open http://localhost:8000
```

`index.html` is written as a page body for publishing as a claude.ai Artifact, which adds the
`<!doctype html>` and viewport tags. To host it anywhere else, add those two lines at the top.

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
| `out_v2/` | The run behind the combined file: one JSON per programme, `summary.csv` (from `check_results.py`), `run_meta.csv` (model, cost, time) and `run_log.csv` (one row per call; overwritten by each run, so after a re-run it covers only that run). |
| `catalogue/` | The combined file. |
| `demo/` | The demo page, its made-up students and the script that precomputes their verdicts. |
| `FEEDBACK_phase1.md`, `taxonomy_rewrite_plan.md`, `taxonomy_open_questions.md` | Vishal's feedback with the task list ticked, the rewrite plan, open questions. |
| `out_sonnet5_40/` | The earlier 40-programme run in the old list format. Kept for comparison only. |

## Choosing a model

Prices per million tokens (input / output). The test set and the full run used Sonnet 5. The
other estimates scale its actual $13.98 by price and assume the same token counts, which a
different model won't exactly have.

| Model | Price | Full run |
|---|---|---|
| `claude-haiku-4-5` | $1 / $5 | ~$7 (estimate) |
| `claude-sonnet-5` (default) | $2 / $10 | $13.98 (actual, effort `low`) |
| `claude-opus-5` | $5 / $25 | ~$35 (estimate) |

The prices only drive the local estimate and `--budget`; check the pricing page when they
change. To compare models, give each run its own `--out-dir`.
