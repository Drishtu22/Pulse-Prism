#!/usr/bin/env python3
"""Measure quotable-fact density, definitional clarity signals and heading shape.

Mechanical measures only. The question-coverage probe in SKILL.md check 1 is a judgment
task and is not attempted here — a regex cannot tell whether a passage answers a
question, and pretending otherwise would produce confident nonsense.

Usage:
    python quotability.py --urls sample.txt --out observations.json
"""
import argparse, json, re, time, urllib.request
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
STRIP = re.compile(r"<(script|style|nav|footer|noscript)\b[^>]*>.*?</\1>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")
MAIN = re.compile(r"<(main|article)\b[^>]*>(.*?)</\1>", re.I | re.S)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")

# NUMERIC/DEFINITIONAL/CAPABILITY/CLAIM are all English-keyword patterns ("is a/an/the",
# "lets you", "we propose"). Confirmed live on a Spanish-language site: a glossary page
# -- 863 words whose entire purpose is defining terms -- scored zero on every kind,
# because Spanish uses "es un/una" and "te permite", not "is a" and "lets you". That is
# a classifier-coverage gap, not evidence the page is thin, and SKILL.md needs the
# page's declared language to tell the two apart. <html lang="..."> is a simple,
# near-universal signal for this -- reported here, not judged; SKILL.md decides what a
# non-English declaration means for this check's numeric threshold.
HTML_LANG = re.compile(r'<html\b[^>]*\blang\s*=\s*["\']([a-zA-Z-]+)["\']', re.I)

# A quotable sentence carries something an assistant can repeat as an answer. Numbers are
# the clearest case but not the only one: "X is a payroll platform for UK companies" has
# no digit and is highly quotable, while "we reimagine what's possible" has none of it.
# Measuring only digits would report near-zero density on almost every real homepage and
# make the threshold fire everywhere — the check has to distinguish abstraction from
# specificity, not prose from numerals.
NUMERIC = re.compile(
    r"(\b\d[\d,.]*\s?(?:%|percent|years?|months?|weeks?|days?|hours?|minutes?|km|mi|kg|GB|MB|TB|"
    r"users?|customers?|employees?|countries|languages?|repositories|projects?|packages?)\b"
    r"|[₹$£€¥]\s?[\d,]+|\b(?:19|20)\d{2}\b|\b\d+\s?(?:x|×)\s?\d+\b)", re.I)

# Definitional: names a thing and states its category or purpose.
DEFINITIONAL = re.compile(
    r"\b(is|are|was|were)\s+(a|an|the)\s+\w+|"
    r"\b(is|are)\s+(designed|built|used|intended)\s+(to|for)\b|"
    r"\bstands for\b|\brefers to\b", re.I)

# Capability: states a concrete action the subject performs or supports.
CAPABILITY = re.compile(
    r"\b(lets? you|allows? you|enables? you|supports?|provides?|includes?|offers?|"
    r"generates?|creates?|converts?|integrates? with|runs? on|works? with|requires?|"
    r"installs?|imports?|exports?|connects? to)\b", re.I)

# Academic/technical-register claim verbs: a paper's core assertions ("we propose a
# method that...", "the approach outperforms...", "this results in a 40% reduction")
# are exactly as quotable as a product's capability statement, just in a different
# register -- CAPABILITY's marketing-style verbs ("lets you", "enables") essentially
# never appear in a scientific abstract or technical report, which would otherwise
# score as near-zero density despite being genuinely dense, substantive prose. Kept
# distinct from CAPABILITY (kind: "claim") since conflating the two would blur what
# each is actually measuring.
CLAIM = re.compile(
    r"\b(we (propose|present|introduce|demonstrate|show|find|report)|"
    r"(results?|leads?) (in|to)|"
    r"(is|are|was|were) (coupled|associated|correlated) with|"
    r"(relies?|depends?) on|"
    r"outperforms?|improves?|reduces?|increases?|achieves?|suffers? from)\b", re.I)

# Abstraction with no assertable content — the opposite of quotable.
CONCRETE = NUMERIC  # retained name for the numeric subset

