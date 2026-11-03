#!/usr/bin/env python3
"""
Classify USC degree-requirement text into constraint records.

Reads one scraped programme .txt, numbers its lines, fills docs/prompt_v2.txt
with the taxonomy and the numbered text, calls the Claude API, and writes the
raw response plus the parsed JSON to out/. The model cites requirements by line
number (source_lines), so the numbering here must match the file as scraped.

Usage
    export ANTHROPIC_API_KEY=...
    python run_classifier.py --limit 1          # one file, prove it works
    python run_classifier.py                    # the full 15-file test set
    python run_classifier.py --dry-run          # build prompts, call nothing

Run --dry-run first. It writes the exact prompt to out/ so you can read what the
model will actually receive before spending anything.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# --- Paths -------------------------------------------------------------------
# Francis's scraper folder is still named catalogue_scraper. It is due to be
# renamed to degree_requirements_scraper. Keep that path here, in one place.

REPO = Path(__file__).resolve().parent.parent
PROGRAMS_DIR = (
    REPO
    / "catalogue_scraper"
    / "data"
    / "usc_undergrad_complete_catalogue_2026_2027"
    / "programs"
)
PROMPT_PATH = REPO / "docs" / "prompt_v2.txt"  # --prompt docs/prompt_v1.txt for the old format
TAXONOMY_PATH = Path(__file__).resolve().parent / "constraint_taxonomy.md"
HERE = Path(__file__).resolve().parent

# --- Model and budget --------------------------------------------------------
# Confirm the model id against your console before a real run:
#   python run_classifier.py --list-models
DEFAULT_MODEL = "claude-sonnet-5"
# Newer models (Sonnet 5, Opus 5) think before answering, and that thinking
# counts toward this limit. 8000 was too small: long programmes ran out before
# the JSON was written. Override with --max-tokens.
DEFAULT_MAX_TOKENS = 20000
# Non-streaming requests error out above this (the API requires streaming for
# calls that may run long). We don't stream, so this is the practical ceiling
# for --max-tokens and for the truncation retry in call_api.
NON_STREAMING_MAX_TOKENS = 21000

# Sonnet 5, Opus 5 and Fable 5.1 think by default at "high" effort. For this
# extraction task that thinking can use 15,000+ tokens and crowd out the JSON.
# --effort (default low) and --no-thinking control it. Other models ignore both.
THINKING_MODELS = ("claude-sonnet-5", "claude-opus-5", "claude-fable-5")
DEFAULT_EFFORT = "low"


def thinking_options(model: str, effort: str, no_thinking: bool) -> dict:
    if not model.startswith(THINKING_MODELS):
        return {}
    body = {"output_config": {"effort": effort}}
    if no_thinking:
        body["thinking"] = {"type": "disabled"}
    return {"extra_body": body}

# Dollars per million tokens, (input, output), per model. This only drives the
# local cost printout and the --budget guard, not billing. Source:
# https://platform.claude.com/docs/en/models/overview (checked 2026-09-15).
# A model not listed here needs --price-in and --price-out on the command line.
MODEL_PRICES = {
    "claude-fable-5-1": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
}


# Prompt caching bills cached input separately from ordinary input, as multiples
# of the base input price: an ephemeral (5-minute) cache write at 1.25x, a cache
# hit at 0.1x. Those tokens do NOT appear in usage.input_tokens, so a cost
# calculated from input_tokens alone undercounts every cached call.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10


def usage_cost(usage, price_in: float, price_out: float) -> tuple[float, int, int]:
    """Returns (cost, cache_read_tokens, cache_write_tokens) for one response."""
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    billable_in = (
        usage.input_tokens
        + cache_write * CACHE_WRITE_MULTIPLIER
        + cache_read * CACHE_READ_MULTIPLIER
    )
    cost = billable_in / 1e6 * price_in + usage.output_tokens / 1e6 * price_out
    return cost, cache_read, cache_write


def model_prices(model: str) -> tuple[float, float] | None:
    """Exact id first, then the longest listed id that prefixes it (dated ids)."""
    if model in MODEL_PRICES:
        return MODEL_PRICES[model]
    matches = [k for k in MODEL_PRICES if model.startswith(k)]
    return MODEL_PRICES[max(matches, key=len)] if matches else None

# The 15 programmes named in docs/catalogue-classifier-brief.md.
TEST_SET = [
    "025_astronomy_ba",
    "042_business_administration_bs",
    "079_cognitive_science_ba",
    "086_computer_science_bs",
    "102_economics_ba",
    "120_global_health_studies_bs",
    "124_history_ba",
    "134_interdisciplinary_studies_ba",
    "141_journalism_ba",
    "162_occupational_therapy_bs",
    "169_performance_violin_viola_violoncello_double_bass_or_bm",
    "183_public_policy_bs",
    "192_social_work_bsw",
    "399_natural_science_minor",
    "458_statistics_minor",
]

DEGREE_WORDS = {
    "ba": "BA", "bs": "BS", "bfa": "BFA", "bm": "BM", "barch": "BArch",
    "bsw": "BSW", "minor": "Minor", "bse": "BSE",
}


def program_name(stem: str, text: str) -> str:
    """The scraper writes "Program Name: Economics (BA)" on the first line; use it.
    Falls back to the filename for a file without that header."""
    m = re.match(r"Program Name:\s*(.+)", text)
    return m.group(1).strip() if m else program_name_from_stem(stem)


def number_lines(text: str) -> str:
    """'L001: first line' and so on, so the model can cite source_lines. Line 1 is
    the file's first line, which is what check_results.py and spot_check.py count."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    width = max(3, len(str(len(lines))))
    return "\n".join(f"L{n:0{width}d}: {line}" for n, line in enumerate(lines, 1))


