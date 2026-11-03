# Taxonomy open questions

Running log for T3: vocabulary additions (and why), sentences that didn't fit, and questions for
Vishal. Newest at the bottom of each section.

## Vocabulary additions

None to the schema. The `eligible_if` terms are as in `FEEDBACK_phase1.md` 2.2.

- **"Any course" (free electives).** Written as `{"level_min": 0}`, which every course passes.
  Without it, the first v2 run encoded Computer Science's free electives as `unresolved`, which
  they aren't. A dedicated term (`{"any_course": true}`) would read better; see Q7.

## Sentences that didn't fit

- **Fractions.** "No more than half of the elective units from one category" (old Distribution
  Bounds note). A `threshold` takes an absolute `value`, so a share of a total can't be written.
  For now it goes to `unclassified` as `no_fit`. See Q3.

## Questions for Vishal

1. **Choose vs count for "N from a list".** Your examples use `choose` over `specific_course`
   leaves only for short "X or Y" alternatives (MATH 126 or 129), and a `count` leaf with
   `{"courses": [...]}` for "N from the following list". I'm writing that into the taxonomy as the
   rule: alternatives joined by "or" → `choose`; "N (courses/units) from a list" → `count`. Is that
   what you intended?
2. **`NO_POOL` vs `unresolved`.** "Two courses approved by the undergraduate adviser, with no
   defined course list" is the old `manual_review` / `NO_POOL` example. Under 2.2 it reads like a
   `count` with `{"unresolved": "..."}` and `courses min 2`. Should I switch it now, or wait for
   the Phase 2 Manual Review note?
3. **Fractions.** Is "no more than half" common enough to add something like `"value_fraction"` to
   `threshold`, or should it stay `no_fit` for now?
4. **College-wide unit rules.** "A minimum of 104 units applicable to the degree must be earned in
   the college's academic departments." I'm treating it as `university_level` (a school-wide rule
   repeated on the program page). Agree?
5. **Lookup tables.** `school` and `count_by: "departments"` both need a mapping from prefix to
   school and from prefix to department. Is a prefix close enough to a department until that data
   exists?
6. **Running the check automatically.** `check_taxonomy.py` runs in under a second. Do you want it
   as a GitHub Action on PRs that touch `deg_requirement_parser/`? That affects the whole repo, so
   it's your call.
7. **"Any course".** Free electives are encoded as `{"level_min": 0}` for now. Would you rather
   add an explicit term to the schema, such as `{"any_course": true}`?
