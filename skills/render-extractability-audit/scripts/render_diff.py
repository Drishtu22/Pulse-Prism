#!/usr/bin/env python3
"""Measure how much of a page's text survives without JavaScript, and inventory
non-text carriers of facts.

Observation only — SKILL.md applies the thresholds. If no headless browser is present the
raw half still runs and the comparative measures are reported as unavailable, because
inferring a render gap from thin HTML alone would be a guess.

Usage:
    python render_diff.py --urls sample.txt --out observations.json
"""
import argparse, json, re, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
TIMEOUT = 12

STRIP = re.compile(r"<(script|style|noscript|template|svg)\b[^>]*>.*?</\1>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")
MAIN = re.compile(r"<(main|article)\b[^>]*>(.*?)</\1>", re.I | re.S)


def visible_text(html, main_only=True):
    """Extract visible text. Measuring over the main region where one exists keeps chat
    widgets and cookie banners from inflating the rendered figure and manufacturing a
    finding.

    Concatenates *every* <main> or <article> region rather than taking the first match.
    A page with no <main> wrapper and several <article> teasers -- any blog index, news
    homepage, or card-grid layout, which is one of the most common HTML5 patterns on the
    web -- would otherwise have every teaser after the first silently discarded,
    understating real content by an order of magnitude and corrupting every downstream
    measurement taken over "main_only" text."""
    if main_only:
        regions = MAIN.findall(html)
        if regions:
            html = " ".join(region for _, region in regions)
    html = STRIP.sub(" ", html)
    return WS.sub(" ", TAG.sub(" ", html)).strip()


