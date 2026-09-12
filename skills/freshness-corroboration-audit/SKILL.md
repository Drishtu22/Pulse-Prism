---
name: freshness-corroboration-audit
description: >
  Audits whether an extractable claim is current, internally consistent, corroborated
  off-site and attached to an unambiguous entity — stage 5 of the ai-citability-audit
  pipeline. Checks recency signals on volatile facts, contradictions across the site,
  independent agreement elsewhere on the web, and name collisions that cause assistants
  to confuse one entity with another. Use when auditing why an assistant describes a
  brand with outdated or wrong information, why it confuses a brand with a similarly
  named entity, or why a claim made only on a brand's own site never gets repeated.
  Invoked by audit-orchestrator; findings feed that skill's report.
license: MIT
allowed-tools: [WebFetch, Bash, Read]
---

# Freshness and corroboration audit — stage 5

## The concern this owns

Whether an extractable claim is **believed**.

A claim can be perfectly reachable, readable and quotable and still not be repeated,
because nothing indicates it is still true, or because nothing else on the web agrees
with it, or because the entity it belongs to cannot be told apart from another entity
with the same name. Machines treat a fact repeated consistently across independent
sources as more reliable than a fact that exists in exactly one place.

This is the only stage that looks beyond the audited site. That is not scope creep: how a
brand is described across the wider web materially determines what assistants say about
it, and an audit confined to the site cannot see the most common cause of a brand being
described wrongly rather than not at all.

## Inputs

Canonical origin · sampled URLs · detected content patterns · entity name and any
variants observed on the site · remaining budget.

## Procedure

Run `scripts/freshness_signals.py --urls <file> --out observations.json` for the
mechanical measures — machine-readable dates (JSON-LD `datePublished`/`dateModified`,
`<time>` elements), visible date-bearing text, copyright years, "coming soon"/"new"
labels, entity self-description candidates, address and phone candidates, and which
independent identity-anchor domains (Wikipedia, LinkedIn, social profiles) already
appear in plain hrefs. The judgment-heavy checks below run over its output, exactly as
in every other skill in this marketplace: the script observes, it does not decide what
counts as stale, inconsistent or ambiguous.

Two checks are deliberately left unscripted. Check 4 (off-site corroboration) requires
open-ended search against sources this script cannot know in advance — that stays a
live `WebFetch` task. Check 5's entity-collision judgment is inherently a reasoning task;
the script surfaces the identity anchors that check depends on, not the verdict.

**Degradation.** If a page cannot be fetched, its observations are simply absent rather
than guessed at — record the gap in `not_assessed` rather than inferring staleness or
consistency from a fetch failure.

### Check 1 — Recency signals on volatile content

**Applies:** to pages carrying volatile facts — prices, hours, availability, staff,
version numbers, service areas, statistics — and to pages matching the `editorial`
pattern.

**Procedure.** For each such page, look for a machine-readable date (`dateModified`,
`datePublished`, an `<time>` element) and a human-visible one. Compare the two where both
exist. Check plausibility: a `dateModified` equal to today's date on every page is a
template artefact rather than a signal, and should be treated as absent.

**Flag when.** A volatile fact carries no recency signal, or the machine-readable and
visible dates disagree, or every page reports the same auto-generated timestamp.

**Do not flag when.** The content is genuinely evergreen — an about page, a contact
page, a legal notice. Dating stable content is not required and flagging its absence is
noise. This is the largest false-positive risk in this skill: apply the check to the
fact, not to the page.

**Evidence format.**
`Pricing page /plans carries no dateModified, no datePublished and no visible last-updated statement. 9 of 11 pages with volatile facts show the same absence.`

**Severity inputs.** stage 5 · prevalence · criticality by fact class.

### Check 2 — Staleness

**Applies:** always.

**Procedure.** Look for concrete evidence that content has fallen out of date: a
copyright year more than one year behind the current year, claims referencing a year that
has passed as though upcoming, events with past dates presented as forthcoming, "new"
or "coming soon" labels on long-published items, roles attributed to people the site
elsewhere no longer lists, and links to services or products the site no longer offers.