# Unresolved reference: the sentence cannot stand alone once lifted from the page.
# "We"/"our" are deliberately excluded -- unlike "this/that/it/they", which genuinely
# depend on an antecedent in a prior sentence, "we"/"our" resolve from context that is
# always available (whoever's page or paper this is), so "We don't outsource support"
# and "We propose a new method for X" are self-contained on their own. Verified against
# real pages across four audited sites: excluding we/our recovered several genuinely
# quotable capability sentences ("We don't outsource support.", "We offer both digital
# and physical gift cards...") that this filter was silently discarding, while
# genuine it/that/they dangling references remained correctly excluded.
DANGLING = re.compile(r"^\s*(this|that|these|those|it|they|he|she|there|here|such)\b", re.I)
QUESTION_H = re.compile(r"^\s*(what|why|how|when|where|who|which|can|do|does|is|are|should|will)\b|\?\s*$", re.I)
HEDGE = re.compile(r"\b(reimagine|empower|unlock|leverage|revolutioni[sz]|seamless|cutting[- ]edge|best[- ]in[- ]class|world[- ]class|next[- ]generation|transform your|future of|happens together|endures)\b", re.I)


def text_of(html, main_only=True):
    """Concatenates every <main> or <article> region rather than taking the first match.
    A page with no <main> wrapper and several <article> teasers -- any blog index, news
    homepage, or card-grid layout -- would otherwise have every teaser after the first
    silently discarded, collapsing word_count toward zero and making every density and
    definitional-clarity measurement on that page meaningless."""
    if main_only:
        regions = MAIN.findall(html)
        if regions:
            html = " ".join(region for _, region in regions)
    return WS.sub(" ", TAG.sub(" ", STRIP.sub(" ", html))).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True)
    ap.add_argument("--entity", help="Entity name, for co-occurrence measurement")
    ap.add_argument("--out", default="observations.json")
    a = ap.parse_args()

    res = {"observed_at": datetime.now(timezone.utc).isoformat(), "entity": a.entity, "pages": []}
    for url in [l.strip() for l in open(a.urls) if l.strip()]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read(2_000_000).decode("utf-8", errors="replace")
        except Exception as e:
            res["pages"].append({"url": url, "error": str(e)})
            continue

        body = text_of(html)
        words = body.split()
        sentences = [s.strip() for s in SENT.split(body) if s.strip()]

        quotable, dangling = [], 0
        kinds = {"numeric": 0, "definitional": 0, "capability": 0, "claim": 0}
        for s in sentences:
            wc = len(s.split())
            if wc > 30 or wc < 4:
                continue
            if DANGLING.match(s):
                dangling += 1
                continue
            hit = None
            if NUMERIC.search(s):
                hit = "numeric"
            elif DEFINITIONAL.search(s):
                hit = "definitional"
            elif CAPABILITY.search(s):
                hit = "capability"
            elif CLAIM.search(s):
                hit = "claim"
            if hit:
                kinds[hit] += 1
                quotable.append({"kind": hit, "text": s[:200]})

        headings = []
        for lvl in range(1, 4):
            for h in re.findall(rf"<h{lvl}\b[^>]*>(.*?)</h{lvl}>", html, re.I | re.S):
                headings.append({"level": lvl, "text": WS.sub(" ", TAG.sub("", h)).strip()[:120]})

        first300 = " ".join(words[:300])
        entity_cooccur = None
        if a.entity:
            entity_cooccur = sum(
                1 for s in sentences
                if a.entity.lower() in s.lower() and CONCRETE.search(s))

        lang_match = HTML_LANG.search(html)
        declared_language = lang_match.group(1).lower() if lang_match else None

        res["pages"].append({
            "url": url,
            "declared_language": declared_language,
            "word_count": len(words),
            "sentence_count": len(sentences),
            "quotable_count": len(quotable),
            "quotable_per_500w": round(len(quotable) / max(len(words), 1) * 500, 2),
            "quotable_by_kind": kinds,
            "numeric_per_500w": round(kinds["numeric"] / max(len(words), 1) * 500, 2),
            "dangling_opener_count": dangling,
            "dangling_ratio": round(dangling / max(len(sentences), 1), 3),
            "quotable_examples": quotable[:6],
            "headings": headings[:30],
            "h1_count": sum(1 for h in headings if h["level"] == 1),
            "question_shaped_headings": sum(1 for h in headings if QUESTION_H.search(h["text"])),
            "hedge_terms_in_first_300w": sorted(set(m.lower() for m in HEDGE.findall(first300))),
            "first_300_words": first300[:1500],
            "entity_attribute_cooccurrence": entity_cooccur,
        })
        time.sleep(0.25)

    json.dump(res, open(a.out, "w"), indent=2)
    print(f"Wrote {a.out}: {len(res['pages'])} pages")


if __name__ == "__main__":
    main()
