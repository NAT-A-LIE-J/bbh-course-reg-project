#!/usr/bin/env python3
"""
Validate classifier output (the tree format) and write a summary CSV.

For each <out-dir>/<stem>.json it checks:

  Errors (the programme fails)
    - valid JSON that validates against requirement_schema.json
    - no old-format keys, every eligible_if evaluable by is_eligible, and every
      node convertible to the solver (the same checks check_taxonomy.py runs)
    - every source_lines range is inside the programme file, and its
      source_quote appears in the cited lines (catches wrong line numbers)
    - no two anchored nodes share an id
    - every "op": "eq" has "exactly" in its cited text
    - status agrees with the unclassified reasons (partial iff any no_fit)

  Warnings (worth a look, don't fail)
    - one specific_course under two different top-level nodes (a missed amendment)
    - two sibling count leaves whose eligible_if overlap (a missed of_which)
    - a node nested more than four levels deep

summary.csv has one row per programme: status, node counts by family,
unresolved terms, unclassified entries by reason, and the problem counts.

Usage
    python check_results.py --out-dir out_v2
    python check_results.py --out-dir out_v2 --verbose   # every problem and warning

Exits non-zero if any programme has an error, so it works as a gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

from check_taxonomy import check_object, load_schema, validators
from eligibility import UNKNOWN, is_eligible

REPO = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
PROGRAMS_DIR = (
    REPO
    / "catalogue_scraper"
    / "data"
    / "usc_undergrad_complete_catalogue_2026_2027"
    / "programs"
)

FAMILIES = ["specific_course", "count", "course_reuse", "sequencing", "manual_review"]
REASONS = ["no_fit", "out_of_scope", "university_level", "advisory"]
MAX_DEPTH = 4
ANCHOR_FIELDS = ("source_lines", "source_quote")
COURSE_IN_TEXT = re.compile(r"[A-Z]{2,5} [0-9]{3}[A-Za-z]{0,3}")


def norm(s: str) -> str:
    """Compare quotes loosely: case, whitespace and curly quotes don't matter."""
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def children(node: dict) -> list:
    return node.get("all_of") or node.get("from") or []


def walk_nodes(node: dict, path: str, depth: int = 0):
    """Yields (path, node, depth) for every node in the tree, root first."""
    yield path, node, depth
    key = "all_of" if "all_of" in node else "from"
    for i, child in enumerate(children(node)):
        if isinstance(child, dict):
            yield from walk_nodes(child, f"{path}/{key}/{i}", depth + 1)


def cited_objects(data: dict):
    """Every object that cites the catalogue: anchored nodes, checks, unclassified."""
    root = data.get("root") or {}
    for path, node, _ in walk_nodes(root, "root"):
        if "source_lines" in node:
            yield path, node
        for j, check in enumerate(node.get("of_which") or []):
            yield f"{path}/of_which/{j}", check
    for i, entry in enumerate(data.get("unclassified") or []):
        yield f"unclassified/{i}", entry


def cited_text(lines: list[str], ranges) -> str | None:
    """The cited lines joined, or None if a range falls outside the file."""
    out = []
    for first, last in ranges:
        if not (1 <= first <= last <= len(lines)):
            return None
        out += lines[first - 1 : last]
    return "\n".join(out)


def unresolved_terms(cond) -> int:
    if isinstance(cond, dict):
        return ("unresolved" in cond) + sum(unresolved_terms(v) for v in cond.values())
    if isinstance(cond, list):
        return sum(unresolved_terms(v) for v in cond)
    return 0


def courses_in(node: dict) -> set[str]:
    return {n["course"] for _, n, _ in walk_nodes(node, "") if n.get("family") == "specific_course"}


def probes(cond) -> list[str]:
    """Courses to test two eligible_if against: every course they name, plus a
    100-, 300- and 400-level course for every prefix they name."""
    text = json.dumps(cond)
    found = set(COURSE_IN_TEXT.findall(text))
    for prefixes in re.findall(r'"prefix": \[([^\]]*)\]', text):
        for p in re.findall(r'"([A-Z]{2,5})"', prefixes):
            found |= {f"{p} 150", f"{p} 350", f"{p} 450"}
    return sorted(found)


def overlap(a: dict, b: dict) -> str | None:
    """A course both conditions definitely accept, if there is one."""
    for course in probes({"a": a, "b": b}):
        if is_eligible(a, course) is True and is_eligible(b, course) is True:
            return course
    return None


