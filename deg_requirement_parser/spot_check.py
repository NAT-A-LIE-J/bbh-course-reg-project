#!/usr/bin/env python3
"""
Build a human review sheet from classifier output (the tree format).

For each <out-dir>/<stem>.json, lists every anchored node with the catalogue
text its source_lines point to (expanded back into full text) next to the
encoding the model chose, plus a blank verdict column. The unclassified entries
come first, since a real requirement hiding there is the easiest mistake to
miss. Rows are sorted low confidence first.

Usage
    python spot_check.py --out-dir out_v2
    python spot_check.py --out-dir out_v2 --only 102_economics_ba
    python spot_check.py --out-dir out_v2 --low-only     # skip high-confidence rows

Writes <out-dir>/review_sheet.md. Mark each row OK / WRONG STRUCTURE /
WRONG DETAILS, then turn each wrong row into a new example in
constraint_taxonomy.md.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from check_results import FAMILIES, PROGRAMS_DIR, walk_nodes

HERE = Path(__file__).resolve().parent
CONF_ORDER = {"low": 0, "medium": 1, "high": 2}
TEXT_LIMIT = 700  # characters of cited text shown per row


def cell(text) -> str:
    """Make text safe inside a markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def expand(lines: list[str], ranges) -> str:
    parts = []
    for first, last in ranges or []:
        chunk = " ".join(l.strip() for l in lines[first - 1 : last] if l.strip() and l.strip() != "---")
        parts.append(f"L{first}-{last}: {chunk}" if first != last else f"L{first}: {chunk}")
    text = " … ".join(parts)
    return text if len(text) <= TEXT_LIMIT else text[:TEXT_LIMIT] + " …"


def encoding(node: dict) -> str:
    """The node without its citation fields, and with anchored children folded to their id."""
    def strip(n):
        if not isinstance(n, dict):
            return n
        out = {}
        for k, v in n.items():
            if k in ("source_lines", "source_quote", "description", "confidence", "note", "id"):
                continue
            if k in ("all_of", "from"):
                v = [f"<{c['id']}>" if isinstance(c, dict) and "id" in c else strip(c) for c in v]
            out[k] = v
        return out
    return json.dumps(strip(node), ensure_ascii=False)


def review_programme(path: Path, low_only: bool) -> tuple[list[str], Counter]:
    data = json.loads(path.read_text(encoding="utf-8"))
    src = PROGRAMS_DIR / f"{path.stem}.txt"
    lines = src.read_text(encoding="utf-8").split("\n") if src.exists() else []
    root = data.get("root") or {}
    anchored = [(p, n) for p, n, _ in walk_nodes(root, "root") if "source_lines" in n]
    families = Counter(n.get("family") for _, n, _ in walk_nodes(root, "root") if n.get("family") in FAMILIES)
    unclassified = data.get("unclassified") or []

    out = [
        f"## {data.get('program', path.stem)}",
        "",
        f"Status: **{data.get('status', '?')}**. {len(anchored)} anchored nodes, "
        f"{len(unclassified)} unclassified. " + ", ".join(f"{f}: {n}" for f, n in families.most_common()),
        "",
    ]
    if unclassified:
        out += ["**Unclassified** (should any of these be in the tree?)", "",
                "| reason | why | text | verdict |", "|---|---|---|---|"]
        for u in unclassified:
            out.append(f"| {cell(u.get('reason', ''))} | {cell(u.get('why', ''))} "
                       f"| {cell(expand(lines, u.get('source_lines')))} |  |")
        out.append("")

    checks = root.get("of_which") or []
    if checks:
        out += ["**Programme-wide checks**", ""]
        out += [f"- `{cell(json.dumps({k: v for k, v in c.items() if k not in ('source_lines', 'source_quote')}))}` "
                f"for: {cell(expand(lines, c.get('source_lines')))}" for c in checks]
        out.append("")

    rows = sorted(anchored, key=lambda pn: CONF_ORDER.get(pn[1].get("confidence"), -1))
    if low_only:
        rows = [pn for pn in rows if pn[1].get("confidence") != "high"]
    if rows:
        out += ["| id | conf | catalogue text | encoding | note | verdict |", "|---|---|---|---|---|---|"]
        for _, n in rows:
            out.append(f"| {cell(n.get('id', ''))} | {cell(n.get('confidence', ''))} "
                       f"| {cell(expand(lines, n.get('source_lines')))} | `{cell(encoding(n))}` "
                       f"| {cell(n.get('note') or '')} |  |")
        out.append("")
    return out, families


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="specific stems")
    ap.add_argument("--low-only", action="store_true", help="skip high-confidence rows")
    ap.add_argument("--out-dir", default="out", help="output folder to read (default: out)")
    args = ap.parse_args()
    out_dir = HERE / args.out_dir

    files = sorted(out_dir.glob("*.json"))
    if args.only:
        files = [p for p in files if p.stem in set(args.only)]
    if not files:
        raise SystemExit(f"No output JSON found in {out_dir}. Run run_classifier.py first.")

    body, totals = [], Counter()
    for path in files:
        try:
            lines, fams = review_programme(path, args.low_only)
        except (json.JSONDecodeError, AttributeError, TypeError) as exc:
            lines, fams = [f"## {path.stem}", "", f"Could not read: {exc}", ""], Counter()
        body += lines
        totals += fams

    header = [
        "# Classifier review sheet",
        "",
        f"{len(files)} programmes. Leaves: " + ", ".join(f"{f}: {n}" for f, n in totals.most_common()),
        "",
        "Verdicts: OK / WRONG STRUCTURE (wrong group, nesting or of_which) / WRONG DETAILS "
        "(a count, bound, pool or course is wrong). Anchored children are shown as <id>.",
        "",
    ]
    sheet = out_dir / "review_sheet.md"
    sheet.write_text("\n".join(header + body), encoding="utf-8")
    print(f"Wrote {sheet} ({len(files)} programmes)")


if __name__ == "__main__":
    main()
