#!/usr/bin/env python3
"""Discover candidate URLs and select a deterministic stratified sample.

Sampling is stratified by URL template rather than random, because fifteen pages drawn
from one template characterise nothing while one page from each of eight templates
characterises a site. The seed is recorded so a re-run inspects the same pages and the
audit is reproducible.

Standard library only.

Usage:
    python discover_pages.py https://example.com --seed 42 --max 15 --out sample.json
"""

import argparse
import gzip
import html
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
TIMEOUT = 10

# Paths no audit should sample: transactional, authenticated, or infinite.
EXCLUDE = re.compile(
    r"/(cart|checkout|basket|login|signin|sign-in|register|signup|sign-up|account|"
    r"admin|wp-admin|logout|search|api|feed|rss|\.well-known)(/|$|\?)", re.I
)
ASSET = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|ico|css|js|zip|mp4|mp3|woff2?|ttf)(\?|$)", re.I)


def fetch(url):
    # A raw, non-percent-encoded non-ASCII URL (confirmed live off a non-English
    # site's page) makes urllib raise UnicodeEncodeError building the request line;
    # re-quoting is idempotent on an already-encoded URL since '%' stays in the safe
    # set. Left unfixed, this silently degrades page discovery specifically on
    # non-English sites, since discovered hrefs/<loc> values are the ones most likely
    # to carry native-script paths.
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw, status = r.read(2_000_000), r.status
    except urllib.error.HTTPError as e:
        return "", e.code
    except Exception:
        return "", None
    # A sitemap named *.xml.gz (a standard, common practice for large sites -- confirmed
    # live on airbnb.com's master sitemap index) is genuine gzip-compressed bytes, not
    # plain XML with an unusual name. urllib never auto-decompresses the way the
    # `requests` library does, so decoding the raw bytes as UTF-8 without checking first
    # silently produces garbage and 0 discovered URLs, with no error to signal it.
    # Detecting by magic number rather than the ".gz" suffix also catches a server that
    # serves gzip content without naming the file that way.
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass  # truncated or corrupt; fall through and decode whatever bytes exist
    return raw.decode("utf-8", errors="replace"), status


def robots_sitemaps(origin):
    """Return (sitemaps, disallowed) from robots.txt, honouring User-agent groups.

    Disallow rules must not leak across groups. A very common real-world pattern is a
    named group blocking a specific bad or obsolete crawler with `Disallow: /` while a
    separate `User-agent: *` group allows everything (python.org does exactly this, for
    HTTrack/puf/MSIECrawler/Nutch). This script crawls with a generic browser
    user-agent, not any bot named in the file, so only the wildcard group governs it.
    Pooling every Disallow line regardless of group previously made this sampler treat
    such sites as entirely off-limits to itself, collapsing the sample to the homepage
    alone on otherwise fully crawlable sites.
    """
    body, status = fetch(f"{origin}/robots.txt")
    if status != 200:
        return [], []

    sitemaps = []
    groups, current, last_was_rule = {}, [], False
    for raw in body.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "sitemap":
            sitemaps.append(value)
        elif field == "user-agent":
            if last_was_rule:
                current = []
            agent = value.lower()
            groups.setdefault(agent, [])
            current.append(agent)
            last_was_rule = False
        elif field == "disallow" and value:
            last_was_rule = True
            for agent in current:
                groups[agent].append(value)
        elif field == "allow":
            last_was_rule = True

    return sitemaps, groups.get("*", [])


SITEMAP_FETCH_BUDGET = 20