def check_program(path: Path, vals: dict) -> tuple[dict, list[str], list[str]]:
    stem = path.stem
    row = {"file": stem, "parsed": False, "schema_ok": False, "status": "",
           "top_nodes": 0, **{f: 0 for f in FAMILIES}, "of_which": 0, "unresolved": 0,
           "unclassified": 0, **{f"unc_{r}": 0 for r in REASONS},
           "low_confidence": 0, "errors": 0, "warnings": 0}
    errors: list[str] = []
    warnings: list[str] = []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{stem}: invalid JSON ({exc})")
        row["errors"] = len(errors)
        return row, errors, warnings
    row["parsed"] = True

    # Schema, old keys, evaluable eligible_if, converts to the solver.
    res = check_object(data, vals, stem, expect="program")
    errors += [f"{stem}: {e}" for e in res.errors]
    row["schema_ok"] = not res.errors
    row["status"] = data.get("status", "")

    root = data.get("root") if isinstance(data.get("root"), dict) else {}
    top = [n for n in root.get("all_of", []) if isinstance(n, dict)]
    row["top_nodes"] = len(top)
    unclassified = [u for u in data.get("unclassified") or [] if isinstance(u, dict)]
    row["unclassified"] = len(unclassified)
    reasons = Counter(u.get("reason") for u in unclassified)
    for r in REASONS:
        row[f"unc_{r}"] = reasons.get(r, 0)

    # Counts over the tree.
    ids = Counter()
    for npath, node, depth in walk_nodes(root, "root"):
        fam = node.get("family")
        if fam in FAMILIES:
            row[fam] += 1
        row["of_which"] += len(node.get("of_which") or [])
        row["unresolved"] += unresolved_terms(node.get("eligible_if"))
        for check in node.get("of_which") or []:
            row["unresolved"] += unresolved_terms(check.get("eligible_if"))
        if node.get("confidence") == "low":
            row["low_confidence"] += 1
        if "id" in node:
            ids[node["id"]] += 1
        if depth > MAX_DEPTH:
            warnings.append(f"{stem}: {npath} is nested {depth} levels deep (more than {MAX_DEPTH})")

        # Sibling count leaves that accept the same course: usually a missed of_which.
        counts = [(i, c) for i, c in enumerate(children(node))
                  if isinstance(c, dict) and c.get("family") == "count" and isinstance(c.get("eligible_if"), dict)]
        for x in range(len(counts)):
            for y in range(x + 1, len(counts)):
                try:
                    hit = overlap(counts[x][1]["eligible_if"], counts[y][1]["eligible_if"])
                except ValueError:
                    hit = None  # malformed eligible_if is already a schema error
                if hit:
                    warnings.append(f"{stem}: {npath} children {counts[x][0]} and {counts[y][0]} "
                                    f"are count leaves that both accept {hit} (a missed of_which?)")

    for cid, n in ids.items():
        if n > 1:
            errors.append(f"{stem}: id '{cid}' is used by {n} anchored nodes")

    # The same specific_course under two top-level nodes: usually a missed amendment.
    seen: dict[str, str] = {}
    for node in top:
        label = node.get("id", "?")
        for course in courses_in(node):
            if course in seen and seen[course] != label:
                warnings.append(f"{stem}: {course} is required under both {seen[course]} and {label} "
                                f"(a missed amendment?)")
            seen.setdefault(course, label)

    status = data.get("status")
    if status == "partial" and not reasons.get("no_fit"):
        errors.append(f"{stem}: status is 'partial' but no unclassified entry has reason no_fit")
    if status == "ok" and reasons.get("no_fit"):
        errors.append(f"{stem}: status is 'ok' but {reasons['no_fit']} unclassified entries are no_fit")

    # Citations: inside the file, quote inside the cited lines, eq only with "exactly".
    src = PROGRAMS_DIR / f"{stem}.txt"
    if not src.exists():
        errors.append(f"{stem}: no programme file at {src}, so citations can't be checked")
    else:
        lines = src.read_text(encoding="utf-8").split("\n")
        for cpath, obj in cited_objects(data):
            ranges = obj.get("source_lines")
            if not isinstance(ranges, list) or not all(isinstance(r, list) and len(r) == 2 for r in ranges):
                continue  # a schema error already
            text = cited_text(lines, ranges)
            if text is None:
                errors.append(f"{stem}: {cpath} cites {ranges}, outside the file's {len(lines)} lines")
                continue
            quote = obj.get("source_quote") or ""
            if quote and norm(quote) not in norm(text):
                errors.append(f"{stem}: {cpath} quote {quote!r} is not in lines {ranges}")
            if '"op": "eq"' in json.dumps({k: v for k, v in obj.items() if k not in ("all_of", "from")}) \
                    and "exactly" not in text.lower():
                errors.append(f"{stem}: {cpath} uses \"op\": \"eq\" but its text doesn't say 'exactly'")

    row["errors"] = len(errors)
    row["warnings"] = len(warnings)
    return row, errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default="out", help="output folder to read (default: out)")
    ap.add_argument("--verbose", action="store_true", help="print every problem and warning")
    args = ap.parse_args()
    out_dir = HERE / args.out_dir

    outputs = sorted(p for p in out_dir.glob("*.json"))
    if not outputs:
        print(f"No .json files in {out_dir}. Run run_classifier.py first.")
        return 1

    vals = validators(load_schema())
    rows, all_errors, all_warnings = [], [], []
    for p in outputs:
        row, errors, warnings = check_program(p, vals)
        rows.append(row)
        all_errors += errors
        all_warnings += warnings

    summary = out_dir / "summary.csv"
    with summary.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print(f"{'file':<56} {'status':<8} {'nodes':>5} {'unres':>5} {'unc':>4} {'no_fit':>6} {'err':>4} {'warn':>4}")
    for r in rows:
        print(f"{r['file']:<56} {r['status']:<8} {r['top_nodes']:>5} {r['unresolved']:>5} "
              f"{r['unclassified']:>4} {r['unc_no_fit']:>6} {r['errors']:>4} {r['warnings']:>4}")

    passed = sum(1 for r in rows if not r["errors"])
    totals = {k: sum(r[k] for r in rows) for k in FAMILIES + ["of_which", "unresolved"] + [f"unc_{x}" for x in REASONS]}
    print(f"\n{passed} of {len(rows)} programmes pass.")
    print("Totals: " + ", ".join(f"{k} {v}" for k, v in totals.items()))

    for title, items in (("error", all_errors), ("warning", all_warnings)):
        if not items:
            continue
        print(f"\n{len(items)} {title}(s):")
        shown = items if args.verbose else items[:20]
        for item in shown:
            print(f"  - {item}")
        if len(items) > len(shown):
            print(f"  ... and {len(items) - len(shown)} more (use --verbose)")

    print(f"\nSummary written to {summary}")
    return 1 if all_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
