#!/usr/bin/env python3
"""Collect engagement signals: overlay occlusion, timing, orientation elements, anchors.

Two tiers of measurement:

1. Always available (standard library only): regex-derived signals from raw HTML —
   overlay *keyword* markers, breadcrumb markers, heading/anchor structure, form-field
   and CTA counts. These need no browser and run on every machine.
2. Only where a headless browser is present (Playwright or Puppeteer via Node, both
   optional): the checks that genuinely require a live viewport and cannot be
   approximated from markup — the actual fraction of the first screen an overlay
   occludes, whether it blocks scrolling, and Largest Contentful Paint / Cumulative
   Layout Shift / Total Blocking Time. Where no browser is available these are reported
   as unavailable rather than guessed at: a large page is not necessarily a slow one,
   and inferring occlusion from a "cookie" keyword match is not the same as measuring
   what covers the viewport.

Standard library only for tier 1. Tier 2 shells out to Node + Playwright/Puppeteer if
present; if neither is installed, or the render fails for a given page, that page's
tier-2 fields are simply absent and `timing_measures_available` /
`viewport_measures_available` say so — never inferred from tier-1 signals.

Usage:
    python engagement_probe.py --urls sample.txt --out observations.json
"""
import argparse, json, os, re, subprocess, tempfile, time, urllib.request
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
OVERLAY = re.compile(r"(cookie[-_ ]?(consent|banner|notice)|gdpr|onetrust|cookiebot|klaro|"
                     r"newsletter[-_ ]?(modal|popup)|age[-_ ]?gate|interstitial|"
                     r"exit[-_ ]?intent|subscribe[-_ ]?modal|app[-_ ]?banner)", re.I)
BREADCRUMB = re.compile(r'(class=["\'][^"\']*breadcrumb|BreadcrumbList|aria-label=["\']breadcrumb)', re.I)
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")

# Full 3-run timing profiling is the expensive part (a fresh navigation per run). Cap it
# to the same order of magnitude as the other per-audit caps in this marketplace (8
# image inspections in render-extractability, 8 external requests in
# freshness-corroboration) so this script cannot itself blow the round's 5-minute
# runtime budget on a large sample. Pages beyond the cap still get a single-run timing
# sample and full occlusion measurement -- only the median-of-three discipline is
# skipped for them, and that is recorded rather than silently downgraded.
MAX_FULL_TIMING_PAGES = 8

