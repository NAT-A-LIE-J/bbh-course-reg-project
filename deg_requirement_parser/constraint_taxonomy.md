# USC Degree-Requirement Taxonomy

Version 2026-11-03. The tree format from `FEEDBACK_phase1.md`. `requirement_schema.json` is the
contract: if this file and the schema disagree, the schema wins.

This file explains how to turn one programme's catalogue text into a tree of requirements. Each
section builds on the one before. Every example pairs a real catalogue sentence (quoted with `>`)
with its encoding.

---

## 1. How to read this

A programme is a **tree**. At the bottom are **leaves**, each one requirement of one kind (take
this course; take enough courses of this kind). Above them are **groups** that combine nodes
(all of these; at least N of these). A node can also carry **checks** (`of_which`): conditions on
the courses that node uses, which never claim courses of their own. The **root** is the whole
programme: an `all_of` of its top-level nodes.

| Term | Meaning |
|---|---|
| `specific_course` | A leaf: take this one course. |
| `count` | A leaf: take enough eligible courses to meet every threshold. |
| `eligible_if` | Which courses count, in a fixed vocabulary (Section 2.2). |
| `unresolved` | A condition the catalogue states but gives no way to check. |
| `thresholds` | A list. Each says what to add up (`count_by`: courses, units or departments), how to compare (`op`) and the number (`value`). |
| `all_of` | A group: every item is required. |
| `choose` / `from` | A group: at least `choose` of the items are required. |
| node | A leaf, an `all_of` of nodes, or a `choose` of nodes. |
| one-slot rule | Each course fills at most one slot in the whole programme. |
| `of_which` | Checks on the courses a node uses. Checks never claim courses. |
| root | The node for the whole programme. |
| anchored node | A node that cites the catalogue lines it encodes, with `source_lines`, `source_quote`, `id`, `description`, `confidence` and `note`. |
| `unclassified` | Catalogue text that is not encoded, with a `reason`. |

**Normalizing.**

- A bare number is a minimum. "Choose N", "complete N", "N units from", "at least N", "a minimum
  of N", "four courses" all mean `"op": "min"`. A student who takes more has still met it.
- "No more than N", "at most N", "a maximum of N", "only one" mean `"op": "max"`.
- `"op": "eq"` only when the catalogue says *exactly* N. This is rare.
- Numbers written as words are numbers: "four courses" is 4, "Twelve units" is 12.
- Active and passive voice mean the same thing.

**Course codes.** Copy each code as the catalogue prints it, including any suffix letters
(`MATH 118gx`, `PSYC 100Lg`, `PPD 497a`, `LAW 200w`), without trailing punctuation. The prefix is
2 to 5 capital letters and the number is three digits. The level of a course is its number:
`CSCI 103L` is level 103.

**When two shapes both fit.**

| The sentence... | Encode it as |
|---|---|
| names one course to take | `specific_course` |
| asks for courses of a kind, or N from a list | a `count` leaf |
| offers alternatives joined by "or" ("MATH 126 or 129") | `choose 1` over the alternatives |
| combines several requirements | `all_of`, or `choose` if only some are required |
| puts a condition on courses already counted ("of these", "of which") | an `of_which` check |
| allows a course to count twice, as an explicit exception | a `course_reuse` leaf |
| is about timing (before, after, within) | a `sequencing` leaf |
| is a real requirement code can't check from a course list | a `manual_review` leaf |
| restates that courses can't be double-counted | a `note`, no node |
| is a grade, GPA, residency or university-wide rule, or advice | `unclassified`, with a reason |

---

## 2. Leaves

Every leaf is an object with a `family`.

### 2.1 `specific_course`

> Required Courses, Lower-Division (4 units): ANTH 263g

```json
{"family": "specific_course", "course": "ANTH 263g"}
```

### 2.2 `count`

A `count` leaf has two fields: `eligible_if` (which courses count) and `thresholds` (how many).

**`eligible_if`** is built only from these terms:

| Term | Meaning | Example |
|---|---|---|
| `courses` | an explicit list of course codes | `{"courses": ["CSCI 201", "CSCI 270"]}` |
| `prefix` | the course's subject prefix is one of these | `{"prefix": ["CSCI"]}` |
| `level_min` / `level_max` | the course number is at least / at most this | `{"level_min": 300}` |
| `school` | the course is offered by this school | `{"school": "Dornsife"}` |
| `ge_category` | the course satisfies this GE category (`GE-A` to `GE-H`) | `{"ge_category": "GE-C"}` |
| `unresolved` | the catalogue gives no rule we can check | `{"unresolved": "department-approved offerings"}` |

