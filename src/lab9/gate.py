"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    man = pr.get("manifest") or {}

    # 1. Every reported metric is a real number (NaN/inf compare False against any floor).
    for k, v in (pr.get("metrics") or {}).items():
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            problems.append(f"metric {k} is not a number: {v!r}")
        elif isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v!r}")

    # 2. Evaluator crashes, even on a green run: a crashed grader is a missing verdict.
    fails = pr.get("evaluator_failures")
    if fails:
        first = list(fails)[:1] if isinstance(fails, (list, tuple, dict)) else [fails]
        n = len(fails) if isinstance(fails, (list, tuple, dict)) else 1
        problems.append(f"{n} evaluator failure(s), first: {first[0] if first else fails!r}")

    # 3. Row accounting: items x seeds, no duplicates, same (item, seed) set as the baseline.
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item, seed) row(s)")
    want_n = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want_n:
        problems.append(f"{len(rows)} rows, manifest promises {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want_n}")
    bman = base.get("manifest") or {}
    if man.get("items") != bman.get("items") or sorted(man.get("seeds") or []) != sorted(bman.get("seeds") or []):
        problems.append(f"manifest items/seeds {man.get('items')}/{man.get('seeds')} differ from baseline "
                        f"{bman.get('items')}/{bman.get('seeds')}")
    pk, bk = set(keys), {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if pk != bk:
        problems.append(f"(item, seed) set differs from baseline: {len(bk - pk)} missing, {len(pk - bk)} extra")

    # 4. Every graded spec metric has a verdict on every row.
    base_cols = set().union(*(r.keys() for r in base_rows)) if base_rows else set()
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for mid in graded:
        if not any(mid in r for r in rows) and mid not in base_cols:
            continue          # metric not produced by either run (older report format): nothing to compare
        bad = [r for r in rows if not _verdict(r.get(mid))]
        if bad:
            problems.append(f"{len(bad)} row(s) with no valid value for graded metric {mid} "
                            f"(first {bad[0].get('item_id')}@{bad[0].get('seed')}: {bad[0].get(mid)!r})")
    bad_cost = [r for r in rows if "cost" in r and not (_num(r["cost"]) and math.isfinite(r["cost"]))]
    if bad_cost:
        problems.append(f"{len(bad_cost)} row(s) with a non-numeric cost")

    # 5. Reported metrics must be what the rows say (a hand-edited aggregate is a forged report).
    if rows and not problems:
        ids = [m for m in graded if m in rows[0]]
        has_cost = all("cost" in r for r in rows)
        try:
            again = aggregate([{"cost": 0.0, **r} for r in rows], ids, k_values=spec.get("pass_k", []))
        except (TypeError, ValueError, KeyError) as exc:   # rows the harness could never have written
            return problems + [f"rows cannot be re-aggregated: {type(exc).__name__}: {exc}"]
        if not has_cost:
            again.pop("cost_per_success", None)
        for k, v in (pr.get("metrics") or {}).items():
            w = again.get(k)
            if isinstance(v, (int, float)) and isinstance(w, (int, float)) and abs(v - w) > 1e-3:
                problems.append(f"metric {k}={v} does not match its rows ({w})")
            elif k in again and (v is None) != (w is None):
                problems.append(f"metric {k}={v} does not match its rows ({w})")

    # 6. Slice membership comes from the label; it may not move between baseline and PR.
    bslices = {r.get("item_id"): sorted(r.get("slices") or []) for r in base_rows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in bslices and sorted(r.get("slices") or []) != bslices[r.get("item_id")]})
    if moved:
        problems.append(f"slice tags changed vs baseline for {len(moved)} item(s): {', '.join(moved[:5])}")

    # 7. Ratchet: same eval-set version => thresholds may only get stricter.
    if base_spec is not None:
        problems += ratchet(spec, base_spec)
    return problems


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _verdict(v) -> bool:
    """A grader verdict as lab9.eval writes it: a bool (or a finite 0/1-style number)."""
    return isinstance(v, bool) or (_num(v) and math.isfinite(v))


def _looser(th: dict, bth: dict) -> list[str]:
    out = []
    for k in ("max", "max_increase", "min"):
        if k in th and not _num(th[k]):
            out.append(f"{k} is not a number: {th[k]!r}")
    if out:
        return out
    for k in ("max", "max_increase"):
        if k in bth and (k not in th or th[k] > bth[k]):
            out.append(f"{k} {bth[k]} -> {th.get(k)}")
    if "min" in bth and ("min" not in th or th["min"] < bth["min"]):
        out.append(f"min {bth['min']} -> {th.get('min')}")
    if bth.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def ratchet(spec: dict, base_spec: dict) -> list[str]:
    problems = []
    # The eval set is identified by the files it grades, not by its version label.
    same_eval_set = (spec.get("eval_set"), spec.get("labels"), spec.get("adversarial_pack")) == \
                    (base_spec.get("eval_set"), base_spec.get("labels"), base_spec.get("adversarial_pack"))
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        if not same_eval_set:
            return []     # genuinely new eval set: thresholds start over (and need a new baseline)
        # Renaming the version while grading the very same items is a way around the ratchet.
        problems.append(f"ratchet: eval_set_version {base_spec.get('eval_set_version')!r} -> "
                        f"{spec.get('eval_set_version')!r} but the eval set (sha) is unchanged")
    cur = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        m = cur.get(bm["id"])
        if m is None:
            problems.append(f"ratchet: metric {bm['id']} removed")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            problems.append(f"ratchet: metric {bm['id']} no longer blocking")
        problems += [f"ratchet: metric {bm['id']} {x}" for x in _looser(m.get("threshold") or {}, bm.get("threshold") or {})]
    cs = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        key = (bs.get("name"), bs.get("metric"))
        s = cs.get(key)
        if s is None:
            problems.append(f"ratchet: slice {key[0]}/{key[1]} removed")
            continue
        if bs.get("blocking") and not s.get("blocking"):
            problems.append(f"ratchet: slice {key[0]}/{key[1]} no longer blocking")
        problems += [f"ratchet: slice {key[0]}/{key[1]} {x}" for x in _looser(s, bs)]
    bb, cb = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    if cb.get("confidence", 0.95) < bb.get("confidence", 0.95):
        problems.append(f"ratchet: bootstrap confidence {bb.get('confidence')} -> {cb.get('confidence')}")
    for k in ("rng", "n_resamples", "method"):    # re-rolling the bootstrap until the CI touches 0
        if cb.get(k) != bb.get(k):
            problems.append(f"ratchet: bootstrap {k} {bb.get(k)!r} -> {cb.get(k)!r}")
    if sorted(spec.get("seeds") or []) != sorted(base_spec.get("seeds") or []):
        problems.append(f"ratchet: seeds {base_spec.get('seeds')} -> {spec.get('seeds')}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, mid = sl["name"], sl["metric"]
        sid = f"slice:{name}/{mid}"
        a, b = per_item(pr, mid, slice_name=name), per_item(base, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", f"n={len(a)} item"
        if val is None:
            verdict = "missing"           # an empty slice cannot vouch for anything
        elif "min" in sl and val < sl["min"]:
            verdict = "fail"
        if sl.get("no_significant_drop") and a:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                                   confidence=bs.get("confidence", 0.95))
                note += f" Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        lines.append(f"  {sid:<34} {val!s:<8} {json.dumps(th):<40} {note:<36} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif any(k in th and not _num(th[k]) for k in ("max", "min", "max_increase")) or not _num(val):
            verdict = "fail"              # a threshold or value that is not a number cannot pass
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                               confidence=bs.get("confidence", 0.95))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