def program_name_from_stem(stem: str) -> str:
    """025_astronomy_ba -> 'Astronomy BA'. Only used when the file has no header."""
    parts = stem.split("_")[1:]  # drop the leading number
    if not parts:
        return stem
    if parts[-1] in DEGREE_WORDS:
        degree = DEGREE_WORDS[parts[-1]]
        words = parts[:-1]
    else:
        degree = ""
        words = parts
    title = " ".join(w.capitalize() for w in words)
    return f"{title} {degree}".strip()


PROMPT_PLACEHOLDERS = ["{{TAXONOMY}}", "{{PROGRAM_NAME}}", "{{REQUIREMENTS}}"]


def require_placeholders(template: str) -> None:
    missing = [p for p in PROMPT_PLACEHOLDERS if p not in template]
    if missing:
        raise SystemExit(
            f"{PROMPT_PATH} is missing placeholder(s): {', '.join(missing)}.\n"
            "Open the file and check the exact spelling, then fix `required` here."
        )


def build_prompt(template: str, taxonomy: str, name: str, requirements: str) -> str:
    require_placeholders(template)
    return (
        template.replace("{{TAXONOMY}}", taxonomy)
        .replace("{{PROGRAM_NAME}}", name)
        .replace("{{REQUIREMENTS}}", requirements)
    )


def split_template(template: str) -> tuple[str, str]:
    """Split the template at {{TAXONOMY}}: everything before it plus the taxonomy
    is identical on every call and worth caching; PROGRAM_NAME/REQUIREMENTS are not."""
    require_placeholders(template)
    marker = "{{TAXONOMY}}"
    idx = template.index(marker)
    return template[:idx], template[idx + len(marker):]


