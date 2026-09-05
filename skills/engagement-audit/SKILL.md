---
name: engagement-audit
description: >
  Audits why a visitor arriving from an AI assistant leaves without engaging — stage 6
  of the brand-ai-readiness pipeline. Unlike a generic UX or performance review, this
  models the assistant-referred visitor specifically: someone who lands on a deep page
  rather than the homepage, already holds a fact the assistant told them, and came to
  verify or act on that one thing. Checks answer continuity above the fold, deep-entry
  orientation, entry obstruction, delivery performance and next-step clarity. Use when
  auditing why AI-referred traffic bounces, why visitors do not convert after arriving
  from ChatGPT or Claude, or why a page fails visitors who did not start at the
  homepage. Invoked by audit-orchestrator; findings feed that skill's report.
license: MIT
allowed-tools: [WebFetch, Bash, Read]
---

# Engagement audit — stage 6

## The concern this owns

Everything upstream succeeded. The assistant found the site, read it, quoted it, and sent
someone. They left anyway.

This is not a general usability audit, and treating it as one is the failure mode to
avoid. The visitor this skill models is specific in three ways, and each has direct
consequences for what counts as a defect:

1. **They landed deep.** The assistant linked to one page, not the homepage. Every
   assumption the site makes about a visitor arriving through the front door is void.
2. **They already know something.** The assistant told them a fact — a price, a
   capability, an address — and that fact is why they clicked.
3. **They came to verify or act on that one thing**, not to browse.

So the governing question is not "is this page well designed" but "does this page
immediately confirm what the visitor was told, and let them act on it, given they have no
prior context and did not choose to be here."

## Inputs

Canonical origin · sampled URLs · detected content patterns · the answerability skill's
derived question set where available · remaining budget.

## Procedure

Run `scripts/engagement_probe.py --urls <file> --out observations.json` for the
mechanical measures — viewport composition, overlay detection, heading and breadcrumb
presence, anchor inventory, interactive-element counts, and timing where measurable.

### Check 1 — Answer continuity

**Applies:** always. **This is the check that distinguishes this skill from a UX review.**

**Procedure.** For each sampled deep page, identify the fact that page is most likely to
have been cited for — its price, its capability, its address, the answer to the question
the page addresses. Then determine whether that fact is visible in the initial viewport
at a standard desktop and mobile size, without scrolling and without interaction.

Where the answerability skill has produced a question set, use it: for each question a
page extractably answers, check that the answer is above the fold on that page.

**Flag when.** The fact that would have caused the citation is not visible on arrival —
buried below a hero section, behind a tab, or several screens down.

**Do not flag when.** The page's primary fact genuinely is visible, even if the design is
otherwise unremarkable. Aesthetic judgment is out of scope here.

**Evidence format.**
`/plans is the page most likely cited for pricing. At 1280x720 the initial viewport contains a hero image, a headline and two navigation rows; the first price appears 1,640 px down the page. At 390x844 it appears after four screens.`

**Severity inputs.** stage 6 · prevalence · criticality `core`. Pages on the primary
conversion path are lifted one band by the severity model.

**Fix mechanism.** A visitor arriving with a specific expectation abandons when the first
screen does not confirm it, because the fastest way to check the assistant was right is
to go back. Surface the page's primary fact in the initial viewport — a summary line, a
specification block, or the price adjacent to the heading — above any promotional
content. Verification: the fact is visible at 1280x720 and 390x844 without scrolling.

### Check 2 — Deep-entry orientation

**Applies:** always.

**Procedure.** Assess each sampled page as though the visitor has never seen the site.
Look for: a visible entity name in the header, a one-line statement of what this page or
site is, breadcrumbs or an equivalent path indicator, a link to the parent section, and
whether the page is reachable from the site's own navigation at all.

**Flag when.** A deep page provides no orientation — a visitor cannot tell what site they
are on, what this page is part of, or where to go for context. Orphan pages are the
worst case: reachable from an assistant, unreachable from the site's own navigation.

