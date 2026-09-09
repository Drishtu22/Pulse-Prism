#!/usr/bin/env python3
"""Collect raw reachability observations for crawl-access-audit.

This script only *observes*. It does not decide severity and does not emit findings —
SKILL.md turns these observations into findings. Keeping measurement separate from
judgment is what makes the audit reproducible: thresholds live in a readable file, not
buried in code.

Standard library only, so the skill stays portable and needs no install step.

Usage:
    python check_access.py https://example.com --urls sampled.txt --out observations.json
"""

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# One retrieval agent and one training-corpus agent. Different behaviour between them is
# itself a signal that a block is deliberate rather than a blanket bot rule.
RETRIEVAL_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot"
TRAINING_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot"

TIMEOUT = 10
MIN_GAP = 0.2
MAX_GAP = 0.5

INTERSTITIAL_MARKERS = [
    "cf-browser-verification", "cf_chl_opt", "checking your browser",
    "captcha", "px-captcha", "incapsula", "distil_r_captcha",
    "just a moment", "enable javascript and cookies to continue",
    "access denied", "request blocked", "are you a robot",
    "verifying you are human", "ddos-guard", "sucuri_cloudproxy",
    "please enable javascript to continue", "browser check",
    # Confirmed live (wsj.com, DataDome): "Please enable JS and disable any ad
    # blocker" -- close in spirit to the existing javascript-themed markers above but
    # different enough in exact wording that none of them matched, on a page that was
    # otherwise unambiguously a bot challenge (see CHALLENGE_ASSET_PATTERNS below,
    # which is what actually caught it).
    "enable js and disable",
]

# Challenge systems that answer with HTTP 200 and a JavaScript shell rather than an error
# status. These are the most damaging case for AI discoverability and the hardest to
# notice: the site owner sees 200s in their logs and assumes all is well, while every
# non-executing fetcher receives a few kilobytes of nothing.
#
# Not every challenge is disguised as a 200, though -- confirmed live on wsj.com, whose
# DataDome challenge is served as an honest 401. That status is not the sneaky case this
# list exists to catch, but the underlying evidence (a captcha-delivery.com asset
# reference) is still the single most specific, useful fact this script can report about
# *why* a fetch failed, and it is checked below regardless of status code -- unlike the
# thin-body signal further down, which is deliberately scoped to 200 specifically.
CHALLENGE_ASSET_PATTERNS = [
    r"/_fs-ch-",            # Fastly bot challenge
    r"/cdn-cgi/challenge",  # Cloudflare
    r"/_Incapsula_Resource",
    r"/akam/\d+/",          # Akamai bot manager
    r"/_sec/cp_challenge",  # Imperva
    r"__cf_chl_",
    r"/px/",                # PerimeterX
    r"captcha-delivery\.com",  # DataDome
]

# A body under this size that consists mostly of script and style, with no substantive
# text, is a shell rather than a page.
THIN_BODY_BYTES = 8_000
THIN_BODY_TEXT_CHARS = 400


def polite_pause():
    time.sleep(random.uniform(MIN_GAP, MAX_GAP))


GOOD_URL_CHARS = ":/?#[]@!$&'()*+,;=%"


def fetch(url, ua, method="GET"):
    """Fetch a URL, returning an observation dict. Never raises."""
    # Confirmed live (ja.wikipedia.org): a URL containing raw, non-percent-encoded
    # non-ASCII characters (real page hrefs are properly encoded, but a malformed site
    # or a non-compliant sitemap generator can still emit one) makes urllib raise
    # UnicodeEncodeError deep inside the HTTP request line -- caught below, but
    # indistinguishable from a genuine network failure without this. Re-quoting is
    # idempotent (the '%' stays in the safe set) so an already-encoded URL is untouched.
    url = urllib.parse.quote(url, safe=GOOD_URL_CHARS)
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(400_000)
            return {
                "ok": True,
                "status": resp.status,
                "final_url": resp.geturl(),
                "bytes": len(body),
                "elapsed_ms": round((time.time() - started) * 1000),
                "headers": {k.lower(): v for k, v in resp.headers.items()},
                "body": body.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read(200_000)
        except Exception:
            pass
        return {
            "ok": True,
            "status": e.code,
            "final_url": url,
            "bytes": len(body),
            "elapsed_ms": round((time.time() - started) * 1000),
            "headers": {k.lower(): v for k, v in (e.headers or {}).items()},
            "body": body.decode("utf-8", errors="replace"),
        }
    except Exception as e:
        return {
            "ok": False,
            "status": None,
            "final_url": url,
            "bytes": 0,
            "elapsed_ms": round((time.time() - started) * 1000),
            "headers": {},
            "body": "",
            "error": f"{type(e).__name__}: {e}",
        }


TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.I | re.S)


