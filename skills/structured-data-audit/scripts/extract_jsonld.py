#!/usr/bin/env python3
"""Extract JSON-LD, microdata and RDFa signals plus candidate visible-text values.

The visible-text capture exists for the agreement check in SKILL.md check 3, which is
what distinguishes this skill from a markup-presence checker.

Usage:
    python extract_jsonld.py --urls sample.txt --out observations.json
"""
import argparse, json, re, time, urllib.request, urllib.error
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
BLOCK = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")
PRICE = re.compile(r"(?:[₹$£€¥]|\bRs\.?|\bINR|\bUSD|\bEUR|\bGBP)\s?[\d,]+(?:\.\d{1,2})?", re.I)
TIME_RANGE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\s*(?:[-–—to]+)\s*(?:[01]?\d|2[0-3]):[0-5]\d\b")
PHONE_CANDIDATE = re.compile(r"\+?\(?\d{1,4}\)?(?:[-.\s]\d{1,4}){2,5}")


def looks_like_phone(s):
    """Reject a candidate where every digit group is a lone single digit.

    The loose grouped-digits shape above also matches a rendered numbered list --
    "1 2 3 4 5 6 7 8 9" -- which is not a phone number. A real phone number always has
    at least one multi-digit group (an area code, an exchange, a line number); a plain
    digit-by-digit sequence never does, so that distinguishes the two cases without
    needing a country-specific format list."""
    groups = [g for g in re.split(r"[-.\s()]+", s.strip()) if g]
    digit_total = sum(len(g) for g in groups)
    return any(len(g) >= 2 for g in groups) and 7 <= digit_total <= 15


def types_in(node, acc):
    if isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str):
            acc.add(t)
        elif isinstance(t, list):
            acc.update(x for x in t if isinstance(x, str))
        for v in node.values():
            types_in(v, acc)
    elif isinstance(node, list):
        for v in node:
            types_in(v, acc)
    return acc


def paths(node, prefix=""):
    """Flatten to property paths so evidence can name offers.price rather than dumping a block."""
    out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(paths(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.update(paths(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = node
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True)
    ap.add_argument("--out", default="observations.json")
    a = ap.parse_args()

    res = {"observed_at": datetime.now(timezone.utc).isoformat(), "pages": []}
    for url in [l.strip() for l in open(a.urls) if l.strip()]:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read(2_000_000).decode("utf-8", errors="replace")
                status = r.status
        except Exception as e:
            res["pages"].append({"url": url, "error": str(e)})
            continue

        blocks, errors, all_types = [], [], set()
        for raw in BLOCK.findall(html):
            try:
                data = json.loads(raw.strip())
                blocks.append({"types": sorted(types_in(data, set())), "paths": paths(data)})
                types_in(data, all_types)
            except json.JSONDecodeError as e:
                errors.append(str(e))

        text = WS.sub(" ", TAG.sub(" ", re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.I | re.S)))
        res["pages"].append({
            "url": url, "status": status,
            "jsonld_blocks": blocks,
            "jsonld_parse_errors": errors,
            "types_declared": sorted(all_types),
            "has_microdata": bool(re.search(r'itemscope', html, re.I)),
            "has_rdfa": bool(re.search(r'\bvocab=|\btypeof=', html, re.I)),
            "visible_candidates": {
                "prices": sorted(set(PRICE.findall(text)))[:15],
                "time_ranges": sorted(set(TIME_RANGE.findall(text)))[:10],
                "phones": sorted({m for m in PHONE_CANDIDATE.findall(text) if looks_like_phone(m)})[:5],
                "title": (re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S).group(1).strip()
                          if re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S) else None),
                "h1": [WS.sub(" ", TAG.sub("", h)).strip()
                       for h in re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, re.I | re.S)][:3],
            },
        })
        time.sleep(0.25)

    json.dump(res, open(a.out, "w"), indent=2)
    print(f"Wrote {a.out}: {len(res['pages'])} pages")


if __name__ == "__main__":
    main()
