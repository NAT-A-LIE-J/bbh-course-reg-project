# Feedback on the Constraint Taxonomy: Phase 1

_Covers `deg_requirement_parser/constraint_taxonomy.md`, version 2026-09-08._

**What's working.** The five families look right. Good consolidation. The pipeline structure is also clean. In particular, splitting review into a structural check (`check_results.py`) and a human read (`spot_check.py`) is good.

**Some issues.** Almost everything below is about the **JSON schema**, not the logic behind the families. Your classification of *what kind of rule* a sentence is mostly holds up. The trouble is in *how the rule gets written down*: in several places the JSON uses (natural language) English. When we write python code downstream, it has to act on this data without a human or an LLM in the loop.  

There's also an issue that sometimes degree requirements depend on one-another in complex logical ways.  One way to resolve some of these dependences is to use a recursive structure via nested JSON.  It seems like a scarier than it is -- it basically takes your famlies and makes them the bottom most leaves in a tree.  Read below.  If it doesn't click, ask questions on slack.

**How to read this.** This is Phase 1: the changes to the *structure* of the JSON. Take it slowly and think through it.  I could have introduced an error. Section 1 explains why the change is needed. Sections 2–5 then build the new structure from the bottom up. A few topics (grade and GPA rules, the Manual Review family, and a way for humans to correct the output) I haven't had a time to address yet, and I'll update this doc when I do and send you a ping.  You should be able to start working with what's here. (The remaining stuff will come tomorrow or day after.)

Two files to read with this document, in the same folder:

- **`requirement_schema.json`**: a formal definition of the new JSON shape. See "The schema file" below for why we wrote it and how to use it.  Previously you were defining the schema in the markdown files, but we need a formal file to validate correctness of outputs.
- **`examples/`**: five real programs we encoded by hand in the new format. Keep one open while you read.

> [!NOTE]
> Read this on GitHub. The boxes marked **Task** are the things we need you to do. They're numbered in reading order (maybe easier to complete them in a different order), and all collected as a checklist in "Your task list" at the end.

### The new shape at a glance

Here is the skeleton of what the classifier returns for one degree program (abbreviated). For now, just skim it to have a sense of where we're going.

```json
{ "program": "Public Policy (BS)",
  "status": "ok",
  "root": {"all_of": [
    { "id": "PP-BS-CORE",
      "source_lines": [[32, 44]], "source_quote": "Core Curriculum (30 Units)",
      "description": "...", "confidence": "high", "note": null,
      "all_of": [
        {"family": "specific_course", "course": "PPD 225"},
        "..." ] },
    { "id": "PP-BS-TRACKS",
      "source_lines": [[46, 50]], "source_quote": "Tracks",
      "description": "...", "confidence": "high", "note": null,
      "choose": 1,
      "from": [
        { "id": "PP-BS-TRACK-HEALTH", "source_lines": [[52, 77]], "...": "...",
          "all_of": [
            {"family": "specific_course", "course": "PPD 325"},
            "...",
            {"family": "count", "...": "..."} ] },
        "..." ],
      "of_which": [ {"source_lines": [[50, 50]], "source_quote": "...", "thresholds": ["..."]} ] }
  ]},
  "unclassified": [ "..." ] }
```

Next, we need to standardize some vocabulary. As the programmer Phil Karlton put it: "There are only two hard things in Computer Science: cache invalidation and naming things."  Here's my attempt.  I've renamed some of your terms with words I think are clearer, but I'm open to discussion on these. Clarity in the word choice also helps the LLM do the parsing.

| Term                           | Meaning                                                                                                                 | Replaces                                    | Explained in |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ------------ |
| `specific_course`              | A leaf: take this one course.                                                                                           | course codes in `fixed` / `choose` lists    | 2.1          |
| `count`                        | A leaf: take enough eligible courses to meet its thresholds.                                                            | Course Selection pools, Distribution Bounds | 2.2          |
| `eligible_if`                  | Which courses count, written in a fixed vocabulary.                                                                     | `filter`, `pool`, `pool_rule`               | 2.2          |
| `unresolved`                   | A condition the catalogue states but gives no way to check.                                                             | (new)                                       | 2.2          |
| `thresholds`                   | What to add up (`count_by`: courses or units) and the number to reach.                                                  | `bound`, `count`, `measure`                 | 2.2          |
| leaf, `family`                 | The bottom of the tree: a node of one kind (`specific_course`, `count`, `course_reuse`, `sequencing`, `manual_review`). | your families                               | 2            |
| `all_of`                       | A group: every item is required.                                                                                        | `fixed`                                     | 3.1          |
| `choose` / `from`              | A group: at least N of the items are required.                                                                          | `choose` (now nestable)                     | 3.1          |
| node                           | A leaf, or a group of nodes.                                                                                            | records, "constraints"                      | 3.1          |
| one-slot rule                  | Each course fills at most one slot in the whole program.                                                                | Course Reuse `PROHIBITS`                    | 3.3          |
| `of_which`, check              | Conditions on the courses a node uses. Checks never claim courses.                                                      | `scope`, many Distribution Bounds           | 4            |
| root                           | The node for the whole program: an `all_of` of its top-level nodes.                                                     | the list of records                         | 5.1          |
| anchored node                  | A node that cites the catalogue text it encodes (`source_lines`).                                                       | a record                                    | 5.1          |
| `source_lines`, `source_quote` | Where in the catalogue file the text is (line numbers), plus its first few words.                                       | `source_text`                               | 5.2          |