**Do not flag when.** Orientation exists in a non-standard but functional form. A clear
sectional header can do the work of breadcrumbs; the requirement is orientation, not a
particular component.

**Severity inputs.** stage 6 · prevalence · criticality by page role.

### Check 3 — Entry obstruction

**Applies:** always.

**Procedure.** Determine what occupies the initial viewport on first load: consent
dialogs, newsletter modals, app-install interstitials, chat widgets, age gates, region
selectors. Estimate the fraction of the viewport occluded and whether the underlying
content is scrollable or blocked while the overlay is present.

**Flag when.** An overlay occludes a substantial part of the first screen on arrival, or
blocks interaction until dismissed, or several appear in sequence.

**Do not flag when.** The overlay is legally required and minimally sized — a compact
consent bar at the screen edge is not an obstruction. Judge by occlusion and blocking, not
by the presence of a consent mechanism, or this check becomes a complaint about
compliance.

**Evidence format.**
`On first load at 1280x720, a consent dialog occupies approximately 74% of the viewport and blocks scrolling until dismissed. A newsletter modal appears 6 seconds later on the same page.`

**Severity inputs.** stage 6 · prevalence · criticality `core` when it affects the
primary path.

### Check 4 — Delivery performance

**Applies:** always, where measurable.

**Procedure.** Measure Largest Contentful Paint, Cumulative Layout Shift and Total
Blocking Time on sampled pages. Take the median of three runs and record the spread —
single measurements are too noisy to report as findings. Also record total transfer size
and blocking script count.

**Flag when.** Median LCP exceeds 4.0 s, or CLS exceeds 0.25, or TBT exceeds 600 ms.
Report the measured value and the spread, never a grade alone.

**Do not flag when.** Measurement was made under conditions unrepresentative of the
site's users, or the spread across runs is wide enough that the median is unreliable — in
that case record `not_assessed` with the observed variance.

**Severity inputs.** stage 6 · prevalence · criticality by page role.

**Degradation.** Where no timing instrumentation is available, record transfer size and
blocking-resource counts as supporting observations at low confidence, and put the
performance checks in `not_assessed`. Do not infer a slow page from a large page.

### Check 5 — Next-step clarity and friction

**Applies:** always.

**Procedure.** Identify the action each page exists to support, and assess whether it is
available and unobstructed: a single clear primary action rather than several competing
ones, no mandatory account creation before any value is delivered, form field counts
proportionate to the request, and no dead ends where a page offers no onward path.

**Flag when.** The page's purpose implies an action that is absent, buried, or gated
behind disproportionate friction.

**Do not flag when.** The page is purely informational and correctly offers no action.
Do not treat the absence of a call to action as a defect on a reference or policy page.

**Severity inputs.** stage 6 · prevalence · criticality by page role.

### Check 6 — Section addressability

**Applies:** where `documentation`, `editorial` or long-form content is detected.

**Procedure.** Check whether substantive sections carry stable `id` anchors that permit
deep linking, and whether those anchors appear stable across builds rather than
auto-generated from position.

**Flag when.** Long pages have no addressable sections, so an assistant can only link to
the page and the visitor lands at the top of a long document with their specific question
unanswered on screen.

**Do not flag when.** Pages are short enough that the whole content is the answer.

**Severity inputs.** stage 6 · prevalence · criticality `supporting`.

## What this skill does not do

It does not judge visual design, brand voice, or aesthetic quality. It does not
recommend layout changes for their own sake. It does not conduct a general accessibility
audit — though where an accessibility defect also blocks machine reading, such as a
fact-bearing image with no alt text, that belongs to `render-extractability-audit` and
should not be duplicated here.

## Output

Findings against `../audit-orchestrator/references/report-schema.json` with
`stage: "engagement"`, `detected_by: "engagement-audit"`, severity inputs, measured values
with their spread where applicable, and `confidence` lowered where measurement ran
degraded.

## Guardrails

Read-only. Never submit a form, create an account, dismiss a consent dialog to reach
gated content, or interact with anything transactional — observing that the obstruction
exists is the finding. Cap rendering at 8 seconds per page. Report measured numbers, never
invented ones.