def has_interstitial(obs):
    """A challenge page says "please complete the captcha" in its visible prose. An
    ordinary page with a captcha-protected contact or signup form -- an extremely
    common, completely benign pattern -- carries the word "captcha" too, but only in
    markup a visitor never reads: a <script src="...hcaptcha.com...">, or a button's
    class="button h-captcha" data-sitekey="...". Stripping script/style content is not
    enough on its own, since the second case lives in an ordinary element's attributes,
    not a script block. Stripping every tag and searching only the remaining visible
    text -- the same extraction soft_block_signals() below already uses for text_chars
    -- keeps the marker search scoped to what a visitor, or a non-executing fetcher
    reading rendered text, actually sees."""
    body = obs.get("body", "")[:20_000]
    text = TAG_RE.sub(" ", SCRIPT_STYLE_RE.sub(" ", body)).lower()
    hits = [m for m in INTERSTITIAL_MARKERS if m in text]
    if "cf-mitigated" in obs.get("headers", {}):
        hits.append("header:cf-mitigated")
    return hits


def soft_block_signals(obs):
    """Detect an HTTP 200 that is actually a challenge shell rather than the page.

    A refused fetch that returns 403 is at least honest — the site owner can see it. A
    challenge served as 200 is invisible in logs and analytics, so the brand quietly
    disappears from assistant answers with no signal that anything is wrong. This is the
    single most consequential thing to catch at stage 1, and it cannot be found by
    comparing a bot user-agent against a browser one, because a datacenter IP is
    challenged either way.
    """
    body = obs.get("body", "")
    signals = []

    for pattern in CHALLENGE_ASSET_PATTERNS:
        if re.search(pattern, body[:20_000]):
            signals.append(f"challenge_asset:{pattern}")
            break

    text = TAG_RE.sub(" ", SCRIPT_STYLE_RE.sub(" ", body))
    text_chars = len(re.sub(r"\s+", " ", text).strip())

    if obs.get("status") == 200 and obs.get("bytes", 0) < THIN_BODY_BYTES \
            and text_chars < THIN_BODY_TEXT_CHARS:
        signals.append(f"thin_200:{obs['bytes']}B_body_{text_chars}_text_chars")

    # A short-lived cookie combined with no-store on an ordinary content page is a
    # challenge handshake, not caching policy.
    headers = obs.get("headers", {})
    sc = headers.get("set-cookie", "")
    if "max-age=10" in sc.lower() or "max-age=5" in sc.lower():
        if "no-store" in headers.get("cache-control", "").lower():
            signals.append("challenge_handshake_cookie")

    return signals, text_chars


def parse_robots(text):
    """Parse robots.txt into {agent_lower: {"allow": [...], "disallow": [...]}} plus
    sitemaps, plus a list of agents declared as a separate group more than once.

    Deliberately simple and explicit rather than using urllib.robotparser, because the
    audit needs to report *which lines* produced a rule, not just whether a fetch is
    permitted.
    """
    groups, sitemaps, current = {}, [], []
    # Consecutive User-agent lines share one group, but a User-agent line appearing
    # *after* a rule line begins a new group. Without this flag every group in the file
    # merges into one and per-agent verdicts become meaningless.
    last_was_rule = False
    # An agent named in two separate, non-contiguous groups is a real, distinct defect
    # -- confirmed live on nba.com, whose GPTBot group appears once with nine Allow
    # exceptions and again, later in the same file, as a bare "Disallow: /". The lines
    # below still merge both groups' rules (one defensible interpretation among several
    # a real crawler's parser might make), but without tracking this separately, that
    # merge would silently swallow the fact that the file has no single well-defined
    # meaning for this agent at all -- the more important observation of the two.
    started_groups = set()
    duplicated = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if last_was_rule:
                current = []
            agent = value.lower()
            if agent not in current:
                if agent in started_groups:
                    duplicated.add(agent)
                started_groups.add(agent)
            groups.setdefault(agent, {"allow": [], "disallow": []})
            current.append(agent)
            last_was_rule = False
        elif field == "sitemap":
            sitemaps.append(value)
        elif field in ("allow", "disallow"):
            last_was_rule = True
            for agent in current:
                groups[agent][field].append(value)
    return groups, sitemaps, sorted(duplicated)


def rule_for(groups, agent, path):
    """Longest-match rule resolution, with a named group overriding '*'."""
    agent = agent.lower()
    group = groups.get(agent) or groups.get("*") or {"allow": [], "disallow": []}
    best, verdict = -1, "allowed"
    for kind in ("allow", "disallow"):
        for pattern in group.get(kind, []):
            if pattern == "":
                continue
            regex = re.escape(pattern).replace(r"\*", ".*")
            if pattern.endswith("$"):
                regex = regex[:-2] + "$"
            if re.match(regex, path):
                if len(pattern) > best:
                    best, verdict = len(pattern), ("allowed" if kind == "allow" else "disallowed")
    return verdict, ("named" if agent in groups else "wildcard")


MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MD_HEADING = re.compile(r"^#{1,6}\s+\S", re.M)


HTML_DOC_START = re.compile(r"^\s*<(!doctype html|html)\b", re.I)


def fetch_llms_txt(origin):
    """Observe /llms.txt without judging it -- SKILL.md decides whether an absent file
    is a non-issue (it is; this is an emerging, informal convention most sites do not
    yet have) versus a present-but-hollow one (a real, if minor, defect)."""
    obs = fetch(f"{origin}/llms.txt", BROWSER_UA)
    if not obs["ok"] or obs["status"] != 200 or not obs["body"].strip():
        return {"present": False, "status": obs["status"]}
    body = obs["body"]
    # Confirmed live (spotify.com): a Next.js app's catch-all route serves its custom
    # 404 page for *any* unrecognized path, including /llms.txt, as an honest HTTP 200
    # with a real HTML body -- the exact case status-only presence checks are blind to.
    # A genuine llms.txt is plain text/markdown; an HTML document at that path, on a
    # site otherwise built this way, is a soft-404 wearing a 200, not a real file.
    content_type = obs.get("headers", {}).get("content-type", "")
    if "text/html" in content_type.lower() or HTML_DOC_START.match(body):
        return {"present": False, "status": 200, "note": "soft_404_html_shell"}
    links = MD_LINK.findall(body)
    return {
        "present": True,
        "bytes": len(body.encode("utf-8", errors="ignore")),
        "has_heading": bool(MD_HEADING.search(body)),
        "link_count": len(links),
        "sample_links": links[:15],
        "raw_preview": body[:2000],
    }


