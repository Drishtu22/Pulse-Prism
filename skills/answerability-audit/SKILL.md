---
name: answerability-audit
description: >
  Audits whether a page's prose contains anything an AI assistant could actually lift as
  an answer — stage 4b of the Pulse-Prism pipeline. Derives the questions a user
  would plausibly ask an assistant about this entity from the site's own content, then
  measures whether the site holds a self-contained, attributable, extractable answer to
  each. Also measures quotable-fact density, definitional clarity and question-shaped
  structure. Use when auditing why a site that is technically crawlable still never gets
  cited, why assistants describe a brand vaguely or generically, or why marketing copy
  fails to surface in AI answers. Invoked by audit-orchestrator; findings feed that
  skill's report.
license: MIT
allowed-tools: [WebFetch, Bash, Read]
---

# Answerability audit — stage 4b

## The concern this owns

Whether readable prose contains **a sentence worth quoting**.

Everything upstream can succeed — the crawler got in, the HTML carried the content, the
text is real text — and the brand can still never appear in an answer, because there is
no sentence on the site that answers a question. Assistants construct answers from
self-contained claims. Copy that reads well to a human and asserts nothing specific
gives them nothing to work with.

This is the failure mode a conventional SEO audit cannot see. A page can score perfectly
on crawlability, performance and markup, and still be unquotable. That is why this is
its own skill rather than a section of the structured-data one: the concern is prose, the
evidence is linguistic, and the fix is written by a content owner, not an engineer.

## Inputs

Canonical origin · sampled URLs · detected content patterns · remaining budget.

## Procedure

Run `scripts/quotability.py --urls <file> --out observations.json` for the mechanical
measures — sentence segmentation, length distribution, entity-mention positions, heading
shapes, first-paragraph analysis. The judgment-heavy checks below run over its output.

### Check 1 — The question-coverage probe

**Applies:** always. This is the primary check.

**Procedure.** Derive 8-12 questions a real user would plausibly ask an assistant about
this entity. Derive them **from the site itself** — its navigation labels, headings,
page titles, product or service names, footer links — not from a fixed list, because a
fixed list would not generalise across a plumber, a university and a bank.

Shape them the way people actually ask assistants:

- What is *<entity>*?
- What does *<entity>* cost?
- Where is *<entity>* / what areas does it serve?
- Does *<entity>* offer *<specific thing named on the site>*?
- Is *<entity>* better than *<alternative the site itself names>*?
- How do I *<primary action the site exists to support>*?
- What are *<entity>*'s hours / turnaround / availability?
- Who is *<entity>* for?

These questions are an internal probe. Nothing is sent to a search engine or an
assistant; the audit asks only whether *this site* holds an extractable answer.

For each question, search the sampled pages for a passage that answers it and classify:

- **extractable** — a self-contained passage answers it, needs no surrounding context,
  and names the entity or is unambiguously about it
- **present but not extractable** — the answer can be assembled by a reader from
  scattered sentences, but no single passage carries it
- **absent** — the site does not answer it at all

**Flag when.** Fewer than 60% of derived questions are extractable. Report the coverage
figure and list the specific unanswered questions — that list is the most actionable
artefact this marketplace produces, because it converts an abstract audit into a content
brief.

**Do not flag when.** A question is not applicable to the entity. Do not ask what a
municipal recycling page costs. Derive only questions the detected patterns license.

**Evidence format.**
`12 questions derived from site navigation and headings. 4 are extractably answered. "What does <entity> cost?" is absent — no page states a price or a pricing model. "What is <entity>?" is present but not extractable: the homepage describes benefits across three paragraphs without a sentence defining what the company does.`

**Severity inputs.** stage 4 · `site-wide` · criticality `core`.

**Fix mechanism.** An assistant answers by quoting; if no passage is quotable, the brand
cannot be cited regardless of its ranking. For each unanswered question, add a
self-contained passage of 40-60 words directly under a heading phrased as that question.
Verification: re-run the probe; coverage above 80%.

### Check 2 — Definitional clarity

**Applies:** always.

**Procedure.** On the homepage and each primary landing page, look within the first 300
words for a sentence that (a) names the entity, (b) states its category in plain words,
and (c) states who it is for or what it does — without metaphor, without a superlative
standing in for a category, and understandable to a reader who has never heard of it.

**Flag when.** No such sentence exists.

**Do not flag when.** The sentence exists but is stylistically plain. Plainness is the
objective here, not a defect.

**Evidence format.**
`The homepage's first 300 words contain no sentence stating what the company does. The opening line reads as a positioning claim rather than a definition, and the words describing the actual service first appear 900 words down, in a footer link label.`

Quote at most a short fragment of the site's own copy as evidence; describe the rest.

**Severity inputs.** stage 4 · prevalence · criticality `core`.

### Check 3 — Quotable-fact density

**Applies:** always.

**Procedure.** In the main content region, count sentences between 4 and 30 words that
are self-contained (no unresolved pronoun opening the sentence) and carry assertable
content of one of four kinds:

- **numeric** — a figure, date, price, quantity or unit
- **definitional** — names the subject and states its category or purpose
- **capability** — states a concrete action the subject performs or supports
- **claim** — an academic or technical-register assertion ("we propose...", "results in
  a 40% reduction", "outperforms the baseline") — the same underlying thing as a
  capability statement, just in research or technical-report voice rather than
  marketing voice, and invisible to capability's product-oriented verb list
  ("lets you", "enables") if not counted separately

Counting only numeric facts is the obvious approach and it is wrong. "Acme is a payroll
platform for UK companies" contains no digit and is highly quotable; "we reimagine what's
possible" contains none of the four. The distinction that matters is abstraction versus
specificity, not prose versus numerals.

A sentence opening with "we" or "our" is not an unresolved reference the way one opening
with "this", "that", "it" or "they" is — "We don't outsource support" and "We propose a
new method for X" are self-contained on their own, because the referent (whoever's page
this is) is always available from context, unlike a demonstrative pronoun that depends on
an antecedent in a prior sentence. Treating "we"/"our" as dangling was measured to
silently discard genuinely quotable capability sentences across every kind of site
audited, not only research content — exclude only the genuinely context-dependent
openers.

Compute the count per 500 words. Separately record whether the entity name appears in the
same sentence as its key attributes, and the ratio of sentences opening with an
unresolved reference.

**Flag when.** Density falls below **1.5 per 500 words** on informational pages, or the
entity name never co-occurs with an attribute in a single sentence. The second condition
is the more damaging one: a sentence reading "our platform reduces onboarding time by
40%" cannot be attributed to the brand once it leaves the page.

**Threshold calibration.** Measured across four unrelated public sites spanning very
different registers — a nonprofit/editorial site, a SaaS marketing site, a local
business site, and a research paper archive — per-page medians were 2.64, 2.41, 1.05 and
0.72 respectively, full range 0.0 to 11.54. Re-run this calibration if the sentence
classifiers change: a threshold invented rather than measured is the likeliest source of
false positives in this skill.

**Do not flag when.** The page is deliberately short — a contact page, a login page, a
sitemap — or its word count is under 100. Do not flag narrative or editorial content for
low density; an essay is not required to read like a fact sheet. Apply this check only to
pages whose role is informational.

**Do not apply the numeric threshold to pages matching the `research` content pattern.**
Scientific and technical abstracts genuinely are dense, quotable prose — a real one reads
as substantive to a human on direct inspection — but they use far more lexically diverse,
domain-specific phrasing than marketing or product copy, which clusters around a small,
predictable set of stock verbs this kind of keyword classifier can actually enumerate. On
four real sites, the `claim` kind and the `we`/`our` fix above measurably recovered
missed sentences everywhere they applied, yet a `research`-pattern site's median density
still sat well below the other three sites' — not because the content was thin, but
because the classifier cannot keep pace with how varied academic writing is. Treat a low
score on `research`-pattern content as inconclusive and judge such pages by direct
reading instead of the numeric threshold; do not report a `research` page as low-density
on the strength of this measurement alone.

**Severity inputs.** stage 4 · prevalence · criticality by page role.

### Check 4 — Question-shaped structure

**Applies:** always.

**Procedure.** Examine the heading tree. Record whether headings are noun-phrase labels
("Solutions", "Platform", "Why us") or question-shaped, and whether the text immediately
following each heading answers it directly within roughly the first 60 words.

Check heading hierarchy: exactly one `H1`, no level skips, headings used semantically
rather than for visual size.

**Flag when.** No question-shaped headings exist anywhere on informational pages, or
headings are consistently followed by preamble rather than an answer, or the hierarchy is
broken.

**Do not flag when.** The site uses noun headings appropriately for navigational or
category pages. This check targets pages that exist to inform.

**Severity inputs.** stage 4 · prevalence · criticality by page role.

### Check 5 — Attribution and specificity of claims

**Applies:** always.

**Procedure.** Sample substantive claims — statistics, capability assertions, outcome
figures. Record whether each carries a source, a date, or a scope qualifier, and whether
comparative claims name what they are compared against.

**Flag when.** Substantive claims are consistently unqualified and unsourced. Assistants
weight attributable claims more heavily, and an unsourced number is one an assistant is
unlikely to repeat.

**Do not flag when.** The claim is plainly subjective brand voice rather than a factual
assertion. Aspirational copy is not a defect; only claims presented as facts are in
scope.

**Severity inputs.** stage 4 · prevalence · criticality `supporting`.

## A caution on scope

This skill judges **extractability of prose**, never the truth, quality or persuasiveness
of the content. It does not recommend keyword density, does not rewrite for tone, and
does not suggest publishing claims the site cannot support. The output is a content brief
about clarity and self-containment, and it must not read as an instruction to
manufacture facts.

## Output

Findings against `../audit-orchestrator/references/report-schema.json` with
`stage: "extractability"`, `detected_by: "answerability-audit"`, severity inputs, and
evidence carrying the coverage figure and the specific unanswered questions. Where the
derived question set is itself uncertain — a site too thin to derive from — record that
in `not_assessed`.

## Guardrails

Read-only. No external queries: questions are derived from the site and evaluated against
the site. Quote at most short fragments of site copy in evidence; paraphrase the rest.
Never fabricate a question the site's own content does not motivate.