combined with `{"all": [...]}` (every condition holds), `{"any": [...]}` (at least one holds)
and `{"not": {...}}` (the condition must not hold). Each term is its own object: write
`{"all": [{"prefix": ["MUSC"]}, {"level_min": 300}]}`, never `{"prefix": ["MUSC"], "level_min": 300}`.
`level_min` and `level_max` may share one object.

> Twelve units from any MUSC course at the 300 level or higher.

```json
{"family": "count",
 "eligible_if": {"all": [{"prefix": ["MUSC"]}, {"level_min": 300}]},
 "thresholds": [{"count_by": "units", "op": "min", "value": 12}]}
```

> Choose three courses from the following list: CSCI 201, CSCI 270, CSCI 310, CSCI 350.

```json
{"family": "count",
 "eligible_if": {"courses": ["CSCI 201", "CSCI 270", "CSCI 310", "CSCI 350"]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 3}]}
```

> 12 units of upper-division electives from the Marshall prefixes ACCT, BAEP, BUCO, DSO, FBE, FIM, MKT and MOR.

```json
{"family": "count",
 "eligible_if": {"all": [{"prefix": ["ACCT", "BAEP", "BUCO", "DSO", "FBE", "FIM", "MKT", "MOR"]}, {"level_min": 300}]},
 "thresholds": [{"count_by": "units", "op": "min", "value": 12}]}
```

> One additional elective in Anthropology is required to complete the major.

```json
{"family": "count",
 "eligible_if": {"prefix": ["ANTH"]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 1}]}
```

Free electives with no restriction ("any course", "free electives") are checkable: every course
counts. Write them as `{"level_min": 0}`, which every course passes. They are not `unresolved`.

> 4 units of free electives.

```json
{"family": "count",
 "eligible_if": {"level_min": 0},
 "thresholds": [{"count_by": "units", "op": "min", "value": 4}]}
```

A list printed under a heading plus a description of a pool ("any ANTH course, or one of the
following") is an `any` of the two:

> Any course in Anthropology, or one of the following: AMST 395m, ANTH 203g, ANTH 275.

```json
{"family": "count",
 "eligible_if": {"any": [{"prefix": ["ANTH"]}, {"courses": ["AMST 395m", "ANTH 203g", "ANTH 275"]}]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 1}]}
```

> No more than two total courses in the major may be taken outside the college.

A rule like this one is usually a check on courses picked elsewhere (Section 4). Its condition
is written with `not`:

```json
{"source_lines": [[30, 30]], "source_quote": "No more than two total courses in the major",
 "eligible_if": {"not": {"school": "Dornsife"}},
 "thresholds": [{"count_by": "courses", "op": "max", "value": 2}]}
```

**`thresholds`** is a list. Every threshold is measured over the same eligible courses, and all of
them must hold. When the catalogue gives both a course count and a unit count, encode both:

> Take at least four 300- or 400-level CSCI courses for a minimum of 16 units.

```json
{"family": "count",
 "eligible_if": {"all": [{"prefix": ["CSCI"]}, {"level_min": 300, "level_max": 499}]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 4},
                {"count_by": "units", "op": "min", "value": 16}]}
```

`count_by` is `courses`, `units`, or `departments` ("from at least three different departments";
the prefix stands in for the department).

**`unresolved`: what we can't check.** Some requirements don't define their pool. Don't invent a
list, and don't throw away what can be checked. Three rules:

1. Use `unresolved` only when the catalogue gives no rule. It is not a shortcut for "hard to encode".
2. Keep every checkable piece next to it, inside an `all`.
3. Quote or closely paraphrase the catalogue in the `unresolved` text.

> Students select four courses from the department's approved upper-division offerings in American, European, or global history.

```json
{"family": "count",
 "eligible_if": {"all": [
   {"prefix": ["HIST"]},
   {"level_min": 300},
   {"unresolved": "department-approved offerings in American, European, or global history"}]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 4}]}
```

> Two courses selected in consultation with the adviser.

```json
{"family": "count",
 "eligible_if": {"unresolved": "two courses selected in consultation with the adviser"},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 2}]}
```

When a list is printed and the catalogue also allows unlisted courses with approval, the pool is
the list *or* the unresolved part:

> Graduate courses in the subject area may be selected in consultation and with the approval of the adviser.

```json
{"family": "count",
 "eligible_if": {"any": [
   {"courses": ["BUCO 485", "IR 371", "PPD 318", "PPD 320"]},
   {"unresolved": "graduate courses in the subject area approved by the adviser"}]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 2}]}
```

---

## 3. Groups

### 3.1 `all_of` and `choose`

| Group | Written as | Meaning |
|---|---|---|
| All of | `{"all_of": [...]}` | every item is required |
| Choose | `{"choose": 2, "from": [...]}` | at least 2 of the items are required |

Items in a group can themselves be groups, so a node is a leaf, an `all_of` of nodes or a
`choose` of nodes. Three or four levels cover every programme we've seen.

> Complete all of the following: PHIL 350, PHIL 351, PHIL 352.

```json
{"all_of": [
  {"family": "specific_course", "course": "PHIL 350"},
  {"family": "specific_course", "course": "PHIL 351"},
  {"family": "specific_course", "course": "PHIL 352"}]}
```

> Complete BUAD 302 and BUAD 304, plus one of BUAD 306 or BUAD 307.

```json
{"all_of": [
  {"family": "specific_course", "course": "BUAD 302"},
  {"family": "specific_course", "course": "BUAD 304"},
  {"choose": 1, "from": [
    {"family": "specific_course", "course": "BUAD 306"},
    {"family": "specific_course", "course": "BUAD 307"}]}]}
```

> MATH 125, and MATH 126 or 129, and MATH 225 or 235, and MATH 226 or 229.

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
    {"family": "specific_course", "course": "MATH 229"}]}]}
