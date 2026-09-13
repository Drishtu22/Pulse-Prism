---
name: render-extractability-audit
description: >
  Determines whether a page's facts survive delivery to a non-executing fetcher and
  exist as machine-readable text — stages 2 and 3 of the AgentLens pipeline.
  Compares raw HTML against the rendered DOM to measure how much content depends on
  JavaScript, and detects facts locked inside images, canvas, video, scanned PDFs or
  interaction-gated regions. Use when auditing why an AI assistant cannot read a page
  that looks complete in a browser, why a site's prices, hours, menu or specifications
  never appear in AI answers, or why a JavaScript-heavy site is invisible to LLMs.
  Invoked by audit-orchestrator; findings feed that skill's report.
license: MIT
allowed-tools: [WebFetch, Bash, Read, Glob]
---

# Render and extractability audit — stages 2 and 3

## The concern this owns

Two adjacent failures with one shared symptom: the page looks complete to a person and
is empty to a machine.

- **Stage 2, delivery.** The fetcher received bytes, but the fact was not in them —
  it arrives later, via JavaScript.
- **Stage 3, textuality.** The fact was in the bytes, but not as text — it is pixels,
  audio, or a scanned image.

These are kept in one skill because they are diagnosed from the same three artefacts
(raw HTML, rendered DOM, page assets) and because separating them would mean fetching
every page twice over. They are still reported as distinct stages, since their fixes are
entirely different: stage 2 is an engineering change to how content is served, stage 3 is
a content change to how facts are expressed.

Many AI fetchers do not execute JavaScript, and those that do often apply a short budget.
Content that only exists after hydration is content that frequently does not exist at all
for the assistant answering a question about the brand.

## Inputs

Canonical origin · sampled URLs · detected content patterns · remaining budget.

## Procedure

Run `scripts/render_diff.py --urls <file> --out observations.json`.

The script fetches each URL twice — once as raw HTML with no execution, once through a
headless browser if one is available — extracts visible text from each, and reports the
ratio plus an inventory of non-text assets. Judgment happens here, not in the script.

**If no headless browser is available**, the script still runs the raw-HTML half and
flags pages whose raw text is implausibly thin (an empty root element, a body under 500
characters with a large script payload). This yields lower-confidence findings and every
comparative check goes to `not_assessed`. Say so plainly rather than inferring a render
gap from thin HTML alone — a genuinely short page is not a defect.

### Check 1 — JavaScript dependency ratio

**Applies:** always.

**Procedure.** Extract visible text from raw HTML with scripts, styles, and template
elements stripped. Extract visible text from the rendered DOM. Compute
`raw_text_length / rendered_text_length`.

**Flag when.** The ratio falls below 0.60 on a page whose content is core. Below 0.25,
treat the page as effectively empty to a non-executing fetcher.

**Do not flag when.** The missing content is genuinely peripheral — a cookie banner, a
chat widget, a recommendation carousel, a live availability counter. Measure the ratio
over the main content region where one can be identified (`<main>`, `<article>`, the
largest text-bearing container), not over the whole document, otherwise a chat widget
inflates the rendered figure and manufactures a finding.

**Evidence format.**
`Raw HTML for /plans contains 214 characters of visible text; the rendered DOM contains 3,180 (ratio 0.07). The plan names and prices appear only after hydration. 11 of 14 sampled pages show a ratio below 0.25.`

**Severity inputs.** stage 2 · prevalence from affected fraction · criticality by whether
the missing content is a core fact.

**Fix mechanism.** The content is produced by a client-side fetch, so a non-executing
fetcher receives a shell. Server-render the core content into the initial HTML response,
or pre-render at build time, or — as a partial mitigation that at least carries the facts
— emit them as JSON-LD in the server response. Verification: `curl -s <url> | grep -c '<price string>'` returns ≥ 1.

### Check 2 — Specific core facts missing from raw HTML

**Applies:** always. This is the sharper version of check 1.

A ratio is abstract; a missing price is concrete. For each fact class licensed by the
detected content patterns — price, address, opening hours, product name, contact
details, the entity's own name — locate the fact in the rendered DOM, then search for it
in the raw HTML.

