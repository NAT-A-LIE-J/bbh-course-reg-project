#!/usr/bin/env python3
"""
Check that requirement JSON can drive the BIP solver, and gives the right answers.

For every program with a golden file in golden/:

  1. Audit. Convert the JSON to BIP constraints and list anything that didn't
     convert: LOST (placeholder families, keys the converter doesn't read),
     "needs data" (unresolved / school / ge_category), and unclassified
     entries, which sit outside the tree by design.
  2. Golden cases. Each case is a hand-made student with a known answer. The
     solver must reach the same verdict (pass / fail / unknown) and, where the
     case lists them, find the same unmet top-level requirements. The unmet ids
     are the ones in examples/, so against model output (which names its own
     ids) only the number of unmet requirements is compared.

Usage
    python check_bip.py                        # programs in examples/
    python check_bip.py --program-dir out_v2   # the model's output, same golden cases
    python check_bip.py --only 102_economics_ba
    python check_bip.py --verbose              # show every audit line and each pass's course assignment

Exits non-zero if any golden case gets the wrong answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import bip

HERE = Path(__file__).resolve().parent
GOLDEN_DIR = HERE / "golden"


def taken_courses(case: dict, default_units: float) -> dict[str, float]:
    """A course is "ECON 203" (default units) or ["MEDS 220", 2]."""
    taken = {}
    for entry in case["courses"]:
        code, units = (entry, default_units) if isinstance(entry, str) else entry
        taken[code] = units
    return taken


def check_program(golden_path: Path, program_dir: Path, verbose: bool) -> tuple[int, int]:
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    stem = golden["program"]
    program_path = program_dir / f"{stem}.json"
    print(f"== {stem}")
    if not program_path.exists():
        print(f"   no {program_path.relative_to(HERE)}, skipped\n")
        return 0, 0
    program = json.loads(program_path.read_text(encoding="utf-8"))

    items = bip.audit(program)
    counts = Counter(i.status for i in items)
    print("   audit: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    for i in items:
        if verbose or i.status in ("LOST", "needs data"):
            extra = f" ({i.detail})" if i.detail else ""
            print(f"     {i.status:<12} {i.what}{extra}")

    ids_comparable = program_dir.resolve() == (HERE / "examples").resolve()
    passed = failed = 0
    for case in golden["cases"]:
        verdict = bip.solve(program, taken_courses(case, golden.get("default_units", 4)))
        problems = []
        if verdict.result != case["expect"]:
            problems.append(f"expected {case['expect']}, got {verdict.result}")
        if "unmet" in case:
            if ids_comparable and sorted(verdict.unmet) != sorted(case["unmet"]):
                problems.append(f"expected unmet {case['unmet']}, got {verdict.unmet}")
            elif not ids_comparable and len(verdict.unmet) != len(case["unmet"]):
                problems.append(f"expected {len(case['unmet'])} unmet ({case['unmet']} in examples/), "
                                f"got {verdict.unmet}")
        mark = "ok  " if not problems else "FAIL"
        unmet = f", unmet {verdict.unmet}" if verdict.unmet else ""
        print(f"   {mark} {case['student']}: {verdict.result}{unmet}")
        for p in problems:
            print(f"          - {p}   [{case['why']}]")
        if verbose and verdict.assignment:
            for leaf, courses in verdict.assignment.items():
                print(f"          {leaf}: {', '.join(courses)}")
        passed += not problems
        failed += bool(problems)
    print()
    return passed, failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--program-dir", default="examples", help="folder of program JSON (default: examples)")
    ap.add_argument("--only", nargs="*", help="specific stems")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    goldens = sorted(GOLDEN_DIR.glob("*.json"))
    if args.only:
        goldens = [g for g in goldens if g.stem in set(args.only)]
    if not goldens:
        print(f"No golden files in {GOLDEN_DIR}", file=sys.stderr)
        return 1

    total_pass = total_fail = 0
    for g in goldens:
        p, f = check_program(g, HERE / args.program_dir, args.verbose)
        total_pass += p
        total_fail += f
    print(f"{total_pass} of {total_pass + total_fail} golden cases right, {total_fail} wrong.")
    return 1 if total_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