```

A pair of courses that together form one option is an `all_of` inside the `choose`:

> OT 251 or EDUC 589 or (PSYC 336L with PSYC 337L).

```json
{"choose": 1, "from": [
  {"family": "specific_course", "course": "OT 251"},
  {"family": "specific_course", "course": "EDUC 589"},
  {"all_of": [
    {"family": "specific_course", "course": "PSYC 336L"},
    {"family": "specific_course", "course": "PSYC 337L"}]}]}
```

**`choose` or `count`?** Alternatives joined by "or" are a `choose` over `specific_course`
leaves ("MATH 126 or 129"). "N courses (or units) from a list" is a `count` leaf with
`{"courses": [...]}`. Use `choose` when an option is more than one course or is itself a group.

**Two layers of combining.** `all_of` / `choose` combine *nodes* ("take this and this"). `all` /
`any` / `not` inside `eligible_if` combine *conditions on one course* ("is this course CSCI and
at least 300-level?"). Never mix them up.

### 3.2 The one-slot rule

**Each course fills at most one slot in the whole programme**, unless the catalogue explicitly
says it may count twice. One course can't satisfy two different nodes, and each item in a
`choose` is used once.

So "elective" needs no special encoding. An elective means an *additional* course meeting some
condition; the courses already required are used by their own slots. Encode only which courses
are eligible:

> Students are required to take ECON 203, ECON 205, ECON 303, ECON 305, ECON 317, ECON 318 and four economics elective courses (300 level or above).

```json
{"all_of": [
  {"family": "specific_course", "course": "ECON 203"},
  {"family": "specific_course", "course": "ECON 205"},
  {"family": "specific_course", "course": "ECON 303"},
  {"family": "specific_course", "course": "ECON 305"},
  {"family": "specific_course", "course": "ECON 317"},
  {"family": "specific_course", "course": "ECON 318"},
  {"family": "count",
   "eligible_if": {"all": [{"prefix": ["ECON"]}, {"level_min": 300}]},
   "thresholds": [{"count_by": "courses", "op": "min", "value": 4}]}]}
```

Many sentences only restate this rule ("courses not used to satisfy these requirements may be
taken as electives", "it can not be double-counted as the cross-cutting course", "ANTH 470 can
be taken as either a course option OR as a Senior Capstone Course option"). Don't make nodes for
them; mention them in the `note` of the node they are about. When such a sentence names courses
that aren't on the elective list, add them to that list's `eligible_if`.

The university's rule for minors (at least 16 units unique to the minor) is handled by the tool.
Don't encode it.

---

## 4. `of_which`: checks on the courses a node uses

Every node uses some courses: a leaf uses the courses filling its slots, and a group uses
everything its children use. `of_which` is a list of **checks** on a node: *of the courses this
node uses, these conditions must hold*. A check only looks; it never claims a course. Each check
cites its own catalogue text with `source_lines` and `source_quote`. A check's `eligible_if` picks
out the courses it counts; leave it out to count all of the node's courses.

**Wording convention.** "Of the N…", "of which…", "of these…", "no more than N of them…" → a
check. "Plus…", "additional…", "and N more…" → a separate node. Anything a check can't express
goes in the `note`.

**On a leaf.**

> Of the four elective courses (300 level or above) a minimum of two must be economics courses at the 400 level or higher.

```json
{"family": "count",
 "eligible_if": {"all": [{"prefix": ["ECON"]}, {"level_min": 300}]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 4}],
 "of_which": [
   {"source_lines": [[21, 21]], "source_quote": "a minimum of two must be economics courses",
    "eligible_if": {"level_min": 400},
    "thresholds": [{"count_by": "courses", "op": "min", "value": 2}]}]}
