---
name: audit-orchestrator
description: >
  Entrypoint for the Pulse&Prism marketplace. Given a website URL or
  domain, profiles the site, samples its pages, runs every diagnostic skill in the
  marketplace against that shared sample, merges their findings into one prioritized
  evidence-backed report, and emits it as JSON. Use this whenever someone asks why a
  brand is missing, invisible, uncited or misrepresented in AI assistants like ChatGPT
  or Claude, why an LLM cannot read or quote their site, why their AI search visibility
  is poor, or why visitors who arrive from an AI assistant leave without engaging. Use
  it for any request phrased as an AI-readiness audit, AI-discoverability review, LLM
  SEO check, GEO audit or answer-engine optimisation review, even when no specific
  defect is named.
license: MIT
allowed-tools: [WebFetch, Bash, Read, Write, Glob, Grep]
---

# Brand AI-Readiness Audit — orchestrator

## What this audits, and what it does not

Input is **one website**. Not a question, not a query, not a set of candidate URLs.

The audit answers, on behalf of the site's owner: when a person asks an AI assistant a
question this brand should win, why doesn't the brand appear — and when someone does
arrive from an assistant, why do they leave?

This is not search, ranking or retrieval. Nothing here selects pages to answer a query.
Nor is it a content scraper: what the site *says* is only inspected to determine whether
a machine could have obtained it. The audit never judges whether the site's claims are
true — only whether they are reachable, readable, quotable and corroborated.

Everything is read-only. No skill in this marketplace modifies a live site, submits a
form, authenticates, or requests anything `robots.txt` disallows. The output is a
recommendation.

## The pipeline this is organised around

A fact on a page has to survive six stages before it reaches an answer. A failure at any
stage makes every later stage moot, which is why findings are grouped and prioritised by
stage rather than by topic.

1. **Reachability** — an AI client obtains the bytes → `crawl-access-audit`
2. **Delivery** — the fact is in the bytes it obtained → `render-extractability-audit`
3. **Textuality** — the fact is text, not pixels or audio → `render-extractability-audit`
4. **Extractability** — the text parses into a clean claim → `structured-data-audit`, `answerability-audit`
5. **Trust** — the claim is current, consistent and corroborated → `freshness-corroboration-audit`
6. **Engagement** — the visitor who arrives stays → `engagement-audit`

## Procedure

### Step 1 — Normalise the target and check permission

Accept a bare domain or full URL. Resolve to a canonical origin: follow redirects from
both `http://` and `https://`, with and without `www`, and record which form is
canonical.

Fetch `/robots.txt` and parse it before fetching anything else. Every subsequent request
in the audit respects it. If a path is disallowed for generic user agents, do not fetch
it — record the restriction instead and note the coverage gap in `not_assessed`.

Set a global budget of **5 minutes** and **60 HTTP requests**. Space requests at least
200 ms apart. Never parallelise beyond 4 concurrent requests. Exceeding a site's
tolerance would make this audit the problem it is meant to diagnose.

### Step 2 — Discover and sample pages

Run `scripts/discover_pages.py <origin> --seed 42 --max 15`.

The script gathers candidate URLs from `sitemap.xml` (following index files), from the
homepage's internal links, and from common route conventions. It then selects a
**stratified** sample: the homepage always, plus the deepest-linked page, plus one
representative of each distinct URL template it can identify, filling remaining slots by
seeded random choice.

Stratification matters more than size here. Fifteen pages drawn from one template teach
nothing about a site; one page from each of eight templates characterises it. Record the
seed and the selected URLs in `audit_scope` so the audit is reproducible.

If no sitemap exists and the homepage exposes fewer than three internal links, sample
what is available and record the limitation — do not fabricate URLs by guessing paths.

### Step 3 — Detect content patterns

Read `references/content-patterns.md` and apply its detection table to the sample.

This step exists to prevent false positives. Downstream skills must not assert that a
site is missing Product markup until it has been established that the site sells
something. Record every detected pattern in `audit_scope.content_patterns_detected` and
pass the list to each diagnostic skill.

Where detection is ambiguous, record the dependent checks in `not_assessed` rather than
resolving the ambiguity by assumption in either direction.

### Step 4 — Run the diagnostic skills

Invoke each of the six diagnostic skills, passing:

- the canonical origin
- the sampled URL list (all skills inspect **the same** pages — otherwise prevalence
  figures are not comparable and the merged report cannot be reasoned about)
- the detected content patterns
- the remaining request and time budget

Run stage 1 first. **If `crawl-access-audit` reports a site-wide reachability block,
continue the remaining skills but mark their findings `blocked_by` that finding.** The
downstream findings are still true and still worth reporting — they will matter the
moment the block clears — but they must not compete with the blocker for attention.