def fetch_raw(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read(2_000_000).decode("utf-8", errors="replace"), r.status
    except urllib.error.HTTPError as e:
        return "", e.code
    except Exception as e:
        return "", None


def have_browser():
    for probe in (["node", "-e", "require('playwright')"], ["node", "-e", "require('puppeteer')"]):
        try:
            if subprocess.run(probe, capture_output=True, timeout=15).returncode == 0:
                return probe[2].split("'")[1]
        except Exception:
            continue
    return None


def render(url, engine):
    """Render via node. Returns HTML or None. Kept as a subprocess so the skill has no
    Python-side browser dependency.

    Playwright and Puppeteer expose different launch APIs — Playwright's module exports
    a named `chromium` launcher, Puppeteer's default export *is* the launcher — so the
    two engines need different launch/viewport code, not a shared template with the
    module name substituted in."""
    if engine == "puppeteer":
        script = """
const puppeteer = require('puppeteer');
(async () => {
  const b = await puppeteer.launch();
  const p = await b.newPage();
  await p.setViewport({ width: 1280, height: 720 });
  try {
    await p.goto(process.argv[1], { waitUntil: 'networkidle0', timeout: 8000 });
  } catch (e) {}
  process.stdout.write(await p.content());
  await b.close();
})();"""
    else:
        script = """
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
  try {
    await p.goto(process.argv[1], { waitUntil: 'networkidle', timeout: 8000 });
  } catch (e) {}
  process.stdout.write(await p.content());
  await b.close();
})();"""
    try:
        r = subprocess.run(["node", "-e", script, url], capture_output=True, timeout=25)
        return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None
    except Exception:
        return None


IMG = re.compile(r"<img\b([^>]*)>", re.I)
ATTR = re.compile(r'(\w[\w-]*)\s*=\s*["\']([^"\']*)["\']')
FACT_HINT = re.compile(r"(menu|price|pricing|rate|hour|spec|table|chart|tariff|plan|fee|schedule|flyer|infographic)", re.I)
GENERIC_ALT = re.compile(r"^(image|img|photo|picture|logo|banner|icon|graphic|\s*|img[_-]?\d+|\S+\.(jpg|jpeg|png|webp|gif))$", re.I)
# Analytics/tracking beacons (Matomo/Piwik "idsite=", Google Analytics "collect", generic
# "pixel"/"beacon" paths) are <img> tags with no real visual content -- they should never
# reach the fact-locked-in-image candidate list at all, and their near-universal absence
# of width/height attributes is exactly what used to make "unknown size" default to
# "large" so damaging: on a real site, a handful of these can crowd out every genuine
# content image from the inspection cap.
TRACKING_BEACON = re.compile(r"(idsite=|[?&]collect\b|/pixel[./?]|/beacon[./?]|1x1\.(?:gif|png))", re.I)


def images(html, base):
    out = []
    for m in IMG.finditer(html):
        a = dict(ATTR.findall(m.group(1)))
        src = a.get("src") or a.get("data-src") or ""
        if TRACKING_BEACON.search(src):
            continue
        try:
            w, h = int(a.get("width", 0) or 0), int(a.get("height", 0) or 0)
        except ValueError:
            w = h = 0
        size_known = w > 0 and h > 0
        alt = a.get("alt")
        out.append({
            "src": src, "width": w, "height": h,
            "alt": alt,
            "alt_missing": alt is None,
            "alt_generic": alt is not None and bool(GENERIC_ALT.match(alt.strip())),
            "filename_suggests_fact": bool(FACT_HINT.search(src)),
            # Only a confirmed >=200x200 image counts as "large" -- an image with no
            # width/height attributes (common with CSS-driven or lazy-loaded images) is
            # unknown, not large, and must not be inspected as if its size were
            # established. size_known lets a reader see which case they're looking at;
            # filename_suggests_fact (below, in the sort key) is what should surface an
            # unsized-but-plausibly-fact-bearing image for inspection instead.
            "size_known": size_known,
            "large": size_known and w >= 200 and h >= 200,
        })
    out.sort(key=lambda i: (i["filename_suggests_fact"], i["alt_missing"] or i["alt_generic"]), reverse=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True)
    ap.add_argument("--out", default="observations.json")
    a = ap.parse_args()

    engine = have_browser()
    urls = [l.strip() for l in open(a.urls) if l.strip()]
    res = {"observed_at": datetime.now(timezone.utc).isoformat(),
           "render_engine": engine,
           "comparative_checks_available": bool(engine),
           "pages": []}

    for url in urls:
        raw, status = fetch_raw(url)
        e = {"url": url, "status": status}
        raw_main = visible_text(raw)
        raw_full = visible_text(raw, main_only=False)
        e["raw_text_chars_main"] = len(raw_main)
        e["raw_text_chars_full"] = len(raw_full)
        e["script_bytes"] = sum(len(x) for x in re.findall(r"<script\b[^>]*>.*?</script>", raw, re.I | re.S))
        e["has_empty_root"] = bool(re.search(r'<div[^>]+id=["\'](root|app|__next)["\'][^>]*>\s*</div>', raw, re.I))
        e["images"] = images(raw, url)[:20]
        e["canvas_count"] = len(re.findall(r"<canvas\b", raw, re.I))
        e["iframe_count"] = len(re.findall(r"<iframe\b", raw, re.I))
        # Whitespace around "=" is valid HTML and real sites use it; requiring "href="
        # with none would silently miss a real PDF link rather than reporting one.
        e["pdf_links"] = re.findall(r'href\s*=\s*["\']([^"\']+\.pdf)["\']', raw, re.I)[:10]
        e["video_without_track"] = bool(re.search(r"<video\b", raw, re.I)) and not re.search(r"<track\b", raw, re.I)

        if engine:
            rendered = render(url, engine)
            if rendered:
                rm = visible_text(rendered)
                e["rendered_text_chars_main"] = len(rm)
                e["js_dependency_ratio"] = round(len(raw_main) / len(rm), 3) if rm else None
            else:
                e["render_error"] = "render failed"
        res["pages"].append(e)
        time.sleep(0.3)

    if not engine:
        res["not_assessed_note"] = (
            "No headless browser available. JS-dependency ratio and rendered-vs-raw fact "
            "comparison could not be measured; raw-side signals only.")

    json.dump(res, open(a.out, "w"), indent=2)
    print(f"Wrote {a.out}: {len(res['pages'])} pages, render_engine={engine}")


if __name__ == "__main__":
    main()