```

> 28 units: seven 4-unit electives with no more than four courses (16 units) from either ECON or PSYC

```json
{"family": "count",
 "eligible_if": {"courses": ["ECON 318", "ECON 404", "ECON 405", "PSYC 305", "PSYC 326", "PSYC 355"]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 7},
                {"count_by": "units", "op": "min", "value": 28}],
 "of_which": [
   {"source_lines": [[56, 56]], "source_quote": "with no more than four courses (16 units) from",
    "eligible_if": {"prefix": ["ECON"]},
    "thresholds": [{"count_by": "courses", "op": "max", "value": 4}]},
   {"source_lines": [[56, 56]], "source_quote": "with no more than four courses (16 units) from",
    "eligible_if": {"prefix": ["PSYC"]},
    "thresholds": [{"count_by": "courses", "op": "max", "value": 4}]}]}
```

> Only one from the following: PPD 314, PPD 415, or PPD 344

```json
{"family": "count",
 "eligible_if": {"courses": ["BUCO 485", "IR 371", "PPD 318", "PPD 320", "PPD 314", "PPD 344", "PPD 415"]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 2},
                {"count_by": "units", "op": "min", "value": 8}],
 "of_which": [
   {"source_lines": [[101, 101]], "source_quote": "Only one from the following: PPD 314, PPD",
    "eligible_if": {"courses": ["PPD 314", "PPD 344", "PPD 415"]},
    "thresholds": [{"count_by": "courses", "op": "max", "value": 1}]}]}
```

Two categories with their own bounds inside one total are one `count` over both lists, with a
check per category:

> Law Electives (min 4 / max 8 units) plus Other Electives (min 4 / max 8 units), jointly totaling 12 units.

```json
{"family": "count",
 "eligible_if": {"courses": ["LAW 310w", "LAW 403", "LAW 404", "ECON 434", "POSC 444", "PPD 360"]},
 "thresholds": [{"count_by": "units", "op": "min", "value": 12}],
 "of_which": [
   {"source_lines": [[118, 118]], "source_quote": "Law Electives (min 4 / max 8 units)",
    "eligible_if": {"prefix": ["LAW"]},
    "thresholds": [{"count_by": "units", "op": "min", "value": 4},
                   {"count_by": "units", "op": "max", "value": 8}]},
   {"source_lines": [[118, 118]], "source_quote": "Other Electives (min 4 / max 8 units)",
    "eligible_if": {"not": {"prefix": ["LAW"]}},
    "thresholds": [{"count_by": "units", "op": "min", "value": 4},
                   {"count_by": "units", "op": "max", "value": 8}]}]}
```

"At least one from each of three groups" is a `count` over all three lists, with one check per
group:

> Choose four courses (16 units), at least one from each of the three thematic groups: Group A (AMST 200, AMST 201), Group B (HIST 255, HIST 256), Group C (SOCI 242, SOCI 250).

```json
{"family": "count",
 "eligible_if": {"courses": ["AMST 200", "AMST 201", "HIST 255", "HIST 256", "SOCI 242", "SOCI 250"]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 4},
                {"count_by": "units", "op": "min", "value": 16}],
 "of_which": [
   {"source_lines": [[40, 40]], "source_quote": "at least one from each of the three thematic",
    "eligible_if": {"courses": ["AMST 200", "AMST 201"]},
    "thresholds": [{"count_by": "courses", "op": "min", "value": 1}]},
   {"source_lines": [[40, 40]], "source_quote": "at least one from each of the three thematic",
    "eligible_if": {"courses": ["HIST 255", "HIST 256"]},
    "thresholds": [{"count_by": "courses", "op": "min", "value": 1}]},
   {"source_lines": [[40, 40]], "source_quote": "at least one from each of the three thematic",
    "eligible_if": {"courses": ["SOCI 242", "SOCI 250"]},
    "thresholds": [{"count_by": "courses", "op": "min", "value": 1}]}]}