NODE_SCRIPT = r"""
const engine = process.argv[2];
const urlsPath = process.argv[3];
const outPath = process.argv[4];
const fs = require('fs');
const jobs = JSON.parse(fs.readFileSync(urlsPath, 'utf8'));

const NAV_TIMEOUT = 8000;
const GRACE_MS = 2000;

function installVitals() {
  window.__vitals = { lcp: 0, cls: 0, longTaskTotal: 0 };
  try {
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const last = entries[entries.length - 1];
      if (last) window.__vitals.lcp = last.renderTime || last.loadTime || last.startTime || 0;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) {}
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) window.__vitals.cls += entry.value;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) {}
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const blocking = entry.duration - 50;
        if (blocking > 0) window.__vitals.longTaskTotal += blocking;
      }
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) {}
}

function measureOcclusion() {
  const w = window.innerWidth, h = window.innerHeight;
  const cols = 8, rows = 8;
  let hits = 0, total = 0;
  const overlayRe = /(modal|dialog|overlay|consent|cookie|gdpr|onetrust|cookiebot|klaro|newsletter|interstitial|popup|backdrop)/i;
  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const x = Math.floor((i + 0.5) * w / cols);
      const y = Math.floor((j + 0.5) * h / rows);
      total++;
      let node = document.elementFromPoint(x, y);
      let matched = false, depth = 0;
      while (node && depth < 6) {
        if (node.nodeType === 1) {
          const style = getComputedStyle(node);
          // Only "fixed" or "sticky" positioning lets an element float above *arbitrary*
          // other content regardless of where that content sits in the page -- which is
          // the actual, defining trait of a consent dialog, newsletter modal, or any
          // other blocking overlay, and is why they are virtually always implemented
          // that way. "absolute" positioning only floats within the element's own
          // positioned ancestor, which is exactly how a purely decorative treatment is
          // built too -- a Squarespace "fluidImageOverlay" darkening a hero image is
          // `position: absolute` with `z-index: auto`, confined to that one image, and
          // keyword-matched "overlay" in its class name with no actual obstruction
          // anywhere. Requiring fixed/sticky here, not just non-static, is what tells
          // the two apart; "backdrop" and "overlay" class names are common on both.
          if (style.position === 'fixed' || style.position === 'sticky') {
            const cls = node.className && node.className.toString ? node.className.toString() : '';
            const id = node.id || '';
            const role = node.getAttribute ? (node.getAttribute('role') || '') : '';
            const ariaModal = node.getAttribute ? node.getAttribute('aria-modal') : null;
            const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : { width: 0 };
            const highZ = parseInt(style.zIndex || '0', 10) > 5 && rect.width >= w * 0.5;
            if (overlayRe.test(cls) || overlayRe.test(id) || role === 'dialog' || ariaModal === 'true' || highZ) {
              matched = true;
              break;
            }
          }
        }
        node = node.parentElement;
        depth++;
      }
      if (matched) hits++;
    }
  }
  const bodyStyle = getComputedStyle(document.body);
  const htmlStyle = getComputedStyle(document.documentElement);
  const scrollBlocked = bodyStyle.overflow === 'hidden' || htmlStyle.overflow === 'hidden';
  return {
    occlusion_fraction: total ? Math.round((hits / total) * 100) / 100 : 0,
    scroll_blocked: scrollBlocked,
  };
}

async function withPage(browser, fn) {
  let page;
  if (engine === 'puppeteer') {
    page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 720 });
  } else {
    page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  }
  try {
    return await fn(page);
  } finally {
    await page.close();
  }
}

async function addInit(page, fn) {
  if (engine === 'puppeteer') {
    await page.evaluateOnNewDocument(fn);
  } else {
    await page.addInitScript(fn);
  }
}

async function oneRun(browser, url, wantOcclusion) {
  return withPage(browser, async (page) => {
    await addInit(page, installVitals);
    let navFailed = null;
    try {
      await page.goto(url, { waitUntil: 'load', timeout: NAV_TIMEOUT });
    } catch (e) {
      // A failed/timed-out navigation must not fall through to measuring the page
      // anyway. Confirmed live: a UTM-tagged ad-landing URL hung past an 8s navigation
      // timeout (a slow ad-conversion pixel, not this site's real content), and the
      // occlusion/timing measurements taken against that stuck, half-loaded state
      // reported a nonsensical 100% viewport occlusion -- indistinguishable, to a
      // reader of the report, from a genuine full-screen blocking overlay. Recording
      // the failure and skipping measurement entirely is the only honest option; a
      // number computed against a page that never finished loading is not a
      // measurement of that page.
      navFailed = String((e && e.message) || e);
    }
    if (navFailed) {
      return { timing: null, viewport: null, nav_error: navFailed };
    }
    await new Promise((r) => setTimeout(r, GRACE_MS));
    const vitals = await page.evaluate(() => window.__vitals || { lcp: 0, cls: 0, longTaskTotal: 0 });
    const timing = {
      // A real largest-contentful-paint entry is never exactly 0ms -- some navigation
      // and processing time always elapses before anything paints. An observed 0 means
      // the callback simply had not fired yet when we read it, which happens on
      // genuinely slow, heavy pages (confirmed live: a video-heavy page read 0ms at this
      // grace period but had a real ~6000ms LCP once given more time). Reporting that as
      // "0ms" reads as excellent when the truth is the opposite -- worse than reporting
      // nothing at all. Recording null instead means "not captured," not "measured
      // fast," and the caller must not silently coerce it into 0.
      lcp_ms: vitals.lcp > 0 ? Math.round(vitals.lcp) : null,
      cls: Math.round((vitals.cls || 0) * 1000) / 1000,
      tbt_ms: Math.round(vitals.longTaskTotal || 0),
    };
    const viewport = wantOcclusion ? await page.evaluate(measureOcclusion) : null;
    return { timing, viewport, nav_error: null };
  });
}

async function main() {
  let browser;
  if (engine === 'puppeteer') {
    const puppeteer = require('puppeteer');
    browser = await puppeteer.launch();
  } else {
    const { chromium } = require('playwright');
    browser = await chromium.launch();
  }

  const results = [];
  for (const job of jobs) {
    const entry = { url: job.url, timing_samples: [], viewport: null, error: null, nav_errors: [] };
    try {
      // Occlusion is measured on the *first* run, not the last. A consent or
      // paywall overlay commonly stops reappearing after the first one or two
      // visits in the same session -- confirmed against a real site, where a
      // GDPR/TCF consent wall covering 89% of the viewport on the first two
      // navigations was gone by the third. Check 3 asks what a visitor sees on
      // arrival; measuring after repeat visits systematically undercounts
      // exactly the obstruction it exists to catch.
      const runs = job.full_timing ? 3 : 1;
      for (let i = 0; i < runs; i++) {
        const { timing, viewport, nav_error } = await oneRun(browser, job.url, i === 0);
        if (nav_error) {
          // A failed navigation contributes no sample at all -- not a zero, not a
          // guess -- rather than polluting the median with a measurement of a page
          // that never actually loaded.
          entry.nav_errors.push(nav_error);
          continue;
        }
        entry.timing_samples.push(timing);
        if (viewport) entry.viewport = viewport;
      }
    } catch (e) {
      entry.error = String((e && e.message) || e);
    }
    results.push(entry);
  }

  await browser.close();
  fs.writeFileSync(outPath, JSON.stringify(results));
}

main().catch((e) => {
  fs.writeFileSync(outPath, JSON.stringify({ fatal_error: String((e && e.message) || e) }));
  process.exit(1);
});
"""


