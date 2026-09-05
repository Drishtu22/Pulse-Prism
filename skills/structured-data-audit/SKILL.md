---
name: structured-data-audit
description: >
  Audits machine-readable claims — stage 4a of the Pulse-Prism pipeline. Checks
  whether schema.org structured data exists for the content patterns a site actually
  exhibits, whether it is valid and complete for its declared type, and critically
  whether it agrees with the page's visible text. Use when auditing why AI assistants
  misstate a brand's prices, hours, location or identity, why a site's JSON-LD is
  ignored, or whether a site's markup gives assistants anything reliable to quote.
  Invoked by audit-orchestrator; findings feed that skill's report.
license: MIT
allowed-tools: [WebFetch, Bash, Read]
---

# Structured data audit — stage 4a

## The concern this owns

Whether the page offers machine-readable claims that are present, well-formed, and
**true to the page**.

The third of those is where this skill earns its place. Almost every audit checks
whether markup exists. Very few check whether it *agrees with the page it is on*, and
disagreement is worse than absence: absent markup means an assistant falls back to
reading the prose, while contradictory markup means it confidently states something the
site does not say. A stale price in JSON-LD is how a brand ends up misquoted rather than
merely unquoted.

Structured data is not required for citation — assistants quote plain prose constantly.
It raises the reliability of extraction rather than being a precondition for it, and
findings here are weighted accordingly. Treating missing JSON-LD as a catastrophe would
misrepresent how these systems work.

## Inputs

Canonical origin · sampled URLs · **detected content patterns** (this skill is the most
pattern-dependent in the marketplace) · remaining budget.

## Procedure

Run `scripts/extract_jsonld.py --urls <file> --out observations.json`, which extracts
JSON-LD blocks, microdata and RDFa, records parse errors, and captures candidate
visible-text values for the comparison in check 3.

Read `../audit-orchestrator/references/content-patterns.md` before flagging any absence.
No expectation in this skill applies unless its licensing pattern was detected.

### Check 1 — Coverage against detected patterns

**Applies:** per pattern, only where detected.

| Detected pattern | Expected type | Required properties |
|---|---|---|
| `organization` | Organization or LocalBusiness | `name`, `url`, `description`, `sameAs` |
| `transactable` | Product with Offer | `name`, `offers.price`, `offers.priceCurrency`, `offers.availability` |
| `physical_location` | LocalBusiness | `address` (full PostalAddress), `openingHours`, `telephone` |
| `editorial` | Article or BlogPosting | `headline`, `datePublished`, `author` |
| `events` | Event | `name`, `startDate`, `location`, `eventStatus` |
| `listings` | ItemList or the item-appropriate type | per-item `url`, `name` |
| `research` | ScholarlyArticle or Dataset | `headline`, `author`, `datePublished`, identifier |
| `documentation` | TechArticle or FAQPage where question-shaped | `headline`, heading anchors |

**Flag when.** A pattern was detected on sampled pages and the corresponding type is
absent from those pages.

**Do not flag when.** The pattern was not detected. Do not flag missing Product markup
on a law firm, missing Event markup on a plumber, or missing `openingHours` on an
online-only service. Do not flag a type's absence on pages that do not exhibit the
pattern even if other pages on the site do — expectations are per-page-role, not
site-wide.

**Evidence format.**
`14 sampled pages match the transactable pattern (currency values beside item names, add-to-cart controls). 0 of 14 contain Product or Offer markup in JSON-LD, microdata or RDFa.`

**Severity inputs.** stage 4 · prevalence · criticality by page role. Note that stage 4
cannot reach `critical` under the severity model, which is deliberate.

### Check 2 — Validity and completeness

**Applies:** wherever markup exists.

**Procedure.** For each block: confirm it parses as JSON; confirm `@context` resolves to
schema.org; confirm `@type` is a real schema.org type; confirm required properties for
that type are present and non-empty; confirm nested objects declare their own `@type`;
confirm dates are ISO 8601 and URLs absolute.

**Flag when.** A block fails to parse, declares an invented type, or omits properties
without which the type conveys nothing — an `Offer` with no `price`, a `PostalAddress`
with no locality, an `Event` with no `startDate`. Markup that is present but hollow is
the common case and is worth distinguishing from markup that is absent, because the fix
is smaller and the site owner believes the work is already done.

**Do not flag when.** Optional properties are missing. Completeness is not the goal;
sufficiency for the claim is. Do not flag vendor extensions or additional non-schema
properties.

**Severity inputs.** stage 4 · prevalence · criticality by type.

### Check 3 — Agreement with visible text