---

## 1. Why change: three degrees the current format can't easily represent

Today each degree program becomes a list of records. Implicitly, the student passes if **every** record is satisfied, and each record is checked **on its own**. But some degrees don't work that way. Three examples:

**Example 1: tracks (Public Policy BS).** "Students select one track for degree emphasis." Your format would give one record choosing a track *name* (`choose 1` from `["Health Policy", "Philanthropy", ...]`), plus separate records for each track's required courses and electives. You can't check these records independently and "and" them. Maria completes the Health track, but nothing links the Health records to the name "Health Policy", and the Philanthropy records fail because she hasn't taken PPD 353. **Maria is told she is missing three tracks.**

**Example 2: a pair of courses as one option (Occupational Therapy BS).** "OT 251 *or* EDUC 589 *or* (PSYC 336L *with* PSYC 337L)." Your `choose` picks from a list of single courses, so the best available is `choose 1 from [OT 251, EDUC 589, PSYC 336L, PSYC 337L]`. Jay takes only PSYC 336L. It's on the list, so **the checker says he's done**. He isn't; he needs 337L too.

**Example 3: "of those" (Economics BA).** "Of the four elective courses (300 level or above) a minimum of two must be economics courses at the 400 level or higher." Your format splits this into two records, linked only by the free-text `"scope": "the four electives"`, which the checker can't read. So it counts *every* 400-level course the student has. Priya has four 300-level ECON electives, plus MATH 407 and CSCI 401 taken for other reasons, so **she passes when she should fail.**

In words: requirements *contain* other requirements (a track contains its required courses and electives), they involve *or* over groups, and some rules only make sense *relative to* another requirement. A list of independent records can't express these dependencies. There is also a quieter problem underneath Example 3: the `filter` itself is free text. (We'll fix that below, too.)

The rest of this document builds a new structure from the bottom up. Section 2 describes the simplest pieces (leaves), Section 3 shows how they combine into groups, Section 4 adds conditions on the courses a group uses, and Section 5 shows how it all becomes a degree program. Each of the three examples is solved along the way.

---

## 2. Leaves: the simplest pieces

A **leaf** is the smallest piece of the structure. Every leaf is a JSON object with a `family` field saying what kind of leaf it is. This section covers the two you'll use most, `specific_course` and `count`. The rest come in Phase 2.

### 2.1 The `specific_course` leaf

The simplest leaf says "take this one course":

```json
{"family": "specific_course", "course": "MATH 125"}
```

This may look like overkill for one course, but it gives this leaf the same shape (an object with a `family`) as every other leaf. So the model has only one pattern to learn, and the checker never needs a special case.

### 2.2 The `count` leaf

The next leaf says "take enough courses of a certain kind". Some examples from the scraped files:

- **Computer Science (BS):** "Take at least four **300- or 400-level CSCI** courses for a minimum of 16 units."
- **Business Administration (BS):** 12 units of upper-division elective from the Marshall prefixes **ACCT, BAEP, BUCO, DSO, FBE, FIM, MKT, MOR**.
- **Your example:** "Twelve units from any **MUSC course at the 300 level or higher**."

You already had the right idea for these: a filter (which courses count), a measure (courses or units) and a bound (the number). The `count` leaf keeps that idea, with two fields:

| Field         | Meaning                                                          |
| ------------- | ---------------------------------------------------------------- |
| `eligible_if` | which courses count (your filter)                                |
| `thresholds`  | what to add up, and the number to reach (your measure and bound) |

Here is your MUSC example:

```json
{ "family": "count",
  "eligible_if": {"all": [ {"prefix": ["MUSC"]}, {"level_min": 300} ]},
  "thresholds": [ {"count_by": "units", "op": "min", "value": 12} ] }
```

In words: *add up the units of the student's MUSC courses at 300 or above, and check the total is at least 12.*

#### `eligible_if`: which courses count

**The problem with the current format.** Today the filter is free text, and your own examples write it five different ways:

| Example in the taxonomy               | How the filter is written                   |
| ------------------------------------- | ------------------------------------------- |
| Twelve units of MUSC at 300 or higher | `"pool_rule": "subject MUSC, level >= 300"` |
| 24 of 32 units upper-division         | `"filter": "level >= 300"`                  |
| At most 2 courses at 100/200 level    | `"filter": "level 100-200"`                 |
| At most 2 courses outside the college | `"filter": "outside the college"`           |
| Law Electives min 4 / max 8           | `"filter": "Law Electives"`                 |

Pathwise (the degree planner) will ask one question over and over: *does MUSC 352 count toward this requirement?* With the filter stored as `"subject MUSC, level >= 300"`, the code has two options, both bad. It can try to parse English, which breaks as soon as the model writes "MUSC 300+" or "upper-division MUSC" instead. Or it can ask an LLM every time, which is slow, costs money, and can give different answers on different days. The point of the pipeline is to do the language understanding **once**, check it, and then rely on it.

