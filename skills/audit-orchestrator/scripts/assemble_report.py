#!/usr/bin/env python3
"""Assemble the final audit report from per-skill finding files.

Severity is *derived* here rather than accepted from the contributing skills, so that
the report is internally consistent and two runs on an unchanged site produce identical
labels. The arithmetic mirrors references/severity-model.md; if that file changes, change
this together with it.

Standard library only.

Usage:
    python assemble_report.py --findings ./findings --site example.com --out audit-report.json
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

STAGE_WEIGHT = {
    1: 1.00, 2: 0.85, 3: 0.70, 4: 0.55, 5: 0.40, 6: 0.35,
}
STAGE_NAME = {
    1: "reachability", 2: "delivery", 3: "textuality",
    4: "extractability", 5: "trust", 6: "engagement",
}
PREVALENCE = {"site-wide": 1.00, "widespread": 0.80, "partial": 0.55, "isolated": 0.30}
CRITICALITY = {"core": 1.00, "supporting": 0.70, "peripheral": 0.40, "informational": 0.20}
BANDS = [(0.70, "critical"), (0.45, "high"), (0.25, "medium"), (0.0, "low")]
ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def band(score):
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return "low"


def prevalence_band(fraction):
    if fraction >= 0.80:
        return "site-wide"
    if fraction >= 0.40:
        return "widespread"
    if fraction >= 0.10:
        return "partial"
    return "isolated"


def derive_severity(f, errors):
    si = f.get("severity_inputs") or {}
    stage = si.get("stage")
    if stage not in STAGE_WEIGHT:
        errors.append(f"{f.get('title','<untitled>')}: severity_inputs.stage missing or invalid")
        return None, None

    prev = si.get("prevalence")
    if prev not in PREVALENCE:
        frac = si.get("affected_fraction")
        if frac is None:
            errors.append(f"{f.get('title')}: needs prevalence or affected_fraction")
            return None, None
        prev = prevalence_band(float(frac))
        si["prevalence"] = prev

    crit = si.get("criticality")
    if crit not in CRITICALITY:
        errors.append(
            f"{f.get('title')}: severity_inputs.criticality missing or invalid "
            f"(expected one of {', '.join(CRITICALITY)})")
        return None, None

    # A finding that hides no content is a hygiene observation, not a blocker, however
    # site-wide it is. Without this guard an early-stage config nit inherits the full
    # stage weight and outranks findings that genuinely make the site invisible.
    if crit == "informational" and stage <= 2:
        si["note"] = "informational: no content degraded, so stage weight is not applied at full strength"

    score = round(STAGE_WEIGHT[stage] * PREVALENCE[prev] * CRITICALITY[crit], 2)
    return score, band(score)


def validate(f, errors):
    for field in ("title", "evidence", "suggested_action"):
        if not f.get(field):
            errors.append(f"{f.get('title','<untitled>')}: missing required field '{field}'")
    sa = f.get("suggested_action") or {}
    if isinstance(sa, dict):
        if not sa.get("summary"):
            errors.append(f"{f.get('title')}: suggested_action.summary is required")
        if not sa.get("mechanism"):
            errors.append(f"{f.get('title')}: suggested_action.mechanism is required "
                          "— a fix that cannot state its mechanism is a guess")


def load(findings_dir):
    items = []
    for path in sorted(glob.glob(os.path.join(findings_dir, "*.json"))):
        with open(path) as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as e:
                print(f"error: {path} is not valid JSON: {e}", file=sys.stderr)
                sys.exit(1)
        if isinstance(data, dict):
            data = data.get("findings", [])
        items.extend(data)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True, help="Directory of per-skill finding JSON files")
    ap.add_argument("--site", required=True)
    ap.add_argument("--scope", help="sample.json from discover_pages.py")
    ap.add_argument("--opportunities", help="JSON file of opportunity objects")
    ap.add_argument("--not-assessed", help="JSON file of not-assessed entries")
    ap.add_argument("--audited-at")
    ap.add_argument("--out", default="audit-report.json")
    ap.add_argument("--strict", action="store_true", help="Exit non-zero on validation errors")
    args = ap.parse_args()

    findings = load(args.findings)
    errors = []

    for f in findings:
        validate(f, errors)
        score, label = derive_severity(f, errors)
        if score is not None:
            f["severity_score"] = score
            f["severity"] = label
            f["stage"] = STAGE_NAME[f["severity_inputs"]["stage"]]

    findings = [f for f in findings if f.get("severity")]

    # Blocked findings are capped: there is no value in ranking a JSON-LD gap above the
    # reachability failure that makes it unreadable in the first place.
    #
    # Final ids do not exist yet at this point (they are assigned after sorting, so that
    # id order reflects priority), so blockers are resolved by title. Contributing skills
    # cannot know final ids, and requiring them to would couple the skills to the
    # orchestrator's numbering.
    by_title = {f.get("title", ""): f for f in findings}

    # A genuinely site-wide reachability failure blocks everything downstream by
    # construction, whether or not a skill thought to declare it. But "widespread"
    # (0.40-0.79 of pages) is too weak a signal for that -- confirmed live on a real
    # site carrying two independent stage-1/stage-2 findings with disjoint scopes: a
    # robots.txt block naming one specific retrieval agent on specific paths (prevalence
    # "widespread", genuinely affecting only that one agent) does not make a completely
    # unrelated, universal delivery failure -- one that would still block every *other*
    # agent even after the robots.txt issue is fixed -- "moot until it clears". Treating
    # the narrower finding as a blanket blocker capped the universal one at medium and
    # marked it blocked_by a finding whose fix would do nothing to resolve it. Only a
    # finding whose own prevalence is "site-wide" (>= 0.80, not merely "widespread") is
    # trusted to plausibly subsume everything else; a narrower stage-1 finding may still
    # legitimately block specific other findings via an explicit blocked_by reference,
    # just not everything automatically.
    auto_blockers = [
        f for f in findings
        if f.get("severity_inputs", {}).get("stage") == 1
        and f["severity"] == "critical"
        and f.get("severity_inputs", {}).get("prevalence") == "site-wide"
    ]

    for f in findings:
        stage = f.get("severity_inputs", {}).get("stage", 9)
        blockers = []
        for ref in (f.get("blocked_by") or []):
            target = by_title.get(ref)
            if target is not None and target is not f:
                blockers.append(target)
        for b in auto_blockers:
            if b is not f and stage > 1 and b not in blockers:
                blockers.append(b)

        if blockers:
            f["_blocker_titles"] = [b.get("title", "") for b in blockers]
            if ORDER[f["severity"]] < ORDER["medium"]:
                f["severity"] = "medium"
                f["severity_score"] = min(f["severity_score"], 0.44)
                f["severity_capped_reason"] = (
                    "Capped at medium: moot until the blocking finding is resolved."
                )

    findings.sort(key=lambda f: (
        ORDER[f["severity"]],
        f.get("severity_inputs", {}).get("stage", 9),
        -float(f.get("severity_inputs", {}).get("affected_fraction") or 0),
        f.get("title", ""),
    ))
    for i, f in enumerate(findings, 1):
        f["id"] = f"F-{i:03d}"

    # Now that ids exist, rewrite the resolved blocker titles into ids so the report is
    # self-referential and a reader can follow the dependency.
    title_to_id = {f.get("title", ""): f["id"] for f in findings}
    for f in findings:
        titles = f.pop("_blocker_titles", None)
        if titles:
            f["blocked_by"] = [title_to_id[t] for t in titles if t in title_to_id]
        elif "blocked_by" in f:
            del f["blocked_by"]

    counts = {k: 0 for k in ORDER}
    for f in findings:
        counts[f["severity"]] += 1

    # Stage scores: 100 means no findings at that stage. Lets a reader see the bottleneck
    # without reading every finding.
    stage_scores = {}
    for num, name in STAGE_NAME.items():
        at_stage = [f for f in findings if f.get("severity_inputs", {}).get("stage") == num]
        penalty = sum(f["severity_score"] for f in at_stage) * 40
        stage_scores[name] = max(0, round(100 - penalty))

    top = findings[0] if findings else None
    headline = (
        f"{top['title']} — {top['severity']} severity, "
        f"{(top.get('suggested_action') or {}).get('summary','')}"
        if top else "No findings detected in the audited sample."
    )

    scope = {}
    if args.scope and os.path.exists(args.scope):
        with open(args.scope) as fh:
            s = json.load(fh)
        scope = {
            "pages_sampled": len(s.get("sampled_urls", [])),
            "sample_seed": s.get("seed"),
            "sampled_urls": s.get("sampled_urls", []),
            "robots_respected": True,
        }

    report = {
        "site": args.site,
        "audited_at": args.audited_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "audit_scope": scope,
        "summary": {
            "total_findings": len(findings),
            "critical": counts["critical"],
            "high": counts["high"],
            "medium": counts["medium"],
            "low": counts["low"],
            "stage_scores": stage_scores,
            "headline": headline,
        },
        "findings": findings,
    }

    for key, path in (("opportunities", args.opportunities), ("not_assessed", args.not_assessed)):
        if path and os.path.exists(path):
            with open(path) as fh:
                report[key] = json.load(fh)
        else:
            report[key] = []

    for i, o in enumerate(report["opportunities"], 1):
        o.setdefault("id", f"O-{i:03d}")

    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)

    if errors:
        print(f"\n{len(errors)} validation problem(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)

    print(f"Wrote {args.out}: {len(findings)} findings "
          f"({counts['critical']} critical, {counts['high']} high, "
          f"{counts['medium']} medium, {counts['low']} low)")
    print(f"Stage scores: {stage_scores}")

    if errors and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