**Flag when.** Concrete staleness is observable — not merely suspected.

**Do not flag when.** A stale copyright year is the only signal. It is weak on its own,
extremely common, and generates noise; report it only as a supporting detail alongside a
substantive staleness finding, or as a low-priority opportunity.

**Severity inputs.** stage 5 · prevalence · criticality by fact class.

### Check 3 — Internal consistency

**Applies:** always.

**Procedure.** Extract the entity's self-description, name form, address, contact
details, and headline claims from every sampled page. Compare.

**Flag when.** The site describes itself materially differently across pages — different
category, different service scope, different address, different name form — such that a
machine reading two pages would form two different pictures.

**Do not flag when.** The variation is stylistic or length-driven. A short footer
descriptor and a long about-page description are not a contradiction. Only material
disagreement counts.

**Evidence format.**
`The homepage describes the entity as a category-A provider; /about describes it as a category-B consultancy; the footer uses a third descriptor. The legal name appears in three forms across sampled pages.`

**Severity inputs.** stage 5 · prevalence · criticality `core`.

### Check 4 — Off-site corroboration

**Applies:** always, budget permitting. Cap at 8 external requests.

**Procedure.** For the entity's two or three most load-bearing claims — what it is, what
it does, where it operates — search for independent sources stating the same thing:
Wikipedia or Wikidata, industry directories, registry or regulator listings, review
platforms, press coverage, the profiles the site's own `sameAs` links point to.

Record how many independent domains corroborate each claim, and whether any contradict
it.

**Flag when.** A load-bearing claim is corroborated on no independent domain, or an
independent source contradicts the site — an outdated address in a widely-cited
directory is a common and highly damaging case, because the assistant will often prefer
the corroborated wrong answer.

**Do not flag when.** The entity is new or deliberately low-profile. Absence of
corroboration for a young entity is an opportunity, not a defect — record it under
`opportunities`. Do not treat social media presence as corroboration; it is
self-published.

**Evidence format.**
`The claim that the entity operates in three named regions appears only on its own domain across 8 external sources checked. A directory listing at <domain>, which ranks above the site for the brand name, states a former address.`

**Severity inputs.** stage 5 · `site-wide` · criticality `core`.

**Fix mechanism.** Assistants weight claims by independent agreement, so a single-source
claim is fragile regardless of how clearly it is stated. Establish the claim on
independent surfaces the entity legitimately controls or can correct — registry entries,
directory listings, a Wikidata item, partner and association pages — and correct the
contradicting listing at source. Verification: re-run; at least two independent domains
agree.

### Check 5 — Entity ambiguity

**Applies:** always.

**Procedure.** Determine whether the entity's name collides with other entities: other
companies, a common word or phrase, a place, a person, a product from a different
category. Check whether the site consistently pairs its name with a disambiguating
descriptor, and whether it offers the identity anchors — `sameAs`, a registry number, a
founding date, a location — that let a system tell it apart.

**Flag when.** A collision exists and the site provides nothing that distinguishes it.

**Do not flag when.** The name is distinctive. Do not manufacture a collision from a
loose partial match.

**Severity inputs.** stage 5 · `site-wide` · criticality `core` where collision is
demonstrable.

## Output

Findings against `../audit-orchestrator/references/report-schema.json` with
`stage: "trust"`, `detected_by: "freshness-corroboration-audit"`, severity inputs, and a
`reproduction` block. External observations record the source domain and what it stated,
paraphrased rather than quoted at length.

## Guardrails

Read-only, on the audited site and on external sources alike. Respect robots.txt
everywhere. Cap external requests at 8 to stay inside the runtime budget. Never assert
what a source says without having fetched it. Where corroboration cannot be checked —
budget exhausted, sources unreachable — record it in `not_assessed`; absence of evidence
must not be reported as evidence of absence.