def origin_forms(origin):
    p = urllib.parse.urlparse(origin)
    host = p.netloc
    bare = host[4:] if host.startswith("www.") else host
    return [
        f"http://{bare}", f"https://{bare}",
        f"http://www.{bare}", f"https://www.{bare}",
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("origin")
    ap.add_argument("--urls", help="File of sampled URLs, one per line")
    ap.add_argument("--out", default="observations.json")
    args = ap.parse_args()

    origin = args.origin.rstrip("/")
    out = {
        "origin": origin,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "robots": {},
        "llms_txt": {},
        "origin_forms": [],
        "pages": [],
        "notes": [],
    }

    out["llms_txt"] = fetch_llms_txt(origin)
    polite_pause()

    # --- robots.txt -------------------------------------------------------------
    robots_obs = fetch(f"{origin}/robots.txt", BROWSER_UA)
    polite_pause()
    # A non-2xx status with a real robots.txt body underneath it (confirmed live on
    # stackoverflow.com: HTTP 418 carrying a genuine "Disallow: /" and
    # "Content-signal: ai-train=no") is a materially different, and more interesting,
    # case than a genuinely missing file. Per Google's documented crawler behavior (and
    # the convention most major crawlers follow), a 4xx status on robots.txt -- 429
    # aside -- is treated as "robots.txt unavailable", which means an unrestricted
    # crawl, silently defeating whatever the body actually says. Discarding that body
    # the same way an empty 404 is discarded would hide the single most useful fact
    # this check can report: the site's own stated policy is likely not being enforced,
    # for a reason that has nothing to do with what the policy says.
    body_looks_real = bool(re.search(r"user-agent\s*:", robots_obs.get("body", ""), re.I))
    if robots_obs["ok"] and (robots_obs["status"] == 200 or body_looks_real):
        groups, sitemaps, duplicate_agent_groups = parse_robots(robots_obs["body"])
        out["robots"] = {
            "present": True,
            "raw": robots_obs["body"][:8000],
            "groups": groups,
            "sitemaps": sitemaps,
            "agents_declared": sorted(groups.keys()),
            "duplicate_agent_groups": duplicate_agent_groups,
            "served_with_status": None if robots_obs["status"] == 200 else robots_obs["status"],
        }
        if robots_obs["status"] != 200:
            out["notes"].append(
                f"robots.txt was served with HTTP {robots_obs['status']}, not 200, "
                "despite containing real directives. Most major crawlers treat a "
                "non-2xx status (other than 429) on robots.txt as 'file unavailable' "
                "and crawl without restriction, which likely means this file's own "
                "stated policy is not being enforced by the crawlers it names.")
    else:
        # Keep the shape identical whether or not robots.txt exists. A consumer that has
        # to branch on presence will eventually forget to, and a missing key crashes the
        # audit on precisely the sites that have the least configuration.
        out["robots"] = {
            "present": False,
            "status": robots_obs["status"],
            "raw": "",
            "groups": {},
            "sitemaps": [],
            "agents_declared": [],
            "duplicate_agent_groups": [],
            "served_with_status": None,
        }
        out["notes"].append(
            "No robots.txt retrieved; all paths treated as permitted. Absence is not "
            "itself a defect, but it means no crawl directives are published.")

    groups = out["robots"].get("groups", {})

    # --- origin canonicalisation ------------------------------------------------
    for form in origin_forms(origin):
        obs = fetch(form, BROWSER_UA)
        polite_pause()
        out["origin_forms"].append({
            "form": form,
            "status": obs["status"],
            "final_url": obs["final_url"],
            "redirected": obs["final_url"].rstrip("/") != form.rstrip("/"),
        })

    # --- per-page parity --------------------------------------------------------
    urls = []
    if args.urls:
        try:
            with open(args.urls) as fh:
                urls = [ln.strip() for ln in fh if ln.strip()]
        except OSError as e:
            print(f"warn: could not read --urls: {e}", file=sys.stderr)
    if not urls:
        urls = [origin]

    for url in urls:
        path = urllib.parse.urlparse(url).path or "/"
        entry = {"url": url, "path": path, "robots": {}}

        for label, ua in (("retrieval", RETRIEVAL_UA), ("training", TRAINING_UA)):
            verdict, source = rule_for(groups, ua.split("compatible; ")[-1].split("/")[0], path)
            entry["robots"][label] = {"verdict": verdict, "rule_source": source}

        browser = fetch(url, BROWSER_UA)
        polite_pause()
        b_signals, b_text = soft_block_signals(browser)
        entry["browser"] = {
            "status": browser["status"], "bytes": browser["bytes"],
            "final_url": browser["final_url"], "elapsed_ms": browser["elapsed_ms"],
            "interstitial": has_interstitial(browser),
            "soft_block_signals": b_signals,
            "text_chars": b_text,
            "error": browser.get("error"),
        }

        # Only probe with an agent the site permits. Fetching a disallowed path with
        # that agent would both misrepresent the site's policy and abuse it.
        for label, ua in (("retrieval", RETRIEVAL_UA), ("training", TRAINING_UA)):
            if entry["robots"][label]["verdict"] == "disallowed":
                entry[label] = {"skipped": "disallowed by robots.txt"}
                continue
            obs = fetch(url, ua)
            polite_pause()
            o_signals, o_text = soft_block_signals(obs)
            entry[label] = {
                "status": obs["status"], "bytes": obs["bytes"],
                "final_url": obs["final_url"], "elapsed_ms": obs["elapsed_ms"],
                "interstitial": has_interstitial(obs),
                "soft_block_signals": o_signals,
                "text_chars": o_text,
                "error": obs.get("error"),
            }
            b = entry["browser"]
            if b["status"] and obs["status"]:
                entry[label]["status_class_differs"] = (b["status"] // 100) != (obs["status"] // 100)
                entry[label]["bytes_ratio"] = round(obs["bytes"] / b["bytes"], 3) if b["bytes"] else None

        # canonical + redirect depth, from the browser response
        canonical = None
        if browser["ok"]:
            # Whitespace around "=" is valid HTML (href ="...") and real sites use it;
            # requiring "href=" with none would silently read a real canonical tag as
            # absent, producing a false "no canonical" finding rather than an error.
            m = re.search(
                r'<link[^>]+rel\s*=\s*["\']canonical["\'][^>]*href\s*=\s*["\']([^"\']+)["\']',
                browser["body"][:200_000], re.I,
            )
            if m:
                canonical = urllib.parse.urljoin(url, m.group(1))
        entry["canonical"] = canonical
        entry["self_canonical"] = (canonical.rstrip("/") == url.rstrip("/")) if canonical else None

        out["pages"].append(entry)

    # Cross-page comparison. A site serving full pages on some routes and challenge
    # shells on others is the signature of a bot-management rule scoped to page type,
    # which no single-page check can see.
    soft = [p for p in out["pages"] if p.get("browser", {}).get("soft_block_signals")]
    full = [p for p in out["pages"] if not p.get("browser", {}).get("soft_block_signals")]
    out["soft_block_summary"] = {
        "pages_soft_blocked": len(soft),
        "pages_total": len(out["pages"]),
        "affected_fraction": round(len(soft) / max(len(out["pages"]), 1), 3),
        "soft_blocked_paths": [p["path"] for p in soft],
        "unblocked_paths": [p["path"] for p in full],
        "median_text_chars_blocked": (
            sorted(p["browser"].get("text_chars", 0) for p in soft)[len(soft) // 2] if soft else None),
        "median_text_chars_unblocked": (
            sorted(p["browser"].get("text_chars", 0) for p in full)[len(full) // 2] if full else None),
    }

    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"Wrote {args.out}: {len(out['pages'])} pages observed, "
          f"{len(soft)} soft-blocked")


if __name__ == "__main__":
    main()