**Applies:** wherever markup exists. **This is the check that distinguishes this skill.**

**Procedure.** For each fact expressed in both markup and visible text — price,
currency, availability, address, opening hours, entity name, headline, date — normalise
both sides (strip currency symbols and separators, canonicalise date formats, collapse
whitespace, case-fold) and compare.

**Flag when.** The two disagree on a fact a user would act on.

**Do not flag when.** The difference is presentational — `4999` versus `₹4,999`,
`2026-01-15` versus `15 January 2026`, a trailing period. Normalise before comparing, or
this check becomes a false-positive generator. Also do not flag where markup is
legitimately more precise than display text, such as a full ISO timestamp against a
displayed date.

**Evidence format.**
`Product JSON-LD on /p/model-x declares offers.price "4999" with availability "InStock". The visible page shows "₹5,499" and "Out of stock". 3 of 14 product pages show a price disagreement.`

**Severity inputs.** stage 4 · prevalence · criticality `core` — a contradiction on a
price or an address is always core, because it is the fact an assistant will repeat.

**Fix mechanism.** Markup and display are being generated from different sources or at
different times. Generate both from a single source at render time so they cannot drift.
Verification: re-run the comparison; zero disagreements.

### Check 4 — Identity linkage

**Applies:** where `organization` is detected — that is, nearly always.

**Procedure.** Look for an Organization node carrying `sameAs` links to independent
identity anchors: Wikidata, Wikipedia, LinkedIn, Crunchbase, an official social profile,
a registry entry. Check that a single canonical Organization node exists rather than
conflicting ones on different pages.

**Flag when.** No `sameAs` links exist, or Organization nodes disagree across pages on
name, URL or logo.

**Do not flag when.** The entity is small enough to have no external presence at all. In
that case this belongs in `opportunities`, not `findings` — the absence is a growth
opportunity rather than a defect, and mislabelling it as a defect is unfair.

**Severity inputs.** stage 4 · `site-wide` · criticality `core` when disambiguation
matters for the entity name.

### Check 5 — Open Graph and Twitter Card completeness

**Applies:** to pages a visitor would plausibly share or an assistant would plausibly
preview — the homepage, primary landing pages, articles, product pages. Not to internal
utility pages (login, search) where sharing is irrelevant.

**Procedure.** `scripts/extract_jsonld.py` records `og_tags` (title, description, image,
type, url) and `twitter_card` from each page's `<meta>` tags. This is a materially
different, lower-depth channel than schema.org — used by link-preview generators
(Slack, iMessage, LinkedIn) and consulted by some assistants as a simple fallback when
richer markup is absent — not a substitute for the Organization/Product markup Checks
1-3 already cover. Compare `og:title`/`og:description` against the page's own `<title>`
and definitional sentence for agreement, the same way Check 3 compares JSON-LD against
visible text.

**Flag when.** A page in scope has no `og:title`/`og:description` at all, or the values
present contradict the page's own visible title or definitional sentence.

**Do not flag when.** The page's role makes sharing implausible. Do not treat a missing
`og:image` alone as more than a minor completeness gap — title and description are the
load-bearing fields; the image is a nice-to-have.

**Evidence format.**
`14 of 15 sampled pages have no og:title or og:description meta tags. The one page that does (the homepage) declares og:title "Acme" while its own <title> reads "Acme — Payroll for UK Teams" -- a narrower, contradictory value.`

**Severity inputs.** stage 4 · prevalence · criticality `supporting` — this is a
lower-depth, higher-adoption complement to full schema.org markup, not a replacement for
it. A missing price or address in JSON-LD is `core`; a missing preview tag is
`supporting`.

**Fix mechanism.** Add `og:title`, `og:description`, `og:image` and `og:type` to the
page template, sourced from the same values already feeding the `<title>` tag and meta
description, so the two cannot drift independently. This is typically a small addition
since the underlying values already exist in the template.

## Interaction with other skills

Where a page fails stage 2 — its content only exists after JavaScript — markup absence
here is often a symptom of the same root cause. Report the observation but flag it for
the orchestrator to merge, rather than presenting it as an independent defect.

## Output

Findings against `../audit-orchestrator/references/report-schema.json` with
`stage: "extractability"`, `detected_by: "structured-data-audit"`, severity inputs, and a
`reproduction` block. Where markup exists but is hollow or contradictory, quote the
offending property path — `offers.price` — rather than the whole block.

## Guardrails

Read-only. Never fetch external validators or send site content to a third-party service;
validation is local. Where a schema type cannot be confirmed against a local vocabulary
list, record reduced confidence rather than asserting the type is invented.