```

> Electives must be drawn from at least three different departments.

```json
{"family": "count",
 "eligible_if": {"all": [{"prefix": ["AMST", "HIST", "SOCI", "POSC"]}, {"level_min": 300}]},
 "thresholds": [{"count_by": "courses", "op": "min", "value": 4}],
 "of_which": [
   {"source_lines": [[44, 44]], "source_quote": "Electives must be drawn from at least three",
    "thresholds": [{"count_by": "departments", "op": "min", "value": 3}]}]}
```

> No more than 2 of the 9 required courses may be at the 100/200 level.

```json
{"source_lines": [[36, 36]], "source_quote": "No more than 2 of the 9 required courses",
 "eligible_if": {"level_max": 299},
 "thresholds": [{"count_by": "courses", "op": "max", "value": 2}]}
```

**On a group.** A check on a `choose` of tracks applies to whichever track is used:

> Students select one track for degree emphasis; they take 28 units from the track selected.

```json
{"choose": 1,
 "from": [
   {"all_of": [
     {"family": "specific_course", "course": "PPD 325"},
     {"family": "specific_course", "course": "PPD 330"}]},
   {"all_of": [
     {"family": "specific_course", "course": "PPD 353"},
     {"family": "specific_course", "course": "PPD 371"}]}],
 "of_which": [
   {"source_lines": [[50, 50]], "source_quote": "they take 28 units from the track selected.",
    "thresholds": [{"count_by": "units", "op": "min", "value": 28}]}]}
```

**On the root.** A programme-wide rule is a check in the root's `of_which` (Section 5):

> The total unit requirement for the major is 32 units (at least 24 units must be upper-division).

```json
{"source_lines": [[21, 21]], "source_quote": "(at least 24 units must be upper-division).",
 "eligible_if": {"level_min": 300},
 "thresholds": [{"count_by": "units", "op": "min", "value": 24}]}
```

> Students may not complete more than one of TAC 115, TAC 116, CSCI 103L and CSCI 113x.

This is not about reuse. It is a root check:

```json
{"source_lines": [[64, 64]], "source_quote": "Students may not complete more than one of",
 "eligible_if": {"courses": ["TAC 115", "TAC 116", "CSCI 103L", "CSCI 113x"]},
 "thresholds": [{"count_by": "courses", "op": "max", "value": 1}]}
```

---

## 5. A whole programme

### 5.1 The root and anchored nodes

The output has a `root`: an `all_of` of the programme's top-level nodes, which may carry
programme-wide `of_which` checks. Every node directly under the root is **anchored**: it carries
`source_lines`, `source_quote`, `id`, `description`, `confidence` and `note`. Deeper nodes are
anchored too whenever they have their own heading or sentence (a track, a capstone).

**The heading rule.** Each heading block, or each standalone rule sentence, becomes one anchored
node, and anchored nodes nest the way the catalogue's headings nest. A track's heading is a node
inside the `choose` of tracks.

**Amendments.** When a later passage changes an earlier one (an asterisk pointing to a section
further down), encode the later passage *inside* the node it modifies and cite both places.
Otherwise two nodes demand the same course.

> Core Curriculum: … PPD 431 \*  (and further down) \*Capstone: This may be fulfilled by taking PPD 431 or PPD 497a, PPD 497b. Students wishing to enroll in PPD 497a, PPD 497b must have a 3.7 GPA in PPD courses and an overall 3.5 GPA.

```json
{"choose": 1,
 "from": [
   {"family": "specific_course", "course": "PPD 431"},
   {"all_of": [
     {"family": "specific_course", "course": "PPD 497a"},
     {"family": "specific_course", "course": "PPD 497b"},
     {"family": "manual_review", "kind": "GATE",
      "details": {"stage": "EMPHASIS_ENTRY", "basis": "NUMERIC_THRESHOLD",
                  "requires": ["3.7 GPA in PPD courses", "3.5 overall GPA"]}}]}],
 "id": "PP-BS-CAPSTONE",
 "source_lines": [[44, 44], [223, 225]],
 "source_quote": "*See alternate capstone options in Additional Requirements section,",
 "description": "PPD 431, or PPD 497a and 497b (which need a 3.7 PPD GPA and 3.5 overall).",
 "confidence": "high",
 "note": "Anchored to the Additional Requirements capstone passage, which amends the core's PPD 431."}