**Flag when.** A licensed core fact is present rendered and absent raw.

**Do not flag when.** The pattern licensing that fact class was not detected. A site
that sells nothing has no price to omit.

**Evidence format.**
`The opening hours "Mon-Fri 9:00-18:00" appear in the rendered DOM of /contact but not in the raw HTML response (curl -s https://example.com/contact | grep -c "9:00" returns 0).`

**Severity inputs.** stage 2 · prevalence · criticality `core` by definition.

### Check 3 — Facts locked in images

**Applies:** always.

**Procedure.** Inventory images above 200×200 px. For each, record whether alt text is
absent, empty, or generic (`image`, `img_1234`, the filename, `logo` on a non-logo).
Prioritise images inside the main content region and those whose filename or
surrounding text suggests a fact-bearing asset — `menu`, `price`, `hours`, `spec`,
`table`, `chart`, `flyer`.

For the highest-priority candidates, up to a cap of 8, view the image and answer one
question: **does this image contain text stating a fact that appears nowhere in the
page's text?** Only an affirmative answer is a finding.

**Flag when.** A fact exists only inside an image.

**Do not flag when.** The image is decorative, or its text is duplicated in the page
body, or it is a logo or icon. A missing alt attribute on a decorative image is an
accessibility nit, not an AI-readability defect, and reporting it as one dilutes the
report.

**Evidence format.**
`The pricing table at /plans is a single 1200x840 PNG (alt=""). The values ₹4,999, ₹9,999 and ₹19,999 shown in the image appear nowhere in the page text.`

**Severity inputs.** stage 3 · prevalence · criticality by fact class.

**Fix mechanism.** Text inside a raster image is not addressable by a text extractor at
any budget. Reproduce the same values as an HTML table or list; keep the image if it
serves the visual design, and give it descriptive alt text. Verification: the values
appear in `curl -s <url>`.

**Degradation.** If image viewing is unavailable, attempt OCR via `pytesseract` when
installed. If neither is available, report the *candidates* with their signals at low
confidence and record the check in `not_assessed` — never assert an image contains text
without having read it.

### Check 4 — Other non-text carriers

**Applies:** always.

Check for: text rendered into `<canvas>`; SVG used as a flattened graphic with no
`<text>` nodes where a chart or table is implied; PDFs linked from primary navigation
with no extractable text layer; video or audio carrying facts with no transcript or
caption track; data presented only as an infographic.

**Do not flag when.** A textual equivalent exists nearby. A chart accompanied by a data
table is correct practice.

**Severity inputs.** stage 3 · prevalence · criticality by fact class.

### Check 5 — Interaction-gated and obstructed content

**Applies:** always.

**Procedure.** Detect content that exists only after a user action: accordions and tabs
whose panels are not in the initial DOM, "load more" pagination with no crawlable
alternative, infinite scroll without paginated URLs, and consent walls that withhold the
DOM until accepted.

**Flag when.** Core content requires interaction to enter the DOM, or a consent
mechanism blocks content delivery to a non-consenting fetcher.

**Do not flag when.** The panels are present in the DOM and merely hidden by CSS —
that is fine, extractors read the DOM, not the viewport. Distinguishing "hidden but
present" from "absent until clicked" is the whole substance of this check; conflating
them produces a large class of false positives on ordinary accordion FAQs.

**Severity inputs.** stage 2 · prevalence · criticality by fact class.

## Output

Findings against `../audit-orchestrator/references/report-schema.json`, each carrying
`stage: "delivery"` or `stage: "textuality"`, `detected_by: "render-extractability-audit"`,
severity inputs, a `reproduction` block, and `confidence` lowered where the check ran
degraded.

## Guardrails

Read-only. No interaction with forms, no clicking through consent dialogs to reach gated
content — if consent is required, that fact *is* the finding. Cap rendering at 8 seconds
per page and 8 image inspections per audit to stay inside the runtime budget. Never
assert the contents of an asset that was not actually read.
