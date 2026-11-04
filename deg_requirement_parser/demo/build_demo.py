#!/usr/bin/env python3
"""
Build the data files for the catalogue demo page (demo/index.html).

The page itself has no degree logic. Every verdict it shows is computed here,
in Python, with the same solver check_bip.py uses (bip.py), and written out
as JSON. The students are made up (demo/students.json).

Writes demo/data/:
  index.json      coverage numbers, the programme list, which chunk holds each one
  p-NN.json       per programme: the catalogue lines, the tree, unclassified, review
  students.json   per showcase programme: each student's courses and the verdict
                  for every node of the tree

Usage
    python demo/build_demo.py                      # reads out_v2 via the combined file
    python demo/build_demo.py --check              # also compare golden students with golden/

Verdict for one node, given a student's courses:
  met      the node's subtree is satisfiable with placeholder leaves counted as NOT met
           and unresolved pools counted as NOT matching
  adviser  satisfiable only if the placeholder leaves (manual_review, sequencing,
           course_reuse) are met. Code can't check those.
  unknown  satisfiable only if an unresolved pool ("approved by your adviser") matches
  needed   not satisfiable even when everything unknown goes the student's way
Each node is solved on its own, but with the courses that other top-level
requirements need taken out of its pool, because one course fills one slot:
  - if the whole tree can be satisfied (possibly with adviser items), the pool for a
    top-level requirement is every course the solver's assignment doesn't put elsewhere;
  - if it can't, the pool leaves out courses named as specific_course leaves in the
    other top-level requirements (so CSCI 310 counts toward the CS core, not toward the
    CS electives).
That second rule is a heuristic for display only. The programme verdict is bip.solve
over the whole tree, unchanged, and the page says so when the two disagree.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARSER = HERE.parent
sys.path.insert(0, str(PARSER))

import bip  # noqa: E402
from check_results import PROGRAMS_DIR  # noqa: E402

CATALOGUE = PARSER / "catalogue" / "usc_degree_requirements_2026_2027.json"
SUMMARY = PARSER / "out_v2" / "summary.csv"
STUDENTS = HERE / "students.json"
OUT = HERE / "data"
CHUNK = 40
IMPOSSIBLE = {"family": "specific_course", "course": "ZZZZ 999"}  # a course no student has


def catalogue_lines(stem: str) -> list[str]:
    """Same numbering as run_classifier.number_lines: line 1 is the file's first line."""
    lines = (PROGRAMS_DIR / f"{stem}.txt").read_text(encoding="utf-8").split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


def children(node: dict) -> list[tuple[str, dict]]:
    key = "all_of" if "all_of" in node else ("from" if "from" in node else None)
    return [(f"/{key}/{i}", c) for i, c in enumerate(node[key])] if key else []


def walk(node: dict, path: str = "root"):
    yield path, node
    for suffix, child in children(node):
        yield from walk(child, path + suffix)


def with_path_ids(node: dict, path: str = "root") -> dict:
    """A copy where every node's id is its path, so the solver's assignment is keyed by path."""
    out = copy.deepcopy(node)
    for p, n in walk(out, path):
        n["id"] = p
    return out


def placeholders_failed(node: dict) -> dict:
    """A copy where every placeholder leaf becomes a course nobody has taken."""
    out = copy.deepcopy(node)

    def fix(n: dict) -> dict:
        if bip.node_kind(n) in bip.PLACEHOLDER_FAMILIES:
            return dict(IMPOSSIBLE)
        for key in ("all_of", "from"):
            if key in n:
                n[key] = [fix(c) for c in n[key]]
        return n

    return fix(out)


def without_of_which(node: dict) -> dict:
    out = dict(node)
    out.pop("of_which", None)
    return out


def feasible(node: dict, taken: dict[str, float], unknown_as: bool) -> bool:
    return bip._solve_once(node, taken, unknown_as) is not None


def node_verdict(node: dict, taken: dict[str, float]) -> str:
    if bip.node_kind(node) in bip.PLACEHOLDER_FAMILIES:
        return "adviser"
    if feasible(placeholders_failed(node), taken, unknown_as=False):
        return "met"
    if feasible(node, taken, unknown_as=False):
        return "adviser"
    if feasible(node, taken, unknown_as=True):
        return "unknown"
    return "needed"


def taken_courses(courses: list, default_units: float = 4) -> dict[str, float]:
    taken = {}
    for c in courses:
        code, units = (c[0], float(c[1])) if isinstance(c, list) else (c, float(default_units))
        taken[code] = units
    return taken