**The fix: a small, fixed vocabulary.** Every filter is built from these few terms:

| Term                      | Meaning                                                    | Example                                           |
| ------------------------- | ---------------------------------------------------------- | ------------------------------------------------- |
| `courses`                 | an explicit list of course codes                           | `{"courses": ["CSCI 201", "CSCI 270"]}`           |
| `prefix`                  | the course's subject prefix is one of these                | `{"prefix": ["CSCI"]}`                            |
| `level_min` / `level_max` | the course number is at least / at most this               | `{"level_min": 300}`                              |
| `school`                  | the course is offered by this school                       | `{"school": "Dornsife"}`                          |
| `ge_category`             | the course satisfies this GE category                      | `{"ge_category": "GE-C"}`                         |
| `unresolved`              | the catalogue doesn't give a rule we can check (see below) | `{"unresolved": "department-approved offerings"}` |

combined with:

| Combinator         | Meaning                               |
| ------------------ | ------------------------------------- |
| `{"all": [ ... ]}` | every condition must hold (AND)       |
| `{"any": [ ... ]}` | at least one condition must hold (OR) |
| `{"not": { ... }}` | the condition must *not* hold         |

Now "does MUSC 352 count?" is mechanical: the MUSC example asks for prefix MUSC *and* level at least 300, and MUSC 352 has both. MUSC 250 fails on level; THTR 352 fails on prefix. A short function gives the same answer every time, with no variants to handle. Your other examples:

- **CS core electives** ("300- or 400-level CSCI"): `{"all": [ {"prefix": ["CSCI"]}, {"level_min": 300, "level_max": 499} ]}`
- **Marshall electives**: `{"all": [ {"prefix": ["ACCT", "BAEP", "BUCO", "DSO", "FBE", "FIM", "MKT", "MOR"]}, {"level_min": 300} ]}`
- **Outside the college**: `{"not": {"school": "Dornsife"}}`

Two things to note for when you write the Python:

- **Level means the course number.** "CSCI 103L" is level 103; letter suffixes (`L`, `g`, `x`, ...) don't change it.
- **`school` needs outside data**, a table from prefix to school, which we don't have yet. Encode the rule correctly now; the data can come later.