```

### 5.2 Citing the catalogue

The programme text arrives with every line numbered (`L021: Students are required...`).

- `source_lines` is a list of `[first, last]` line ranges, inclusive. Cite the heading line
  through the last line of its block. Text in two places is two ranges: `[[44, 44], [223, 225]]`.
- `source_quote` is the first few words of the cited text (up to about 10 words), copied
  exactly, without the `L021:` prefix. It must appear inside the cited lines.
- `id` is a short programme slug plus a name, in capitals and hyphens: `ECON-BA-ELECTIVES`.
  Every anchored node's `id` is unique within the programme.
- `confidence` is `high`, `medium` or `low`. Use `low` for a judgment call, and say why in `note`.
- `note` is `null` unless something needs flagging: a restated one-slot rule, part of a sentence
  a check can't express, an approval nobody can check.

### 5.3 Example: Economics (BA)

> L021: Students are required to take ECON 203, ECON 205, ECON 303, ECON 305, ECON 317, ECON 318 and four economics elective courses. Of the four elective courses (300 level or above) a minimum of two must be economics courses at the 400 level or higher. The remaining two economics courses must be approved by the department's director of undergraduate studies. A grade of C (2.0) or better is required for each of the core courses ECON 303, ECON 305, ECON 317 and ECON 318. MATH 118gx or MATH 125 is required for the major; students are advised to meet the requirement by their sophomore year. Majors are also required to take at least one two-unit course on computing chosen from TAC 101 or CSCI 101L.

```json
{"program": "Economics (BA)",
 "status": "ok",
 "root": {"all_of": [
   {"all_of": [
      {"family": "specific_course", "course": "ECON 203"},
      {"family": "specific_course", "course": "ECON 205"},
      {"family": "specific_course", "course": "ECON 303"},
      {"family": "specific_course", "course": "ECON 305"},
      {"family": "specific_course", "course": "ECON 317"},
      {"family": "specific_course", "course": "ECON 318"},
      {"family": "count",
       "eligible_if": {"all": [{"prefix": ["ECON"]}, {"level_min": 300}]},
       "thresholds": [{"count_by": "courses", "op": "min", "value": 4}],
       "of_which": [
         {"source_lines": [[21, 21]], "source_quote": "a minimum of two must be economics courses",
          "eligible_if": {"level_min": 400},
          "thresholds": [{"count_by": "courses", "op": "min", "value": 2}]}],
       "id": "ECON-BA-ELECTIVES",
       "source_lines": [[21, 21]],
       "source_quote": "Of the four elective courses (300 level or",
       "description": "Four ECON electives at 300+, of which at least two at 400+.",
       "confidence": "medium",
       "note": "Approval of the two non-400-level electives by the director of undergraduate studies cannot be checked; not encoded."}],
    "id": "ECON-BA-MAJOR",
    "source_lines": [[21, 21]],
    "source_quote": "Students are required to take ECON 203 ,",
    "description": "Six named ECON core courses plus four ECON electives.",
    "confidence": "high",
    "note": null},
   {"choose": 1,
    "from": [
      {"family": "specific_course", "course": "MATH 118gx"},
      {"family": "specific_course", "course": "MATH 125"}],
    "id": "ECON-BA-MATH",
    "source_lines": [[21, 21]],
    "source_quote": "MATH 118gx or MATH 125 is required for",
    "description": "MATH 118 or MATH 125.",
    "confidence": "high",
    "note": null},
   {"choose": 1,
    "from": [
      {"family": "specific_course", "course": "TAC 101"},
      {"family": "specific_course", "course": "CSCI 101L"}],
    "id": "ECON-BA-COMPUTING",
    "source_lines": [[21, 21]],
    "source_quote": "Majors are also required to take at least",
    "description": "TAC 101 or CSCI 101L.",
    "confidence": "high",
    "note": null}]},
 "unclassified": [
   {"source_lines": [[21, 21]], "source_quote": "A grade of C (2.0) or better is",
    "reason": "out_of_scope", "why": "Grade rule; Phase 2."},
   {"source_lines": [[21, 21]], "source_quote": "students are advised to meet the requirement",
    "reason": "advisory", "why": "Timing advice, not a requirement."}]}