def build_cached_blocks(cached_head: str, tail_template: str, name: str, requirements: str) -> list[dict]:
    tail = tail_template.replace("{{PROGRAM_NAME}}", name).replace("{{REQUIREMENTS}}", requirements)
    return [
        {"type": "text", "text": cached_head, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": tail},
    ]


def extract_json(text: str):
    """Pull the JSON object out of a response that may be fenced or padded."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidate = fence.group(1) if fence else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in response")
    return json.loads(candidate[start : end + 1])


def call_api(client, model: str, content, max_tokens: int, extra: dict, attempts: int = 4):
    """Returns (response, retries) where retries counts transient-error retries.

    `content` is either a plain prompt string or a list of content blocks (used to
    mark part of the prompt cacheable). No console output here: under concurrency
    several stems retry at once, and per-attempt prints from different threads
    would interleave. Retry counts surface in the caller's one-line summary instead.
    """
    delay = 4
    retries = 0
    for attempt in range(1, attempts + 1):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": content}],
                **extra,
            )
            return resp, retries
        except Exception as exc:  # noqa: BLE001
            transient = any(
                s in type(exc).__name__.lower() or s in str(exc).lower()
                for s in ("overloaded", "rate", "timeout", "connection", "529", "500")
            )
            if attempt == attempts or not transient:
                raise
            retries += 1
            time.sleep(delay)
            delay *= 2


def format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def make_row(stem: str, model: str, effort: str, elapsed: float, retries: int, chars_in: int,
             stop_reason: str, in_tokens: int = 0, out_tokens: int = 0, cost: float = 0.0,
             cache_read: int = 0, cache_write: int = 0) -> dict:
    return {
        "stem": stem,
        "model": model,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "cost_usd": round(cost, 4),
        "stop_reason": stop_reason,
        "effort": effort,
        "seconds": round(elapsed, 1),
        "retries": retries,
        "chars_in": chars_in,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_write,
    }


def process_stem(i: int, total: int, stem: str, name: str, requirements: str, client, args,
                  price_in: float, price_out: float, extra: dict, effort_label: str,
                  cached_head: str, tail_template: str, out_dir: Path, out_label: str,
                  budget_lock: threading.Lock, budget_state: dict) -> dict | None:
    """Runs in a worker thread. Returns a result dict, or None if skipped because
    an earlier-finishing stem already pushed spend over budget."""
    with budget_lock:
        if budget_state["stop"]:
            return None

    content = build_cached_blocks(cached_head, tail_template, name, requirements)
    chars_in = len(requirements)
    t0 = time.perf_counter()
    try:
        resp, retries = call_api(client, args.model, content, args.max_tokens, extra)
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        row = make_row(stem, args.model, effort_label, elapsed, 0, chars_in, "error")
        line = f"[{i}/{total}] {stem}: API ERROR after {elapsed:.1f}s: {type(exc).__name__}: {exc}"
        return {"row": row, "line": line, "failure": True, "cost": 0.0}
    elapsed = time.perf_counter() - t0
    max_tokens_used = args.max_tokens
    note_suffix = ""
    # A truncated first attempt is still billed, so its cost carries forward.
    sunk_cost = 0.0

    # A max_tokens stop is a "successful" response as far as the API is concerned,
    # so call_api's transient-error retry never catches it. Retry once, with a
    # bigger budget, before giving up on the programme.
    if resp.stop_reason == "max_tokens":
        retry_budget = min(args.max_tokens * 2, NON_STREAMING_MAX_TOKENS)
        if retry_budget > args.max_tokens:
            note_suffix = f", retried at {retry_budget:,}"
            sunk_cost = usage_cost(resp.usage, price_in, price_out)[0]
            t1 = time.perf_counter()
            try:
                resp, more_retries = call_api(client, args.model, content, retry_budget, extra)
            except Exception as exc:  # noqa: BLE001
                elapsed += time.perf_counter() - t1
                row = make_row(stem, args.model, effort_label, elapsed, retries + 1, chars_in,
                               "error", cost=sunk_cost)
                line = (f"[{i}/{total}] {stem}: API ERROR on truncation retry after {elapsed:.1f}s: "
                        f"{type(exc).__name__}: {exc}")
                return {"row": row, "line": line, "failure": True, "cost": sunk_cost}
            elapsed += time.perf_counter() - t1
            retries += more_retries + 1
            max_tokens_used = retry_budget
        else:
            note_suffix = f", at the {NON_STREAMING_MAX_TOKENS:,}-token ceiling, not retried"

    text = "".join(block.text for block in resp.content if block.type == "text")
    cost, cache_read, cache_write = usage_cost(resp.usage, price_in, price_out)
    cost += sunk_cost

    with budget_lock:
        budget_state["spent"] += cost
        if budget_state["spent"] >= args.budget:
            budget_state["stop"] = True

    if resp.stop_reason == "max_tokens":
        (out_dir / f"{stem}.truncated.txt").write_text(text, encoding="utf-8")
        row = make_row(stem, args.model, effort_label, elapsed, retries, chars_in, resp.stop_reason,
                        resp.usage.input_tokens, resp.usage.output_tokens, cost, cache_read, cache_write)
        line = (f"[{i}/{total}] {stem}: TRUNCATED again at {max_tokens_used:,} tokens{note_suffix}, "
                f"{elapsed:.1f}s, ${cost:.3f}. Raw kept at {out_label}/{stem}.truncated.txt")
        return {"row": row, "line": line, "failure": True, "cost": cost}

    (out_dir / f"{stem}.response.txt").write_text(text, encoding="utf-8")
    json_path = out_dir / f"{stem}.json"
    try:
        data = extract_json(text)
    except Exception as exc:  # noqa: BLE001
        note = f"UNPARSEABLE: {exc}. Raw kept at {out_label}/{stem}.response.txt"
        failure = True
    else:
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        n = len((data.get("root") or {}).get("all_of", []))
        u = len(data.get("unclassified", []))
        note = f"ok: {n} top-level nodes, {u} unclassified, status={data.get('status')}"
        failure = False

    if cache_read:
        cache_note = f", cache hit {cache_read:,}"
    elif cache_write:
        cache_note = f", cache write {cache_write:,}"
    else:
        cache_note = ", uncached"
    line = f"[{i}/{total}] {stem}: {note}{note_suffix}, {elapsed:.1f}s, ${cost:.3f}{cache_note}"
    row = make_row(stem, args.model, effort_label, elapsed, retries, chars_in, resp.stop_reason,
                    resp.usage.input_tokens, resp.usage.output_tokens, cost, cache_read, cache_write)
    return {"row": row, "line": line, "failure": failure, "cost": cost}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="only the first N programmes")
    ap.add_argument("--only", nargs="*", help="specific stems, e.g. 025_astronomy_ba")
    ap.add_argument("--all", action="store_true", help="every programme, not just the 15 (costs real money)")
    ap.add_argument("--test-set", help="text file of stems, one per line (see make_test_set.py); "
                    "overrides the built-in TEST_SET, but --only wins over this")
    ap.add_argument("--dry-run", action="store_true", help="write prompts, call nothing")
    ap.add_argument("--force", action="store_true", help="redo programmes that already have output")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--budget", type=float, default=50.0, help="stop before exceeding this many dollars")
    ap.add_argument("--list-models", action="store_true", help="print available model ids and exit")
    ap.add_argument("--out-dir", default="out",
                    help="output folder inside deg_requirement_parser, e.g. out_sonnet5 (default: out)")
    ap.add_argument("--effort", default=DEFAULT_EFFORT, choices=["low", "medium", "high"],
                    help="thinking effort for Sonnet 5 / Opus 5 / Fable 5.1 (default: low)")
    ap.add_argument("--no-thinking", action="store_true",
                    help="turn thinking off entirely on Sonnet 5 / Opus 5 / Fable 5.1")
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                    help=f"output token budget per call (default: {DEFAULT_MAX_TOKENS})")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="parallel API calls; these are I/O bound so threads, not processes (default: 4)")
    ap.add_argument("--price-in", type=float, help="input $/million tokens, for a model not in MODEL_PRICES")
    ap.add_argument("--price-out", type=float, help="output $/million tokens, for a model not in MODEL_PRICES")
    ap.add_argument("--prompt", help=f"prompt template (default: {PROMPT_PATH.relative_to(REPO)})")
    args = ap.parse_args()
    prompt_path = (REPO / args.prompt) if args.prompt else PROMPT_PATH

    if args.list_models:
        from anthropic import Anthropic

        for m in Anthropic().models.list().data:
            print(m.id)
        return 0

    for path in (prompt_path, TAXONOMY_PATH):
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            return 1
    if not PROGRAMS_DIR.is_dir():
        print(f"missing programmes folder: {PROGRAMS_DIR}", file=sys.stderr)
        print("Has catalogue_scraper been renamed? Update PROGRAMS_DIR.", file=sys.stderr)
        return 1

    out_dir = HERE / args.out_dir
    out_label = args.out_dir.rstrip("/")

    prices = model_prices(args.model)
    if args.price_in is not None and args.price_out is not None:
        prices = (args.price_in, args.price_out)
    if prices is None and not args.dry_run:
        print(f"No price known for model '{args.model}'.", file=sys.stderr)
        print("Add it to MODEL_PRICES or pass --price-in and --price-out.", file=sys.stderr)
        return 1
    price_in, price_out = prices or (0.0, 0.0)
    if not args.dry_run:
        print(f"Model {args.model} at ${price_in:g} in / ${price_out:g} out per million tokens. "
              f"Output folder: {out_label}/\n")

    extra = thinking_options(args.model, args.effort, args.no_thinking)
    if extra and not args.dry_run:
        mode = "off" if args.no_thinking else f"on, effort {args.effort}"
        print(f"Thinking: {mode}\n")

    template = prompt_path.read_text(encoding="utf-8")
    taxonomy = TAXONOMY_PATH.read_text(encoding="utf-8")
    head_template, tail_template = split_template(template)
    cached_head = head_template + taxonomy

    if args.only:
        stems = args.only
    elif args.test_set:
        test_set_path = Path(args.test_set)
        if not test_set_path.exists():
            print(f"missing: {test_set_path}", file=sys.stderr)
            return 1
        stems = [
            line.strip() for line in test_set_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    elif args.all:
        stems = sorted(p.stem for p in PROGRAMS_DIR.glob("*.txt"))
    else:
        stems = TEST_SET
    if args.limit:
        stems = stems[: args.limit]

    out_dir.mkdir(parents=True, exist_ok=True)

    client = None
    if not args.dry_run:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set. export it first.", file=sys.stderr)
            return 1
        from anthropic import Anthropic

        client = Anthropic()

    rows = []
    failures = 0
    effort_label = "" if not extra else ("no-thinking" if args.no_thinking else args.effort)
    run_started_at = datetime.now().astimezone()
    run_t0 = time.perf_counter()

    # Pass 1: skip/dry-run decisions are cheap and order-sensitive for their own
    # console lines, so they stay a plain sequential loop. Only calls that will
    # actually hit the API go into to_process, for the concurrent pass below.
    to_process = []
    for i, stem in enumerate(stems, 1):
        src = PROGRAMS_DIR / f"{stem}.txt"
        if not src.exists():
            print(f"[{i}/{len(stems)}] {stem}: SKIP, no such file")
            failures += 1
            continue

        json_path = out_dir / f"{stem}.json"
        if json_path.exists() and not args.force and not args.dry_run:
            print(f"[{i}/{len(stems)}] {stem}: already done, use --force to redo")
            continue

        raw = src.read_text(encoding="utf-8")
        name = program_name(stem, raw)
        # v1 asked for verbatim source_text, so it gets the file as is; v2 cites line numbers.
        requirements = raw if prompt_path.name == "prompt_v1.txt" else number_lines(raw)

        if args.dry_run:
            prompt = build_prompt(template, taxonomy, name, requirements)
            (out_dir / f"{stem}.prompt.txt").write_text(prompt, encoding="utf-8")
            approx = len(prompt) // 4
            print(f"[{i}/{len(stems)}] {stem}: prompt {len(prompt):,} chars (~{approx:,} tokens) -> {out_label}/{stem}.prompt.txt")
            continue

        to_process.append((i, stem, name, requirements))

    # Pass 2: the actual API calls, fanned out over threads. These are I/O
    # bound (waiting on the network), so threads are the right tool here, not
    # multiprocessing. budget_lock protects budget_state, which both throttles
    # new work once --budget is hit and accumulates the running spend that
    # workers check concurrently.
    if to_process:
        budget_lock = threading.Lock()
        budget_state = {"spent": 0.0, "stop": False}
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
            futures = {
                ex.submit(process_stem, i, len(stems), stem, name, requirements, client, args,
                          price_in, price_out, extra, effort_label, cached_head, tail_template,
                          out_dir, out_label, budget_lock, budget_state): (i, stem)
                for i, stem, name, requirements in to_process
            }
            for fut in as_completed(futures):
                result = fut.result()
                if result is None:
                    i, stem = futures[fut]
                    print(f"[{i}/{len(stems)}] {stem}: SKIP, budget exhausted before this call started")
                    continue
                print(result["line"], flush=True)
                rows.append(result["row"])
                if result["failure"]:
                    failures += 1

        if budget_state["stop"]:
            print(f"\nStopping: spent ${budget_state['spent']:.2f}, at the ${args.budget:.2f} budget.")

    run_seconds = time.perf_counter() - run_t0

    if rows:
        with (out_dir / "run_log.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

        # run_log.csv times each call; this records how long the run itself took.
        # The two differ by roughly --concurrency, which is the point of measuring both.
        spent = sum(r["cost_usd"] for r in rows)
        call_seconds = sum(r["seconds"] for r in rows)
        meta = {
            "model": args.model,
            "concurrency": args.concurrency,
            "programmes": len(rows),
            "wall_seconds": round(run_seconds, 1),
            "call_seconds": round(call_seconds, 1),
            "cost_usd": round(spent, 4),
            "started_at": run_started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        with (out_dir / "run_meta.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(meta))
            w.writeheader()
            w.writerow(meta)

        speedup = ""
        if run_seconds > 0 and call_seconds > run_seconds * 1.05:
            speedup = f", {call_seconds / run_seconds:.1f}x faster than one at a time"
        print(f"\nSpent ${spent:.2f} across {len(rows)} call(s). "
              f"Log: {out_label}/run_log.csv")
        print(f"Finished in {format_duration(run_seconds)} of wall time; "
              f"{format_duration(call_seconds)} of call time{speedup}.")
    if failures:
        print(f"{failures} programme(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