> [!IMPORTANT]
> **Task T1.** In the taxonomy (and the prompt's examples), replace every free-text `filter` / `pool_rule` with an `eligible_if` built from this vocabulary.

> [!IMPORTANT]
> **Task T2.** Write a small function `is_eligible(eligible_if, course_code)` that returns `True`, `False`, or `"unknown"` (for `unresolved`, and for `school` until we have that table). `eligible_if` is the value of a `count` leaf's `"eligible_if"` field *after* `json.load`, so it arrives as a Python dict (e.g. `{"all": [{"prefix": ["CSCI"]}, {"level_min": 300}]}`), not a string; `course_code` is a string like `"CSCI 353"`. Test it on a few cases, e.g. for the CS core-electives condition: CSCI 353 → `True`; CSCI 201 → `False`; MATH 407 → `False`. If you can't write this function cleanly, the vocabulary isn't correct yet.

> [!IMPORTANT]
> **Task T3.** Keep the vocabulary short. Add a new term only when several programs need it, and log each addition (and why) in `taxonomy_open_questions.md` (create it if you haven't), along with any sentence that didn't fit and anything you'd have asked us.

#### `unresolved`: what we can't check

Some requirements don't define their pool. Your history example:

> Students select four courses from the department's approved upper-division offerings in American, European, or global history.

No list of "approved offerings" exists. We shouldn't invent one, but we also shouldn't throw away what we *can* check: it's a history course, and it's upper-division.

```json
{ "family": "count",
  "eligible_if": {"all": [
    {"prefix": ["HIST"]},
    {"level_min": 300},
    {"unresolved": "department-approved offerings in American, European, or global history"}
  ]},
  "thresholds": [ {"count_by": "courses", "op": "min", "value": 4} ] }
```

Now the tool can say: *HIST 350 might count, but the department has to approve it; check with your adviser.* And HIST 150 fails outright. Three rules:

1. **Use it only when the catalogue gives no rule.** It isn't a shortcut for "this was hard to encode."
2. **Keep every checkable piece**, as in the history example.
3. **Quote or closely paraphrase the catalogue** in the `unresolved` text.

As a bonus, counting `unresolved` across the catalogue tells us how much of the planner can be automatic and how much must end with "ask your adviser."

> [!IMPORTANT]
> **Task T4.** Add `unresolved` and these three rules to the taxonomy, with the history example.

#### `thresholds`: how many

Each threshold is `{"count_by": ..., "op": ..., "value": ...}`: count by `"courses"` or `"units"` (or `"departments"`, for "from at least three different departments"), and compare with `min`, `max` or `eq`. For example, "no more than two courses outside the college" is `{"count_by": "courses", "op": "max", "value": 2}`. Two things to get right.

**VERY IMPORTANT: "Choose N" means *at least* N, not *exactly* N.** Your taxonomy encodes "Choose three courses from the following list" as `{"op": "eq", "value": 3}`. A student who takes four courses from the list has obviously satisfied "choose three", but a checker reading `eq 3` sees 4 ≠ 3 and reports a failure. The extra course doesn't hurt anything; at worst it counts as a free elective. So:

- "Choose N", "complete N", "N units from", "at least N", "a minimum of N" → `"op": "min"`.
- "No more than N", "at most N", "a maximum of N" → `"op": "max"`.
- `"op": "eq"` only when the catalogue says *exactly* N, which should be rare.

"Choose three courses from CSCI 201, CSCI 270, CSCI 310, CSCI 350" becomes `{"count_by": "courses", "op": "min", "value": 3}`, and a student who took all four passes.

> [!IMPORTANT]
> **Task T5.** Update the **Normalizing** paragraph of the taxonomy to say this explicitly (a bare number like "four courses" means `min`; `eq` only for "exactly"), and change every example that uses `eq`.

**Some requirements need more than one threshold**, which is why `thresholds` is a list. CS says "at least four ... courses **for a minimum of 16 units**." The Public Policy Health track asks for "8 electives" (units) and "Select two" (courses), but two courses on its list, MEDS 220 and MEDS 405, are only 2 units each. Every threshold is measured over the *same* eligible courses, and all must hold:

```json
{ "family": "count",
  "eligible_if": {"courses": ["ACAD 260", "GERO 416", "HP 408", "LAW 403", "MEDS 220", "MEDS 405", "..."]},
  "thresholds": [
    {"count_by": "courses", "op": "min", "value": 2},
    {"count_by": "units",   "op": "min", "value": 8} ] }
```

Dana picks MEDS 220 + MEDS 405: two courses, but only four units, so she fails the second threshold. Usually `thresholds` has just one entry.

> [!IMPORTANT]
> **Task T6.** Make `thresholds` a list in the taxonomy, and encode both numbers whenever the catalogue states both (e.g. your "four courses (16 units)" example).

#### Why these names

The renames are listed in the glossary at the top. The reasoning:

- **`bound` → `threshold`.** This is the one I feel most strongly about. "Bound" is math jargon; "threshold" is the everyday word for the number you have to reach, or must not go over. (Your taxonomy also calls the same thing `count` in Course Selection. One name for one thing.)
- **`filter` → `eligible_if`.** It reads as a sentence: *a course is eligible if...* "Filter" doesn't tell you whether matching courses are kept or thrown out.
- **`measure` → `count_by`.** "Count by units" says what it does.

And **drop `pool` and `pool_rule`**: both now go in `eligible_if` (`{"courses": [...]}` for a list, the vocabulary for a description).

> [!IMPORTANT]
> **Task T7.** Adopt these three names and drop `pool` / `pool_rule` everywhere (taxonomy, prompt, scripts). If you disagree with a name, tell us why rather than silently keeping the old one.

### 2.3 The other leaf families

Your other families become leaves too. For now they keep your `kind` values and your current `details`, with one exception:

- `course_reuse`: narrows to *explicit exceptions* to "no double counting" (see Sections 3.3 and 6). Its `details` are otherwise unchanged for now.
- `sequencing`: unchanged for now.
- `manual_review`: unchanged for now.

Expect all three to change shape somewhat when I send feedback on the rest of your taxonomy. The schema treats them as placeholders (any `details` passes), so you can keep working in the meantime, but don't put much effort into polishing their `details` yet.

---

## 3. Groups: combining nodes

### 3.1 `all_of` and `choose`

Two ways to combine nodes:

| Group  | Written as                       | Meaning                              |
| ------ | -------------------------------- | ------------------------------------ |
| All of | `{"all_of": [ ... ]}`            | every item is required               |
| Choose | `{"choose": 2, "from": [ ... ]}` | at least 2 of the items are required |

(`choose` means *at least*, for the same reason as `min` in Section 2.2.)

The items inside a group can themselves be groups. So the full definition refers to itself:

> A **node** is a leaf, an `all_of` of nodes, or a `choose` of nodes.

That's what makes the structure a tree. In practice three or four levels cover every program we've tried.

**CS Math.** "MATH 125, and MATH 126 or 129, and MATH 225 or 235, and MATH 226 or 229."

```json
{"all_of": [
  {"family": "specific_course", "course": "MATH 125"},
  {"choose": 1, "from": [
    {"family": "specific_course", "course": "MATH 126"},
    {"family": "specific_course", "course": "MATH 129"}]},
  {"choose": 1, "from": [
    {"family": "specific_course", "course": "MATH 225"},
    {"family": "specific_course", "course": "MATH 235"}]},
  {"choose": 1, "from": [
    {"family": "specific_course", "course": "MATH 226"},
    {"family": "specific_course", "course": "MATH 229"}]}
]}
```

Your current `fixed` + `choose` could already say this one. `all_of` is `fixed` under a new name, with the difference that its items can themselves be groups.

**Occupational Therapy.** "OT 251 or EDUC 589 or (PSYC 336L with PSYC 337L)."

```json
{"choose": 1, "from": [
  {"family": "specific_course", "course": "OT 251"},
  {"family": "specific_course", "course": "EDUC 589"},
  {"all_of": [
    {"family": "specific_course", "course": "PSYC 336L"},
    {"family": "specific_course", "course": "PSYC 337L"}]}
]}
```

The pair is an `all_of` inside the `choose`. This is Example 2 from Section 1, solved: Jay's PSYC 336L alone no longer passes.

### 3.2 Two layers of combining

You've now seen two sets of combinators, and they work at different layers:

- **`all_of` / `choose`** combine *nodes*: "take this and this", "pick two of these".
- **`all` / `any` / `not`**, inside `eligible_if`, combine *conditions on a single course*: "is this one course CSCI *and* at least 300-level?"

The names are deliberately different so the two layers can't be confused.

### 3.3 The one-slot rule

**Each course fills at most one slot in the whole program**, unless the catalogue explicitly says it may count twice. An item in a `choose` can only be used once, and one course can't satisfy two different nodes.

Here's why this matters. Economics requires "ECON 203, ECON 205, ECON 303, ECON 305, ECON 317, ECON 318 and four economics elective courses (300 level or above)":

```json
{"all_of": [
  {"family": "specific_course", "course": "ECON 203"},
  "... five more specific_course leaves ...",
  {"family": "count",
   "eligible_if": {"all": [ {"prefix": ["ECON"]}, {"level_min": 300} ]},
   "thresholds": [ {"count_by": "courses", "op": "min", "value": 4} ]}
]}
```

A student has taken the six named courses plus ECON 351 and ECON 352. Without the one-slot rule, the `count` leaf sees six eligible courses (ECON 303, 305, 317, 318, 351, 352) and passes, even though she has only two electives. With the rule, the four 300-level core courses are already used by their `specific_course` leaves, so the `count` leaf sees two and correctly fails.

Two consequences:

- **"Elective" needs no special encoding.** In the catalogue, an elective almost always means "an *additional* course meeting some condition, beyond the ones already required." You never need to write "not one of the required courses"; the one-slot rule handles it. Just encode which courses are eligible.
- **Many catalogue sentences only restate this rule.** For example: "the courses not used to satisfy these requirements may be taken as electives" (Public Policy); "it can not be double-counted as the cross-cutting course" (Public Policy); "ANTH 470 can be taken as either a course option OR as a Senior Capstone Course option" (Anthropology). Don't create records for these; mention them in the relevant `note`. One wrinkle: when such a sentence names courses that aren't on the elective list (the Law track's "courses not used" are LAW 300, POSC 340, LAW 200w and PPD 357), add those courses to the elective list's `eligible_if`.

The explicit exceptions ("may double-count no more than three courses toward another major") are what your Course Reuse family is for. One exception is university-wide: a minor may share courses with a major, but at least 16 units must be unique to the minor. Don't encode that one; the tool will handle it.

(A note for later, when you write the checker: it has to *assign* courses to slots sensibly. ECON 303 should go to its `specific_course` slot, not to an elective slot. So it has to try different assignments, not just fill slots in order.)

---

## 4. `of_which`: conditions on the courses a node uses

The full Economics text continues: "Of the four elective courses (300 level or above) **a minimum of two** must be economics courses at the 400 level or higher." This is a condition on courses *already counted*, not a request for more courses. Written as a second `count` leaf next to the first, the one-slot rule would demand 4 + 2 = 6 electives.

Every node *uses* some courses: a leaf uses the courses that fill its slots, and a group uses everything its children use. An **`of_which`** list attaches **checks** to a node: *of the courses this node uses, these conditions must hold*. A check only looks. It never claims a course.

```json
{ "family": "count",
  "eligible_if": {"all": [ {"prefix": ["ECON"]}, {"level_min": 300} ]},
  "thresholds": [ {"count_by": "courses", "op": "min", "value": 4} ],
  "of_which": [
    { "source_lines": [[21, 21]],
      "source_quote": "a minimum of two must be economics courses",
      "eligible_if": {"level_min": 400},
      "thresholds": [ {"count_by": "courses", "op": "min", "value": 2} ] } ] }
```

In words: *four ECON electives at 300+, of which at least two are at 400+.* This is Example 3 from Section 1, solved. Priya's four 300-level electives fail the check, and her MATH 407 was never a candidate because `eligible_if` says ECON. Every check cites its own catalogue text (`source_lines`, Section 5.2), because it's the construct most likely to be misread.

**Attach the check to the node the sentence is about.** Examples at each level, all from real programs in `examples/`:

- **A leaf.** Behavioral Economics: "seven 4-unit electives with no more than four courses (16 units) from either ECON or PSYC" is a `count` leaf with two checks (at most four ECON, at most four PSYC). Philanthropy track: "Only one from the following: PPD 314, PPD 415, or PPD 344" is a check with a `max 1` threshold on the electives leaf.
- **A group.** Public Policy: "they take 28 units from the track selected" is a check on the `choose` of tracks.
- **The whole program.** Religion: "at least 24 units must be upper-division" is a check on the root (Section 5.1).

**A wording convention.** "Of the N…", "of which…", "of these…" → `of_which`. "Plus…", "additional…", "and N more…" → a separate node. If part of the sentence can't be expressed, put it in the `note`. (Economics continues "The remaining two economics courses must be approved by the department's director of undergraduate studies"; a check can't target "the remaining two", so that goes in the note.)

> [!IMPORTANT]
> **Task T8.** Add `of_which` to the taxonomy, with one example at each of the three levels and the wording convention above.

---

## 5. From nodes to a degree program

### 5.1 The root and anchored nodes

A program's output has a **root**: an `all_of` of its top-level nodes. The degree requires all of them. The root may also carry program-wide `of_which` checks.

An **anchored node** is a node that cites the catalogue text it encodes. It carries `source_lines` and `source_quote` (Section 5.2), plus the fields you already have: `id`, `description`, `confidence`, `note`. Every node directly under the root must be anchored. Deeper nodes may be anchored too, and should be whenever they have their own heading or sentence.

**Each heading block, or standalone rule sentence, becomes an anchored node, and anchored nodes nest the way the catalogue's headings nest.** This gives the model a mechanical rule instead of a judgment call about "what counts as one constraint". It also roughly mirrors how STARS lays out its blocks, which we'll need later.

**One exception: amendments.** Sometimes a later passage changes an earlier one. Public Policy's core lists "PPD 431 \*", and the asterisk points to a Capstone section further down offering PPD 431 *or* PPD 497a + 497b. Encode the later passage *inside* the node it modifies (here, as the capstone slot of the core), citing both places. Otherwise two nodes both demand PPD 431, and no student can satisfy both.

### 5.2 Citing the catalogue by line number

Quoting a heading plus sixty bullet points word for word isn't practical, and an abbreviated quote can't be checked. So instead of `source_text`, the model cites **line numbers** in the program's `.txt` file:

- `run_classifier.py` numbers every line when it builds the prompt (`L052: ### Health Policy and Management Track`).
- The model cites ranges: `"source_lines": [[52, 77]]`. It's a list, so text in two places can be cited together: the Public Policy capstone is `[[44, 44], [223, 225]]`.
- It also copies the first few words of the cited text into `source_quote`. `check_results.py` checks that the quote appears inside the cited lines, which catches wrong line numbers.
- `spot_check.py` expands the ranges back into full text for the human review.

Line numbers refer to the file as scraped. The content hash in each file's header records which version.

> [!IMPORTANT]
> **Task T9.** Number the lines in `run_classifier.py` when building the prompt, and replace `source_text` with `source_lines` + `source_quote` everywhere (including `unclassified`).

### 5.3 Tracks, solved

Each Public Policy track has its own heading, so each is an anchored node nested inside the `choose`:

```json
{ "id": "PP-BS-TRACKS",
  "source_lines": [[46, 50]], "source_quote": "Tracks", "...": "...",
  "choose": 1,
  "from": [
    { "id": "PP-BS-TRACK-HEALTH",
      "source_lines": [[52, 77]], "source_quote": "Health Policy and Management Track", "...": "...",
      "all_of": [
        {"family": "specific_course", "course": "PPD 325"},
        "... four more specific_course leaves ...",
        {"family": "count",
         "eligible_if": {"courses": ["ACAD 260", "GERO 416", "...", "MEDS 220", "MEDS 405", "..."]},
         "thresholds": [ {"count_by": "courses", "op": "min", "value": 2},
                         {"count_by": "units",   "op": "min", "value": 8} ]} ] },
    "... the other four tracks ..." ],
  "of_which": [ {"source_lines": [[50, 50]], "source_quote": "they take 28 units from the track selected",
                 "thresholds": [ {"count_by": "units", "op": "min", "value": 28} ]} ] }
```

The `choose 1` needs one satisfied track. Maria completes Health, so it passes, and the other tracks are never demanded. This is Example 1 from Section 1, solved.

> [!IMPORTANT]
> **Task T10.** Write `prompt_v2.txt` (keep v1). Update its output template to the new shape, and add these instructions: (1) each heading block or standalone rule sentence becomes an anchored node, nested as the headings nest; (2) a passage that amends an earlier one goes inside that node; (3) each course fills at most one slot, and sentences that only restate this go in a `note`; (4) "of the N…" becomes `of_which`, and anything a check can't express goes in the `note`; (5) cite `source_lines` and `source_quote`. Keep the template in step with `requirement_schema.json`: the model only sees the prompt, not the schema file.

### 5.4 What doesn't fit: `unclassified`, with a reason

Your taxonomy's "Out of scope" table tells the model to emit *nothing* for grade rules, residency, P/NP, honors and so on. That silently throws information away, and it hides the number we most want: how much of the catalogue the taxonomy can't handle. Instead, record every such sentence in `unclassified`, with a `reason`:

| `reason` | Use for |
|---|---|
| `no_fit` | a requirement the taxonomy has no place for |
| `out_of_scope` | things we deliberately don't encode yet: grades, residency, P/NP, honors, graduate programs |
| `university_level` | university- or school-wide rules repeated on the program page (GE, the writing requirement, the 128-unit total), which we take from STARS instead |
| `advisory` | recommendations, not requirements ("students are encouraged to…") |

```json
{"source_lines": [[27, 27]], "source_quote": "A minimum grade of C, 2.0",
 "reason": "out_of_scope", "why": "Grade rule; Phase 2."}
```

`status` is `partial` only if there's a `no_fit`. Counting `no_fit` across the 15 files answers the original question behind all of this: does the taxonomy cover the catalogue?

> [!IMPORTANT]
> **Task T11.** Replace the "emit nothing" instruction for out-of-scope items with `unclassified` entries carrying a `reason`, in both the taxonomy and the prompt.

---

## 6. Where your families went

Your taxonomy work isn't lost; it moves down into the leaves and checks.

- **Course Selection** becomes the structure itself: `fixed` → `all_of` of `specific_course` leaves, `choose` → `choose` (now nestable), `pool` / `pool_rule` → a `count` leaf's `eligible_if`, and tracks → a `choose` over nested anchored nodes.
- **Distribution Bounds** splits in two. A rule that picks courses ("12 units from any MUSC course at 300 or higher") is a `count` leaf. A rule about courses picked elsewhere ("no more than two courses in the major outside the college", "24 of the 32 major units upper-division") is an `of_which` check on the relevant group or on the root. `CATEGORY_BOUNDS` ("four courses, at least one from each of three groups") is a `count` leaf with one check per group.
- **Course Reuse** keeps only the *explicit exceptions* to the one-slot rule. `PROHIBITS` records and restatements become notes. "Students may not complete more than one of TAC 115, TAC 116, CSCI 103L and CSCI 113x" isn't about reuse: it's a check with a `max 1` threshold on the root.
- **Sequencing** and **Manual Review** are unchanged for now (Section 2.3).

> [!IMPORTANT]
> **Task T12.** Re-map your families in the taxonomy as described above.

> [!IMPORTANT]
> **Task T13.** Rewrite `constraint_taxonomy.md` around the new structure (Sections 2–5), with your real catalogue examples re-encoded. **Remove every example in the old format.** The model copies the examples it sees, so one leftover old example will leak into the output.

---

## The schema file

### Why we wrote it

`check_results.py` never looks inside `details`, so *any* `details` passes: a misspelled key (`"treshold"`), a string where a number belongs, an invented field. With the tree structure there's much more to get wrong. `requirement_schema.json` defines every shape in this document exactly, in the standard [JSON Schema](https://json-schema.org/) format, and **rejects unknown fields everywhere**. We wrote it ourselves because a recursive JSON Schema is fiddly; every definition has a `description` saying what it's for.

**How the two documents relate.** `requirement_schema.json` is the *contract*: exactly what a valid output looks like. `constraint_taxonomy.md` is the *explanation*: what each piece means, with real catalogue sentences and their encodings, for both the model and people. If you find they disagree, the schema wins, and please tell us. If you think the schema is wrong, which is quite possible, propose the change rather than working around it.

**The `examples/` folder** holds five complete programs we encoded by hand against the schema: Economics, Public Policy, Religion, Behavioral Economics and Psychology, and Anthropology (Visual Anthropology). Economics and Public Policy are in your test set, so you can compare your pipeline's output to ours directly.

### How to use it

1. **Validate in `check_results.py`.** Python's `jsonschema` package does all the work:
   
   ```python
   import json, jsonschema
   
   schema = json.load(open("requirement_schema.json"))
   validator = jsonschema.Draft7Validator(schema)
   
   data = json.load(open("out/086_computer_science_bs.json"))
   for error in validator.iter_errors(data):
       print(list(error.path), error.message)
   ```
   
   Each error comes with its location in the file (e.g. `['root', 'all_of', 3, 'from', 1]`), so you can find it. Treat any error as a failed program in `summary.csv`.
   
   One warning: when a piece could be one of several shapes (a node can be an `all_of`, a `choose`, or any of the leaf families), the error messages can be vague ("is not valid under any of the given schemas"). When that happens, look at the location, then compare that piece against the examples.

2. **Try it on `examples/` first.** Every file should pass. Then break something on purpose (misspell `threshold`, put a string in `eligible_if`) and confirm you get an error. That's how you know the check is wired up.

3. **Add the checks a schema can't do.** A JSON Schema checks the *shape* of each piece, not its relation to anything else. Add these to `check_results.py` yourself:
   
   - every `source_lines` range is inside the file, and its `source_quote` appears in the cited lines;
   - no two anchored nodes share an `id`;
   - a warning when one `specific_course` appears under two different top-level nodes (usually a missed amendment, Section 5.1);
   - a warning when two sibling `count` leaves have overlapping `eligible_if` (e.g. both ECON, one 300+ and one 400+), which is usually a missed `of_which`;
   - a warning when a node nests deeper than four levels;
   - every `"op": "eq"` has "exactly" (or equivalent) in its cited text;
   - columns in `summary.csv` counting `unresolved` terms, and `unclassified` entries by `reason`, per program.

> [!IMPORTANT]
> **Task T14.** Add schema validation (steps 1–2) and the extra checks (step 3) to `check_results.py`.

---

## Your task list

Every **Task** box above, in one place. When you're done, tick the boxes (edit this file, or copy the list into Slack) and add a one-line note next to anything you skipped, changed, or disagreed with. That way we can check your work against this list instead of going back and forth.

Nobody expects all of this in a week. A suggested order: read Sections 1–5 with `examples/` open, until the structure makes sense (ask if it doesn't); then the taxonomy (T1, T3–T8, T11, T12, T13); then the prompt and pipeline (T9, T10); then the code (T2, T14); then a run (T15).

**The taxonomy (`constraint_taxonomy.md`)**

- [x] **T1.** Free-text filters replaced by `eligible_if`. *Done when:* no `filter` or `pool_rule` strings remain. (2.2) *Done. No `filter` or `pool_rule` left; `check_taxonomy.py` fails on them.*
- [x] **T3.** Vocabulary kept short; additions and misfits logged. *Done when:* `taxonomy_open_questions.md` exists and lists any new term and why. (2.2) *Done. One addition, "any course" as `{"level_min": 0}`, logged as Q7 in `taxonomy_open_questions.md`.*
- [x] **T4.** `unresolved` added, with its three rules and the history example. (2.2) *Done, with the history example and two more (adviser-selected, list-or-approved).*
- [x] **T5.** Normalizing paragraph says "a bare number means `min`; `eq` only for 'exactly'". *Done when:* no example uses `eq` without "exactly". (2.2) *Done. No example uses `eq`; both `check_taxonomy.py` and `check_results.py` reject `eq` without "exactly".*
- [x] **T6.** `thresholds` is a list; examples with both a course and a unit count encode both. (2.2) *Done. CS (4 courses, 16 units), Health track (2 courses, 8 units) and others encode both.*
- [x] **T7.** Names adopted (`threshold`, `eligible_if`, `count_by`), `pool` / `pool_rule` gone, or a note saying why not. (2.2) *Done. `threshold`, `eligible_if`, `count_by` adopted; `pool` and `pool_rule` gone.*
- [x] **T8.** `of_which` added, with an example at each level and the wording convention. (4) *Done. Examples on a leaf (Economics, Behavioral Economics, Philanthropy), a group (tracks) and the root (Religion, TAC/CSCI).*
- [x] **T11.** Out-of-scope items go to `unclassified` with a `reason` instead of being dropped. (5.4) *Done. Four reasons, with examples, in the taxonomy and the prompt.*
- [x] **T12.** Families re-mapped. (6) *Done. Section 6 of the old plan; Course Reuse `PROHIBITS` and restatements are notes now.*
- [x] **T13.** Taxonomy rewritten around the tree structure. *Done when:* every example validates against `requirement_schema.json`, and no old-format example remains. (2–6) *Done. 50 of 50 examples validate; no old-format example remains.*

**The prompt and pipeline**

- [x] **T9.** `run_classifier.py` numbers the lines; `source_lines` + `source_quote` replace `source_text`. (5.2) *Done. Lines are numbered `L021:`; `source_lines` + `source_quote` everywhere.*
- [x] **T10.** `prompt_v2.txt` written (v1 kept): new output template, plus the five instructions. (5.3) *Done. `docs/prompt_v2.txt`, v1 kept (`--prompt docs/prompt_v1.txt`).*

**The code**

- [x] **T2.** `is_eligible` written and tested on hand-picked courses. (2.2) *Done earlier (`eligibility.py`, tested in `test_taxonomy.py`).*
- [x] **T14.** `check_results.py` validates against the schema and runs the extra checks. *Done when:* every file in `examples/` passes, and a deliberately broken copy fails. (The schema file) *Done. All five `examples/` pass; seven deliberately broken copies each fail. Status is now set by the pipeline from `no_fit`, because the model kept marking any unclassified entry as partial.*

**The run**

- [x] **T15.** Re-run the 15 test files with `prompt_v2.txt`, then review. Start with: *Done. 15 of 15 pass `check_results.py`; golden cases right on the model's output; review notes in the README. Then the full 470-programme run.*
  
  - `102_economics_ba` and `183_public_policy_bs`: compare to `examples/`.
  - `162_occupational_therapy_bs`: pairs inside a choice.
  - `086_computer_science_bs`: nested choices; should have no `unresolved`.
  - `042_business_administration_bs`: prefix lists.
  - `124_history_ba`: likely some real `unresolved`.
  - `134_interdisciplinary_studies_ba`: should be mostly `unresolved`. If it isn't, the model is inventing pools.
  
  For every `unresolved`, ask: is this really unresolvable, or did the model take the easy way out? *Done when:* `summary.csv` shows every file passing the schema, and you've noted anything odd in `taxonomy_open_questions.md`.

---

## Coming in Phase 2

So you know what's deliberately *not* in this round:

- **Grade and GPA rules.** For now, record them in `unclassified` with reason `out_of_scope` (Section 5.4). Some of them should become real requirements, and we will come back to how.
- **The Manual Review family**, and how it relates to `unresolved`.
- **Human corrections.** A way for a person to fix or confirm an entry, and for that fix to survive when the pipeline is re-run next year.
- **Smaller items:** a standard form for course codes, so they match STARS; university-wide items that appear in program files (GE, the writing requirement, the 128-unit total); requirements that repeat every semester; and "per department" limits such as "no more than 12 units in any one department".