```

### 5.4 Example: a programme-wide check (Religion, BA)

> L021: The department major requires REL 301 Introduction to the Study of Religion and REL 401 Seminar in Religious Studies. Further, students must take six additional courses from the list below. The total unit requirement for the major is 32 units (at least 24 units must be upper-division).

```json
{"program": "Religion (BA)",
 "status": "ok",
 "root": {"all_of": [
   {"all_of": [
      {"family": "specific_course", "course": "REL 301"},
      {"family": "specific_course", "course": "REL 401"}],
    "id": "REL-BA-CORE",
    "source_lines": [[21, 21]],
    "source_quote": "The department major requires REL 301 Introduction to",
    "description": "REL 301 and REL 401.",
    "confidence": "high",
    "note": null},
   {"family": "count",
    "eligible_if": {"courses": ["REL 111g", "REL 112g", "REL 114g", "REL 302", "REL 304", "REL 312"]},
    "thresholds": [{"count_by": "courses", "op": "min", "value": 6}],
    "id": "REL-BA-ADDITIONAL",
    "source_lines": [[21, 30]],
    "source_quote": "Further, students must take six additional courses",
    "description": "Six more courses from the list.",
    "confidence": "high",
    "note": null}],
  "of_which": [
    {"source_lines": [[21, 21]], "source_quote": "The total unit requirement for the major is",
     "thresholds": [{"count_by": "units", "op": "min", "value": 32}]},
    {"source_lines": [[21, 21]], "source_quote": "(at least 24 units must be upper-division).",
     "eligible_if": {"level_min": 300},
     "thresholds": [{"count_by": "units", "op": "min", "value": 24}]}]},
 "unclassified": []}
```

---

## 6. What isn't encoded: `unclassified`, with a reason

Never drop a requirement sentence silently. Anything not encoded in the tree goes in
`unclassified` with a `reason` and a short `why`:

| `reason` | Use for |
|---|---|
| `no_fit` | a requirement this taxonomy has no place for |
| `out_of_scope` | deliberately not encoded yet: grades, GPA, residency, pass/no pass, honors, progressive degrees, graduate programmes, substitution caps |
| `university_level` | university- or school-wide rules repeated on the programme page (GE, the writing requirement, the 128-unit total, college-wide unit rules), which come from STARS instead |
| `advisory` | recommendations, not requirements ("students are encouraged to…", "strongly recommended") |

`status` is `"partial"` if any entry has reason `no_fit`, `"failed"` if the text has no usable
requirements, otherwise `"ok"`. Contact details, faculty names and programme descriptions are not
requirements at all; leave them out entirely.

> A minimum grade of C, 2.0 (A = 4.0) is required in each course taken for the major.

```json
{"source_lines": [[27, 27]], "source_quote": "A minimum grade of C, 2.0 (A =",
 "reason": "out_of_scope", "why": "Grade rule; Phase 2."}
```

> Completion of the program requires a minimum of 128 units.

```json
{"source_lines": [[27, 27]], "source_quote": "Completion of the program requires a minimum of",
 "reason": "university_level", "why": "University-wide unit total; reused from STARS."}
```

> A minimum of 104 units applicable to the degree must be earned in the college's academic departments.

```json
{"source_lines": [[31, 31]], "source_quote": "A minimum of 104 units applicable to the",
 "reason": "university_level", "why": "College-wide unit rule repeated on the programme page."}
```

> No more than 12 units may be taken in any one USC department.

```json
{"source_lines": [[33, 33]], "source_quote": "No more than 12 units may be taken",
 "reason": "out_of_scope", "why": "Per-department limit; Phase 2."}
```

> No more than half of the elective units may come from one category.

```json
{"source_lines": [[35, 35]], "source_quote": "No more than half of the elective units",
 "reason": "no_fit", "why": "A share of a total; thresholds take absolute values only."}
```

> Students are encouraged to study abroad during their junior year.

```json
{"source_lines": [[38, 38]], "source_quote": "Students are encouraged to study abroad",
 "reason": "advisory", "why": "A recommendation, not a requirement."}
```

When one sentence carries both a requirement and an out-of-scope rule, encode the requirement in
the tree and put the rest in `unclassified`, both citing the same line.

---

## 7. Placeholder families (change in Phase 2)

Three more leaf families exist for requirements that aren't about picking courses. Their shape
will change in Phase 2, so keep them simple: `family`, a `kind`, and a `details` object with the
relevant facts. The solver treats them as met and reports them, so use them only for real
requirements.

### 7.1 `course_reuse`

Only *explicit exceptions* to the one-slot rule. `kind` is `DOUBLE_COUNT` or `UNIQUENESS_FLOOR`.

> Students may double-count no more than three courses from this degree to satisfy any other major.

```json
{"family": "course_reuse", "kind": "DOUBLE_COUNT",
 "details": {"max_courses": 3, "applies_to": "any other major"}}