def evaluate(program: dict, courses: list, default_units: float) -> dict:
    taken = taken_courses(courses, default_units)
    root = program["root"]
    verdict = bip.solve(program, taken)  # the real programme verdict, unchanged
    tagged = with_path_ids(root)
    # Prefer the strict assignment: the lenient one may park a real elective in a free
    # slot and fill the elective from an "approved by your adviser" pool instead.
    solved = bip._solve_once(tagged, taken, unknown_as=False) or bip._solve_once(tagged, taken, unknown_as=True)
    assignment = {}
    if solved:
        for leaf, xs in solved.leaf_x.items():
            used = sorted(c for c, x in xs.items() if (x.value() or 0) > 0.5)
            if used:
                assignment[leaf] = used
    nodes, checks_failed = {}, {}
    tops = children(root) if "all_of" in root else []
    for suffix, top in tops:
        top_path = "root" + suffix
        if solved:
            elsewhere = {c for leaf, used in assignment.items()
                         if not (leaf == top_path or leaf.startswith(top_path + "/")) for c in used}
        else:
            mine = {n["course"] for _, n in walk(top) if n.get("family") == "specific_course"}
            elsewhere = {n["course"] for s2, other in tops if s2 != suffix
                         for _, n in walk(other) if n.get("family") == "specific_course"} - mine
        pool = {c: u for c, u in taken.items() if c not in elsewhere}
        for path, n in walk(top, top_path):
            nodes[path] = node_verdict(n, pool)
            if n.get("of_which") and nodes[path] != "met":
                checks_failed[path] = node_verdict(without_of_which(n), pool) != nodes[path]
    nodes["root"] = node_verdict(root, taken) if verdict.result != "fail" else "needed"
    if root.get("of_which") and nodes["root"] != "met":
        checks_failed["root"] = node_verdict(without_of_which(root), taken) != nodes["root"]
    return {
        "courses": [[c, u] for c, u in taken.items()],
        "result": verdict.result,
        "unmet": verdict.unmet,
        "nodes": nodes,
        "checks_failed": [p for p, failed in checks_failed.items() if failed],
        "assignment": assignment,
    }


def coverage(cat: dict) -> dict:
    rows = list(csv.DictReader(SUMMARY.open(encoding="utf-8")))
    progs = cat["programmes"]
    full = [p for p in progs if p["requirements"]["status"] == "ok"
            and not p["review"]["needs_data"] and not p["review"]["not_checked_by_code"]]
    return {
        "scraped": cat["counts"]["programmes_in_catalogue"],
        "included": cat["counts"]["included"],
        "not_included": cat["counts"]["not_included"],
        "fully_checkable": len(full),
        "partial": sum(1 for r in rows if r["status"] == "partial"),
        "with_unresolved": sum(1 for r in rows if int(r["unresolved"])),
        "unresolved_terms": sum(int(r["unresolved"]) for r in rows),
        "no_fit_sentences": sum(int(r["unc_no_fit"]) for r in rows),
        "with_placeholders": sum(1 for r in rows if int(r["course_reuse"]) + int(r["sequencing"])
                                 + int(r["manual_review"])),
        "model": cat["model"],
        "generated_at": cat["generated_at"],
        "run_started_at": next(csv.DictReader((PARSER / "out_v2" / "run_meta.csv").open(encoding="utf-8")))["started_at"],
        "not_included_stems": [x["stem"] for x in cat["not_included"]],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="compare golden students with golden/*.json")
    args = ap.parse_args()

    cat = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    by_stem = {p["stem"]: p for p in cat["programmes"]}
    students = json.loads(STUDENTS.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()

    index, chunks = [], {}
    for i, p in enumerate(cat["programmes"]):
        n = i // CHUNK
        r = p["requirements"]
        index.append({"stem": p["stem"], "name": p.get("name") or r["program"],
                      "credential": p.get("credential"), "status": r["status"], "chunk": n,
                      "showcase": p["stem"] in students["programmes"]})
        chunks.setdefault(n, {})[p["stem"]] = {
            "name": p.get("name") or r["program"],
            "url": p.get("catalogue_url"),
            "status": r["status"],
            "lines": catalogue_lines(p["stem"]),
            "root": r["root"],
            "unclassified": r["unclassified"],
            "review": p["review"],
        }
    for n, data in chunks.items():
        (OUT / f"p-{n:02d}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                                             encoding="utf-8")

    show, wrong = {}, 0
    for stem, people in students["programmes"].items():
        program = by_stem[stem]["requirements"]
        golden_path = PARSER / "golden" / f"{stem}.json"
        golden = json.loads(golden_path.read_text(encoding="utf-8")) if golden_path.exists() else {"cases": []}
        cases = {c["student"]: c for c in golden["cases"]}
        show[stem] = []
        for s in people:
            if "golden" in s:
                case = cases[s["golden"]]
                ev = evaluate(program, case["courses"], golden.get("default_units", 4))
                if args.check:
                    ok = ev["result"] == case["expect"] and (
                        "unmet" not in case or len(ev["unmet"]) == len(case["unmet"]))
                    wrong += not ok
                    print(f"{'ok  ' if ok else 'WRONG'} {stem} {s['name']}: {ev['result']} "
                          f"(golden: {case['expect']}), unmet {ev['unmet']}")
            else:
                ev = evaluate(program, s["courses"], 4)
                if args.check:
                    print(f"     {stem} {s['name']}: {ev['result']}, unmet {ev['unmet']}")
            show[stem].append({"name": s["name"], "summary": s["summary"],
                               "golden": s.get("golden"), **ev})

    (OUT / "index.json").write_text(json.dumps({"coverage": coverage(cat), "programmes": index},
                                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "students.json").write_text(json.dumps({"about": students["about"], "programmes": show},
                                                  ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = sum(f.stat().st_size for f in OUT.glob("*.json"))
    print(f"Wrote {len(list(OUT.glob('*.json')))} files to {OUT} ({size / 1e6:.1f} MB).")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