Each skill returns findings against the schema in `references/report-schema.json`. No
skill writes the report; only this orchestrator does.

If a skill cannot run — a missing headless browser, an unavailable network dependency —
capture what it could not check in `not_assessed` with a stated impact. A gap declared
honestly costs far less than a confident conclusion drawn from a check that never ran.

### Step 5 — Merge

**Deduplicate.** Two skills observing one root cause must produce one finding. A page
that returns 403 to bot user-agents will look empty to the render skill too; that is one
reachability finding, not two. Merge on root cause, keep the earliest-stage framing, and
union the evidence.

**Arbitrate severity.** Recompute every severity yourself from
`references/severity-model.md` using the skill's reported stage, prevalence and
criticality. Do not accept a skill's severity label on trust — deriving it centrally is
what makes the report internally consistent.

**Apply suppression and lift.** Cap blocked findings at `medium`. Raise stage-6 findings
on the primary conversion path one band.

**Sort.** By severity, then by stage ascending, then by affected fraction descending.
The reading order should be the fixing order.

**Assign ids.** Sequential `F-001` upward after sorting, so ids reflect priority.

### Step 6 — Add opportunities

The round explicitly asks for improvements beyond detected defects, so a report
containing only defects is incomplete.

Derive these from what is *absent* rather than what is broken. Absences are invisible to
per-page checks: a site cannot fail a pricing-page check if it has no pricing page.
Consider, against the detected patterns, whether the site lacks a definitional "what is
X" page, question-shaped FAQ content, comparison content, an identity hub with a
complete `sameAs` graph, an `llms.txt`, original data worth citing, or a last-verified
convention on volatile facts.

Include an opportunity only where the mechanism is stated and the pattern licenses it.
Recommending a comparison page to a municipal water authority is padding.

### Step 7 — Emit

Validate against `references/report-schema.json`, then write the report to
`audit-report.json`.

Run `scripts/assemble_report.py --findings <dir> --out audit-report.json` to compute the
summary counts, stage scores and headline, and to fail loudly on any finding missing a
required field.

Alongside the JSON, print a short human summary: the headline, the count by severity,
and the three highest-priority actions. The JSON is the deliverable; the summary is what
makes it usable by someone who will not read JSON.

## Evidence discipline

This applies to every skill in the marketplace and is the single most important rule
here. Evidence is a **statement of what was observed**, never an inference.

- Good: `Fetched 14 product URLs with User-Agent "GPTBot"; 14 returned HTTP 403. The same URLs with a Chrome User-Agent returned HTTP 200 with a median 47 KB body.`
- Bad: `The site blocks AI crawlers.`

The second may be a correct conclusion, but it cannot be checked by the reader. Every
finding carries a `reproduction` block with the URLs, a single shell command, the
observed result and the expected result. A site owner who can reproduce a finding in ten
seconds acts on it; one who cannot, argues with it.

## Fix discipline

Every finding requires a `suggested_action`, and every action states its **mechanism** —
why this change resolves this cause at this stage. An action that cannot name its
mechanism is a guess.

- Weak: `Improve your structured data.`
- Strong: `The price is written into the DOM by a client-side fetch, so the raw HTML contains no price text and non-executing fetchers see none. Server-render the price into the initial HTML response, or emit Product/Offer JSON-LD containing it server-side. Verify: curl -s <url> | grep -c '₹' returns ≥ 1.`

Order actions by dependency, not by ease. If reachability is broken, say plainly that
the later fixes should wait.

## Report shape

`references/report-schema.json` is the contract. The round's required minimum — `site`,
`audited_at`, a counts-by-severity `summary`, and findings each carrying `id`, `title`,
`severity`, `evidence`, `suggested_action` — is a subset of it. The additions
(`reproduction`, `severity_inputs`, `blocked_by`, `confidence`, `opportunities`,
`not_assessed`) exist because a report without them states conclusions the reader has to
take on faith.

## Determinism

Two runs against an unchanged site must produce the same findings and the same
severities. Fix the sample seed, derive severity arithmetically, use fixed thresholds
from each skill's reference file, and sort deterministically. Where a check is genuinely
non-deterministic — network timing, performance measurement — take the median of three
samples and record the spread.

## Guardrails

- Read-only. No writes to the audited site, no form submission, no authentication.
- Respect `robots.txt` without exception, including for the bot-parity check: send
  AI-crawler user-agents only to paths those agents are permitted to fetch.
- No crawling of authenticated areas, checkout flows, or anything behind a paywall.
- Stay inside the request and time budget; abort cleanly and report partial coverage in
  `not_assessed` rather than overrunning.
- Never invent a URL, a count, or an observation. If a check did not run, it goes in
  `not_assessed`.