def parse_sitemap(url, depth=0, seen=None, budget=None):
    """Collect URLs from a sitemap, following index files one level.

    `budget` must be a single mutable counter shared across every call in one run --
    including every top-level sitemap in main()'s loop, not just the recursive calls
    within one sitemap's own index tree. A real site commonly declares many top-level
    sitemaps (nytimes.com declares 25), and each one independently fanning out to up to
    5 children with no shared cap could cost 100+ requests just discovering candidates,
    before the orchestrator's own budget for the rest of the audit even starts."""
    seen = seen if seen is not None else set()
    if budget is None:
        budget = [SITEMAP_FETCH_BUDGET]
    if depth > 1 or url in seen or budget[0] <= 0:
        return []
    seen.add(url)
    budget[0] -= 1
    body, status = fetch(url)
    if status != 200 or not body:
        return []
    # XML sitemaps escape "&" as "&amp;" per spec, so a <loc> with a query string needs
    # the same unescaping as an HTML href -- otherwise a multi-parameter sitemap URL is
    # fetched as one literal opaque parameter instead of a normal query string.
    locs = [html.unescape(l) for l in re.findall(r"<loc>\s*([^<]+?)\s*</loc>", body, re.I)]
    if "<sitemapindex" in body[:2000].lower():
        out = []
        for child in locs[:5]:  # cap: index fan-out can be enormous
            if budget[0] <= 0:
                break
            out.extend(parse_sitemap(child.strip(), depth + 1, seen, budget))
            time.sleep(0.2)
        return out
    return [l.strip() for l in locs]


def homepage_links(origin):
    body, status = fetch(origin)
    if status != 200:
        return []
    # HTML5 permits whitespace around "=" in an attribute (href ="...", href = "..."),
    # and real sites use it -- arxiv.org's own listing-page template emits exactly
    # `href ="/abs/<id>"` for its primary article links. A regex expecting "href=" with
    # no space silently discovers zero of a page's most important links rather than
    # erroring, which is far more dangerous: the gap never surfaces as a failure.
    hrefs = re.findall(r'<a[^>]+href\s*=\s*["\']([^"\'#]+)["\']', body, re.I)
    out = []
    host = urllib.parse.urlparse(origin).netloc
    for h in hrefs:
        # href attributes are HTML source text, so an "&" in a query string is written
        # as "&amp;" -- left undecoded, "?type=event&amp;type=event" is fetched as one
        # literal opaque parameter instead of a normal two-parameter query string.
        full = urllib.parse.urljoin(origin, html.unescape(h))
        if urllib.parse.urlparse(full).netloc == host:
            out.append(full.split("#")[0])
    return out


def segments(url):
    path = urllib.parse.urlparse(url).path.rstrip("/") or "/"
    return [s for s in path.split("/") if s]


def build_template_map(urls, min_distinct=8, min_ratio=0.25):
    """Learn which path positions are variable, from the URLs themselves.

    Per-segment heuristics (is it a number? does it contain a hyphen?) do not generalise:
    on a package index every project slug looks like a distinct literal, so a site with
    38k pages yields 31k 'templates' and stratified sampling degenerates into random
    sampling from the single largest template.

    A position is variable when, under a given parent prefix, it takes *many* distinct
    values *and* those values are close to one-per-URL. Both conditions are needed:

    - absolute count alone marks top-level route names variable, because a large site
      legitimately has 20+ first segments (/project, /user, /help, ...), collapsing every
      route into one meaningless template;
    - ratio alone marks a two-page section variable, because 2 distinct values across 2
      URLs is a ratio of 1.0.

    Together they describe a structural fact about the site rather than a guess about
    naming conventions, so this works equally on /project/<name>, /2024/<slug>, /p/<id>
    and /<country>/<city>.
    """
    distinct = defaultdict(set)
    total = defaultdict(int)
    for u in urls:
        segs = segments(u)
        for i in range(len(segs)):
            key = ("/".join(segs[:i]), i)
            distinct[key].add(segs[i])
            total[key] += 1

    variable = set()
    for key, values in distinct.items():
        if len(values) >= min_distinct and len(values) / max(total[key], 1) >= min_ratio:
            variable.add(key)

    def template_of(url):
        segs = segments(url)
        parts = []
        for i, seg in enumerate(segs):
            prefix = "/".join(segs[:i])
            if (prefix, i) in variable:
                parts.append("<var>")
            elif seg.isdigit():
                parts.append("<num>")
            else:
                parts.append(seg.lower())
        return "/" + "/".join(parts) if parts else "/"

    return template_of


