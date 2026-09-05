# Severity model

Every skill in this marketplace assigns severity using this file and nothing else. If
each skill invented its own scale the merged report would be incoherent and its
prioritisation meaningless, so severity is derived here rather than judged locally.

## Why severity is derived, not chosen

A finding's severity is a function of three observable quantities, not an impression:

```
severity = f(stage_weight, prevalence, content_criticality)
```

- **stage_weight** — how early in the pipeline the failure occurs. Earlier failures
  invalidate everything downstream, so they weigh more.
- **prevalence** — the fraction of sampled pages exhibiting the defect.
- **content_criticality** — whether the affected content is a *core* fact (what the
  entity is, what it offers, where it is, what it costs, how to contact it) or
  *peripheral* (a blog post, a press archive, a careers page).

Record all three on every finding. A grader, and the site owner, can then see why a
finding sits where it does instead of taking the label on trust.

## Stage weights

| Stage | Name | Weight | Failure means |
|-------|------|--------|---------------|
| 1 | Reachability | 1.00 | No AI client obtains the bytes at all |
| 2 | Delivery | 0.85 | Bytes obtained, facts absent from them |
| 3 | Textuality | 0.70 | Facts present but not as machine-readable text |
| 4 | Extractability | 0.55 | Text present but not parseable into a clean claim |
| 5 | Trust | 0.40 | Claim extractable but unverifiable or ambiguous |
| 6 | Engagement | 0.35 | Everything worked; the visitor still left |

Stage 6 is not less important than stage 5 in business terms — it is weighted lower
only because its failures are recoverable by the visitor, whereas a stage-1 failure is
silent and absolute. Engagement findings affecting the primary conversion path are
lifted one band by the criticality multiplier below.

## Prevalence bands

| Band | Fraction of the site's pages affected | Multiplier |
|------|--------------------------------------|------------|
| site-wide | ≥ 0.80 | 1.00 |
| widespread | 0.40 – 0.79 | 0.80 |
| partial | 0.10 – 0.39 | 0.55 |
| isolated | < 0.10 | 0.30 |

**Weight by template, not by sample count.** The sample is stratified across URL
templates, so a template covering 99% of a site's pages contributes the same number of
sampled pages as one covering three. Counting sampled pages therefore understates
prevalence badly on large sites.

Observed in testing: a challenge-shell block affected 2 of 8 sampled pages — a raw
fraction of 0.25, banded `partial` — while those two pages represented the `/project/<name>`
and `/user/<name>` templates, which together covered 38,737 of the site's 38,745
discovered URLs. The true fraction was 0.9998, and the finding was being ranked below a
missing `www` redirect.

So compute:

```
affected_fraction = Σ(pages in affected templates) / Σ(pages in all discovered templates)
```

using the `template_sizes` recorded by `discover_pages.py`. Fall back to the raw sampled
fraction only where template sizes are unavailable, and say so in the evidence.

A defect on a single page is a defect. A defect on every page is a characteristic of
the site, and is what actually determines whether the brand surfaces in an assistant.

Where a check is inherently site-level rather than per-page — robots.txt, sitemap
presence, absence of an identity hub — record prevalence as `site-wide` and say so in
the evidence.

## Content criticality

| Value | Multiplier | Applies when the affected content is |
|-------|-----------|--------------------------------------|
| core | 1.00 | Identity, offering, pricing, location, hours, contact, primary conversion path |
| supporting | 0.70 | Documentation, category and hub pages, comparison and FAQ content |
| peripheral | 0.40 | Blog archive, press releases, careers, legal boilerplate |
| informational | 0.20 | No content is unreachable or unreadable — a configuration or hygiene observation |

`informational` exists because the first three bands all assume *some content is
degraded*. Without it, a site-level configuration nit inherits stage 1's full weight and a
missing `www` redirect scores 1.00 × 1.00 × 0.70 = 0.70 and is reported as **critical**,
outranking findings that genuinely hide the site from assistants. Observed in testing on a
live site. If a finding does not make any content harder to reach, read, quote or trust,
it is `informational` regardless of how site-wide it is.

## Score to band

```
score = stage_weight × prevalence_multiplier × criticality_multiplier
```

| Score | Severity |
|-------|----------|
| ≥ 0.70 | critical |
| 0.45 – 0.69 | high |
| 0.25 – 0.44 | medium |
| < 0.25 | low |

Round to two decimals and record the score on the finding as `severity_score`. Showing
the arithmetic is the point: two auditors running this marketplace on the same site
should produce the same severities, and a disagreement should be traceable to a
disagreement about prevalence or criticality rather than about taste.

## Worked examples

**robots.txt disallows GPTBot and ClaudeBot for the whole site.**
Stage 1 (1.00) × site-wide (1.00) × core (1.00) = **1.00 → critical**. Correct: every
other finding on the site is moot until this is fixed.

**Product prices rendered client-side, absent from raw HTML, on all 14 sampled product
pages.**
Stage 2 (0.85) × site-wide (1.00) × core (1.00) = **0.85 → critical**.

**No `dateModified` on the blog archive.**
Stage 5 (0.40) × site-wide (1.00) × peripheral (0.40) = **0.16 → low**. Correct: this
is real but it is not why the brand is invisible.

**Consent modal occludes 78% of the viewport on first paint across all pages.**
Stage 6 (0.35) × site-wide (1.00) × core (1.00) = **0.35 → medium**, lifted to **high**
by the primary-conversion-path rule below.

## Two adjustments the orchestrator applies after merge

**Blocked-by suppression.** A finding whose stage is later than an unresolved finding
affecting the same pages is capped at `medium` and carries `blocked_by: [<id>]`. There
is no value in telling a site owner their JSON-LD is incomplete on pages no assistant
can fetch. The finding is still reported — it will matter once the blocker is cleared —
but it must not compete for attention with the blocker.

**Primary-path lift.** A stage-6 finding on the page that the site's own navigation
treats as the primary conversion target is raised one band. Losing the visitor at the
moment of intent costs more than the raw score suggests.

## Never do this

- Do not assign severity by how alarming the defect sounds.
- Do not assign `critical` to anything at stage 4 or later. By construction it cannot
  reach 0.70, and a report where everything is critical prioritises nothing.
- Do not raise severity because a fix is easy, or lower it because a fix is hard.
  Effort belongs in `suggested_action.effort`, not in severity.
