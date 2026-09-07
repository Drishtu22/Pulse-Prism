#!/usr/bin/env python3
"""Collect raw freshness, consistency and identity-anchor observations.

This script only *observes*. It does not decide what counts as stale, inconsistent or
ambiguous -- SKILL.md turns these observations into findings, the same
measurement/judgment split every other skill in this marketplace uses. Two checks in
this skill's SKILL.md are deliberately left unscripted: check 4 (off-site corroboration)
requires open-ended search against sources this script cannot know in advance, and
check 5's entity-collision judgment is inherently a reasoning task -- this script
surfaces the identity anchors (or their absence) that check depends on, not the verdict.

Standard library only, so the skill stays portable and needs no install step.

Usage:
    python freshness_signals.py --urls sample.txt --out observations.json
"""
import argparse, json, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")
SCRIPT_STYLE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.I | re.S)

JSONLD_BLOCK = re.compile(r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
TIME_EL = re.compile(r'<time\b([^>]*)>(.*?)</time>', re.I | re.S)
ATTR = re.compile(r'(\w[\w-]*)\s*=\s*["\']([^"\']*)["\']')

# Visible date text in the formats real pages actually use. Deliberately conservative --
# a false match here would misdate a page that never claimed a date at all.
DATE_TEXT = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+\d{1,2},?\s+(19|20)\d{2}\b"
    r"|\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?,?\s+(19|20)\d{2}\b"
    r"|\b(19|20)\d{2}-\d{2}-\d{2}\b", re.I)

COPYRIGHT = re.compile(r"(?:©|&copy;|\(c\)|copyright)\s*©?\s*((?:19|20)\d{2})(?:\s*[-–]\s*((?:19|20)\d{2}))?", re.I)

# Candidates for check 2 (staleness): a label implying something is imminent or brand
# new, which is exactly the kind of claim that silently rots if the page is not revisited.
STALE_LABEL = re.compile(r"\b(coming soon|new!|just launched|now available|newly opened)\b", re.I)

# Any four-digit year in a plausible range, for the agent to compare against the current
# date and against other years found on the same or other pages -- this script does not
# know "today", so it records candidates rather than judging which ones are stale. A
# street number that happens to fall in the same numeric range ("2027 Anchor Lane") is
# not a year. The street-suffix word sits after the street *name*, not immediately after
# the number, so the lookahead has to allow a short run of name words in between --
# matching the same "number, then words, then suffix" shape ADDRESS_HINT below uses.
YEAR = re.compile(
    r"\b(19[5-9]\d|20[0-4]\d)\b"
    r"(?!\s+[A-Za-z][\w'.-]*(?:\s+[A-Za-z][\w'.-]*){0,3}\s+"
    r"(?:St(?:reet)?|Ave(?:nue)?|Rd|Road|Blvd|Boulevard|Dr(?:ive)?|Ln|Lane|Way|Ct|Court)\b)",
    re.I)

# A light definitional pattern for check 3 (internal consistency): a sentence naming the
# subject and stating its category, the same shape the answerability skill looks for --
# duplicated here rather than imported, since every skill's scripts are self-contained.
SELF_DESCRIPTION = re.compile(r"[^.!?]*\b(?:is|are|was|were)\s+(?:a|an|the)\s+[^.!?]{3,120}[.!?]")

ADDRESS_HINT = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.'\- ]{3,40}\b(?:St(?:reet)?|Ave(?:nue)?|Rd|Road|Blvd|Boulevard|"
    r"Dr(?:ive)?|Ln|Lane|Way|Ct|Court|Suite|Ste)\b[^.\n]{0,60}", re.I)
PHONE_CANDIDATE = re.compile(r"\+?\(?\d{1,4}\)?(?:[-.\s]\d{1,4}){2,5}")

# Independent identity anchors: the same domains structured-data-audit's check 4 looks
# for in sameAs links, found here in plain hrefs too since not every site expresses them
# as schema.org markup.
IDENTITY_ANCHOR = re.compile(
    r'href\s*=\s*["\']https?://(?:[\w.-]*\.)?(wikipedia\.org|wikidata\.org|linkedin\.com|'
    r'crunchbase\.com|facebook\.com|instagram\.com|twitter\.com|x\.com)/[^"\']*["\']', re.I)


def looks_like_phone(s):
    groups = [g for g in re.split(r"[-.\s()]+", s.strip()) if g]
    digit_total = sum(len(g) for g in groups)
    return any(len(g) >= 2 for g in groups) and 7 <= digit_total <= 15


def visible_text(html):
    return WS.sub(" ", TAG.sub(" ", SCRIPT_STYLE.sub(" ", html))).strip()


def json_ld_dates(html):
    dates = {"datePublished": [], "dateModified": []}
    for raw in JSONLD_BLOCK.findall(html):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key in ("datePublished", "dateModified"):
                    v = node.get(key)
                    if isinstance(v, str):
                        dates[key].append(v)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return dates


def time_elements(html):
    out = []
    for attrs, inner in TIME_EL.findall(html):
        a = dict(ATTR.findall(attrs))
        out.append({
            "datetime": a.get("datetime"),
            "text": WS.sub(" ", TAG.sub(" ", inner)).strip()[:60],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True)
    ap.add_argument("--out", default="observations.json")
    a = ap.parse_args()

    res = {"observed_at": datetime.now(timezone.utc).isoformat(), "pages": []}
    for url in [l.strip() for l in open(a.urls) if l.strip()]:
        try:
            # A raw, non-percent-encoded non-ASCII URL makes urllib raise
            # UnicodeEncodeError building the request line; re-quoting is idempotent
            # on an already-encoded URL since '%' stays in the safe set.
            safe_url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
            req = urllib.request.Request(safe_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read(2_000_000).decode("utf-8", errors="replace")
                status = r.status
        except Exception as e:
            res["pages"].append({"url": url, "error": str(e)})
            continue

        text = visible_text(html)
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        h1s = [WS.sub(" ", TAG.sub("", h)).strip()
               for h in re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, re.I | re.S)][:3]

        res["pages"].append({
            "url": url,
            "status": status,
            "json_ld_dates": json_ld_dates(html),
            "time_elements": time_elements(html)[:20],
            "visible_date_candidates": sorted(set(m.group(0) for m in DATE_TEXT.finditer(text)))[:20],
            "copyright_years": sorted(set(
                y for m in COPYRIGHT.finditer(text) for y in m.groups() if y
            )),
            "stale_labels": sorted(set(m.group(0).lower() for m in STALE_LABEL.finditer(text))),
            "years_mentioned": sorted(set(YEAR.findall(text))),
            "title": title_m.group(1).strip() if title_m else None,
            "h1": h1s,
            "self_description_sentences": [
                m.group(0).strip()[:200] for m in SELF_DESCRIPTION.finditer(text)
            ][:5],
            "address_candidates": [m.group(0).strip()[:120] for m in ADDRESS_HINT.finditer(text)][:5],
            "phone_candidates": sorted({
                m.group(0) for m in PHONE_CANDIDATE.finditer(text) if looks_like_phone(m.group(0))
            })[:5],
            "identity_anchor_domains": sorted(set(
                m.group(1).lower() for m in IDENTITY_ANCHOR.finditer(html)
            )),
        })
        time.sleep(0.25)

    json.dump(res, open(a.out, "w"), indent=2)
    print(f"Wrote {a.out}: {len(res['pages'])} pages")


if __name__ == "__main__":
    main()