def have_browser():
    """Return 'playwright', 'puppeteer', or None. Presence is checked by requiring the
    module, not by launching a browser -- a missing browser binary (vs. missing module)
    still fails at launch time and is handled as a per-run error, same as render_diff.py."""
    for name in ("playwright", "puppeteer"):
        try:
            r = subprocess.run(["node", "-e", f"require('{name}')"],
                               capture_output=True, timeout=15)
            if r.returncode == 0:
                return name
        except Exception:
            continue
    return None


def median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2, 3)


def run_browser_measurements(engine, urls):
    """Drive one Node subprocess for the whole sample rather than one per URL/run --
    launching a browser is the expensive part, so it happens once regardless of sample
    size or run count."""
    jobs = [{"url": u, "full_timing": i < MAX_FULL_TIMING_PAGES} for i, u in enumerate(urls)]
    with tempfile.TemporaryDirectory() as td:
        script_path = os.path.join(td, "probe.js")
        urls_path = os.path.join(td, "jobs.json")
        out_path = os.path.join(td, "out.json")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write(NODE_SCRIPT)
        with open(urls_path, "w", encoding="utf-8") as fh:
            json.dump(jobs, fh)

        # Generous but bounded: worst case every page times out on every run.
        timeout_s = min(600, 20 + len(urls) * 12 + sum(3 for j in jobs if j["full_timing"]) * 20)
        try:
            r = subprocess.run(
                ["node", script_path, engine, urls_path, out_path],
                capture_output=True, timeout=timeout_s,
            )
        except Exception as e:
            return None, f"node subprocess failed to run: {e}"

        if not os.path.exists(out_path):
            stderr = r.stderr.decode("utf-8", errors="replace")[:2000] if r else ""
            return None, f"no output produced (exit {getattr(r, 'returncode', '?')}): {stderr}"

        with open(out_path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and "fatal_error" in data:
            return None, data["fatal_error"]
        return data, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", required=True)
    ap.add_argument("--out", default="observations.json")
    a = ap.parse_args()

    urls = [l.strip() for l in open(a.urls) if l.strip()]
    engine = have_browser()

    res = {"observed_at": datetime.now(timezone.utc).isoformat(),
           "render_engine": engine,
           "viewport_measures_available": False,
           "timing_measures_available": False,
           "pages": []}

    browser_by_url, browser_error = {}, None
    if engine:
        data, browser_error = run_browser_measurements(engine, urls)
        if data:
            browser_by_url = {p["url"]: p for p in data}
            res["viewport_measures_available"] = True
            res["timing_measures_available"] = True
        else:
            res["not_assessed_note"] = (
                f"Headless browser ('{engine}') detected but measurement failed: "
                f"{browser_error}. Viewport occlusion and LCP/CLS/TBT were not measured; "
                "DOM-side signals only.")
    else:
        res["not_assessed_note"] = (
            "No headless browser available. Viewport occlusion and LCP/CLS/TBT were not "
            "measured; DOM-side signals only.")

    for url in urls:
        started = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read(3_000_000).decode("utf-8", errors="replace")
                size = len(html)
        except Exception as e:
            res["pages"].append({"url": url, "error": str(e)})
            continue

        anchors = re.findall(r'<h[2-4]\b[^>]*\bid=["\']([^"\']+)["\']', html, re.I)
        h2plus = len(re.findall(r"<h[2-4]\b", html, re.I))
        buttons = re.findall(r"<(?:button|a)\b[^>]*>(.*?)</(?:button|a)>", html, re.I | re.S)
        cta = [WS.sub(" ", TAG.sub("", b)).strip() for b in buttons]
        cta = [c for c in cta if 2 <= len(c) <= 40][:40]

        page = {
            "url": url,
            "html_bytes": size,
            "ttfb_proxy_ms": round((time.time() - started) * 1000),
            "blocking_scripts": len(re.findall(r'<script\b(?![^>]*\b(async|defer|type=["\']module)\b)[^>]*\bsrc=', html, re.I)),
            "total_scripts": len(re.findall(r"<script\b", html, re.I)),
            "stylesheets": len(re.findall(r'<link[^>]+rel=["\']stylesheet', html, re.I)),
            "overlay_markers": sorted(set(m[0].lower() if isinstance(m, tuple) else m.lower()
                                          for m in OVERLAY.findall(html)))[:10],
            "has_breadcrumb_signal": bool(BREADCRUMB.search(html)),
            "has_site_name_in_header": bool(re.search(r"<header\b.*?</header>", html, re.I | re.S)),
            "h2plus_count": h2plus,
            "anchored_sections": len(anchors),
            "anchor_coverage": round(len(anchors) / h2plus, 2) if h2plus else None,
            "form_field_count": len(re.findall(r"<input\b(?![^>]*type=[\"']hidden)", html, re.I)),
            "candidate_ctas": cta[:12],
            # Whitespace around "=" is valid HTML and real sites use it; requiring
            # "href=" with none would silently undercount internal links.
            "internal_link_count": len(re.findall(r'<a\b[^>]+href\s*=\s*["\'](?:/|\.)[^"\']*["\']', html, re.I)),
        }

        bm = browser_by_url.get(url)
        if bm:
            if bm.get("nav_errors"):
                page["nav_errors"] = bm["nav_errors"]
            if bm.get("error"):
                page["viewport_timing_error"] = bm["error"]
            elif not (bm.get("timing_samples") or []):
                # Every run's navigation failed (confirmed live: an ad-campaign
                # UTM-tagged URL hung past the navigation timeout on every attempt).
                # No sample exists to summarise -- this belongs in not_assessed, not
                # in a report field defaulting to a number that looks like a
                # measurement.
                page["viewport_timing_error"] = (
                    "All navigation attempts failed or timed out: "
                    + "; ".join(bm.get("nav_errors") or ["unknown"]))
            else:
                samples = bm.get("timing_samples") or []
                page["timing_run_count"] = len(samples)
                if len(samples) < 3:
                    page["timing_note"] = (
                        "single-run timing (page beyond the "
                        f"{MAX_FULL_TIMING_PAGES}-page full-profiling cap, or one or "
                        "more runs failed to navigate); treat as lower-confidence "
                        "than a median-of-three figure."
                    )
                lcp_values = [s["lcp_ms"] for s in samples]
                lcp_captured = [v for v in lcp_values if v is not None]
                page["lcp_ms_samples"] = lcp_values
                page["lcp_ms_median"] = median(lcp_captured) if lcp_captured else None
                if len(lcp_captured) < len(lcp_values):
                    page["lcp_not_captured_note"] = (
                        f"{len(lcp_values) - len(lcp_captured)} of {len(lcp_values)} "
                        "run(s) had no largest-contentful-paint entry within the grace "
                        "period -- treat as not measured, not as a fast paint."
                    )
                page["cls_samples"] = [s["cls"] for s in samples]
                page["cls_median"] = median([s["cls"] for s in samples])
                page["tbt_ms_samples"] = [s["tbt_ms"] for s in samples]
                page["tbt_ms_median"] = median([s["tbt_ms"] for s in samples])
                if bm.get("viewport"):
                    page["viewport_occlusion_fraction"] = bm["viewport"]["occlusion_fraction"]
                    page["viewport_scroll_blocked"] = bm["viewport"]["scroll_blocked"]

        res["pages"].append(page)
        time.sleep(0.3)

    json.dump(res, open(a.out, "w"), indent=2)
    print(f"Wrote {a.out}: {len(res['pages'])} pages, render_engine={engine}")


if __name__ == "__main__":
    main()