```

> A minimum of four courses (16 units) must be unique to the minor.

```json
{"family": "course_reuse", "kind": "UNIQUENESS_FLOOR",
 "details": {"min_courses": 4, "min_units": 16, "applies_to": "the minor"}}
```

### 7.2 `sequencing`

Ordering in time. `kind` is `PREREQUISITE`, `BEFORE_MILESTONE` or `UNIT_WINDOW`.

> 200-level IR courses must be completed before 400-level IR courses are attempted.

```json
{"family": "sequencing", "kind": "PREREQUISITE",
 "details": {"before": "IR 200-level courses", "after": "IR 400-level courses"}}
```

> FBE 391 must be completed before declaring the Real Estate Finance emphasis.

```json
{"family": "sequencing", "kind": "BEFORE_MILESTONE",
 "details": {"before": ["FBE 391"], "milestone": "declare the Real Estate Finance emphasis"}}
```

> The four core courses must be completed within the student's first 32 units.

```json
{"family": "sequencing", "kind": "UNIT_WINDOW",
 "details": {"courses": "the four core courses", "within_units": 32}}
```

### 7.3 `manual_review`

Real requirements code can't check from a course list. `kind` is `GATE` (this programme's own
admission or entry process), `PROGRAM_RULE` (depends on the student's other programmes),
`DISCRETIONARY` (needs someone's approval), `NO_POOL` (no pool at all, not even a partial one),
`PROCEDURAL` (advising, deadlines) or `HOURS` (hours rather than courses). A pool with no list
is a `count` leaf with `unresolved` (Section 2.2), not `NO_POOL`.

> A performance audition is required of applicants to most degree programs.

```json
{"family": "manual_review", "kind": "GATE",
 "details": {"stage": "INITIAL_ADMISSION", "basis": "QUALITATIVE_REVIEW", "process": "performance audition"}}
```

> Admission to the major is by application, reviewed by a special admissions committee; interested students must have a GPA of 3.0 or above.

The GPA clause goes to `unclassified` (`out_of_scope`); the committee review is the gate:

```json
{"family": "manual_review", "kind": "GATE",
 "details": {"stage": "INITIAL_ADMISSION", "basis": "QUALITATIVE_REVIEW", "process": "committee-reviewed application"}}
```

> To enter this emphasis, a student must have sophomore standing and credit for FBE 391.

```json
{"family": "manual_review", "kind": "GATE",
 "details": {"stage": "EMPHASIS_ENTRY", "basis": "NUMERIC_THRESHOLD", "requires": ["sophomore standing", "FBE 391"]}}
```

> Not available to majors in the natural sciences.

```json
{"family": "manual_review", "kind": "PROGRAM_RULE",
 "details": {"direction": "EXCLUDES", "applies_to": "natural sciences majors"}}
```

> Biology majors must take CHEM 300L, CHEM 426 and CHEM 453 rather than the alternate options.

```json
{"family": "manual_review", "kind": "PROGRAM_RULE",
 "details": {"direction": "ROUTES", "applies_to": "Biology majors", "courses": ["CHEM 300L", "CHEM 426", "CHEM 453"]}}
```

> This degree cannot be combined as an additional major in business administration.

```json
{"family": "manual_review", "kind": "PROGRAM_RULE",
 "details": {"direction": "COMBINATION", "applies_to": "business administration majors", "effect": "cannot be combined"}}
```

> A graduate-level course may substitute for an upper-division elective with permission of the co-directors.

```json
{"family": "manual_review", "kind": "DISCRETIONARY",
 "details": {"action": "SUBSTITUTE", "approver": "co-directors"}}
```

> Students are required to meet with an academic adviser once each semester through graduation.

```json
{"family": "manual_review", "kind": "PROCEDURAL",
 "details": {"procedure": "ADVISING"}}
```

> Public Policy majors are required to complete 140 hours of internship by enrolling in PPD 301 or the Washington, D.C., Semester internship.

```json
{"family": "manual_review", "kind": "HOURS",
 "details": {"min_hours": 140, "setting": "internship via PPD 301 or the Washington, D.C., Semester"}}
```