def eligible(url, origin, disallowed):
    p = urllib.parse.urlparse(url)
    if p.netloc != urllib.parse.urlparse(origin).netloc:
        return False
    if ASSET.search(p.path) or EXCLUDE.search(p.path):
        return False
    for d in disallowed:
        pattern = re.escape(d).replace(r"\*", ".*")
        if re.match(pattern, p.path):
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("origin")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max", type=int, default=15)
    ap.add_argument("--out", default="sample.json")
    args = ap.parse_args()

    origin = args.origin.rstrip("/")
    rng = random.Random(args.seed)

    sitemaps, disallowed = robots_sitemaps(origin)
    candidates, sources = [], {}

    # One seen-set and one fetch budget shared across every declared sitemap, not a
    # fresh one per top-level entry -- see parse_sitemap's docstring.
    sitemap_seen, sitemap_budget = set(), [SITEMAP_FETCH_BUDGET]
    for sm in sitemaps or [f"{origin}/sitemap.xml", f"{origin}/sitemap_index.xml"]:
        if sitemap_budget[0] <= 0:
            break
        for u in parse_sitemap(sm, seen=sitemap_seen, budget=sitemap_budget):
            if u not in sources:
                sources[u] = "sitemap"
                candidates.append(u)
        time.sleep(0.2)

    for u in homepage_links(origin):
        if u not in sources:
            sources[u] = "homepage_link"
            candidates.append(u)

    candidates = [u for u in candidates if eligible(u, origin, disallowed)]

    # Learn the site's URL templates from the candidate set, then stratify across them so
    # the sample characterises the site's distinct page shapes rather than its largest
    # template.
    template_of = build_template_map(candidates)

    buckets = defaultdict(list)
    for u in candidates:
        buckets[template_of(u)].append(u)
    for t in buckets:
        buckets[t].sort()

    # Visit shapes with more pages first: a template covering 30k pages characterises the
    # site more than one covering two.
    ordered_templates = sorted(buckets, key=lambda t: (-len(buckets[t]), t))

    selected = [origin]
    for t in ordered_templates:
        if len(selected) >= args.max:
            break
        pick = rng.choice(buckets[t])
        if pick.rstrip("/") != origin and pick not in selected:
            selected.append(pick)

    remaining = [u for u in sorted(candidates) if u not in selected]
    rng.shuffle(remaining)
    while len(selected) < args.max and remaining:
        selected.append(remaining.pop())

    result = {
        "origin": origin,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "candidates_found": len(candidates),
        "templates_found": len(buckets),
        "sitemaps": sitemaps,
        "sampled_urls": selected,
        "templates_sampled": sorted({template_of(u) for u in selected}),
        "template_sizes": {t: len(buckets[t]) for t in sorted(buckets, key=lambda x: -len(buckets[x]))[:10]},
        "coverage_note": (
            "No sitemap discovered; sample drawn from homepage links only."
            if not sitemaps else
            f"Sitemap fetch budget ({SITEMAP_FETCH_BUDGET} requests) exhausted before all "
            f"{len(sitemaps)} declared sitemaps could be read; candidates reflect only "
            "the sitemaps reached before the cap, not the site's full inventory."
            if sitemap_budget[0] <= 0 else ""
        ),
    }

    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2)
    with open(args.out.replace(".json", ".txt"), "w") as fh:
        fh.write("\n".join(selected) + "\n")

    print(f"{len(selected)} URLs sampled from {len(candidates)} candidates "
          f"across {len(buckets)} templates -> {args.out}")


if __name__ == "__main__":
    main()
